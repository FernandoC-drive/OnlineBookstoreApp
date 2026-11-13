"""Checkout, order history, payment status, and sales analytics."""

from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal

from flask import Blueprint, current_app, g, request
from mysql.connector import Error as MySQLError
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from billing import invoice_html, invoice_path, queue_invoice_email, save_invoice
from catalog import MAX_AMOUNT, MAX_QUANTITY, book_object_id, books_collection, price_amount
from service import ApiError, connect_mysql, json_object, mysql_connection, require_auth, utc_timestamp


orders = Blueprint("orders", __name__)


class UnknownCommit(ApiError):
    def __init__(self):
        super().__init__(503, "Could not confirm whether MySQL saved the order")


def checkout_items():
    items = json_object().get("items")
    if not isinstance(items, list) or not items:
        raise ApiError(400, "items must be a nonempty list")
    validated = []
    for item in items:
        if not isinstance(item, dict):
            raise ApiError(400, "Each item must be an object")
        book_id = book_object_id(item.get("book_id"))
        transaction_type = item.get("transaction_type")
        quantity = item.get("quantity")
        if transaction_type not in ("BUY", "RENT"):
            raise ApiError(400, "transaction_type must be BUY or RENT")
        if type(quantity) is not int or not 1 <= quantity <= MAX_QUANTITY:
            raise ApiError(400, "quantity must be a positive integer in range")
        validated.append((book_id, transaction_type, quantity))
    return validated


def reserve_inventory(items, reservations):
    books = books_collection()
    quantities = Counter()
    for book_id, _, quantity in items:
        quantities[book_id] += quantity

    snapshots = {}
    for book_id, quantity in quantities.items():
        book = books.find_one_and_update(
            {"_id": book_id, "available_copies": {"$gte": quantity}},
            {"$inc": {"available_copies": -quantity}},
            projection={"title": 1, "author": 1, "buy_price": 1, "rent_price": 1},
            return_document=ReturnDocument.BEFORE,
        )
        if book is None:
            if books.find_one({"_id": book_id}, {"_id": 1}) is None:
                raise ApiError(404, f"Book {book_id} not found")
            raise ApiError(409, f"Insufficient available copies for book {book_id}")
        reservations[book_id] = quantity
        snapshots[book_id] = book
    return snapshots


def restore_inventory(reservations):
    books = books_collection()
    for book_id, quantity in reservations.items():
        try:
            result = books.update_one({"_id": book_id}, {"$inc": {"available_copies": quantity}})
            if not result.matched_count:
                current_app.logger.error("Could not restore inventory for missing book %s.", book_id)
        except PyMongoError:
            current_app.logger.exception("Could not restore %s copies for book %s.", quantity, book_id)


def rollback_mysql():
    connection = g.get("mysql")
    try:
        if connection is not None and connection.in_transaction:
            connection.rollback()
    except MySQLError:
        current_app.logger.exception("Could not roll back the MySQL transaction.")


def commit_order(connection, order_id, expected_status=None):
    try:
        connection.commit()
    except MySQLError as commit_error:
        # A lost commit response can mean MySQL already committed the transaction.
        try:
            g.pop("mysql", None)
            connection.close()
            with connect_mysql() as probe, probe.cursor() as cursor:
                cursor.execute("SELECT payment_status FROM orders WHERE id = %s", (order_id,))
                row = cursor.fetchone()
        except MySQLError:
            current_app.logger.exception("Could not determine the commit result for order %s.", order_id)
            raise UnknownCommit() from commit_error
        if row is None or (expected_status is not None and row[0] != expected_status):
            raise


def build_order_items(requested, snapshots):
    items = []
    for book_id, transaction_type, quantity in requested:
        book = snapshots[book_id]
        price_field = "buy_price" if transaction_type == "BUY" else "rent_price"
        unit_price = price_amount(book[price_field], price_field)
        items.append({
            "book_id": str(book_id),
            "book_title": book["title"],
            "author": book["author"],
            "transaction_type": transaction_type,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": unit_price * quantity,
        })
    return items


def insert_order(connection, items, total, created_at):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO orders (user_id, total_amount, payment_status, bill_html_path, created_at)
            VALUES (%s, %s, 'Pending', '', %s)
            """,
            (g.user["user_id"], total, created_at),
        )
        order_id = cursor.lastrowid
        relative_path = f"bills/{invoice_path(order_id).name}"
        cursor.execute("UPDATE orders SET bill_html_path = %s WHERE id = %s", (relative_path, order_id))
        cursor.executemany(
            """
            INSERT INTO order_items
                (order_id, book_id, book_title, author, transaction_type, quantity, unit_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (order_id, item["book_id"], item["book_title"], item["author"],
                 item["transaction_type"], item["quantity"], item["unit_price"])
                for item in items
            ],
        )
    return {
        "order_id": order_id,
        "username": g.user["username"],
        "email": g.user["email"],
        "total_amount": total,
        "payment_status": "Pending",
        "bill_html_path": relative_path,
        "created_at": utc_timestamp(created_at),
        "items": items,
    }


@orders.post("/api/orders")
@require_auth(role="CUSTOMER")
def place_order():
    requested = checkout_items()
    reservations = {}
    saved_path = None
    connection = mysql_connection()

    with current_app.extensions["inventory_lock"]:
        connection.start_transaction()
        try:
            snapshots = reserve_inventory(requested, reservations)
            items = build_order_items(requested, snapshots)
            total = sum(item["line_total"] for item in items)
            if total > MAX_AMOUNT:
                raise ApiError(400, "Order total exceeds the maximum supported amount")

            created_at = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
            order = insert_order(connection, items, total, created_at)
            html = invoice_html(order)
            path = invoice_path(order["order_id"])
            save_invoice(path, html)
            saved_path = path
            commit_order(connection, order["order_id"])
        except UnknownCommit:
            raise
        except Exception:
            rollback_mysql()
            restore_inventory(reservations)
            if saved_path is not None:
                try:
                    saved_path.unlink(missing_ok=True)
                except OSError:
                    current_app.logger.exception("Could not remove rolled-back invoice %s.", saved_path.name)
            raise

    return {
        "order_id": order["order_id"],
        "total_amount": float(total),
        "payment_status": order["payment_status"],
        "bill_html_path": order["bill_html_path"],
        "bill_html_content": html,
        "email_status": queue_invoice_email(order, html),
    }, 201


def load_orders(connection, conditions=(), params=()):
    sql = """
        SELECT o.id AS order_id, o.user_id, u.username, u.email, o.total_amount,
               o.payment_status, o.bill_html_path, o.created_at,
               i.id AS item_id, i.book_id, i.book_title, i.author,
               i.transaction_type, i.quantity, i.unit_price
        FROM orders o
        JOIN users u ON u.id = o.user_id
        LEFT JOIN order_items i ON i.order_id = o.id
        """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY o.created_at DESC, o.id DESC, i.id ASC"
    grouped = {}
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(sql, params)
        for row in cursor:
            order_id = row["order_id"]
            if order_id not in grouped:
                order = {key: row[key] for key in (
                    "order_id", "user_id", "username", "email", "total_amount",
                    "payment_status", "bill_html_path",
                )}
                order["id"] = order_id
                order["created_at"] = utc_timestamp(row["created_at"]) if row["created_at"] else None
                order["items"] = []
                grouped[order_id] = order
            if row["item_id"] is not None:
                item = {key: row[key] for key in (
                    "order_id", "book_id", "book_title", "author", "transaction_type", "quantity", "unit_price",
                )}
                item["id"] = row["item_id"]
                item["line_total"] = row["unit_price"] * row["quantity"]
                grouped[order_id]["items"].append(item)
    return list(grouped.values())


def order_json(order, include_invoice=False):
    result = {
        **order,
        "total_amount": float(order["total_amount"]),
        "items": [
            {**item, "unit_price": float(item["unit_price"]), "line_total": float(item["line_total"])}
            for item in order["items"]
        ],
    }
    if include_invoice:
        result["bill_html_content"] = invoice_html(order)
    return result


@orders.get("/api/orders/my-history")
@require_auth(role="CUSTOMER")
def customer_orders():
    history = load_orders(mysql_connection(), ("o.user_id = %s",), (g.user["user_id"],))
    return [order_json(order, include_invoice=True) for order in history]


@orders.get("/api/manager/orders")
@require_auth(role="MANAGER")
def manager_orders():
    return [order_json(order, include_invoice=True) for order in load_orders(mysql_connection())]


@orders.put("/api/manager/orders/<int:order_id>/status")
@require_auth(role="MANAGER")
def update_payment(order_id):
    status = json_object().get("payment_status")
    if status not in ("Pending", "Paid"):
        raise ApiError(400, "payment_status must be Pending or Paid")

    connection = mysql_connection()
    original_html = None
    path = invoice_path(order_id)
    invoice_replaced = False
    connection.start_transaction()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM orders WHERE id = %s FOR UPDATE", (order_id,))
            if cursor.fetchone() is None:
                raise ApiError(404, "Order not found")
            order = load_orders(connection, ("o.id = %s",), (order_id,))[0]
            original_html = invoice_html(order)
            order["payment_status"] = status
            cursor.execute("UPDATE orders SET payment_status = %s WHERE id = %s", (status, order_id))
        save_invoice(path, invoice_html(order))
        invoice_replaced = True
        commit_order(connection, order_id, status)
    except UnknownCommit:
        raise
    except Exception:
        if invoice_replaced:
            try:
                save_invoice(path, original_html)
            except ApiError:
                current_app.logger.error("Could not restore the invoice for order %s.", order_id)
        rollback_mysql()
        raise

    return {"message": "Order status updated", "order_id": order_id, "payment_status": status}


def query_date(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        parsed = date.fromisoformat(raw)
        if parsed.isoformat() == raw:
            return parsed
    except ValueError:
        pass
    raise ApiError(400, f"{name} must be a date in YYYY-MM-DD format")


@orders.get("/api/manager/analytics")
@require_auth(role="MANAGER")
def analytics():
    start = query_date("start_date")
    end = query_date("end_date")
    if start and end and start > end:
        raise ApiError(400, "start_date must be on or before end_date")
    conditions, params = [], []
    if start:
        conditions.append("o.created_at >= %s")
        params.append(datetime.combine(start, time.min))
    if end:
        conditions.append("o.created_at <= %s")
        params.append(datetime.combine(end, time.max))

    matching = load_orders(mysql_connection(), conditions, tuple(params))
    totals = defaultdict(lambda: [0, Decimal("0.00")])
    for order in matching:
        for item in order["items"]:
            book = (item["book_id"], item["book_title"], item["author"])
            totals[book][0] += item["quantity"]
            totals[book][1] += item["line_total"]
    sorted_books = sorted(totals, key=lambda book: (-totals[book][0], -totals[book][1], book))

    return {
        "summary": {
            "total_orders": len(matching),
            "total_revenue": float(sum(order["total_amount"] for order in matching)),
            "paid_revenue": float(sum(order["total_amount"] for order in matching
                                      if order["payment_status"] == "Paid")),
        },
        "orders_in_period": [order_json(order) for order in matching],
        "best_sellers": [
            {"book_id": book_id, "book_title": title, "author": author,
             "total_units": totals[(book_id, title, author)][0],
             "total_sales": float(totals[(book_id, title, author)][1])}
            for book_id, title, author in sorted_books
        ],
    }

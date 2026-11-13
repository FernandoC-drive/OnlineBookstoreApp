"""Exercise the live Java and Flask services with uniquely named test books."""

from datetime import date, timedelta
from decimal import Decimal
from html import escape
from time import perf_counter
from uuid import uuid4

import requests

from service import PROJECT_ROOT, load_settings


class ApiChecks:
    def __init__(self, session):
        settings = load_settings()
        self.session = session
        self.java = f"http://127.0.0.1:{settings.get('USER_SERVICE_PORT', '8001')}"
        self.flask = f"http://127.0.0.1:{settings.get('FLASK_SERVICE_PORT', '8002')}"
        self.timings = []

    def call(self, method, path, expected, *, token=None, java=False, **kwargs):
        base_url = self.java if java else self.flask
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        started = perf_counter()
        with self.session.request(method, base_url + path, headers=headers, timeout=5, **kwargs) as response:
            elapsed = (perf_counter() - started) * 1000
            self.timings.append((elapsed, method, path, "Java" if java else "Flask"))
            assert response.status_code == expected, (
                f"{method} {path} expected {expected}, got {response.status_code}: {response.text[:350]}"
            )
            return response.json()

    def login(self, username, password, role):
        account = self.call("POST", "/api/users/login", 200, java=True,
                            json={"username": username, "password": password})
        assert account["username"] == username and account["role"] == role
        print(f"{username} login passed in {self.timings[-1][0]:.0f} ms")
        return account


def find_order(orders, order_id):
    return next(order for order in orders if order["order_id"] == order_id)


def check_role_rejections(api, customer, manager, book_id):
    api.call("GET", "/api/books", 401)
    api.call("GET", "/api/books", 401, token=str(uuid4()))
    for method, path in (
        ("POST", "/api/orders"),
        ("POST", f"/api/books/{book_id}/reviews"),
        ("GET", "/api/orders/my-history"),
    ):
        api.call(method, path, 403, token=manager)
    for method, path in (
        ("GET", "/api/manager/orders"),
        ("PUT", "/api/manager/orders/1/status"),
        ("POST", "/api/manager/books"),
        ("PUT", f"/api/manager/books/{book_id}"),
        ("GET", "/api/manager/analytics"),
    ):
        api.call(method, path, 403, token=customer)


def check_flask(api, customer, manager):
    customer_token, manager_token = customer["token"], manager["token"]
    suffix = uuid4().hex
    author = f"QA Author {suffix}"
    buy_fields = {
        "title": f"E2E Buy & <Print> [{suffix}]",
        "author": author,
        "buy_price": 12.35,
        "rent_price": 2.50,
        "available_copies": 4,
    }
    rent_fields = {**buy_fields, "title": f"E2E Rental {suffix}", "rent_price": 3.25, "available_copies": 2}
    buy_book = api.call("POST", "/api/manager/books", 201, token=manager_token, json=buy_fields)
    rent_book = api.call("POST", "/api/manager/books", 201, token=manager_token, json=rent_fields)
    buy_id, rent_id = buy_book["id"], rent_book["id"]
    assert buy_book["available_copies"] == 4 and buy_book["reviews"] == []
    check_role_rejections(api, customer_token, manager_token, buy_id)

    results = api.call("GET", "/api/books", 200, token=customer_token)["books"]
    assert {buy_id, rent_id} <= {book["id"] for book in results}
    results = api.call("GET", "/api/books", 200, token=manager_token, params={"q": author.upper()})["books"]
    assert {book["id"] for book in results} == {buy_id, rent_id}
    results = api.call("GET", "/api/books", 200, token=customer_token,
                       params={"q": buy_fields["title"].lower()})["books"]
    assert [book["id"] for book in results] == [buy_id]

    review_url = f"/api/books/{buy_id}/reviews"
    api.call("POST", review_url, 400, token=customer_token, json={"rating": True, "comment": "Invalid rating"})
    review = api.call("POST", review_url, 201, token=customer_token,
                      json={"rating": 5, "comment": "End-to-end review"})
    assert review == {"message": "Review added", "avg_rating": 5}
    updated = api.call("PUT", f"/api/manager/books/{buy_id}", 200, token=manager_token,
                       json={**buy_fields, "available_copies": 5})
    assert updated["available_copies"] == 5 and updated["review_count"] == 1
    assert updated["reviews"][0]["user_id"] == customer["user_id"]
    assert updated["reviews"][0]["username"] == customer["username"]

    buy_item = {"book_id": buy_id, "transaction_type": "BUY", "quantity": 2}
    rent_item = {"book_id": rent_id, "transaction_type": "RENT", "quantity": 1}
    api.call("POST", "/api/orders", 409, token=customer_token,
             json={"items": [buy_item, {**rent_item, "quantity": 3}]})
    api.call("POST", "/api/orders", 409, token=customer_token,
             json={"items": [buy_item, {**buy_item, "transaction_type": "RENT", "quantity": 4}]})
    results = api.call("GET", "/api/books", 200, token=customer_token, params={"q": author})["books"]
    assert {book["id"]: book["available_copies"] for book in results} == {buy_id: 5, rent_id: 2}

    checkout = api.call("POST", "/api/orders", 201, token=customer_token, json={"items": [buy_item, rent_item]})
    order_id = checkout["order_id"]
    assert checkout["payment_status"] == "Pending"
    assert Decimal(str(checkout["total_amount"])) == Decimal("27.95")
    assert checkout["email_status"] in ("skipped", "queued")
    assert checkout["bill_html_path"] == f"bills/bill_order_{order_id}.html"
    bill_file = PROJECT_ROOT / checkout["bill_html_path"]
    pending_html = bill_file.read_text(encoding="utf-8")
    assert pending_html == checkout["bill_html_content"]
    assert all(text in pending_html for text in (
        f"Order {order_id}", escape(buy_fields["title"]), customer["username"],
        customer["email"], "BUY", "RENT", "$27.95", "<dd>Pending</dd>",
    ))
    results = api.call("GET", "/api/books", 200, token=manager_token, params={"q": author})["books"]
    assert {book["id"]: book["available_copies"] for book in results} == {buy_id: 3, rent_id: 1}

    history = api.call("GET", "/api/orders/my-history", 200, token=customer_token)
    order = find_order(history, order_id)
    assert all(entry["user_id"] == customer["user_id"] for entry in history)
    assert order["bill_html_content"] == pending_html
    assert [(item["transaction_type"], item["quantity"], item["unit_price"]) for item in order["items"]] == [
        ("BUY", 2, 12.35), ("RENT", 1, 3.25),
    ]
    manager_orders = api.call("GET", "/api/manager/orders", 200, token=manager_token)
    assert find_order(manager_orders, order_id) == order

    status_url = f"/api/manager/orders/{order_id}/status"
    api.call("PUT", status_url, 400, token=manager_token, json={"payment_status": "Other"})
    paid = api.call("PUT", status_url, 200, token=manager_token, json={"payment_status": "Paid"})
    assert paid == {"message": "Order status updated", "order_id": order_id, "payment_status": "Paid"}
    paid_html = bill_file.read_text(encoding="utf-8")
    assert "<dd>Paid</dd>" in paid_html and "$27.95" in paid_html and "$0.00" in paid_html
    paid_orders = api.call("GET", "/api/manager/orders", 200, token=manager_token)
    paid_order = find_order(paid_orders, order_id)
    assert paid_order["payment_status"] == "Paid" and paid_order["bill_html_content"] == paid_html

    order_date = order["created_at"][:10]
    analytics_url = "/api/manager/analytics"
    analytics = api.call("GET", analytics_url, 200, token=manager_token,
                         params={"start_date": order_date, "end_date": order_date})
    matching = analytics["orders_in_period"]
    assert find_order(matching, order_id)["payment_status"] == "Paid"
    assert all(entry["created_at"][:10] == order_date for entry in matching)
    assert analytics["summary"] == {
        "total_orders": len(matching),
        "total_revenue": float(sum(Decimal(str(entry["total_amount"])) for entry in matching)),
        "paid_revenue": float(sum(Decimal(str(entry["total_amount"])) for entry in matching
                                  if entry["payment_status"] == "Paid")),
    }
    best_sellers = analytics["best_sellers"]
    assert [(entry["total_units"], entry["total_sales"]) for entry in best_sellers] == sorted(
        [(entry["total_units"], entry["total_sales"]) for entry in best_sellers], reverse=True
    )
    fixture_sales = {entry["book_id"]: (entry["total_units"], entry["total_sales"])
                     for entry in best_sellers if entry["book_id"] in (buy_id, rent_id)}
    assert fixture_sales == {buy_id: (2, 24.70), rent_id: (1, 3.25)}
    tomorrow = (date.fromisoformat(order_date) + timedelta(days=1)).isoformat()
    outside = api.call("GET", analytics_url, 200, token=manager_token, params={"start_date": tomorrow})
    assert order_id not in {entry["order_id"] for entry in outside["orders_in_period"]}
    print(f"All Flask endpoints passed, including role enforcement and inventory rollback. Invoice {bill_file}")


def main():
    with requests.Session() as session:
        session.trust_env = False
        api = ApiChecks(session)
        tokens = []
        try:
            customer = api.login("customer1", "password123", "CUSTOMER")
            tokens.append(customer["token"])
            manager = api.login("manager1", "admin123", "MANAGER")
            tokens.append(manager["token"])
            check_flask(api, customer, manager)
        finally:
            for token in tokens:
                api.call("POST", "/api/users/logout", 200, token=token, java=True)

        api.call("GET", "/api/books", 401, token=customer["token"])
        elapsed, method, path, service = max(api.timings)
        flask_elapsed, flask_method, flask_path, _ = max(
            timing for timing in api.timings if timing[3] == "Flask"
        )
        print(f"Slowest Flask response {flask_elapsed:.0f} ms ({flask_method} {flask_path})")
        print(f"Slowest of {len(api.timings)} requests {elapsed:.0f} ms ({service} {method} {path})")
        assert elapsed < 500, "N1 latency limit exceeded"


if __name__ == "__main__":
    main()

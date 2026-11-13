"""Book search, reviews, cart, and checkout for a signed-in customer."""

from dataclasses import dataclass
from decimal import Decimal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QSpinBox, QSplitter, QVBoxLayout, QWidget

from desktop_common.widgets import (
    InvoiceDialog, ReviewDialog, button, fill_table, label, money, selected_row, show_error, surface, table,
)


@dataclass
class CartLine:
    book_id: str
    title: str
    transaction_type: str
    quantity: int
    unit_price: Decimal

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


class CatalogView(QWidget):
    checkout_changed = pyqtSignal(bool)

    def __init__(self, request_customer):
        super().__init__()
        self.request = request_customer
        self.books = []
        self.cart = {}
        self.query = ""
        self._revision = 0
        self.checkout_pending = False
        self.review_dialog = None
        self.invoice_dialog = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        panes = QSplitter(Qt.Orientation.Horizontal)
        panes.setChildrenCollapsible(False)
        panes.setHandleWidth(10)
        panes.addWidget(self._build_books())
        panes.addWidget(self._build_cart())
        panes.setStretchFactor(0, 3)
        panes.setStretchFactor(1, 2)
        panes.setSizes([740, 455])
        layout.addWidget(panes)
        self._update_controls()

    def _build_books(self):
        card, layout = surface()
        card.setMinimumWidth(560)
        heading = QHBoxLayout()
        heading.addWidget(label("Book catalog", "heading"))
        heading.addStretch()
        self.result_count = label("", "muted")
        heading.addWidget(self.result_count)
        self.review_button = button("View / Add Reviews", self.open_reviews)
        heading.addWidget(self.review_button)
        layout.addLayout(heading)

        search = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by title or author")
        self.search_edit.setAccessibleName("Search by title or author")
        self.search_edit.returnPressed.connect(self.search)
        search.addWidget(self.search_edit, 1)
        search.addWidget(button("Search", self.search, "primary"))
        search.addWidget(button("Show All", self.show_all))
        layout.addLayout(search)

        self.book_table = table(("Title", "Author", "Buy Price", "Rent Price", "Copies", "Rating"), (0, 1))
        for column, description in enumerate(("Buy Price ($)", "Rent Price ($)", "Available Copies", "Average Rating"), 2):
            self.book_table.horizontalHeaderItem(column).setToolTip(description)
        self.book_table.itemSelectionChanged.connect(self._update_controls)
        layout.addWidget(self.book_table, 1)

        actions = QHBoxLayout()
        quantity_label = label("Quantity")
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 1)
        self.quantity.setMinimumWidth(57)
        quantity_label.setBuddy(self.quantity)
        actions.addWidget(quantity_label)
        actions.addWidget(self.quantity)
        self.buy_button = button("Add to Cart (BUY)", lambda: self.add_to_cart("BUY"), "primary")
        self.rent_button = button("Add to Cart (RENT)", lambda: self.add_to_cart("RENT"))
        actions.addWidget(self.buy_button)
        actions.addWidget(self.rent_button)
        actions.addStretch()
        layout.addLayout(actions)
        return card

    def _build_cart(self):
        card, layout = surface()
        card.setMinimumWidth(370)
        layout.addWidget(label("Shopping cart", "heading"))
        self.cart_table = table(("Title", "Type", "Qty", "Unit price", "Subtotal"))
        self.cart_table.itemSelectionChanged.connect(self._update_controls)
        layout.addWidget(self.cart_table, 1)

        actions = QHBoxLayout()
        self.remove_button = button("Remove Selected", self.remove_selected)
        self.clear_button = button("Clear Cart", self.clear_cart)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        layout.addLayout(actions)

        total = QHBoxLayout()
        total.addWidget(label("Total amount due"))
        total.addStretch()
        self.total_amount = label(money(0), "total")
        total.addWidget(self.total_amount)
        layout.addLayout(total)
        self.checkout_button = button("Checkout && Place Order", self.checkout, "primary")
        self.checkout_button.setMinimumHeight(39)
        layout.addWidget(self.checkout_button)
        return card

    def search(self):
        self.query = self.search_edit.text().strip()
        self.refresh()

    def show_all(self):
        self.search_edit.clear()
        self.search()

    def refresh(self):
        self._revision += 1
        revision = self._revision

        def received(result):
            if revision != self._revision:
                return
            if not result.ok:
                show_error(self, "Catalog unavailable", result.message)
                return
            self._show_books(result.data["books"])

        self.request("flask", "GET", "/api/books", received, params={"q": self.query})

    def _show_books(self, books):
        selection = self._selected_book()
        selected_id = selection["id"] if selection else None
        self.books = books
        fill_table(self.book_table, [
            (
                book["title"], book["author"], money(book["buy_price"]), money(book["rent_price"]),
                book["available_copies"],
                f"{book['avg_rating']:.1f} ★ ({book['review_count']})" if book["review_count"] else "— (0)",
            )
            for book in books
        ], numeric_columns=(2, 3, 4, 5))
        self.result_count.setText(f"{len(books)} {'book' if len(books) == 1 else 'books'}")
        for row, book in enumerate(books):
            if book["id"] == selected_id:
                self.book_table.selectRow(row)
            for transaction_type in ("BUY", "RENT"):
                line = self.cart.get((book["id"], transaction_type))
                if line:
                    line.title = book["title"]
                    line.unit_price = Decimal(str(book[f"{transaction_type.lower()}_price"]))
            if self.review_dialog is not None and self.review_dialog.book_id == book["id"]:
                self.review_dialog.set_reviews(book["reviews"])
        self._show_cart()

    def _selected_book(self):
        row = selected_row(self.book_table)
        return self.books[row] if 0 <= row < len(self.books) else None

    def _remaining(self, book):
        reserved = sum(line.quantity for line in self.cart.values() if line.book_id == book["id"])
        return book["available_copies"] - reserved

    def _update_controls(self):
        book = self._selected_book()
        remaining = self._remaining(book) if book else 0
        can_add = remaining > 0 and not self.checkout_pending
        self.quantity.setMaximum(max(1, remaining))
        self.quantity.setEnabled(can_add)
        self.buy_button.setEnabled(can_add)
        self.rent_button.setEnabled(can_add)
        self.review_button.setEnabled(book is not None)
        has_cart = bool(self.cart) and not self.checkout_pending
        self.remove_button.setEnabled(has_cart and selected_row(self.cart_table) >= 0)
        self.clear_button.setEnabled(has_cart)
        self.checkout_button.setEnabled(has_cart)

    def add_to_cart(self, transaction_type):
        book = self._selected_book()
        quantity = self.quantity.value()
        if book is None or self.checkout_pending or quantity > self._remaining(book):
            return
        key = (book["id"], transaction_type)
        line = self.cart.get(key)
        if line:
            line.quantity += quantity
        else:
            price = Decimal(str(book[f"{transaction_type.lower()}_price"]))
            self.cart[key] = CartLine(book["id"], book["title"], transaction_type, quantity, price)
        self._show_cart()

    def _show_cart(self):
        fill_table(self.cart_table, [
            (line.title, line.transaction_type, line.quantity, money(line.unit_price), money(line.subtotal))
            for line in self.cart.values()
        ], numeric_columns=(2, 3, 4))
        self.total_amount.setText(money(sum(line.subtotal for line in self.cart.values())))
        self._update_controls()

    def remove_selected(self):
        row = selected_row(self.cart_table)
        if row >= 0 and not self.checkout_pending:
            del self.cart[list(self.cart)[row]]
            self._show_cart()

    def clear_cart(self):
        if not self.checkout_pending:
            self.cart.clear()
            self._show_cart()

    def open_reviews(self):
        book = self._selected_book()
        if book is None or self.review_dialog is not None:
            return
        dialog = ReviewDialog(book, self)
        self.review_dialog = dialog
        dialog.finished.connect(self._review_closed)
        dialog.submit_requested.connect(lambda rating, comment: self._submit_review(dialog, rating, comment))
        dialog.open()

    def _review_closed(self):
        self.review_dialog = None

    def _submit_review(self, dialog, rating, comment):
        dialog.set_sending(True)
        dialog.notice.setText("")

        def received(result):
            if self.review_dialog is dialog:
                dialog.set_sending(False)
                dialog.notice.setText("Review submitted." if result.ok else result.message)
                if result.ok:
                    dialog.comment.clear()
            if result.ok:
                self.refresh()

        self.request(
            "flask", "POST", f"/api/books/{dialog.book_id}/reviews", received,
            payload={"rating": rating, "comment": comment},
        )

    def checkout(self):
        if not self.cart or self.checkout_pending:
            return
        items = [
            {"book_id": line.book_id, "transaction_type": line.transaction_type, "quantity": line.quantity}
            for line in self.cart.values()
        ]
        self._set_checkout_pending(True)
        self.request("flask", "POST", "/api/orders", self._checkout_received, payload={"items": items})

    def _set_checkout_pending(self, pending):
        self.checkout_pending = pending
        self.checkout_changed.emit(pending)
        self._update_controls()

    def _checkout_received(self, result):
        self._set_checkout_pending(False)
        if not result.ok:
            message = result.message
            if result.status in (0, 201, 503):
                message += " Check My Profile & Order History before trying checkout again."
            show_error(self, "Checkout failed", message)
            if result.status in (404, 409):
                self.refresh()
            return

        self.clear_cart()
        self.refresh()
        self.invoice_dialog = InvoiceDialog(result.data, self)
        self.invoice_dialog.finished.connect(self._invoice_closed)
        self.invoice_dialog.open()

    def _invoice_closed(self):
        self.invoice_dialog = None

    def reset(self):
        self._revision += 1
        for dialog in (self.review_dialog, self.invoice_dialog):
            if dialog is not None:
                dialog.close()
        self.cart.clear()
        self.books.clear()
        self.query = ""
        self.search_edit.clear()
        self.book_table.setRowCount(0)
        self.result_count.clear()
        self._set_checkout_pending(False)
        self._show_cart()

"""Catalog inventory and manager create and edit forms."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit, QSpinBox,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from desktop_common.widgets import button, fill_table, label, money, selected_row, show_error, surface, table


class BookForm(QWidget):
    def __init__(self, action, submit):
        super().__init__()
        self.title = QLineEdit()
        self.author = QLineEdit()
        self.title.setMaxLength(255)
        self.author.setMaxLength(255)
        self.buy_price = QDoubleSpinBox()
        self.rent_price = QDoubleSpinBox()
        for field in (self.buy_price, self.rent_price):
            field.setDecimals(2)
            field.setRange(0, 99_999_999.99)
            field.setPrefix("$")
        self.copies = QSpinBox()
        self.copies.setRange(0, 2_147_483_647)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for name, field in (("Title", self.title), ("Author", self.author), ("Buy price", self.buy_price),
                            ("Rent price", self.rent_price), ("Available copies", self.copies)):
            field.setAccessibleName(name)
            form.addRow(name, field)
        layout.addLayout(form)
        self.submit_button = button(action, submit, "primary")
        layout.addWidget(self.submit_button)
        layout.addStretch()

    def load(self, book=None):
        book = book or {}
        self.title.setText(book.get("title", ""))
        self.author.setText(book.get("author", ""))
        self.buy_price.setValue(book.get("buy_price", 0))
        self.rent_price.setValue(book.get("rent_price", 0))
        self.copies.setValue(book.get("available_copies", 0))

    def fields(self):
        return {
            "title": self.title.text().strip(),
            "author": self.author.text().strip(),
            "buy_price": self.buy_price.value(),
            "rent_price": self.rent_price.value(),
            "available_copies": self.copies.value(),
        }


class InventoryView(QWidget):
    def __init__(self, request):
        super().__init__()
        self.request = request
        self.books = []
        self.revision = 0
        self.saving = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        panes = QSplitter(Qt.Orientation.Horizontal)
        panes.setHandleWidth(10)
        panes.setChildrenCollapsible(False)
        card, inventory = surface()
        heading = QHBoxLayout()
        heading.addWidget(label("Book inventory", "heading"))
        heading.addStretch()
        self.refresh_button = button("Refresh", self.refresh)
        heading.addWidget(self.refresh_button)
        inventory.addLayout(heading)
        self.book_table = table(("Title", "Author", "Buy Price", "Rent Price", "Copies", "Avg Rating"), (0, 1))
        self.book_table.horizontalHeaderItem(4).setToolTip("Available Copies")
        self.book_table.itemSelectionChanged.connect(self.selection_changed)
        inventory.addWidget(self.book_table, 1)
        self.notice = label("", "muted")
        inventory.addWidget(self.notice)
        panes.addWidget(card)

        card, forms = surface()
        card.setMinimumWidth(330)
        self.forms = QTabWidget()
        self.edit_form = BookForm("Save Changes", self.save_book)
        self.add_form = BookForm("Create Book", self.create_book)
        self.forms.addTab(self.edit_form, "Edit Selected Book")
        self.forms.addTab(self.add_form, "Add New Book")
        forms.addWidget(self.forms)
        panes.addWidget(card)
        panes.setSizes([740, 410])
        layout.addWidget(panes, 1)
        self.selection_changed()

    def selected_book(self):
        row = selected_row(self.book_table)
        return self.books[row] if 0 <= row < len(self.books) else None

    def selection_changed(self):
        self.edit_form.load(self.selected_book())
        self.update_controls()

    def update_controls(self):
        self.edit_form.setEnabled(self.selected_book() is not None and not self.saving)
        self.add_form.setEnabled(not self.saving)
        self.refresh_button.setEnabled(not self.saving)

    def refresh(self):
        if not self.saving:
            self.load_books()

    def load_books(self, preferred_id=None, message=""):
        self.revision += 1
        revision = self.revision

        def received(result):
            if revision != self.revision:
                return
            if not result.ok:
                self.notice.setText(result.message)
                return
            selected = self.selected_book()
            book_id = preferred_id or (selected and selected["id"])
            self.books = result.data["books"]
            fill_table(self.book_table, [
                (book["title"], book["author"], money(book["buy_price"]), money(book["rent_price"]),
                 book["available_copies"], f"{book['avg_rating']:.1f} ★" if book["review_count"] else "—")
                for book in self.books
            ], numeric_columns=(2, 3, 4, 5))
            for row, book in enumerate(self.books):
                if book["id"] == book_id:
                    self.book_table.selectRow(row)
                    break
            self.notice.setText(message or f"{len(self.books)} books")
            self.update_controls()

        self.request("GET", "/api/books", received)

    def save_book(self):
        book = self.selected_book()
        if book:
            self.submit_book("PUT", f"/api/manager/books/{book['id']}", self.edit_form)

    def create_book(self):
        self.submit_book("POST", "/api/manager/books", self.add_form)

    def submit_book(self, method, path, form):
        if self.saving:
            return
        fields = form.fields()
        if not fields["title"] or not fields["author"]:
            show_error(self, "Book details incomplete", "Enter a title and author.")
            return
        self.revision += 1
        self.saving = True
        self.update_controls()

        def received(result):
            self.saving = False
            self.update_controls()
            if not result.ok:
                show_error(self, "Could not save book", result.message)
                return
            if method == "POST":
                self.add_form.load()
                self.forms.setCurrentWidget(self.edit_form)
            self.load_books(result.data["id"], "Book created." if method == "POST" else "Book updated.")

        self.request(method, path, received, payload=fields)

    def reset(self):
        self.revision += 1
        self.saving = False
        self.books = []
        self.book_table.setRowCount(0)
        self.add_form.load()
        self.forms.setCurrentWidget(self.edit_form)
        self.notice.clear()
        self.selection_changed()

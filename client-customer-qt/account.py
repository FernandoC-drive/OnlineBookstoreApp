"""Login, registration, and customer profile and history views."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout, QGridLayout, QHBoxLayout, QLineEdit, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from desktop_common.widgets import button, fill_table, label, local_date, money, selected_row, show_error, surface, table, text_browser


class AuthView(QWidget):
    login_requested = pyqtSignal(str, str)
    register_requested = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setObjectName("appPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addStretch(1)
        card, card_layout = surface()
        card.setFixedWidth(476)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.addWidget(label("Online Bookstore", "hero"))
        card_layout.addWidget(label("Customer accounts", "muted"))
        card_layout.addSpacing(6)

        self.tabs = QTabWidget()
        card_layout.addWidget(self.tabs)

        self.login_username = QLineEdit()
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password.returnPressed.connect(self._login)
        self.login_button = button("Sign in", self._login, "primary")
        login = self._form(
            (("Username", self.login_username), ("Password", self.login_password)), self.login_button,
        )
        self.tabs.addTab(login, "Login")

        self.register_username = QLineEdit()
        self.register_email = QLineEdit()
        self.register_password = QLineEdit()
        self.register_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.register_password.returnPressed.connect(self._register)
        self.register_button = button("Create account", self._register, "primary")
        register = self._form(
            (("Username", self.register_username), ("Email", self.register_email), ("Password", self.register_password)),
            self.register_button,
        )
        self.tabs.addTab(register, "Register Account")

        self.notice = label("", "muted")
        self.notice.setWordWrap(True)
        self.notice.hide()
        card_layout.addWidget(self.notice)
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

    @staticmethod
    def _form(fields, submit_button):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setSpacing(10)
        for name, widget in fields:
            widget.setAccessibleName(name)
            form.addRow(name, widget)
        layout.addLayout(form)
        layout.addWidget(submit_button)
        layout.addStretch()
        return page

    def set_busy(self, busy):
        self.tabs.setEnabled(not busy)

    def set_notice(self, text):
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    def _login(self):
        username = self.login_username.text().strip()
        password = self.login_password.text()
        if not username or not password.strip():
            self.set_notice("Enter your username and password.")
            return
        self.login_password.clear()
        self.login_requested.emit(username, password)

    def _register(self):
        username = self.register_username.text().strip()
        email = self.register_email.text().strip()
        password = self.register_password.text()
        if not username or not email or not password.strip():
            show_error(self, "Registration incomplete", "Enter a username, email address, and password.")
            return
        self.register_password.clear()
        self.register_requested.emit({"username": username, "email": email, "password": password})

    def registered(self, username):
        self.register_username.clear()
        self.register_email.clear()
        self.login_username.setText(username)
        self.tabs.setCurrentIndex(0)
        self.login_password.setFocus()
        self.set_notice("Account created. Sign in with your new account.")


class ProfileView(QWidget):
    def __init__(self, request_customer):
        super().__init__()
        self.request = request_customer
        self.orders = []
        self._revision = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        card, details = surface()
        heading = QHBoxLayout()
        heading.addWidget(label("My profile", "heading"))
        heading.addStretch()
        heading.addWidget(button("Refresh", self.refresh))
        details.addLayout(heading)

        columns = QGridLayout()
        columns.setHorizontalSpacing(22)
        self.values = {}
        for column, field in enumerate(("Username", "Email", "Role", "Member Since")):
            columns.addWidget(label(field, "muted"), 0, column)
            value = label("—")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            value.setAccessibleName(field)
            columns.addWidget(value, 1, column)
            columns.setColumnStretch(column, 1 if field != "Email" else 2)
            self.values[field] = value
        details.addLayout(columns)
        self.profile_notice = label("", "muted")
        self.profile_notice.hide()
        details.addWidget(self.profile_notice)
        layout.addWidget(card)

        panes = QSplitter(Qt.Orientation.Horizontal)
        panes.setChildrenCollapsible(False)
        panes.setHandleWidth(10)
        history_card, history = surface()
        history_card.setMinimumWidth(530)
        history.addWidget(label("Order history", "heading"))
        self.order_table = table(("Order ID", "Date", "Total Amount", "Payment Status", "Item Summary"), (4,))
        self.order_table.itemSelectionChanged.connect(self._show_invoice)
        history.addWidget(self.order_table, 1)
        self.history_notice = label("", "muted")
        self.history_notice.hide()
        history.addWidget(self.history_notice)
        panes.addWidget(history_card)

        preview_card, preview = surface()
        preview_card.setMinimumWidth(270)
        self.preview_heading = label("Invoice preview", "heading")
        preview.addWidget(self.preview_heading)
        self.preview = text_browser()
        self.preview.setPlaceholderText("Select an order to view its invoice.")
        preview.addWidget(self.preview, 1)
        panes.addWidget(preview_card)
        panes.setSizes([675, 520])
        layout.addWidget(panes, 1)

    def refresh(self):
        self._revision += 1
        revision = self._revision
        self.profile_notice.hide()
        self.history_notice.hide()

        def profile_received(result):
            if revision != self._revision:
                return
            if not result.ok:
                self.profile_notice.setText(result.message)
                self.profile_notice.show()
                return
            profile = result.data
            self.values["Username"].setText(profile["username"])
            self.values["Email"].setText(profile["email"])
            self.values["Role"].setText(profile["role"])
            self.values["Member Since"].setText(local_date(profile.get("created_at")))

        def history_received(result):
            if revision != self._revision:
                return
            if not result.ok:
                self.history_notice.setText(result.message)
                self.history_notice.show()
                return
            self._show_orders(result.data)

        self.request("java", "GET", "/api/users/profile", profile_received)
        self.request("flask", "GET", "/api/orders/my-history", history_received)

    def _show_orders(self, orders):
        self.orders = orders
        rows = []
        for order in orders:
            summary = ", ".join(
                f"{item['quantity']}× {item['book_title']} ({item['transaction_type']})" for item in order["items"]
            )
            rows.append((
                order["order_id"], local_date(order["created_at"]), money(order["total_amount"]),
                order["payment_status"], summary,
            ))
        fill_table(self.order_table, rows, numeric_columns=(0, 2))
        if orders:
            self.order_table.selectRow(0)
        else:
            self.history_notice.setText("No orders yet.")
            self.history_notice.show()
        self._show_invoice()

    def _show_invoice(self):
        row = selected_row(self.order_table)
        if 0 <= row < len(self.orders):
            order = self.orders[row]
            self.preview_heading.setText(f"Invoice · Order {order['order_id']}")
            self.preview.setHtml(order["bill_html_content"])
        else:
            self.preview_heading.setText("Invoice preview")
            self.preview.clear()

    def reset(self):
        self._revision += 1
        self.orders = []
        self.order_table.setRowCount(0)
        for value in self.values.values():
            value.setText("—")
        self.profile_notice.hide()
        self.history_notice.hide()
        self._show_invoice()

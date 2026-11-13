"""Native desktop workspace for bookstore managers."""

from pathlib import Path
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout, QFrame, QHBoxLayout, QLineEdit, QMainWindow, QProgressBar,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_common.api import ApiClient
from desktop_common.widgets import button, create_application, label, show_error, surface
from inventory_view import InventoryView
from orders_view import OrdersView
from reports_view import ReportsView


class ManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Online Bookstore · Manager")
        self.setMinimumSize(1040, 640)
        self.resize(1290, 800)
        self.token = None
        self.generation = 0
        self.api = ApiClient(self)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(72, 8)
        self.statusBar().addPermanentWidget(self.progress)
        self.progress.hide()
        self.api.pending_changed.connect(self.show_loading)

        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self.login_page = self.build_login()
        self.pages.addWidget(self.login_page)
        self.workspace = self.build_workspace()
        self.pages.addWidget(self.workspace)
        self.username.setFocus()

    def build_login(self):
        page = QWidget()
        page.setObjectName("appPage")
        layout = QVBoxLayout(page)
        layout.addStretch()
        self.login_card, card = surface()
        self.login_card.setFixedWidth(476)
        card.setContentsMargins(28, 24, 28, 24)
        card.addWidget(label("Online Bookstore", "hero"))
        card.addWidget(label("Manager sign-in", "muted"))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self.sign_in)
        self.username.setAccessibleName("Username")
        self.password.setAccessibleName("Password")
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        card.addLayout(form)
        self.sign_in_button = button("Sign in", self.sign_in, "primary")
        card.addWidget(self.sign_in_button)
        layout.addWidget(self.login_card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return page

    def build_workspace(self):
        page = QWidget()
        page.setObjectName("appPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)
        top = QFrame()
        top.setObjectName("topBar")
        bar = QHBoxLayout(top)
        bar.setContentsMargins(17, 12, 17, 12)
        bar.addWidget(label("Bookstore Management", "brand"))
        bar.addStretch()
        self.account_name = label("", "accountName")
        bar.addWidget(self.account_name)
        self.logout_button = button("Logout", self.logout, "header")
        bar.addWidget(self.logout_button)
        layout.addWidget(top)

        self.tabs = QTabWidget()
        self.orders = OrdersView(self.request_manager)
        self.inventory = InventoryView(self.request_manager)
        self.reports = ReportsView(self.request_manager)
        self.tabs.addTab(self.orders, "Order Administration")
        self.tabs.addTab(self.inventory, "Book Inventory")
        self.tabs.addTab(self.reports, "Sales Reports")
        self.tabs.currentChanged.connect(self.refresh_tab)
        layout.addWidget(self.tabs, 1)
        return page

    def show_loading(self, pending):
        self.progress.setVisible(bool(pending))
        self.statusBar().showMessage("Loading…" if pending else "")

    def sign_in(self):
        username = self.username.text().strip()
        password = self.password.text()
        if not username or not password.strip():
            show_error(self, "Sign-in incomplete", "Enter your username and password.")
            return
        self.password.clear()
        self.login_card.setEnabled(False)
        self.api.request(
            "java", "POST", "/api/users/login", self.login_received,
            payload={"username": username, "password": password},
        )

    def login_received(self, result):
        if not result.ok:
            self.login_card.setEnabled(True)
            show_error(self, "Sign-in failed", result.message)
            return
        data = result.data
        if not isinstance(data, dict) or not isinstance(data.get("token"), str) or not data["token"]:
            self.login_card.setEnabled(True)
            show_error(self, "Sign-in failed", "The user service returned an invalid sign-in response.")
            return
        if data.get("role") != "MANAGER":
            self.api.request("java", "POST", "/api/users/logout", self.logout_received, token=data["token"])
            show_error(self, "Access denied", "This workspace requires a manager account. Use the Customer App.")
            return

        self.login_card.setEnabled(True)
        self.token = data["token"]
        self.generation += 1
        name = data.get("username")
        self.account_name.setText(name if isinstance(name, str) else self.username.text().strip())
        self.pages.setCurrentWidget(self.workspace)
        self.refresh_tab()

    def refresh_tab(self, _index=None):
        if self.token:
            self.tabs.currentWidget().refresh()

    def request_manager(self, method, path, finished, **kwargs):
        if not self.token:
            return
        generation = self.generation

        def received(result):
            if generation != self.generation:
                return
            if result.status == 401:
                self.clear_session()
                show_error(self, "Session expired", "Sign in again to continue.")
            else:
                finished(result)

        self.api.request("flask", method, path, received, token=self.token, **kwargs)

    def logout(self):
        if self.token:
            token = self.token
            self.clear_session()
            self.login_card.setEnabled(False)
            self.api.request("java", "POST", "/api/users/logout", self.logout_received, token=token)

    def logout_received(self, result):
        self.login_card.setEnabled(True)
        if not result.ok and result.status != 401:
            self.statusBar().showMessage("The server could not confirm logout. " + result.message, 8000)

    def clear_session(self):
        self.token = None
        self.generation += 1
        self.pages.setCurrentWidget(self.login_page)
        self.account_name.clear()
        for view in (self.orders, self.inventory, self.reports):
            view.reset()
        self.tabs.setCurrentWidget(self.orders)
        self.username.setFocus()


def main():
    application = create_application()
    window = ManagerWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    sys.exit(main())

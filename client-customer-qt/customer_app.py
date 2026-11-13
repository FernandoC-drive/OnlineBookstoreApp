"""Native desktop application for bookstore customers."""

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QMainWindow, QProgressBar,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

# Support direct execution from the client directory and from the root launcher.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from account import AuthView, ProfileView
from catalog import CatalogView
from desktop_common.api import ApiClient
from desktop_common.widgets import button, create_application, label, show_error


class CustomerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Online Bookstore · Customer")
        self.setMinimumSize(1000, 620)
        self.resize(1270, 780)
        self.token = None
        self._session_generation = 0

        self.api = ApiClient(self)
        self.api.pending_changed.connect(self._show_loading)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(72, 8)
        self.statusBar().addPermanentWidget(self.progress)
        self._show_loading(0)

        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self.auth = AuthView()
        self.auth.login_requested.connect(self.login)
        self.auth.register_requested.connect(self.register)
        self.pages.addWidget(self.auth)
        self.dashboard = self._dashboard()
        self.pages.addWidget(self.dashboard)
        self.auth.login_username.setFocus()

    def _dashboard(self):
        page = QWidget()
        page.setObjectName("appPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)

        top = QFrame()
        top.setObjectName("topBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(17, 12, 17, 12)
        top_layout.setSpacing(14)
        top_layout.addWidget(label("Online Bookstore", "brand"))
        top_layout.addStretch()
        self.account_name = label("", "accountName")
        top_layout.addWidget(self.account_name)
        self.logout_button = button("Logout", self.logout, "header")
        top_layout.addWidget(self.logout_button)
        layout.addWidget(top)

        self.tabs = QTabWidget()
        self.catalog = CatalogView(self.request_customer)
        self.catalog.checkout_changed.connect(self._checkout_changed)
        self.profile = ProfileView(self.request_customer)
        self.tabs.addTab(self.catalog, "Catalog && Cart")
        self.tabs.addTab(self.profile, "My Profile && Order History")
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)
        return page

    def _show_loading(self, pending):
        self.progress.setVisible(pending > 0)
        self.statusBar().showMessage("Loading…" if pending else "")

    def _checkout_changed(self, pending):
        self.logout_button.setEnabled(not pending)

    def _tab_changed(self, _index):
        if self.token and self.tabs.currentWidget() is self.profile:
            self.profile.refresh()

    def login(self, username, password):
        self.auth.set_notice("")
        self.auth.set_busy(True)
        self.api.request(
            "java", "POST", "/api/users/login", self._login_received,
            payload={"username": username, "password": password},
        )

    def _login_received(self, result):
        if not result.ok:
            self.auth.set_busy(False)
            self.auth.set_notice(result.message)
            return
        user = result.data
        if not isinstance(user, dict) or not user.get("token") or not user.get("role"):
            self.auth.set_busy(False)
            self.auth.set_notice("The user service returned an invalid sign-in response.")
            return
        if user["role"] != "CUSTOMER":
            self.token = None
            self.api.request("java", "POST", "/api/users/logout", self._logout_received, token=user["token"])
            show_error(self, "Customer account required", "Managers must sign in through the separate Manager App.")
            return

        self.auth.set_busy(False)
        self.token = user["token"]
        self._session_generation += 1
        self.account_name.setText(user["username"])
        self.pages.setCurrentWidget(self.dashboard)
        self.catalog.refresh()

    def register(self, payload):
        username = payload["username"]
        self.auth.set_notice("")
        self.auth.set_busy(True)

        def received(result):
            self.auth.set_busy(False)
            if result.status == 201:
                # Registration does not require a token or any response fields.
                self.auth.registered(username)
            else:
                show_error(self, "Registration failed", result.message or "The service did not confirm registration.")

        self.api.request("java", "POST", "/api/users/register", received, payload=payload)

    def logout(self):
        if not self.token or self.catalog.checkout_pending:
            return
        token = self.token
        self._clear_session()
        self.auth.set_busy(True)
        self.api.request("java", "POST", "/api/users/logout", self._logout_received, token=token)

    def _logout_received(self, result):
        self.auth.set_busy(False)
        if not result.ok and result.status != 401:
            self.auth.set_notice("The server could not confirm logout. " + result.message)

    def _clear_session(self):
        self.token = None
        self._session_generation += 1
        self.pages.setCurrentWidget(self.auth)
        self.auth.set_notice("")
        self.account_name.clear()
        self.catalog.reset()
        self.profile.reset()
        self.tabs.setCurrentWidget(self.catalog)

    def request_customer(self, service, method, path, finished, **kwargs):
        if not self.token:
            return
        generation = self._session_generation

        def received(result):
            if generation != self._session_generation:
                return
            if result.status == 401:
                self._clear_session()
                show_error(self, "Session expired", "Sign in again to continue.")
                return
            finished(result)

        self.api.request(service, method, path, received, token=self.token, **kwargs)


def main():
    application = create_application()
    window = CustomerWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    sys.exit(main())

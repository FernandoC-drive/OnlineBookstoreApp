"""Offscreen integration smoke test using the running local bookstore services."""

import os
from threading import Event, get_ident
from time import monotonic
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt" and "SystemRoot" in os.environ:
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ["SystemRoot"], "Fonts"))

from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from customer_app import CustomerWindow, create_application
from desktop_common.api import ApiWorker
from requests import Response


class CustomerSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = create_application()

    def setUp(self):
        self.window = CustomerWindow()
        self.window.show()
        self.main_thread = get_ident()
        self.calls = []
        self.pending = []
        self.window.api.pending_changed.connect(lambda count: self.pending.append((count, get_ident())))

    def tearDown(self):
        for dialog in self.window.findChildren(QMessageBox):
            if dialog.isVisible():
                dialog.accept()
        if self.window.token:
            self.window.logout()
            self.wait_for(lambda: not self.window.progress.isVisible(), "Logout did not finish")
        self.window.close()

    def wait_for(self, condition, message):
        deadline = monotonic() + 12
        while not condition() and monotonic() < deadline:
            QTest.qWait(20)
        self.assertTrue(condition(), message)

    def sign_in(self, username, password):
        auth = self.window.auth
        auth.login_username.setText(username)
        auth.login_password.setText(password)
        auth.login_button.click()

    def register(self, username, email, password="registration-test-password"):
        auth = self.window.auth
        auth.tabs.setCurrentIndex(1)
        auth.register_username.setText(username)
        auth.register_email.setText(email)
        auth.register_password.setText(password)
        auth.register_button.click()

    def dismiss_warning(self):
        def warnings():
            return [box for box in self.window.findChildren(QMessageBox) if box.isVisible()]

        self.wait_for(warnings, "Registration warning did not appear")
        warning = warnings()[0]
        self.assertEqual(warning.icon(), QMessageBox.Icon.Warning)
        message = warning.text()
        warning.accept()
        return message

    def test_register_and_sign_in_with_new_account(self):
        username = f"gui_test_{uuid4().hex}"
        email = f"{username}@example.com"
        self.register(username, email)
        auth = self.window.auth
        self.wait_for(lambda: auth.tabs.currentIndex() == 0, "Registration did not return to Login")
        self.assertIn("Account created", auth.notice.text())
        self.assertEqual(auth.login_username.text(), username)

        self.register(username, f"other_{email}")
        self.assertIn("already exists", self.dismiss_warning())
        self.register(f"other_{username}", email)
        self.assertIn("already exists", self.dismiss_warning())

        auth.tabs.setCurrentIndex(0)
        self.sign_in(username, "registration-test-password")
        self.wait_for(lambda: self.window.catalog.book_table.rowCount() > 0, "New account could not log in")
        self.assertEqual(self.window.account_name.text(), username)
        self.assertTrue(self.window.token)

    def test_registration_rejects_invalid_input_and_unexpected_error_bodies(self):
        self.register("", "")
        self.assertIn("Enter a username", self.dismiss_warning())
        self.register("invalid_email", "not-an-email")
        self.assertIn("valid email", self.dismiss_warning())
        for body in (b'<html>Database error</html>', b'{"message":{"reason":"database error"}}'):
            with self.subTest(body=body):
                response = Response()
                response.status_code = 500
                response._content = body
                with patch("desktop_common.api.requests.Session.request", return_value=response):
                    self.register("server_error", "server_error@example.com")
                    self.assertIn("HTTP 500", self.dismiss_warning())
                self.assertTrue(self.window.auth.register_button.isEnabled())

    def test_live_customer_and_manager_role_rejection(self):
        original_send = ApiWorker._send
        allow_login = Event()
        loading_during_timer = []

        def observed_send(worker):
            self.calls.append((worker.method, worker.url, worker.token, get_ident()))
            if worker.payload and worker.payload.get("username") == "customer1":
                if not allow_login.wait(4):
                    raise RuntimeError("The GUI timer could not run during login")
            return original_send(worker)

        def release_login():
            loading_during_timer.append(self.window.progress.isVisible())
            allow_login.set()

        with patch.object(ApiWorker, "_send", observed_send):
            QTimer.singleShot(50, release_login)
            self.sign_in("customer1", "password123")
            self.wait_for(
                lambda: self.window.catalog.book_table.rowCount() > 0,
                f"Login or catalog loading failed. {self.window.auth.notice.text()}",
            )
            self.assertEqual(loading_during_timer, [True])
            self.assertIs(self.window.pages.currentWidget(), self.window.dashboard)
            self.assertTrue(self.window.token)
            print(f"Catalog loaded {self.window.catalog.book_table.rowCount()} books")

            self.window.tabs.setCurrentWidget(self.window.profile)
            self.wait_for(
                lambda: self.window.profile.values["Username"].text() == "customer1"
                and not self.window.progress.isVisible(),
                "Profile and order history did not finish loading",
            )
            self.assertEqual(self.window.profile.values["Role"].text(), "CUSTOMER")
            self.assertIn("@", self.window.profile.values["Email"].text())
            self.assertTrue(any(url.endswith("/api/orders/my-history") for _, url, _, _ in self.calls))
            if self.window.profile.order_table.rowCount():
                self.assertIn("Bookstore Invoice", self.window.profile.preview.toPlainText())

            customer_token = self.window.token
            self.window.logout_button.click()
            self.wait_for(lambda: not self.window.progress.isVisible(), "Customer logout did not finish")
            self.assertIsNone(self.window.token)
            self.assertTrue(any(
                url.endswith("/api/users/logout") and token == customer_token for _, url, token, _ in self.calls
            ))

            self.sign_in("manager1", "admin123")
            self.wait_for(
                lambda: any(box.isVisible() for box in self.window.findChildren(QMessageBox))
                and not self.window.progress.isVisible(),
                "Manager login was not rejected and logged out",
            )
            dialog = next(box for box in self.window.findChildren(QMessageBox) if box.isVisible())
            self.assertIn("Manager App", dialog.text())
            self.assertIsNone(self.window.token)
            self.assertIs(self.window.pages.currentWidget(), self.window.auth)
            manager_token = next(
                token for _, url, token, _ in self.calls
                if url.endswith("/api/users/logout") and token != customer_token
            )
            dialog.accept()
            result = []
            self.window.api.request("java", "GET", "/api/users/profile", result.append, token=manager_token)
            self.wait_for(lambda: bool(result), "Manager token revocation check did not finish")
            self.assertEqual(result[0].status, 401)

        self.assertTrue(self.calls)
        self.assertTrue(all(thread != self.main_thread for _, _, _, thread in self.calls))
        self.assertTrue(all(thread == self.main_thread for _, thread in self.pending))
        print("Verified live login, background requests, responsive Qt timers, profile, and manager token revocation")


if __name__ == "__main__":
    unittest.main(verbosity=2)

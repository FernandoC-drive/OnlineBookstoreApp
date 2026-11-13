"""Exercise the manager workspace against the live Java and Flask services."""

import os
from pathlib import Path
from threading import Event, get_ident
from time import monotonic
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt" and "SystemRoot" in os.environ:
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ["SystemRoot"], "Fonts"))

from PyQt6.QtCore import QDate, QTimer
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from manager_app import ManagerWindow
from desktop_common.api import ApiWorker, PROJECT_ROOT
from desktop_common.widgets import create_application


class ManagerSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = create_application()

    def setUp(self):
        self.window = ManagerWindow()
        self.window.show()

    def tearDown(self):
        for dialog in self.window.findChildren(QMessageBox):
            if dialog.isVisible():
                dialog.accept()
        if self.window.token:
            self.window.logout()
            self.wait_for(lambda: not self.window.progress.isVisible(), "Manager logout did not finish")
        self.window.close()

    def wait_for(self, condition, message):
        deadline = monotonic() + 12
        while not condition() and monotonic() < deadline:
            QTest.qWait(20)
        self.assertTrue(condition(), message)

    def sign_in(self, username, password):
        self.window.username.setText(username)
        self.window.password.setText(password)
        self.window.sign_in_button.click()

    def api(self, service, method, path, status=200, **kwargs):
        responses = []
        self.window.api.request(service, method, path, responses.append, **kwargs)
        self.wait_for(lambda: bool(responses), f"{method} {path} did not finish")
        response = responses[0]
        self.assertEqual(response.status, status, response.message)
        return response.data

    def test_workspace_and_role_rejection(self):
        main_thread = get_ident()
        worker_calls = []
        timer_state = []
        allow_login = Event()
        original_send = ApiWorker._send

        def observe(worker):
            worker_calls.append((worker.url, worker.token, get_ident()))
            if worker.payload and worker.payload.get("username") == "manager1":
                if not allow_login.wait(4):
                    raise RuntimeError("The GUI event loop did not run during login")
            return original_send(worker)

        def release_login():
            timer_state.append(self.window.progress.isVisible())
            allow_login.set()

        with patch.object(ApiWorker, "_send", observe):
            self.sign_in("customer1", "password123")
            self.wait_for(lambda: self.window.login_card.isEnabled() and any(
                dialog.isVisible() for dialog in self.window.findChildren(QMessageBox)
            ), "Customer sign-in was not rejected")
            self.assertIsNone(self.window.token)
            self.assertIs(self.window.pages.currentWidget(), self.window.login_page)
            warning = next(dialog for dialog in self.window.findChildren(QMessageBox) if dialog.isVisible())
            self.assertIn("Customer App", warning.text())
            warning.accept()
            denied_token = next(token for url, token, _ in worker_calls if url.endswith("/api/users/logout"))
            self.api("java", "GET", "/api/users/profile", 401, token=denied_token)

            QTimer.singleShot(50, release_login)
            self.sign_in("manager1", "admin123")
            self.wait_for(lambda: self.window.token and not self.window.progress.isVisible(), "Manager login failed")
            self.assertEqual(timer_state, [True])
            self.assertIs(self.window.pages.currentWidget(), self.window.workspace)
            self.assertEqual(self.window.tabs.count(), 3)
            self.check_workspace()

            manager_token = self.window.token
            self.window.logout_button.click()
            self.wait_for(lambda: not self.window.progress.isVisible(), "Manager logout did not finish")
            self.assertIsNone(self.window.token)
            self.assertIs(self.window.pages.currentWidget(), self.window.login_page)
            self.api("java", "GET", "/api/users/profile", 401, token=manager_token)

        self.assertTrue(all(thread != main_thread for _, _, thread in worker_calls))

    def check_workspace(self):
        inventory = self.window.inventory
        self.window.tabs.setCurrentWidget(inventory)
        self.wait_for(lambda: inventory.book_table.rowCount() > 0, "Inventory did not load")
        title = f"Manager GUI test {uuid4().hex[:12]}"
        inventory.forms.setCurrentWidget(inventory.add_form)
        inventory.add_form.title.setText(title)
        inventory.add_form.author.setText("Manager smoke test")
        inventory.add_form.buy_price.setValue(11.50)
        inventory.add_form.rent_price.setValue(3.25)
        inventory.add_form.copies.setValue(4)
        inventory.add_form.submit_button.click()
        self.wait_for(lambda: inventory.notice.text() == "Book created.", "Create Book did not finish")
        self.assertEqual(inventory.edit_form.title.text(), title)
        book_id = inventory.selected_book()["id"]
        inventory.edit_form.copies.setValue(6)
        inventory.edit_form.submit_button.click()
        self.wait_for(lambda: inventory.notice.text() == "Book updated.", "Save Changes did not finish")
        self.assertEqual(inventory.selected_book()["available_copies"], 6)

        # A customer session creates a test order without changing an existing customer's order.
        customer = self.api("java", "POST", "/api/users/login",
                            payload={"username": "customer1", "password": "password123"})
        try:
            order = self.api("flask", "POST", "/api/orders", 201, token=customer["token"], payload={
                "items": [{"book_id": book_id, "transaction_type": "RENT", "quantity": 2}],
            })
        finally:
            self.api("java", "POST", "/api/users/logout", token=customer["token"])

        order_id = order["order_id"]
        orders = self.window.orders
        self.window.tabs.setCurrentWidget(orders)
        self.wait_for(lambda: any(order["order_id"] == order_id for order in orders.orders), "Order did not load")
        row = next(index for index, order in enumerate(orders.orders) if order["order_id"] == order_id)
        orders.order_table.selectRow(row)
        self.assertIn(title, orders.preview.toPlainText())
        self.assertIn("Pending", orders.preview.toPlainText())
        bill = PROJECT_ROOT / order["bill_html_path"]
        self.assertTrue(bill.is_file())
        with patch.object(QDesktopServices, "openUrl", return_value=True) as browser:
            orders.open_button.click()
            self.assertEqual(Path(browser.call_args.args[0].toLocalFile()).resolve(), bill.resolve())

        orders.status.setCurrentText("Paid")
        orders.update_button.click()
        self.wait_for(lambda: orders.selected_order() and orders.selected_order()["payment_status"] == "Paid",
                      "Updated order did not reload")
        self.assertIn("Paid", orders.preview.toPlainText())
        self.assertIn("<dd>Paid</dd>", bill.read_text(encoding="utf-8"))

        reports = self.window.reports
        self.assertEqual(reports.end_date.date(), QDate.currentDate())
        self.assertEqual(reports.start_date.date().daysTo(reports.end_date.date()), 29)
        self.window.tabs.setCurrentWidget(reports)
        self.wait_for(lambda: reports.notice.isVisible(), "Date-filtered report did not load")
        self.assertIn("UTC", reports.notice.text())
        reports.all_time.setChecked(True)
        self.assertFalse(reports.start_date.isEnabled())
        reports.generate()
        self.wait_for(lambda: reports.notice.text() == "All time", "All Time report did not load")
        self.assertGreaterEqual(int(reports.totals["total_orders"].text()), 1)
        self.assertTrue(reports.totals["paid_revenue"].text().startswith("$"))
        self.assertIn(str(order_id), [reports.order_table.item(row, 0).text()
                                     for row in range(reports.order_table.rowCount())])
        self.assertIn(title, [reports.sales_table.item(row, 1).text() for row in range(reports.sales_table.rowCount())])
        print(f"Verified inventory create/edit, payment update, invoice and print link, and reports for test order {order_id}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

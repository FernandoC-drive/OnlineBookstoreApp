"""Order listing, invoice preview, and payment status updates."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QSplitter, QTextEdit, QVBoxLayout, QWidget

from desktop_common.widgets import (
    button, fill_table, label, local_date, money, open_saved_bill, selected_row, show_error, surface, table,
    text_browser,
)


class OrdersView(QWidget):
    def __init__(self, request):
        super().__init__()
        self.request = request
        self.orders = []
        self.revision = 0
        self.saving = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        panes = QSplitter(Qt.Orientation.Horizontal)
        panes.setHandleWidth(10)
        panes.setChildrenCollapsible(False)

        card, orders = surface()
        heading = QHBoxLayout()
        heading.addWidget(label("Customer orders", "heading"))
        heading.addStretch()
        self.refresh_button = button("Refresh", self.refresh)
        heading.addWidget(self.refresh_button)
        orders.addLayout(heading)
        self.order_table = table(("Order ID", "Customer", "Email", "Date", "Items", "Total ($)", "Status"), (2, 4))
        self.order_table.horizontalHeaderItem(6).setToolTip("Payment Status")
        self.order_table.itemSelectionChanged.connect(self.selection_changed)
        orders.addWidget(self.order_table, 1)
        self.notice = label("", "muted")
        orders.addWidget(self.notice)
        panes.addWidget(card)

        card, invoice = surface()
        card.setMinimumWidth(305)
        self.invoice_heading = label("Invoice preview", "heading")
        invoice.addWidget(self.invoice_heading)
        self.preview = text_browser()
        self.preview.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth)
        self.preview.setLineWrapColumnOrWidth(580)
        self.preview.setPlaceholderText("Select an order to view its invoice.")
        invoice.addWidget(self.preview, 1)
        self.open_button = button("Open Saved Bill / Print", self.open_bill)
        invoice.addWidget(self.open_button)
        actions = QHBoxLayout()
        status_label = label("Payment status")
        self.status = QComboBox()
        self.status.addItems(("Pending", "Paid"))
        self.status.setAccessibleName("Payment status")
        status_label.setBuddy(self.status)
        actions.addWidget(status_label)
        actions.addWidget(self.status, 1)
        invoice.addLayout(actions)
        self.update_button = button("Update Payment Status", self.update_status, "primary")
        invoice.addWidget(self.update_button)
        panes.addWidget(card)
        panes.setSizes([760, 440])
        layout.addWidget(panes, 1)
        self.selection_changed()

    def selected_order(self):
        row = selected_row(self.order_table)
        return self.orders[row] if 0 <= row < len(self.orders) else None

    def refresh(self):
        if not self.saving:
            self.load_orders()

    def load_orders(self, preferred_id=None, message=""):
        self.revision += 1
        revision = self.revision

        def received(result):
            if revision != self.revision:
                return
            if not result.ok:
                self.notice.setText(result.message)
                return
            selected = self.selected_order()
            order_id = preferred_id if preferred_id is not None else (selected and selected["order_id"])
            self.orders = result.data
            rows = []
            for order in self.orders:
                items = ", ".join(
                    f"{item['quantity']}× {item['book_title']} ({item['transaction_type']})"
                    for item in order["items"]
                )
                rows.append((order["order_id"], order["username"], order["email"], local_date(order["created_at"]),
                             items, money(order["total_amount"]), order["payment_status"]))
            fill_table(self.order_table, rows, numeric_columns=(0, 5))
            for row, order in enumerate(self.orders):
                if order["order_id"] == order_id:
                    self.order_table.selectRow(row)
                    break
            count = f"{len(rows)} {'order' if len(rows) == 1 else 'orders'}"
            self.notice.setText(message or (count if rows else "No customer orders yet."))
            self.selection_changed()

        self.request("GET", "/api/manager/orders", received)

    def selection_changed(self):
        order = self.selected_order()
        self.open_button.setEnabled(bool(order and order.get("bill_html_path")))
        self.status.setEnabled(order is not None and not self.saving)
        self.update_button.setEnabled(order is not None and not self.saving)
        self.refresh_button.setEnabled(not self.saving)
        if order:
            self.status.setCurrentText(order["payment_status"])
            self.invoice_heading.setText(f"Invoice · Order {order['order_id']}")
            self.preview.setHtml(order.get("bill_html_content") or "<p>Invoice unavailable.</p>")
        else:
            self.invoice_heading.setText("Invoice preview")
            self.preview.clear()

    def open_bill(self):
        order = self.selected_order()
        if order and order.get("bill_html_path"):
            open_saved_bill(self, order["bill_html_path"])

    def update_status(self):
        order = self.selected_order()
        if order is None or self.saving:
            return
        order_id = order["order_id"]
        status = self.status.currentText()
        self.saving = True
        self.selection_changed()

        def received(result):
            self.saving = False
            self.selection_changed()
            if result.ok:
                self.load_orders(order_id, f"Order {order_id} marked {status}.")
            else:
                show_error(self, "Could not update payment status", result.message)

        self.request("PUT", f"/api/manager/orders/{order_id}/status", received, payload={"payment_status": status})

    def reset(self):
        self.revision += 1
        self.orders = []
        self.saving = False
        self.order_table.setRowCount(0)
        self.notice.clear()
        self.selection_changed()

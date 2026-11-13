"""Date-filtered sales totals, matching orders, and best sellers."""

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import QCheckBox, QDateEdit, QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from desktop_common.widgets import button, fill_table, label, local_date, money, show_error, surface, table


class ReportsView(QWidget):
    def __init__(self, request):
        super().__init__()
        self.request = request
        self.revision = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        filters, filter_layout = surface()
        controls = QHBoxLayout()
        today = QDate.currentDate()
        self.start_date = self.date_field("Start Date", today.addDays(-29), controls)
        self.end_date = self.date_field("End Date", today, controls)
        self.all_time = QCheckBox("All Time")
        self.all_time.toggled.connect(self.date_controls)
        controls.addWidget(self.all_time)
        controls.addStretch()
        controls.addWidget(button("Generate Report", self.generate, "primary"))
        filter_layout.addLayout(controls)
        self.notice = label("", "muted")
        self.notice.hide()
        filter_layout.addWidget(self.notice)
        layout.addWidget(filters)

        summaries = QHBoxLayout()
        summaries.setSpacing(10)
        self.totals = {}
        for key, title in (("total_orders", "Total Orders"), ("total_revenue", "Total Revenue"),
                           ("paid_revenue", "Paid Revenue")):
            card, contents = surface()
            contents.addWidget(label(title, "muted"))
            self.totals[key] = label("—", "total")
            contents.addWidget(self.totals[key])
            summaries.addWidget(card, 1)
        layout.addLayout(summaries)

        tables = QSplitter(Qt.Orientation.Horizontal)
        tables.setHandleWidth(10)
        tables.setChildrenCollapsible(False)
        card, contents = surface()
        contents.addWidget(label("Orders in Selected Period", "heading"))
        self.order_table = table(("Order ID", "Customer", "Date", "Status", "Total Amount"), (1,))
        contents.addWidget(self.order_table, 1)
        tables.addWidget(card)
        card, contents = surface()
        contents.addWidget(label("Best-Selling Books", "heading"))
        self.sales_table = table(("Rank", "Book Title", "Author", "Units", "Revenue"), (1, 2))
        self.sales_table.horizontalHeaderItem(3).setToolTip("Total units sold or rented")
        contents.addWidget(self.sales_table, 1)
        tables.addWidget(card)
        tables.setSizes([550, 590])
        layout.addWidget(tables, 1)

    @staticmethod
    def date_field(name, date, controls):
        field = QDateEdit(date)
        field.setDisplayFormat("yyyy-MM-dd")
        field.setCalendarPopup(True)
        field.setAccessibleName(name)
        controls.addWidget(label(name))
        controls.addWidget(field)
        return field

    def date_controls(self, all_time):
        self.start_date.setEnabled(not all_time)
        self.end_date.setEnabled(not all_time)

    def refresh(self):
        self.generate()

    def generate(self):
        params = {}
        if not self.all_time.isChecked():
            start, end = self.start_date.date(), self.end_date.date()
            if start > end:
                show_error(self, "Invalid date range", "Start Date must be on or before End Date.")
                return
            params = {"start_date": start.toString(Qt.DateFormat.ISODate), "end_date": end.toString(Qt.DateFormat.ISODate)}
        self.revision += 1
        revision = self.revision

        def received(result):
            if revision != self.revision:
                return
            if not result.ok:
                self.notice.setText(result.message)
                self.notice.show()
                return
            report = result.data
            for key, widget in self.totals.items():
                value = report["summary"][key]
                widget.setText(str(value) if key == "total_orders" else money(value))
            fill_table(self.order_table, [
                (order["order_id"], order["username"], local_date(order["created_at"]),
                 order["payment_status"], money(order["total_amount"]))
                for order in report["orders_in_period"]
            ], numeric_columns=(0, 4))
            fill_table(self.sales_table, [
                (rank, book["book_title"], book["author"], book["total_units"], money(book["total_sales"]))
                for rank, book in enumerate(report["best_sellers"], 1)
            ], numeric_columns=(0, 3, 4))
            period = f"{params['start_date']} through {params['end_date']} (UTC)" if params else "All time"
            self.notice.setText(period if report["orders_in_period"] else f"{period} · No orders")
            self.notice.show()

        self.request("GET", "/api/manager/analytics", received, params=params)

    def reset(self):
        self.revision += 1
        self.notice.hide()
        self.all_time.setChecked(False)
        today = QDate.currentDate()
        self.start_date.setDate(today.addDays(-29))
        self.end_date.setDate(today)
        for widget in self.totals.values():
            widget.setText("—")
        self.order_table.setRowCount(0)
        self.sales_table.setRowCount(0)

"""Shared styling, table helpers, and invoice and review dialogs."""

from datetime import datetime
from html import escape
from pathlib import Path
import sys

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout,
)

from shared_ui.theme import apply_modern_theme, style_invoice_preview, style_status_cell

from .api import PROJECT_ROOT


def label(text="", style=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if style:
        widget.setObjectName(style)
    return widget


def button(text, action=None, variant=None):
    widget = QPushButton(text)
    if variant:
        widget.setProperty("variant", variant)
    if action is not None:
        widget.clicked.connect(action)
    return widget


def surface():
    frame = QFrame()
    frame.setObjectName("surface")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)
    return frame, layout


def table(columns, stretch_columns=(0,)):
    widget = QTableWidget(0, len(columns))
    widget.setHorizontalHeaderLabels(columns)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setAlternatingRowColors(True)
    widget.setShowGrid(True)
    widget.setWordWrap(False)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(38)
    header = widget.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    for column in stretch_columns:
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
    return widget


def fill_table(widget, rows, numeric_columns=(), status_column=None):
    widget.clearSelection()
    widget.setRowCount(len(rows))
    for column in range(widget.columnCount()):
        side = Qt.AlignmentFlag.AlignRight if column in numeric_columns else Qt.AlignmentFlag.AlignLeft
        widget.horizontalHeaderItem(column).setTextAlignment(side | Qt.AlignmentFlag.AlignVCenter)
    for row_number, row in enumerate(rows):
        for column, value in enumerate(row):
            text = str(value)
            item = QTableWidgetItem(text)
            item.setToolTip(f"<qt>{escape(text)}</qt>")
            if column in numeric_columns:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if column == status_column:
                style_status_cell(item)
            widget.setItem(row_number, column, item)


def selected_row(widget):
    indexes = widget.selectionModel().selectedRows()
    return indexes[0].row() if indexes else -1


def money(value):
    return "$" + f"{value:,.2f}"


def local_date(value):
    if not value:
        return "—"
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return value
    return stamp.strftime("%b %d, %Y · %H:%M")


def text_browser():
    widget = QTextBrowser()
    widget.setOpenLinks(False)
    widget.setOpenExternalLinks(False)
    return widget


def invoice_browser():
    widget = text_browser()
    widget.setObjectName("invoicePreview")
    return widget


def show_error(parent, title, text):
    message = QMessageBox(parent)
    message.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    message.setIcon(QMessageBox.Icon.Warning)
    message.setWindowTitle(title)
    message.setTextFormat(Qt.TextFormat.PlainText)
    message.setText(text)
    message.setStandardButtons(QMessageBox.StandardButton.Ok)
    message.open()


def create_application():
    application = QApplication(sys.argv)
    application.setApplicationName("Online Bookstore")
    apply_modern_theme(application)
    return application


def open_saved_bill(parent, bill_path):
    bills = (PROJECT_ROOT / "bills").resolve()
    path = (PROJECT_ROOT / Path(bill_path)).resolve()
    if not path.is_relative_to(bills) or not path.is_file():
        show_error(parent, "Invoice unavailable", "The saved bill could not be found in the bills folder.")
        return
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        show_error(parent, "Invoice unavailable", "The bill could not be opened in the default browser.")


class ReviewDialog(QDialog):
    submit_requested = pyqtSignal(int, str)

    def __init__(self, book, parent=None):
        super().__init__(parent)
        self.book_id = book["id"]
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Book reviews")
        self.resize(560, 490)
        layout = QVBoxLayout(self)
        title = label(book["title"], "heading")
        title.setWordWrap(True)
        layout.addWidget(title)
        self.reviews = text_browser()
        layout.addWidget(self.reviews, 1)
        self.set_reviews(book["reviews"])

        form = QFormLayout()
        self.rating = QSpinBox()
        self.rating.setRange(1, 5)
        self.rating.setValue(5)
        self.rating.setSuffix(" ★")
        self.comment = QPlainTextEdit()
        self.comment.setPlaceholderText("Write a comment")
        self.comment.setFixedHeight(78)
        form.addRow("Rating", self.rating)
        form.addRow("Comment", self.comment)
        layout.addLayout(form)
        self.notice = label("", "muted")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Close", self.close))
        self.submit_button = button("Submit review", self._submit, "primary")
        actions.addWidget(self.submit_button)
        layout.addLayout(actions)

    def _submit(self):
        comment = self.comment.toPlainText().strip()
        if not comment:
            self.notice.setText("Enter a comment before submitting.")
            self.comment.setFocus()
            return
        self.submit_requested.emit(self.rating.value(), comment)

    def set_reviews(self, reviews):
        parts = []
        for review in reviews:
            stars = "★" * review["rating"]
            author = escape(review["username"])
            date = escape(local_date(review.get("created_at")))
            comment = escape(review["comment"]).replace("\n", "<br>")
            parts.append(f"<p><b>{author}</b> &nbsp; {stars}<br><small>{date}</small></p><p>{comment}</p><hr>")
        self.reviews.setHtml("".join(parts) if parts else "<p>No reviews yet.</p>")

    def set_sending(self, sending):
        self.submit_button.setEnabled(not sending)
        self.rating.setEnabled(not sending)
        self.comment.setEnabled(not sending)


class InvoiceDialog(QDialog):
    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"Invoice · Order {order['order_id']}")
        self.resize(830, 630)
        self.bill_path = order["bill_html_path"]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(label(f"Order {order['order_id']} invoice", "heading"))
        form = QFormLayout()
        path_label = label(self.bill_path)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setWordWrap(True)
        form.addRow("Saved bill", path_label)
        status = {
            "queued": "Queued for delivery",
            "skipped": "Skipped · Email is unconfigured",
            "failed": "Could not queue delivery",
        }.get(order["email_status"], order["email_status"])
        form.addRow("Email notification", label(status))
        layout.addLayout(form)
        self.preview = invoice_browser()
        style_invoice_preview(self.preview, order["bill_html_content"])
        layout.addWidget(self.preview, 1)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Close", self.close))
        actions.addWidget(button("Open Bill in Browser / Print", self.open_bill, "primary"))
        layout.addLayout(actions)

    def open_bill(self):
        open_saved_bill(self, self.bill_path)

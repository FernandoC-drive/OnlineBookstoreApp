"""Visual styles and table accents shared by all bookstore windows."""

from pathlib import Path
import re

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFontDatabase, QFontMetrics, QPainter, QPalette
from PyQt6.QtWidgets import QApplication, QComboBox, QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem


ICONS = str(Path(__file__).resolve().parent / "icons").replace("\\", "/")
STYLESHEET = """
QMainWindow, QDialog, QMessageBox, QWidget#appPage {
    background: #0F172A;
}
QFrame#surface, QFrame#topBar {
    background: #1E293B; border: 1px solid #334155; border-radius: 8px;
}
QFrame#portalCard[role="customer"]:hover { border-color: #3B82F6; }
QFrame#portalCard[role="manager"]:hover { border-color: #818CF8; }
QFrame#portalCard {
    background: #1E293B; border: 1px solid #334155; border-radius: 8px;
}
QFrame#surface[kpi="orders"] { border-top: 3px solid #60A5FA; }
QFrame#surface[kpi="revenue"] { border-top: 3px solid #A5B4FC; }
QFrame#surface[kpi="paid"] { border-top: 3px solid #34D399; }
QLabel#brand { font-size: 24px; font-weight: 700; }
QLabel#hero { font-size: 30px; font-weight: 700; }
QLabel#heading { font-size: 19px; font-weight: 700; }
QLabel#muted { color: #94A3B8; }
QLabel#total { font-size: 27px; font-weight: 700; }
QLabel#kpiValue { font-size: 32px; font-weight: 700; }
QLabel#pill {
    padding: 4px 10px; border: 1px solid #475569; border-radius: 10px;
    background: #1E293B; color: #CBD5E1; font-weight: 600;
}
QLabel#pill[tone="customer"] { background: #172D50; border-color: #345985; color: #BFDBFE; }
QLabel#pill[tone="manager"] { background: #312E54; border-color: #5A4C70; color: #FBBF24; }
QLabel#pill[tone="online"] { background: #123832; border-color: #256257; color: #6EE7B7; }
QLabel#pill[tone="offline"] { background: #42252E; border-color: #7F3946; color: #FCA5A5; }
QPushButton {
    background: #25334A; color: #F8FAFC; border: 1px solid #475569;
    border-radius: 6px; padding: 7px 13px; font-weight: 600;
}
QPushButton:hover { background: #334155; border-color: #64748B; }
QPushButton[variant="primary"] { background: #3B82F6; color: #020617; border-color: #3B82F6; }
QPushButton[variant="primary"]:hover, QPushButton[variant="primary"]:pressed {
    background: #2563EB; color: #FFFFFF; border-color: #2563EB;
}
QPushButton[variant="success"] { background: #10B981; color: #022C22; border-color: #10B981; }
QPushButton[variant="success"]:hover, QPushButton[variant="success"]:pressed {
    background: #059669; color: #020617; border-color: #059669;
}
QPushButton[variant="danger"] { background: #EF4444; color: #020617; border-color: #EF4444; }
QPushButton[variant="danger"]:hover, QPushButton[variant="danger"]:pressed {
    background: #DC2626; color: #FFFFFF; border-color: #DC2626;
}
QPushButton:focus, QPushButton[variant]:focus { border-color: #BFDBFE; }
QPushButton:disabled, QPushButton[variant]:disabled {
    color: #94A3B8; background: #1E293B; border-color: #334155;
}
QLineEdit, QComboBox, QAbstractSpinBox, QTextEdit, QPlainTextEdit {
    background: #0F172A; color: #F8FAFC; border: 1px solid #334155;
    border-radius: 6px; padding: 7px 9px;
    selection-background-color: #1D4ED8; selection-color: #F8FAFC;
}
QAbstractSpinBox { padding-right: 28px; }
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #3B82F6;
}
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled, QPlainTextEdit:disabled {
    color: #94A3B8; background: #1E293B;
}
QComboBox { min-height: 34px; padding: 0 34px 0 9px; }
QComboBox:enabled:hover { border-color: #3B82F6; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 28px; border-left: 1px solid #334155;
    border-top-right-radius: 5px; border-bottom-right-radius: 5px;
    background: #1E293B;
}
QComboBox::drop-down:hover { background: #334155; }
QComboBox::down-arrow { image: url("@icons@/chevron-down.svg"); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: #1E293B; color: #F8FAFC; selection-background-color: #2563EB;
    selection-color: #F8FAFC; border: 1px solid #475569; padding: 4px;
    outline: 0;
}
QComboBox QAbstractItemView::item { min-height: 32px; padding: 0 8px; }
QComboBox QAbstractItemView::item:hover { background: #334155; }
QComboBox QAbstractItemView::item:selected { background: #2563EB; color: #F8FAFC; }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: padding; width: 24px;
    background: #1E293B; border-left: 1px solid #334155;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-position: top right; border-top-right-radius: 5px; border-bottom: 1px solid #334155;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-position: bottom right; border-bottom-right-radius: 5px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #334155; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("@icons@/chevron-up.svg"); width: 11px; height: 11px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("@icons@/chevron-down.svg"); width: 11px; height: 11px;
}
QTextBrowser#invoicePreview {
    background-color: #FFFFFF; color: #111111; border: 1px solid #CBD5E1;
    border-radius: 6px; padding: 14px;
    selection-background-color: #DBEAFE; selection-color: #111111;
}
QTabWidget::pane { border: 0; }
QTabBar::tab {
    background: #0F172A; color: #94A3B8; border-bottom: 2px solid #334155;
    padding: 10px 16px; margin-right: 4px;
}
QTabBar::tab:hover { background: #25334A; color: #F8FAFC; }
QTabBar::tab:selected {
    background: #1E293B; color: #F8FAFC; border-bottom: 2px solid #3B82F6; font-weight: 700;
}
QTableWidget {
    background: #0F172A; alternate-background-color: #1E293B; color: #F8FAFC;
    selection-background-color: #1D4ED8; selection-color: #F8FAFC;
    gridline-color: #1E293B; border: 1px solid #334155; border-radius: 6px;
}
QTableWidget::item { padding: 0 7px; }
QHeaderView::section {
    background: #1E293B; color: #94A3B8; font-weight: 700;
    border: none; border-bottom: 1px solid #334155; padding: 9px 7px;
}
QTableCornerButton::section { background: #1E293B; border: none; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #334155; }
QScrollBar:vertical { background: #0F172A; width: 10px; margin: 0; }
QScrollBar:horizontal { background: #0F172A; height: 10px; margin: 0; }
QScrollBar::handle { background: #475569; border: 2px solid #0F172A; border-radius: 5px; }
QScrollBar::handle:vertical { min-height: 24px; }
QScrollBar::handle:horizontal { min-width: 24px; }
QScrollBar::handle:hover { background: #64748B; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: #1E293B; }
QCalendarWidget QToolButton { color: #F8FAFC; padding: 4px; }
QStatusBar { background: #0F172A; color: #94A3B8; }
QStatusBar::item { border: 0; }
QProgressBar { border: 0; background: #334155; border-radius: 4px; }
QProgressBar::chunk { background: #3B82F6; border-radius: 4px; }
QToolTip { background: #1E293B; color: #F8FAFC; border: 1px solid #475569; padding: 4px; }
""".replace("@icons@", ICONS)


def apply_modern_theme(app):
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        "Window": "#0F172A", "WindowText": "#F8FAFC", "Base": "#0F172A",
        "AlternateBase": "#1E293B", "Text": "#F8FAFC", "Button": "#1E293B",
        "ButtonText": "#F8FAFC", "Light": "#475569", "Mid": "#334155",
        "Dark": "#0F172A", "Shadow": "#020617", "Highlight": "#1D4ED8",
        "HighlightedText": "#F8FAFC", "PlaceholderText": "#94A3B8",
        "ToolTipBase": "#1E293B", "ToolTipText": "#F8FAFC", "Link": "#93C5FD",
    }
    for role, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#94A3B8"))
    app.setPalette(palette)

    font = app.font()
    available = set(QFontDatabase.families())
    for family in ("Inter", "DM Sans", "Roboto", "Segoe UI", "Arial"):
        if family in available:
            font.setFamily(family)
            break
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)


def style_pill(label, tone):
    label.setObjectName("pill")
    label.setProperty("tone", tone)
    label.style().unpolish(label)
    label.style().polish(label)


def style_status_cell(item):
    color = {"Pending": "#FBBF24", "Paid": "#34D399"}.get(item.text())
    if color:
        item.setForeground(QColor(color))
        font = item.font()
        font.setBold(True)
        item.setFont(font)


class _DropdownDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(32, size.height()))
        return size


class ModernComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        popup = QListView(self)
        popup.setItemDelegate(_DropdownDelegate(popup))
        popup.setMouseTracking(True)
        self.setView(popup)


class _TransactionBadgeDelegate(QStyledItemDelegate):
    colors = {"BUY": ("#17365F", "#BFDBFE"), "RENT": ("#39316D", "#DDD6FE")}

    def paint(self, painter, option, index):
        text = index.data()
        if text not in self.colors:
            super().paint(painter, option, index)
            return
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)
        cell.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, cell, painter, option.widget)
        font = option.font
        font.setBold(True)
        width = QFontMetrics(font).horizontalAdvance(text) + 14
        rect = QRectF(0, 0, width, 23)
        rect.moveCenter(QRectF(option.rect).center())
        background, foreground = self.colors[text]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor(foreground))
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setWidth(max(64, size.width()))
        return size


def style_transaction_badges(table, column):
    table.setItemDelegateForColumn(column, _TransactionBadgeDelegate(table))


def style_invoice_preview(browser, html):
    # Older bill documents can still carry the previous template's colors.
    colors = {
        "#f3f5f7": "#ffffff", "#fff": "#ffffff", "#16232d": "#111111",
        "#485767": "#111111", "#cad1d9": "#111111",
    }

    def recolor(style_block):
        return re.sub(r"#[0-9a-f]{3,8}\b", lambda color: colors.get(color[0].lower(), color[0]),
                      style_block[0], flags=re.IGNORECASE)

    browser.setHtml(re.sub(r"<style\b[^>]*>.*?</style\s*>", recolor, html, flags=re.IGNORECASE | re.DOTALL))

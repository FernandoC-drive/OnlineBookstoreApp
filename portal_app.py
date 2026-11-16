"""Desktop launcher for the independent customer and manager applications."""

import sys
from urllib.parse import urlsplit

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from desktop_common.api import ApiClient, PROJECT_ROOT
from desktop_common.widgets import button, create_application, label, show_error, surface
from shared_ui.theme import style_pill


SERVICES = {
    "java": ("Java User Service", "/api/users/profile"),
    "flask": ("Flask Book/Order Service", "/api/books"),
}
HEALTH_PROBE_TOKEN = "00000000-0000-0000-0000-000000000000"


class PortalWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Online Bookstore System")
        self.setMinimumSize(690, 420)
        self.resize(980, 490)
        self.api = ApiClient(self)
        self.probes_in_flight = set()
        self.service_pills = {}
        self.launch_buttons = {}

        page = QWidget()
        page.setObjectName("appPage")
        self.setCentralWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(18)
        layout.addWidget(label("Online Bookstore System", "hero"))

        services = QHBoxLayout()
        services.setSpacing(10)
        for key, (name, _) in SERVICES.items():
            pill = label()
            self.service_pills[key] = pill
            self.show_status(key, name, "Checking", "neutral")
            services.addWidget(pill)
        services.addStretch()
        layout.addLayout(services)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(self.workspace_card(
            "customer", "Customer Storefront",
            "Browse and review books, buy or rent titles, and find invoices in your order history.",
            "Launch Customer App",
        ), 1)
        cards.addWidget(self.workspace_card(
            "manager", "Manager Operations Portal",
            "Manage customer orders and payments, update inventory, and generate sales reports.",
            "Launch Manager App",
        ), 1)
        layout.addLayout(cards, 1)

        footer = QHBoxLayout()
        footer.addWidget(label("Demo accounts", "muted"))
        footer.addStretch()
        for credentials in ("customer1 / password123", "manager1 / admin123"):
            demo = label(credentials, "muted")
            demo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            footer.addWidget(demo)
        footer.setSpacing(16)
        layout.addLayout(footer)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.check_services)
        self.timer.start()
        self.check_services()

    def workspace_card(self, role, title, description, action):
        card, contents = surface()
        card.setObjectName("portalCard")
        card.setProperty("role", role)
        contents.setContentsMargins(24, 22, 24, 22)
        contents.setSpacing(12)
        badge = label(role.upper())
        style_pill(badge, role)
        contents.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        heading = label(title, "heading")
        heading.setWordWrap(True)
        contents.addWidget(heading)
        summary = label(description, "muted")
        summary.setWordWrap(True)
        contents.addWidget(summary)
        contents.addStretch()
        launch = button(action, lambda: self.launch(role), "primary")
        launch.setMinimumHeight(44)
        contents.addWidget(launch)
        self.launch_buttons[role] = launch
        return card

    def show_status(self, key, name, state, tone):
        pill = self.service_pills[key]
        endpoint = urlsplit(self.api.urls[key]).netloc
        pill.setText(f"{name} · {endpoint} · {state}")
        style_pill(pill, tone)

    def check_services(self):
        for key, (_, path) in SERVICES.items():
            if key not in self.probes_in_flight:
                self.probes_in_flight.add(key)
                self.api.request(
                    key, "GET", path, lambda result, service=key: self.probe_finished(service, result),
                    token=HEALTH_PROBE_TOKEN,
                )

    def probe_finished(self, key, result):
        self.probes_in_flight.discard(key)
        responding = result.status == 401 and result.message == "Invalid or missing session token"
        self.show_status(
            key, SERVICES[key][0], "Online" if responding else "Unavailable", "online" if responding else "offline",
        )

    def launch(self, role):
        script = PROJECT_ROOT / f"client-{role}-qt" / f"{role}_app.py"
        started, _pid = QProcess.startDetached(sys.executable, [str(script)], str(PROJECT_ROOT))
        if not started:
            show_error(self, "Launch failed", f"The {role} app could not be started.")


def main():
    application = create_application()
    window = PortalWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    sys.exit(main())

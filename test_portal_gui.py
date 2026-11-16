"""Offscreen checks for live service indicators and independent client launches."""

import os
import sys
from threading import get_ident
from time import monotonic
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt" and "SystemRoot" in os.environ:
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ["SystemRoot"], "Fonts"))

from PyQt6.QtGui import QPalette
from PyQt6.QtTest import QTest

from desktop_common.api import ApiResult, ApiWorker, PROJECT_ROOT
from desktop_common.widgets import create_application
from portal_app import PortalWindow


class PortalSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = create_application()

    def test_live_status_refresh_and_separate_entry_points(self):
        main_thread = get_ident()
        worker_threads = []
        send = ApiWorker._send

        def observe(worker):
            worker_threads.append(get_ident())
            return send(worker)

        with patch.object(ApiWorker, "_send", observe):
            window = PortalWindow()
            window.show()
            self.addCleanup(window.close)
            self.assertEqual(window.windowTitle(), "Online Bookstore System")
            self.assertEqual(self.application.palette().color(QPalette.ColorRole.Window).name(), "#0f172a")
            self.wait_for_probes(window)
            self.assertTrue(worker_threads)
            self.assertTrue(all(thread != main_thread for thread in worker_threads))
            self.assertTrue(all(pill.property("tone") == "online" for pill in window.service_pills.values()))

            with patch.object(ApiWorker, "_send", return_value=ApiResult(0, message="Unreachable")):
                window.check_services()
                self.wait_for_probes(window)
            self.assertTrue(all(pill.property("tone") == "offline" for pill in window.service_pills.values()))
            window.check_services()
            self.wait_for_probes(window)
            self.assertTrue(all(pill.property("tone") == "online" for pill in window.service_pills.values()))

        with patch("portal_app.QProcess.startDetached", return_value=(True, 1234)) as launch:
            for role in ("customer", "manager"):
                window.launch_buttons[role].click()
                script = PROJECT_ROOT / f"client-{role}-qt" / f"{role}_app.py"
                launch.assert_called_with(sys.executable, [str(script)], str(PROJECT_ROOT))
            self.assertEqual(launch.call_count, 2)

    def wait_for_probes(self, window):
        deadline = monotonic() + 12
        while window.probes_in_flight and monotonic() < deadline:
            QTest.qWait(20)
        self.assertFalse(window.probes_in_flight, "Portal service checks did not complete")


if __name__ == "__main__":
    unittest.main(verbosity=2)

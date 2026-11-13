"""Run service requests on Qt's thread pool and deliver results on the GUI thread."""

from dataclasses import dataclass
import logging
import os
from pathlib import Path

from dotenv import dotenv_values
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal, pyqtSlot
import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ApiResult:
    status: int
    data: object = None
    message: str = ""

    @property
    def ok(self):
        return 200 <= self.status < 300 and not self.message


class WorkerSignals(QObject):
    finished = pyqtSignal(int, object)


class ApiWorker(QRunnable):
    def __init__(self, request_id, method, url, *, token=None, payload=None, params=None):
        super().__init__()
        self.signals = WorkerSignals()
        self.request_id = request_id
        self.method = method
        self.url = url
        self.token = token
        self.payload = payload
        self.params = params

    def run(self):
        try:
            result = self._send()
        except requests.Timeout:
            result = ApiResult(0, message="The service did not respond in time.")
        except requests.RequestException:
            result = ApiResult(0, message="The service could not be reached.")
        except Exception:
            logging.exception("Unexpected failure while making a bookstore request.")
            result = ApiResult(0, message="The request could not be completed.")
        self.signals.finished.emit(self.request_id, result)

    def _send(self):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(
                self.method, self.url, headers=headers, json=self.payload, params=self.params,
                timeout=(3, 8), allow_redirects=False,
            )
            try:
                data = response.json()
            except ValueError:
                data = None

            if 200 <= response.status_code < 300:
                if isinstance(data, (dict, list)):
                    return ApiResult(response.status_code, data)
                return ApiResult(response.status_code, message="The service returned an invalid response.")
            message = data.get("message") if isinstance(data, dict) else None
            if not isinstance(message, str) or not message.strip():
                message = f"Request failed (HTTP {response.status_code})."
            return ApiResult(response.status_code, message=message)


class ApiClient(QObject):
    pending_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        settings = {**dotenv_values(PROJECT_ROOT / ".env"), **os.environ}
        self.urls = {
            "java": f"http://127.0.0.1:{settings.get('USER_SERVICE_PORT', '8001')}",
            "flask": f"http://127.0.0.1:{settings.get('FLASK_SERVICE_PORT', '8002')}",
        }
        self.pool = QThreadPool.globalInstance()
        self._next_id = 0
        self._pending = {}

    def request(self, service, method, path, finished, **kwargs):
        self._next_id += 1
        request_id = self._next_id
        worker = ApiWorker(request_id, method, self.urls[service] + path, **kwargs)
        worker.signals.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        self._pending[request_id] = (worker, finished)
        self.pending_changed.emit(len(self._pending))
        self.pool.start(worker)

    @pyqtSlot(int, object)
    def _finished(self, request_id, result):
        _worker, finished = self._pending.pop(request_id)
        self.pending_changed.emit(len(self._pending))
        finished(result)

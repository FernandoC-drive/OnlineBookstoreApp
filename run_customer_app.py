"""Start the local bookstore services as needed, then open the customer app."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
USER_SERVICE = ROOT / "user-service-java"
JAR = USER_SERVICE / "target" / "user-service.jar"
LOGS = ROOT / "db-data" / "customer-launcher"
HTTP = build_opener(ProxyHandler({}))


def healthy(url):
    # A well-formed, unissued token exercises the database-backed auth route without creating a session.
    request = Request(url, headers={"Authorization": "Bearer 00000000-0000-0000-0000-000000000000"})
    try:
        with HTTP.open(request, timeout=1.5):
            return False
    except HTTPError as error:
        with error:
            if error.code != 401:
                return False
            try:
                data = json.load(error)
            except (ValueError, OSError):
                return False
            return isinstance(data, dict) and data.get("message") == "Invalid or missing session token"
    except (URLError, TimeoutError, OSError):
        return False


def java_command():
    java = shutil.which("java")
    if not java:
        raise RuntimeError("Java was not found on PATH. Install a Java 17 or newer JDK.")
    if not JAR.is_file():
        maven = shutil.which("mvn")
        if not maven and os.name == "nt":
            install_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Apache" / "Maven"
            maven = next(iter(sorted(install_dir.glob("apache-maven-*/bin/mvn.cmd"), reverse=True)), None)
        if not maven:
            raise RuntimeError(f"Maven was not found. Build {USER_SERVICE / 'pom.xml'} before launching.")
        print("Building the Java User Service…", flush=True)
        subprocess.run([str(maven), "-B", "-f", str(USER_SERVICE / "pom.xml"), "package"], cwd=ROOT, check=True)
    return [java, "-jar", str(JAR)]


def start_service(command, log_path):
    options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt" else {"start_new_session": True}
    )
    with log_path.open("ab") as log:
        return subprocess.Popen(
            command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **options
        )


def ensure_services(settings, python):
    services = (
        ("Java User Service", f"http://127.0.0.1:{settings.get('USER_SERVICE_PORT', '8001')}/api/users/profile",
         java_command, LOGS / "java.log"),
        ("Flask Book and Order Service", f"http://127.0.0.1:{settings.get('FLASK_SERVICE_PORT', '8002')}/api/books",
         lambda: [python, "-u", str(ROOT / "book-order-flask" / "app.py")], LOGS / "flask.log"),
    )
    started = {}
    for name, url, command, log in services:
        if healthy(url):
            continue
        LOGS.mkdir(parents=True, exist_ok=True)
        print(f"Starting {name}…", flush=True)
        started[name] = start_service(command(), log)

    waiting = {name: (url, log) for name, url, _, log in services if name in started}
    deadline = monotonic() + 45
    while waiting and monotonic() < deadline:
        for name, (url, log) in list(waiting.items()):
            if healthy(url):
                waiting.pop(name)
            elif started[name].poll() is not None:
                raise RuntimeError(f"{name} exited during startup. See {log}")
        if waiting:
            sleep(0.25)
    if waiting:
        failed = ", ".join(f"{name} ({log})" for name, (_, log) in waiting.items())
        raise RuntimeError(f"Services did not become ready within 45 seconds. Check {failed}")
    return started


def launch_client(client_name):
    client_dir = ROOT / f"client-{client_name}-qt"
    venv_python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_python.is_file() and Path(sys.prefix).resolve() != VENV.resolve():
        launcher = ROOT / f"run_{client_name}_app.py"
        return subprocess.call([str(venv_python), str(launcher)], cwd=ROOT)

    try:
        from dotenv import dotenv_values
    except ImportError:
        print(f"Install the desktop requirements from {client_dir / 'requirements.txt'}.",
              file=sys.stderr)
        return 1

    settings = {**dotenv_values(ROOT / ".env"), **os.environ}
    try:
        ensure_services(settings, sys.executable)
        app = client_dir / f"{client_name}_app.py"
        return subprocess.call([sys.executable, str(app)], cwd=ROOT)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Could not launch the {client_name} app. {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(launch_client("customer"))

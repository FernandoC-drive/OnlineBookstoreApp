"""Run integration checks against a Java User Service backed by the Phase 1 data."""

import argparse
from datetime import datetime
import json
import sys
from time import perf_counter
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4


class UserServiceTests(unittest.TestCase):
    base_url = "http://127.0.0.1:8001"
    request_times = []

    def request(self, method, endpoint, status, *, payload=None, token=None):
        url = f"{self.base_url}/api/users/{endpoint}"
        request = Request(url, method=method)
        if payload is not None:
            request.data = json.dumps(payload).encode("utf-8")
            request.add_header("Content-Type", "application/json")
        if token is not None:
            request.add_header("Authorization", f"Bearer {token}")

        started = perf_counter()
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        except URLError as error:
            self.fail(f"Could not reach {url}: {error.reason}")

        with response:
            body = json.load(response)
            self.request_times.append((perf_counter() - started, f"{method} /api/users/{endpoint}"))
            expected = status if isinstance(status, tuple) else (status,)
            self.assertIn(response.status, expected, f"{method} {url} returned {response.status}: {body}")
            self.assertEqual(response.headers.get_content_type(), "application/json")
        return body

    def login(self, username, password, role):
        session = self.request("POST", "login", 200, payload={"username": username, "password": password})
        token = session["token"]
        self.addCleanup(self.request, "POST", "logout", (200, 401), token=token)
        self.assertEqual(set(session), {"token", "user_id", "username", "email", "role"})
        self.assertEqual(session["username"], username)
        self.assertEqual(session["role"], role)
        self.assertEqual(UUID(token).version, 4)
        self.assertIs(type(session["user_id"]), int)
        self.assertGreater(session["user_id"], 0)
        return session

    def check_profile(self, session):
        profile = self.request("GET", "profile", 200, token=session["token"])
        self.assertEqual(set(profile), {"user_id", "username", "email", "role", "created_at"})
        for field in ("user_id", "username", "email", "role"):
            self.assertEqual(profile[field], session[field])
        self.assertIsNotNone(datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00")).tzinfo)

    def test_seeded_accounts_and_profiles(self):
        accounts = (
            ("customer1", "password123", "CUSTOMER", "customer1@example.com"),
            ("manager1", "admin123", "MANAGER", "manager1@example.com"),
        )
        for username, password, role, email in accounts:
            with self.subTest(username=username):
                session = self.login(username, password, role)
                self.assertEqual(session["email"], email)
                self.check_profile(session)

    def test_invalid_credentials(self):
        for username in ("customer1", f"missing_{uuid4().hex}"):
            with self.subTest(username=username):
                self.request("POST", "login", 401, payload={"username": username, "password": "wrong"})

    def test_register_customer_and_reject_duplicates(self):
        username = f"phase2_test_{uuid4().hex}"
        email = f"{username}@example.com"
        password = "test-password123"
        account = {"username": username, "email": email, "password": password}
        registration = self.request("POST", "register", 201, payload=account)
        self.assertEqual(registration, {
            "message": "User registered successfully",
            "user_id": registration["user_id"],
        })

        session = self.login(username, password, "CUSTOMER")
        self.assertEqual(session["user_id"], registration["user_id"])
        self.assertEqual(session["email"], email)
        self.check_profile(session)

        self.request("POST", "register", 409, payload={**account, "email": f"other_{email}"})
        self.request("POST", "register", 409, payload={**account, "username": f"other_{username}"})

    def test_registration_validation(self):
        account = {"username": "validation_test", "email": "validation@example.com", "password": "valid-password"}
        for field, invalid in (("username", " "), ("email", "bad-email"), ("password", "")):
            with self.subTest(field=field):
                self.request("POST", "register", 400, payload={**account, field: invalid})

    def test_logout_revokes_token(self):
        session = self.login("customer1", "password123", "CUSTOMER")
        token = session["token"]
        self.check_profile(session)
        self.assertEqual(
            self.request("POST", "logout", 200, token=token),
            {"message": "Logged out successfully"},
        )
        self.request("GET", "profile", 401, token=token)
        self.request("POST", "logout", 401, token=token)

    def test_bearer_token_required(self):
        unknown_token = str(uuid4())
        for method, endpoint in (("GET", "profile"), ("POST", "logout")):
            with self.subTest(endpoint=endpoint):
                self.request(method, endpoint, 401)
                self.request(method, endpoint, 401, token=unknown_token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=UserServiceTests.base_url)
    args = parser.parse_args()
    UserServiceTests.base_url = args.base_url.rstrip("/")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(UserServiceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if UserServiceTests.request_times:
        slowest, endpoint = max(UserServiceTests.request_times)
        print(f"Slowest of {len(UserServiceTests.request_times)} requests: {slowest * 1000:.0f} ms ({endpoint})")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

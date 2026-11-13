"""Shared configuration, MySQL access, and HTTP validation."""

from datetime import timezone
from functools import wraps
import os
from pathlib import Path
import re

from dotenv import dotenv_values
from flask import current_app, g, request
import mysql.connector


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BEARER = re.compile(r"(?i:Bearer) +([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def load_settings():
    cwd = Path.cwd()
    candidates = (cwd / ".env", cwd.parent / ".env", PROJECT_ROOT / ".env")
    env_file = next((path for path in candidates if path.is_file()), None)
    values = dotenv_values(env_file) if env_file else {}
    return {**values, **os.environ}


def connect_mysql():
    return mysql.connector.connect(**current_app.config["MYSQL"])


def mysql_connection():
    if "mysql" not in g:
        g.mysql = current_app.extensions["mysql_pool"].get_connection()
    return g.mysql


def close_mysql(_error):
    connection = g.pop("mysql", None)
    if connection is not None:
        try:
            connection.close()
        except mysql.connector.Error:
            current_app.logger.warning("Could not close the MySQL connection.", exc_info=True)


def require_auth(role=None):
    def decorate(endpoint):
        @wraps(endpoint)
        def authenticated(*args, **kwargs):
            header = request.headers.get("Authorization", "").strip()
            token = BEARER.fullmatch(header)
            if token is None:
                raise ApiError(401, "Invalid or missing session token")

            with mysql_connection().cursor(dictionary=True) as cursor:
                cursor.execute(
                    """
                    SELECT s.user_id, u.username, u.email, s.role
                    FROM sessions s JOIN users u ON u.id = s.user_id
                    WHERE s.token = %s
                    """,
                    (token[1],),
                )
                user = cursor.fetchone()
            if user is None:
                raise ApiError(401, "Invalid or missing session token")
            if role is not None and user["role"] != role:
                raise ApiError(403, "Forbidden for this account role")

            g.user = user
            return endpoint(*args, **kwargs)

        return authenticated

    return decorate


def json_object():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(400, "Expected a JSON object")
    return payload


def utc_timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

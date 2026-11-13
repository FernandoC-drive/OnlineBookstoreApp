"""Local Flask book and order service."""

import logging
from threading import Lock

from flask import Flask, current_app, jsonify
from mysql.connector import Error as MySQLError
from mysql.connector.pooling import MySQLConnectionPool
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from catalog import catalog
from orders import orders
from service import ApiError, PROJECT_ROOT, close_mysql, load_settings


def create_app():
    settings = load_settings()
    app = Flask(__name__)
    bills_dir = PROJECT_ROOT / "bills"
    bills_dir.mkdir(exist_ok=True)
    app.config.update(
        PORT=int(settings.get("FLASK_SERVICE_PORT", "8002")),
        BILLS_DIR=bills_dir,
        MYSQL={
            "host": settings.get("MYSQL_HOST", "127.0.0.1"),
            "port": int(settings.get("MYSQL_PORT", "3306")),
            "user": settings.get("MYSQL_USER", "root"),
            "password": settings.get("MYSQL_PASSWORD", ""),
            "database": settings.get("MYSQL_DATABASE", "bookstore_db"),
            "use_pure": True,
            "autocommit": True,
            "time_zone": "+00:00",
            "connection_timeout": 3,
            "read_timeout": 5,
            "write_timeout": 5,
        },
        SMTP={
            "host": settings.get("SMTP_HOST", ""),
            "port": int(settings.get("SMTP_PORT") or "587"),
            "user": settings.get("SMTP_USER", ""),
            "password": settings.get("SMTP_PASSWORD", ""),
            "sender": settings.get("SMTP_FROM") or "noreply@bookstore.local",
        },
    )
    mongo = MongoClient(
        settings.get("MONGO_URI", "mongodb://127.0.0.1:27017/"),
        serverSelectionTimeoutMS=3000,
        socketTimeoutMS=5000,
    )
    app.extensions["mysql_pool"] = MySQLConnectionPool(
        pool_name="bookstore_flask", pool_size=8, **app.config["MYSQL"]
    )
    app.extensions["books"] = mongo[settings.get("MONGO_DB", "bookstore_mongo")].books
    app.extensions["inventory_lock"] = Lock()
    app.register_blueprint(catalog)
    app.register_blueprint(orders)
    app.teardown_appcontext(close_mysql)
    app.register_error_handler(ApiError, api_error)
    app.register_error_handler(MySQLError, storage_error)
    app.register_error_handler(PyMongoError, storage_error)
    return app


def api_error(error):
    response = jsonify(message=str(error))
    if error.status == 401:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response, error.status


def storage_error(error):
    current_app.logger.error("Database request failed.", exc_info=error)
    return {"message": "Database temporarily unavailable"}, 503


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    app.run(host="127.0.0.1", port=app.config["PORT"], threaded=True, load_dotenv=False)

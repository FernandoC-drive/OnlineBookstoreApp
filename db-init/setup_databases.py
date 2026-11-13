"""Initialize and verify the local MySQL database and MongoDB catalog."""

from hashlib import sha256
from pathlib import Path
import sys

import bcrypt
from bson import ObjectId
from dotenv import dotenv_values
import mysql.connector
from pymongo import MongoClient
from pymongo.errors import PyMongoError


INIT_DIR = Path(__file__).resolve().parent
TABLES = {"users", "sessions", "orders", "order_items"}
ACCOUNTS = (
    ("customer1", "customer1@example.com", b"password123", "CUSTOMER"),
    ("manager1", "manager1@example.com", b"admin123", "MANAGER"),
)

# Title, author, buy price, rent price, available copies, review rating and comment.
BOOKS = (
    ("Clean Code", "Robert C. Martin", 35.99, 9.99, 12, 5,
     "Essential software engineering book."),
    ("Kindred", "Octavia E. Butler", 17.99, 4.49, 8, 5,
     "The time travel makes the history feel immediate."),
    ("Braiding Sweetgrass", "Robin Wall Kimmerer", 20.00, 5.49, 10, 5,
     "I enjoyed how the author ties botany to personal stories."),
    ("The Left Hand of Darkness", "Ursula K. Le Guin", 16.99, 4.49, 6, 4,
     "The journey across the ice was my favorite part."),
    ("The House on Mango Street", "Sandra Cisneros", 13.99, 3.49, 15, 5,
     "The short vignettes say a lot in very few words."),
    ("The Remains of the Day", "Kazuo Ishiguro", 16.00, 4.49, 7, 4,
     "The narrator's restraint made the ending hit harder."),
    ("The Joy of x", "Steven Strogatz", 18.99, 4.99, 9, 4,
     "The everyday examples made the math approachable."),
    ("Salt, Fat, Acid, Heat", "Samin Nosrat", 37.50, 8.99, 5, 5,
     "The lessons on seasoning helped me cook without a recipe."),
    ("Persepolis", "Marjane Satrapi", 19.99, 4.99, 11, 5,
     "The black-and-white panels capture both humor and fear."),
    ("The Secret History", "Donna Tartt", 18.00, 4.99, 4, 4,
     "The opening gives away the crime, but I still wanted to know why."),
    ("The Boy Who Harnessed the Wind", "William Kamkwamba and Bryan Mealer",
     17.00, 4.49, 13, 5, "The windmill project was my favorite part of the memoir."),
    ("The Hobbit", "J. R. R. Tolkien", 15.99, 3.99, 14, 5,
     "Bilbo's riddles are still fun on a reread."),
)


def seed_account(cursor, username, email, password, role):
    cursor.execute("SELECT id, role, password_hash FROM users WHERE username = %s", (username,))
    existing = cursor.fetchone()
    password_hash = existing[2] if existing else ""

    try:
        valid_hash = password_hash.startswith("$2a$10$") and bcrypt.checkpw(
            password, password_hash.encode("utf-8")
        )
    except ValueError:
        valid_hash = False
    if valid_hash and existing[1] == role:
        return existing[0]
    if not valid_hash:
        password_hash = bcrypt.hashpw(password, bcrypt.gensalt(rounds=10, prefix=b"2a")).decode("ascii")

    # Both username and email are unique. Only update the intended account.
    cursor.execute(
        """
        INSERT INTO users (username, email, password_hash, role)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            password_hash = IF(username = %s, %s, password_hash),
            role = IF(username = %s, %s, role)
        """,
        (username, email, password_hash, role, username, password_hash, username, role),
    )
    cursor.execute("SELECT id, role, password_hash FROM users WHERE username = %s", (username,))
    account = cursor.fetchone()
    if account is None or account[1:] != (role, password_hash):
        raise RuntimeError(f"Could not verify {username}. Check whether {email} is already in use.")
    return account[0]


def setup_mysql(settings):
    database = settings["MYSQL_DATABASE"]
    # Skip the CREATE DATABASE and USE statements included for standalone SQL execution.
    _, _, table_sql = (INIT_DIR / "init.sql").read_text(encoding="utf-8").split(";", 2)

    with mysql.connector.connect(
        host=settings["MYSQL_HOST"],
        port=int(settings["MYSQL_PORT"]),
        user=settings["MYSQL_USER"],
        password=settings["MYSQL_PASSWORD"],
        # The connector's native extension crashes when opening this Windows connection.
        use_pure=True,
        connection_timeout=5,
        read_timeout=10,
        write_timeout=10,
    ) as connection:
        with connection.cursor() as cursor:
            database_identifier = database.replace("`", "``")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_identifier}`;")
            connection.database = database
            cursor.execute(table_sql)
            while cursor.nextset():
                pass

            cursor.execute("SHOW TABLES")
            missing_tables = TABLES - {name for (name,) in cursor.fetchall()}
            if missing_tables:
                raise RuntimeError(f"Missing MySQL tables: {', '.join(sorted(missing_tables))}")

            user_ids = {
                username: seed_account(cursor, username, email, password, role)
                for username, email, password, role in ACCOUNTS
            }
        connection.commit()

    print(f"MySQL {database}: {', '.join(sorted(TABLES))}")
    for username, _, _, role in ACCOUNTS:
        print(f"  {username} ({role}, ID {user_ids[username]})")
    return user_ids["customer1"]


def setup_mongo(settings, customer_id):
    database = settings["MONGO_DB"]
    with MongoClient(settings["MONGO_URI"], serverSelectionTimeoutMS=5000) as client:
        client.admin.command("ping")
        books = client[database]["books"]
        book_ids = []
        inserted = 0
        for title, author, buy_price, rent_price, copies, rating, comment in BOOKS:
            existing = books.find_one({"title": title, "author": author}, {"_id": 1})
            if existing:
                book_ids.append(existing["_id"])
                continue

            # Stable ObjectIds prevent concurrent setup runs from creating duplicates.
            book_id = ObjectId(sha256(f"{title}\0{author}".encode("utf-8")).digest()[:12])
            book = {
                "title": title,
                "author": author,
                "buy_price": buy_price,
                "rent_price": rent_price,
                "available_copies": copies,
                "reviews": [{
                    "user_id": customer_id,
                    "username": "customer1",
                    "rating": rating,
                    "comment": comment,
                    "created_at": "2026-11-11T15:00:00Z",
                }],
            }
            result = books.update_one({"_id": book_id}, {"$setOnInsert": book}, upsert=True)
            inserted += int(result.upserted_id is not None)
            book_ids.append(book_id)

        catalog = list(books.find({"_id": {"$in": book_ids}}, {"title": 1, "author": 1}).sort("title"))
        if len(catalog) != len(BOOKS):
            raise RuntimeError(f"Expected {len(BOOKS)} seeded books, found {len(catalog)}.")

    print(f"MongoDB {database}.books: {len(catalog)} seed books verified ({inserted} inserted)")
    for book in catalog:
        print(f"  {book['title']} by {book['author']}")


def main():
    env_path = INIT_DIR.parent / ".env"
    try:
        if not env_path.is_file():
            raise FileNotFoundError(f"Create {env_path} from .env.example before running setup.")
        settings = dotenv_values(env_path)
        customer_id = setup_mysql(settings)
        setup_mongo(settings, customer_id)
    except KeyError as exc:
        print(f"Database setup failed: missing configuration key {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, mysql.connector.Error, PyMongoError) as exc:
        print(f"Database setup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

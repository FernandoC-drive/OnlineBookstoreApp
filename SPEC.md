# Online Bookstore System Specification (`SPEC.md`)

## 1. Architecture Overview
This project is a native desktop client/server application for an online bookstore. It consists of:
1. **Databases**:
   - **MySQL (`bookstore_db` on Port `3306`)**: Stores users, active auth sessions, orders, and order items.
   - **MongoDB (`bookstore_mongo` on Port `27017`)**: Stores the book catalog, inventory counts, and embedded customer reviews/ratings.
2. **User Service (`user-service-java/` on Port `8001`)**:
   - Built with **Java `com.sun.net.httpserver.HttpServer`** (Maven project).
   - Handles user registration, login, logout, password hashing (`jbcrypt`), session token creation in MySQL, and user profile retrieval.
3. **Book & Order Service (`book-order-flask/` on Port `8002`)**:
   - Built with **Python Flask**.
   - Connects to both **MongoDB** (book search, reviews, manager book CRUD) and **MySQL** (session verification, order creation, HTML bill generation, async email sending, order history, and manager analytics).
4. **Two Native Desktop GUI Applications (`PyQt6`)**:
   - **Customer App (`client-customer-qt/`)**: Native desktop GUI for customers (login, register, search books, view/add reviews, buy/rent cart checkout, view HTML bill, view user profile & order history).
   - **Manager App (`client-manager-qt/`)**: Separate native desktop GUI for managers (login, view all orders, update payment status, add/update book inventory, view sales analytics & best-sellers).
   - **Non-Blocking Requirement (`N2`)**: All HTTP calls in both PyQt6 clients MUST run asynchronously using `QRunnable` / `QThreadPool` so the UI never freezes.

---

## 2. Environment Configuration (`.env`)
All services and setup scripts read configuration from a root `.env` file (with sensible local defaults):
```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=bookstore_db

MONGO_URI=mongodb://127.0.0.1:27017/
MONGO_DB=bookstore_mongo

USER_SERVICE_PORT=8001
FLASK_SERVICE_PORT=8002

# Optional SMTP settings for FR10 (Auto-email HTML bill)
# If SMTP_HOST is empty or fails, log email dispatch gracefully without crashing the order flow.
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@bookstore.local
```

---

## 3. Database Schemas

### 3.1 MySQL Schema (`bookstore_db`)

```sql
CREATE DATABASE IF NOT EXISTS bookstore_db;
USE bookstore_db;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('CUSTOMER', 'MANAGER') NOT NULL DEFAULT 'CUSTOMER',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    token VARCHAR(64) PRIMARY KEY,
    user_id INT NOT NULL,
    role ENUM('CUSTOMER', 'MANAGER') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    payment_status ENUM('Pending', 'Paid') NOT NULL DEFAULT 'Pending',
    bill_html_path VARCHAR(512) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    book_id VARCHAR(64) NOT NULL,
    book_title VARCHAR(255) NOT NULL,
    author VARCHAR(255) NOT NULL,
    transaction_type ENUM('BUY', 'RENT') NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);
```

### 3.2 MongoDB Schema (`bookstore_mongo.books`)
Each document in the `books` collection has the structure:

```json
{
  "_id": "ObjectId('...')",
  "title": "Clean Code",
  "author": "Robert C. Martin",
  "buy_price": 35.99,
  "rent_price": 9.99,
  "available_copies": 12,
  "reviews": [
    {
      "user_id": 1,
      "username": "customer1",
      "rating": 5,
      "comment": "Essential software engineering book.",
      "created_at": "2026-11-11T15:00:00Z"
    }
  ]
}
```

---

## 4. Authentication & Security Contract (`N3`, `N4`, `N5`)
1. **Password Hashing (`N3`)**: Passwords are hashed using `bcrypt` with the `$2a$` prefix and cost factor 10 (`bcrypt.gensalt(rounds=10, prefix=b"2a")` in Python seed scripts and `BCrypt.gensalt(10)` for Java registration).
2. **Session Tokens (`FR1`, `FR2`, `N4`)**:
   - On login, the Java User Service generates a UUID token, stores `(token, user_id, role)` in the MySQL `sessions` table, and returns it to the client.
   - Clients send `Authorization: Bearer <token>` on all protected requests to both Port `8001` (Java) and Port `8002` (Flask).
   - On logout (`FR2`), the Java User Service deletes the token row from MySQL `sessions`.
3. **Role Enforcement (`N5`, `FR11`)**:
   - Customer endpoints require a valid session with `role == 'CUSTOMER'`. Managers attempting customer actions (such as placing an order) must receive `403 Forbidden`.
   - Manager endpoints require a valid session with `role == 'MANAGER'`. Customers attempting manager actions must receive `403 Forbidden`.

---

## 5. REST API Specification

### 5.1 Java User Service (`http://127.0.0.1:8001`)
* **`POST /api/users/register`** *(FR3 - Extra Credit)*
  - **Auth**: Public
  - **Request**: `{"username": "alice", "email": "alice@example.com", "password": "secretpassword"}`
  - **Response (`201`)**: `{"message": "User registered successfully", "user_id": 3}`
* **`POST /api/users/login`** *(FR1)*
  - **Auth**: Public
  - **Request**: `{"username": "customer1", "password": "password123"}`
  - **Response (`200`)**: `{"token": "uuid-string", "user_id": 1, "username": "customer1", "email": "customer1@example.com", "role": "CUSTOMER"}`
* **`POST /api/users/logout`** *(FR2)*
  - **Auth**: Bearer Token (`CUSTOMER` or `MANAGER`)
  - **Response (`200`)**: `{"message": "Logged out successfully"}`
* **`GET /api/users/profile`** *(Extra Credit - User Profile)*
  - **Auth**: Bearer Token (`CUSTOMER` or `MANAGER`)
  - **Response (`200`)**: `{"user_id": 1, "username": "customer1", "email": "customer1@example.com", "role": "CUSTOMER", "created_at": "..."}`

### 5.2 Python Flask Book & Order Service (`http://127.0.0.1:8002`)
* **`GET /api/books?q=<keyword>`** *(FR4, FR5)*
  - **Auth**: Bearer Token (`CUSTOMER` or `MANAGER`)
  - **Behavior**: If `q` is empty, return all books. If `q` is provided, match case-insensitively against `title` OR `author`. Include computed `avg_rating` and `review_count`.
  - **Response (`200`)**: `{"books": [{"id": "...", "title": "...", "author": "...", "buy_price": 29.99, "rent_price": 7.99, "available_copies": 10, "avg_rating": 4.5, "review_count": 2, "reviews": [...] }]}`
* **`POST /api/books/<book_id>/reviews`** *(Extra Credit - Reviews & Ratings)*
  - **Auth**: Bearer Token (`CUSTOMER`)
  - **Request**: `{"rating": 5, "comment": "Great read!"}` (rating must be integer 1–5)
  - **Response (`201`)**: `{"message": "Review added", "avg_rating": 4.8}`
* **`POST /api/orders`** *(FR6, FR7, FR8, FR9, FR10)*
  - **Auth**: Bearer Token (`CUSTOMER` only)
  - **Request**:
    ```json
    {
      "items": [
        {"book_id": "654321...", "transaction_type": "BUY", "quantity": 1},
        {"book_id": "654322...", "transaction_type": "RENT", "quantity": 1}
      ]
    }
    ```
  - **Behavior**:
    1. Validate `available_copies >= quantity` for each book in MongoDB and decrement `available_copies`.
    2. Insert order (`Pending`) and `order_items` in MySQL.
    3. Generate detailed HTML invoice (Order ID, customer info, timestamp, itemized buy/rent breakdown, unit prices, total amount due) and save to `bills/bill_order_<order_id>.html` (`FR8`, `FR9`).
    4. Trigger asynchronous background email of the HTML bill to the customer's email address (`FR10`).
  - **Response (`201`)**:
    ```json
    {
      "order_id": 101,
      "total_amount": 43.98,
      "payment_status": "Pending",
      "bill_html_path": "bills/bill_order_101.html",
      "bill_html_content": "<!DOCTYPE html>...",
      "email_status": "queued"
    }
    ```
* **`GET /api/orders/my-history`** *(Extra Credit - User Profile Order History)*
  - **Auth**: Bearer Token (`CUSTOMER` only)
  - **Response (`200`)**: List of all orders belonging to `user_id` including nested `items` and `bill_html_content`.
* **`GET /api/manager/orders`** *(FR12)*
  - **Auth**: Bearer Token (`MANAGER` only)
  - **Response (`200`)**: List of all orders in the system with customer username, email, total_amount, payment_status, created_at, bill_html_path, and items.
* **`PUT /api/manager/orders/<order_id>/status`** *(FR13)*
  - **Auth**: Bearer Token (`MANAGER` only)
  - **Request**: `{"payment_status": "Paid"}` (`"Pending"` or `"Paid"`)
  - **Response (`200`)**: `{"message": "Order status updated", "order_id": 101, "payment_status": "Paid"}`
* **`POST /api/manager/books`** *(FR14 - Add Book)*
  - **Auth**: Bearer Token (`MANAGER` only)
  - **Request**: `{"title": "...", "author": "...", "buy_price": 25.00, "rent_price": 6.00, "available_copies": 15}`
  - **Response (`201`)**: Created book object.
* **`PUT /api/manager/books/<book_id>`** *(FR14 - Update Book)*
  - **Auth**: Bearer Token (`MANAGER` only)
  - **Request**: `{"title": "...", "author": "...", "buy_price": 25.00, "rent_price": 6.00, "available_copies": 20}`
  - **Response (`200`)**: Updated book object.
* **`GET /api/manager/analytics?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`** *(Extra Credit - Manager Sales Analytics)*
  - **Auth**: Bearer Token (`MANAGER` only)
  - **Response (`200`)**:
    ```json
    {
      "summary": {"total_orders": 12, "total_revenue": 340.50, "paid_revenue": 290.00},
      "orders_in_period": [...],
      "best_sellers": [
        {"book_id": "...", "book_title": "...", "author": "...", "total_units": 8, "total_sales": 240.00}
      ]
    }
    ```

---

## 6. Default Seeded Test Accounts
- **Customer Account**: `username`: `customer1` | `password`: `password123` | `role`: `CUSTOMER`
- **Manager Account**: `username`: `manager1` | `password`: `admin123` | `role`: `MANAGER`

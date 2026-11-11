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
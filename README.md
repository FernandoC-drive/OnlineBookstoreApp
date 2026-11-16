# Online Bookstore System

A full-stack native desktop application for browsing, purchasing, renting, and managing books. Built with a polyglot microservices backend (**Java 17 `HttpServer`** + **Python Flask**), dual database persistence (**MySQL** + **MongoDB**), and two separate native desktop GUI clients built with **PyQt6**.

---

## Key Features

### Customer Storefront (`client-customer-qt`)
* **Account Management & Security**: Self-service account registration with valid email validation, secure `bcrypt` password hashing, and persistent session authentication until explicit logout.
* **Catalog Search & Reviews**: Real-time keyword search matching book titles and authors, displaying prices, available stock, and average star ratings. Customers can read community reviews and submit 1–5 star ratings and comments.
* **Combined Buy & Rent Cart**: Add multiple titles to a single cart as either a **Purchase (`BUY`)** or **Rental (`RENT`)** and check out in one transaction.
* **Automated HTML Invoices & Email Receipts**: Every order automatically generates a printable black-and-white HTML invoice saved to `bills/bill_order_<id>.html` and dispatches an email copy to the customer's registered email address.
* **User Profile & Order History**: View account metadata alongside complete past order history and live payment status (`Pending` vs. `Paid`).

### Manager Operations Portal (`client-manager-qt`)
* **Strict Role Isolation**: Dedicated administrative desktop interface inaccessible to standard customer accounts.
* **Order & Payment Administration**: View all customer orders across the system, preview or open printable HTML invoices in a browser, and update order payment statuses from `Pending` to `Paid`.
* **Inventory Management**: Add new books to the catalog or update prices and available copy counts in real time.
* **Sales Reports & Best-Seller Analytics**: Filter orders by date range to view summary KPIs (**Total Orders**, **Total Revenue**, **Paid Revenue**) and a ranked **Best-Selling Books** leaderboard.

---

## System Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                 Native PyQt6 Desktop Clients (Async)                 │
│   ┌──────────────────────┐              ┌────────────────────────┐   │
│   │  Customer Storefront │              │   Manager Operations   │   │
│   └──────────┬───────────┘              └───────────┬────────────┘   │
└──────────────┼──────────────────────────────────────┼────────────────┘
               │           REST / JSON + Bearer Token │
       ┌───────▼────────────────┐            ┌────────▼───────────────┐
       │   Java 17 HttpServer   │            │   Python Flask API     │
       │   User Service (:8001) │            │ Book & Order (:8002)   │
       └───────┬────────────────┘            └───┬────────────────┬───┘
               │                                 │                │
               └──────────────┬──────────────────┘                │
                              ▼                                   ▼
                 ┌─────────────────────────┐         ┌─────────────────────────┐
                 │     MySQL (:3306)       │         │    MongoDB (:27017)     │
                 │  users, sessions,       │         │  books catalog &        │
                 │  orders, order_items    │         │  embedded reviews       │
                 └─────────────────────────┘         └─────────────────────────┘
```

### Project Structure
```text
OnlineBookstoreApp/
├── run_bookstore.py         # Single-command launcher (starts backends + Portal UI)
├── portal_app.py            # Unified Launcher Portal window
├── run_customer_app.py      # Standalone Customer Storefront launcher
├── run_manager_app.py       # Standalone Manager Portal launcher
├── SPEC.md                  # Master API, schema, and architecture specification
├── db-init/                 # MySQL schema & MongoDB/MySQL seeding script
├── user-service-java/       # Java 17 HttpServer authentication & profile service (:8001)
├── book-order-flask/        # Python Flask catalog, ordering, billing & analytics API (:8002)
├── client-customer-qt/      # Native PyQt6 Customer desktop GUI
├── client-manager-qt/       # Native PyQt6 Manager desktop GUI
└── shared_ui/               # Shared modern dark theme, custom icons, and async helpers
```

---

## Prerequisites

1. **Python 3.10+**
2. **Java 17+** and **Apache Maven**
3. **MySQL Server** running locally on `127.0.0.1:3306`
4. **MongoDB Community Server** running locally on `127.0.0.1:27017`

---

## Setup & Installation

### 1. Configure Environment Variables
Copy `.env.example` to `.env` in the project root and update your local MySQL credentials (and optional SMTP credentials if you want live email delivery):
```bash
cp .env.example .env
```

### 2. Install Python Dependencies
Create and activate a virtual environment, then install the dependencies for database setup, Flask, and PyQt6:
```bash
python -m venv .venv

# Windows (Git Bash):
source .venv/Scripts/activate
# Windows (PowerShell):
# .\.venv\Scripts\Activate.ps1

pip install -r db-init/requirements.txt
pip install -r book-order-flask/requirements.txt
pip install -r client-customer-qt/requirements.txt
```

### 3. Initialize & Seed the Databases
Ensure your local MySQL and MongoDB services are running, then execute the setup script to create `bookstore_db`, build all relational tables, seed test accounts, and populate the MongoDB book catalog:
```bash
python db-init/setup_databases.py
```

### 4. Compile the Java User Service
```bash
cd user-service-java
mvn clean package -DskipTests
cd ..
```

---

## Running the Application

### Option A: Single-Command Unified Launcher (Recommended)
Run one command from the project root to automatically verify/start both backend services (`:8001` and `:8002`) and open the **Unified Launcher Portal**:
```bash
./.venv/Scripts/python.exe run_bookstore.py
```
From the Portal window, click **Launch Customer App** or **Launch Manager App** (you can open both windows side-by-side).

### Option B: Launch Each Desktop Client Individually
* **Customer Storefront only:**
  ```bash
  ./.venv/Scripts/python.exe run_customer_app.py
  ```
* **Manager Operations Portal only:**
  ```bash
  ./.venv/Scripts/python.exe run_manager_app.py
  ```

---

## Default Test Accounts

| Role | Username | Password |
| :--- | :--- | :--- |
| **Customer** | `customer1` | `password123` |
| **Manager** | `manager1` | `admin123` |
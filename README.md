# Online Bookstore

A CSCE 310 project with separate native PyQt6 applications for customers and managers. Customers can search, review, buy, and rent books and view their invoices. Managers can administer payments, update inventory, and run sales reports.

## Architecture

| Component | Default address | Responsibility |
| --- | --- | --- |
| [Java User Service](user-service-java/) | 127.0.0.1:8001 | Registration, bcrypt passwords, login, logout, and profiles |
| [Flask Book and Order Service](book-order-flask/) | 127.0.0.1:8002 | Catalog, reviews, checkout, invoices, inventory, and reporting |
| MySQL | 127.0.0.1:3306 | Users, bearer-token sessions, orders, and order items in `bookstore_db` |
| MongoDB | 127.0.0.1:27017 | Books, available copies, and reviews in `bookstore_mongo.books` |

Both desktop apps run HTTP requests in a Qt thread pool. The Java service creates the session, and both backends use the same MySQL session table to check access. See [SPEC.md](SPEC.md) for the API contract and schemas.

## Local setup on Windows

Install Python 3.11, a Java 17 or newer JDK, Maven, MySQL Server, and MongoDB Community Server. Start MySQL and MongoDB locally before running the setup. If installed as Windows services, start them in the Windows Services console.

From the repository root in PowerShell, create your configuration if you do not already have a `.env`. Set `MYSQL_USER` and `MYSQL_PASSWORD` to your local credentials.

```powershell
Copy-Item .env.example .env
notepad .env
```

Create the virtual environment, install the dependencies, and initialize both databases.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r db-init/requirements.txt -r book-order-flask/requirements.txt -r client-manager-qt/requirements.txt
.\.venv\Scripts\python.exe db-init/setup_databases.py
mvn -f user-service-java/pom.xml package
```

The manager requirements include the customer requirements, so one install covers both clients. Rerun the database setup to verify or restore the seed accounts and add missing seed books. Git ignores `.env` and generated invoices. Leave SMTP credentials blank to skip email delivery during local testing.

## Launch the desktop apps

Run the desired command from the repository root. The launchers reuse healthy services, start any missing services in the background, and wait for them before opening the app. If the Java JAR is missing, the launcher builds it with Maven.

```powershell
.\.venv\Scripts\python.exe run_customer_app.py
.\.venv\Scripts\python.exe run_manager_app.py
```

Use separate terminals to keep both windows open. Both launchers log to `db-data/customer-launcher/`. Open saved invoices from `bills/` in the default browser for printing.

| App | Seeded username | Seeded password |
| --- | --- | --- |
| Customer | `customer1` | `password123` |
| Manager | `manager1` | `admin123` |

## Run the GUI smoke tests

With Java and Flask running against the seeded databases, use a separate PowerShell terminal. The tests exercise the live services and create uniquely named test records.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe client-customer-qt/test_customer_gui.py
.\.venv\Scripts\python.exe client-manager-qt/test_manager_gui.py
Remove-Item Env:QT_QPA_PLATFORM
```

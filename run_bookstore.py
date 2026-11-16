"""Start the local services and open the bookstore portal."""

import sys

from run_customer_app import launch_app


if __name__ == "__main__":
    sys.exit(launch_app("portal_app.py", "run_bookstore.py", "the bookstore portal"))

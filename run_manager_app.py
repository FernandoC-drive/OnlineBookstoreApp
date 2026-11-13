"""Start the local bookstore services as needed, then open the manager app."""

import sys

from run_customer_app import launch_client


if __name__ == "__main__":
    sys.exit(launch_client("manager"))

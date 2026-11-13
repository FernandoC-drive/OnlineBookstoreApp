"""Invoice rendering, atomic file updates, and background SMTP delivery."""

from email.message import EmailMessage
import os
from pathlib import Path
import smtplib
import ssl
from tempfile import NamedTemporaryFile
from threading import Thread

from flask import current_app, render_template

from service import ApiError


def invoice_path(order_id):
    return current_app.config["BILLS_DIR"] / f"bill_order_{order_id}.html"


def invoice_html(order):
    return render_template("invoice.html", order=order)


def save_invoice(path, html):
    temporary_path = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(html)
        os.replace(temporary_path, path)
    except OSError as error:
        current_app.logger.exception("Could not write invoice %s.", path.name)
        raise ApiError(500, "Could not save the invoice") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                current_app.logger.warning("Could not remove temporary invoice %s.", temporary_path.name)


def send_invoice(settings, order_id, recipient, html, logger):
    try:
        message = EmailMessage()
        message["Subject"] = f"Bookstore invoice for order {order_id}"
        message["From"] = settings["sender"]
        message["To"] = recipient
        message.set_content(f"Your invoice for bookstore order {order_id} is included in this email.")
        message.add_alternative(html, subtype="html")

        context = ssl.create_default_context()
        host, port = settings["host"], settings["port"]
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
        with server:
            if port != 465:
                server.starttls(context=context)
            server.login(settings["user"], settings["password"])
            server.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as error:
        logger.warning("Invoice email for order %s failed (%s).", order_id, type(error).__name__)
    else:
        logger.info("Invoice email sent for order %s.", order_id)


def queue_invoice_email(order, html):
    settings = current_app.config["SMTP"]
    logger = current_app.logger
    order_id = order["order_id"]
    if not all((settings["host"], settings["user"], settings["password"])):
        logger.info("Invoice email skipped for order %s because SMTP is not configured.", order_id)
        return "skipped"

    try:
        Thread(
            target=send_invoice,
            args=(settings, order_id, order["email"], html, logger),
            daemon=True,
        ).start()
    except RuntimeError:
        logger.exception("Could not start the invoice email thread for order %s.", order_id)
        return "failed"
    return "queued"

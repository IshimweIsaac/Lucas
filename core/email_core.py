"""Lucas Email — SMTP send + IMAP read operations."""

from __future__ import annotations

import imaplib
import json
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "email_config.json"


# ── Config ──


def _load_config() -> dict:
    """Load email config from disk, returning {} if missing or corrupt."""
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load email config: %s", exc)
            return {}
    return {}


def _save_config(config: dict) -> None:
    """Persist email config to disk."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def configure(
    email_addr: str,
    smtp_server: str,
    smtp_port: int,
    imap_server: str,
    imap_port: int,
    password: str,
) -> str:
    """Save email account details and return a confirmation message."""
    config = {
        "email": email_addr,
        "smtp_server": smtp_server,
        "smtp_port": smtp_port,
        "imap_server": imap_server,
        "imap_port": imap_port,
        "password": password,
    }
    _save_config(config)
    logger.info("Email configured for %s", email_addr)
    return f"Email configured for {email_addr}"


def config_status() -> str:
    """Return a human-readable string describing the current email config."""
    config = _load_config()
    if config.get("email"):
        return f"Email configured: {config['email']}"
    return "Email not configured. Use configure action."


# ── Send ──


def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via SMTP. Returns a result string."""
    config = _load_config()
    if not config.get("email"):
        return "Email not configured. Use configure action first."
    if not to or not to.strip():
        return "Error: recipient address is empty."
    if not subject or not subject.strip():
        return "Error: subject is empty."
    try:
        msg = MIMEMultipart()
        msg["From"] = config["email"]
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["email"], config["password"])
            server.send_message(msg)
        logger.info("Email sent to %s: %s", to, subject)
        return f"Email sent to {to}: {subject}"
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending to %s: %s", to, exc)
        return f"Failed to send email: {exc}"
    except OSError as exc:
        logger.error("Connection error sending to %s: %s", to, exc)
        return f"Failed to send email: {exc}"


# ── Read Inbox (last N emails) ──


def read_inbox(count: int = 5) -> str:
    """Fetch the last *count* emails from the IMAP INBOX."""
    config = _load_config()
    if not config.get("email"):
        return "Email not configured."
    if count < 1:
        count = 1
    try:
        mail = imaplib.IMAP4_SSL(config["imap_server"], config["imap_port"])
        mail.login(config["email"], config["password"])
        mail.select("INBOX")
        status, data = mail.search(None, "ALL")
        if status != "OK":
            mail.logout()
            return "Failed to read inbox."

        ids = data[0].split()
        recent = ids[-count:] if len(ids) >= count else ids

        messages: list[str] = []
        for mid in reversed(recent):
            fetch_status, msg_data = mail.fetch(mid, "(RFC822)")
            if fetch_status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            messages.append(f"  From: {msg['From']} | Subject: {msg['Subject']}")

        mail.logout()

        if not messages:
            return "No emails in inbox."
        return f"Inbox ({len(messages)} of {len(ids)}):\n" + "\n".join(messages)
    except imaplib.IMAP4.error as exc:
        logger.error("IMAP error: %s", exc)
        return f"Failed to read inbox: {exc}"
    except OSError as exc:
        logger.error("Connection error reading inbox: %s", exc)
        return f"Failed to read inbox: {exc}"


def unread_count() -> str:
    """Return the number of unseen (unread) emails in the INBOX."""
    config = _load_config()
    if not config.get("email"):
        return "Email not configured."
    try:
        mail = imaplib.IMAP4_SSL(config["imap_server"], config["imap_port"])
        mail.login(config["email"], config["password"])
        mail.select("INBOX")
        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            mail.logout()
            return "Failed to check inbox."
        count = len(data[0].split()) if data[0] else 0
        mail.logout()
        return f"You have {count} unread email(s)."
    except imaplib.IMAP4.error as exc:
        logger.error("IMAP error checking unread: %s", exc)
        return f"Failed to check: {exc}"
    except OSError as exc:
        logger.error("Connection error checking unread: %s", exc)
        return f"Failed to check: {exc}"

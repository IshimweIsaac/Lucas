"""Lucas Email control — configure, send, read inbox, check unread via voice."""

from __future__ import annotations

from core import email_core as ec
from core.logger import get_logger

logger = get_logger(__name__)

TOOL_SCHEMA = {
    "name": "email_control",
    "description": (
        "Lucas email client — configure an email account, send emails via SMTP, "
        "read inbox messages via IMAP, and check unread count. "
        "Use action=help to see available commands."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "configure | config_status | send_email | read_inbox | "
                    "unread_count | help"
                ),
            },
            "email": {
                "type": "STRING",
                "description": "Your email address (for configure)",
            },
            "smtp_server": {
                "type": "STRING",
                "description": "SMTP server hostname (for configure)",
            },
            "smtp_port": {
                "type": "INTEGER",
                "description": "SMTP server port (for configure)",
            },
            "imap_server": {
                "type": "STRING",
                "description": "IMAP server hostname (for configure)",
            },
            "imap_port": {
                "type": "INTEGER",
                "description": "IMAP server port (for configure)",
            },
            "password": {
                "type": "STRING",
                "description": "Email account password or app password (for configure)",
            },
            "to": {
                "type": "STRING",
                "description": "Recipient email address (for send_email)",
            },
            "subject": {
                "type": "STRING",
                "description": "Email subject line (for send_email)",
            },
            "body": {
                "type": "STRING",
                "description": "Email body text (for send_email)",
            },
            "count": {
                "type": "INTEGER",
                "description": "Number of recent emails to read (for read_inbox, default 5)",
            },
        },
        "required": ["action"],
    },
}


def email_control(parameters: dict, player=None) -> str:
    """Dispatch email actions based on the *action* parameter."""
    action = (parameters.get("action") or "").lower().strip()

    if action == "help":
        return (
            "Available email actions:\n"
            "  configure – set up email account (email, smtp_server, smtp_port, "
            "imap_server, imap_port, password)\n"
            "  config_status – show current email config\n"
            "  send_email – send email (to, subject, body)\n"
            "  read_inbox – read recent emails (count, default 5)\n"
            "  unread_count – check unread messages"
        )

    if action == "configure":
        missing = [
            k
            for k in (
                "email",
                "smtp_server",
                "smtp_port",
                "imap_server",
                "imap_port",
                "password",
            )
            if k not in parameters
        ]
        if missing:
            return f"Error: missing required parameters: {', '.join(missing)}"
        return ec.configure(
            email_addr=str(parameters["email"]),
            smtp_server=str(parameters["smtp_server"]),
            smtp_port=int(parameters["smtp_port"]),
            imap_server=str(parameters["imap_server"]),
            imap_port=int(parameters["imap_port"]),
            password=str(parameters["password"]),
        )

    if action == "config_status":
        return ec.config_status()

    if action == "send_email":
        missing = [k for k in ("to", "subject", "body") if k not in parameters]
        if missing:
            return f"Error: missing required parameters: {', '.join(missing)}"
        return ec.send_email(
            to=str(parameters["to"]),
            subject=str(parameters["subject"]),
            body=str(parameters["body"]),
        )

    if action == "read_inbox":
        count = int(parameters.get("count", 5))
        return ec.read_inbox(count=count)

    if action == "unread_count":
        return ec.unread_count()

    return f"Unknown action: {action}. Use action=help to see available actions."

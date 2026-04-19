"""Brevo SMTP delivery + SQLite run log.

Brevo's SMTP login (e.g. ``a89cbc001@smtp-brevo.com``) is distinct from the
visible ``From`` address — the login authenticates the relay while the
sender is the verified email the recipient actually sees.
"""

from __future__ import annotations

import logging
import smtplib
import sqlite3
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from digest.config import BREVO_SMTP_HOST, BREVO_SMTP_PORT

logger = logging.getLogger(__name__)

DB_PATH = Path("data/digest.db")


class SendError(Exception):
    """Raised when SMTP delivery fails."""


def send_email(
    subject: str,
    html_body: str,
    *,
    recipient: str,
    sender: str,
    smtp_login: str,
    smtp_password: str,
    smtp_host: str = BREVO_SMTP_HOST,
    smtp_port: int = BREVO_SMTP_PORT,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=ctx)
            server.login(smtp_login, smtp_password)
            server.sendmail(sender, [recipient], msg.as_string())
    except (smtplib.SMTPException, OSError) as exc:
        raise SendError(str(exc)) from exc


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            timestamp INTEGER NOT NULL,
            num_stories INTEGER NOT NULL,
            send_status TEXT NOT NULL,
            error_msg TEXT
        )"""
    )
    return conn


def log_run(
    run_id: str,
    num_stories: int,
    send_status: str,
    error_msg: str | None = None,
    *,
    db_path: Path = DB_PATH,
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, timestamp, num_stories, send_status, error_msg)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, int(time.time()), num_stories, send_status, error_msg),
        )
        conn.commit()
    finally:
        conn.close()

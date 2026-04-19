"""Gmail SMTP delivery + SQLite run log."""

from __future__ import annotations

import logging
import smtplib
import sqlite3
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 465
DB_PATH = Path("data/digest.db")


class SendError(Exception):
    """Raised when SMTP delivery fails."""


def send_email(
    subject: str,
    html_body: str,
    *,
    recipient: str,
    sender: str,
    password: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(GMAIL_HOST, GMAIL_PORT, context=ctx) as server:
            server.login(sender, password)
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

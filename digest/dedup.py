"""SQLite-backed seen-stories filter so we don't re-send yesterday's digest.

Table: ``seen_stories(source, story_id, first_seen_date)`` with composite
primary key on ``(source, story_id)``. Written once per successful send.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = Path("data/digest.db")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_stories (
    source TEXT NOT NULL,
    story_id TEXT NOT NULL,
    first_seen_date TEXT NOT NULL,
    PRIMARY KEY (source, story_id)
)
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    return conn


def filter_unseen(
    stories: list[dict[str, Any]],
    *,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    """Return ``stories`` minus anything already recorded in seen_stories."""
    if not stories:
        return []
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT source, story_id FROM seen_stories"
        ).fetchall()
    seen = {(src, sid) for src, sid in rows}
    kept = [s for s in stories if (s["source"], str(s["id"])) not in seen]
    dropped = len(stories) - len(kept)
    if dropped:
        logger.info("dedup: dropped %d already-seen stories", dropped)
    return kept


def mark_sent(
    stories: list[dict[str, Any]],
    *,
    db_path: Path = DB_PATH,
) -> None:
    """Record ``stories`` as seen. Safe to re-run (INSERT OR IGNORE)."""
    if not stories:
        return
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    rows = [(s["source"], str(s["id"]), today) for s in stories]
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_stories "
            "(source, story_id, first_seen_date) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()

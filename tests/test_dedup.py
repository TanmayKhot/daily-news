"""Unit tests for dedup: no network, writes to a tmp SQLite path."""

from __future__ import annotations

from pathlib import Path

from digest.dedup import filter_unseen, mark_sent


def _story(source: str, story_id: str, title: str = "t") -> dict:
    return {"source": source, "id": story_id, "title": title}


def test_filter_unseen_empty_db_passes_everything(tmp_path: Path) -> None:
    db = tmp_path / "digest.db"
    stories = [_story("hn", "1"), _story("reddit", "abc")]
    assert filter_unseen(stories, db_path=db) == stories


def test_mark_sent_then_filter_drops_seen(tmp_path: Path) -> None:
    db = tmp_path / "digest.db"
    mark_sent([_story("hn", "1"), _story("reddit", "abc")], db_path=db)
    remaining = filter_unseen(
        [
            _story("hn", "1"),
            _story("hn", "2"),
            _story("reddit", "abc"),
            _story("reddit", "xyz"),
        ],
        db_path=db,
    )
    kept = {(s["source"], s["id"]) for s in remaining}
    assert kept == {("hn", "2"), ("reddit", "xyz")}


def test_mark_sent_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "digest.db"
    s = [_story("hn", "42")]
    mark_sent(s, db_path=db)
    mark_sent(s, db_path=db)
    assert filter_unseen(s, db_path=db) == []


def test_filter_unseen_handles_int_ids(tmp_path: Path) -> None:
    """Stories from HN carry int ids; dedup must coerce to str consistently."""
    db = tmp_path / "digest.db"
    mark_sent([{"source": "hn", "id": 12345}], db_path=db)
    assert filter_unseen([{"source": "hn", "id": 12345}], db_path=db) == []
    assert filter_unseen([{"source": "hn", "id": "12345"}], db_path=db) == []


def test_filter_unseen_empty_list(tmp_path: Path) -> None:
    db = tmp_path / "digest.db"
    assert filter_unseen([], db_path=db) == []


def test_mark_sent_empty_list_is_noop(tmp_path: Path) -> None:
    db = tmp_path / "digest.db"
    mark_sent([], db_path=db)
    assert not db.exists() or filter_unseen(
        [_story("hn", "1")], db_path=db
    ) == [_story("hn", "1")]

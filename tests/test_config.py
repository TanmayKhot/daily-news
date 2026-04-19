"""Unit tests for the time-window helpers in digest.config."""

from __future__ import annotations

from datetime import datetime, timezone

from digest.config import yesterday_date_utc, yesterday_window_utc

SECONDS_PER_DAY = 86_400


def test_yesterday_window_spans_exactly_one_day() -> None:
    now = datetime(2026, 4, 19, 22, 30, 0, tzinfo=timezone.utc)
    start, end = yesterday_window_utc(now=now)
    assert end - start == SECONDS_PER_DAY


def test_yesterday_window_ends_at_todays_midnight_utc() -> None:
    now = datetime(2026, 4, 19, 22, 30, 0, tzinfo=timezone.utc)
    _, end = yesterday_window_utc(now=now)
    assert datetime.fromtimestamp(end, tz=timezone.utc) == datetime(
        2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc
    )


def test_yesterday_window_starts_at_yesterdays_midnight_utc() -> None:
    now = datetime(2026, 4, 19, 22, 30, 0, tzinfo=timezone.utc)
    start, _ = yesterday_window_utc(now=now)
    assert datetime.fromtimestamp(start, tz=timezone.utc) == datetime(
        2026, 4, 18, 0, 0, 0, tzinfo=timezone.utc
    )


def test_yesterday_window_handles_month_boundary() -> None:
    now = datetime(2026, 5, 1, 3, 0, 0, tzinfo=timezone.utc)
    start, end = yesterday_window_utc(now=now)
    assert datetime.fromtimestamp(start, tz=timezone.utc) == datetime(
        2026, 4, 30, 0, 0, 0, tzinfo=timezone.utc
    )
    assert datetime.fromtimestamp(end, tz=timezone.utc) == datetime(
        2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc
    )


def test_yesterday_date_string_is_previous_utc_day() -> None:
    now = datetime(2026, 4, 19, 22, 30, 0, tzinfo=timezone.utc)
    assert yesterday_date_utc(now=now) == "2026-04-18"


def test_yesterday_date_handles_year_boundary() -> None:
    now = datetime(2027, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
    assert yesterday_date_utc(now=now) == "2026-12-31"

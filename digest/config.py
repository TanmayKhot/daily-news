"""Central constants for the digest pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

MODEL_ID = "claude-haiku-4-5-20251001"

RECIPIENT_EMAIL = "tnmykhot@gmail.com"

SUBREDDITS: tuple[str, ...] = (
    "MachineLearning",
    "LocalLLaMA",
    "singularity",
    "artificial",
    "OpenAI",
)

AI_KEYWORDS: tuple[str, ...] = (
    "AI",
    "LLM",
    "GPT",
    "Claude",
    "transformer",
    "agent",
    "diffusion",
    "neural",
    "model",
    "Anthropic",
    "OpenAI",
)

USER_AGENT = "ai-digest/0.1 by tnmykhot"

HN_HITS_PER_KEYWORD = 20

REDDIT_POSTS_PER_SUB = 25

COMMENT_TOKEN_CAP = 500
TOP_COMMENTS_PER_POST = 5
REPLIES_PER_TOP_COMMENT = 2

FINAL_DIGEST_SIZE = 10

BREVO_SMTP_HOST = "smtp-relay.brevo.com"
BREVO_SMTP_PORT = 587


def yesterday_window_utc(
    now: datetime | None = None,
) -> tuple[int, int]:
    """Return ``(start, end)`` UNIX timestamps for yesterday's UTC calendar day.

    End is midnight UTC of today (exclusive). ``now`` is injectable for tests.
    """
    now = now or datetime.now(tz=timezone.utc)
    today_start = datetime(
        now.year, now.month, now.day, tzinfo=timezone.utc
    )
    yesterday_start = today_start - timedelta(days=1)
    return int(yesterday_start.timestamp()), int(today_start.timestamp())


def yesterday_date_utc(now: datetime | None = None) -> str:
    """Return yesterday's UTC calendar date as ``YYYY-MM-DD``."""
    now = now or datetime.now(tz=timezone.utc)
    return (now - timedelta(days=1)).strftime("%Y-%m-%d")

"""Reddit candidate fetcher using the public JSON endpoints."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from digest.config import REDDIT_POSTS_PER_SUB, SUBREDDITS, USER_AGENT

logger = logging.getLogger(__name__)

REDDIT_TOP_URL = "https://www.reddit.com/r/{sub}/top.json"
REDDIT_POST_URL = "https://www.reddit.com{permalink}"


def fetch_candidates(
    *,
    subreddits: tuple[str, ...] = SUBREDDITS,
    limit: int = REDDIT_POSTS_PER_SUB,
    time_window: str = "day",
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Return top posts from each subreddit over ``time_window`` (``day`` by default)."""
    owns_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=15.0
    )

    candidates: list[dict[str, Any]] = []
    try:
        for sub in subreddits:
            try:
                resp = client.get(
                    REDDIT_TOP_URL.format(sub=sub),
                    params={"t": time_window, "limit": limit},
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Reddit sub %r failed: %s", sub, exc)
                continue

            listing = resp.json().get("data", {}).get("children", [])
            for child in listing:
                data = child.get("data", {})
                if data.get("stickied") or data.get("over_18"):
                    continue
                permalink = data.get("permalink") or ""
                candidates.append(
                    {
                        "id": data.get("id"),
                        "title": data.get("title") or "",
                        "url": data.get("url_overridden_by_dest")
                        or data.get("url")
                        or REDDIT_POST_URL.format(permalink=permalink),
                        "points": data.get("score") or 0,
                        "num_comments": data.get("num_comments") or 0,
                        "created_at_i": int(data.get("created_utc") or 0),
                        "subreddit": data.get("subreddit") or sub,
                        "permalink": permalink,
                        "reddit_discussion_url": REDDIT_POST_URL.format(
                            permalink=permalink
                        ),
                        "source": "reddit",
                    }
                )
    finally:
        if owns_client:
            client.close()

    return candidates

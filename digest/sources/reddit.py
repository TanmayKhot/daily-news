"""Reddit candidate fetcher + comment-tree fetcher (public JSON endpoints)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from digest.config import (
    COMMENT_TOKEN_CAP,
    REDDIT_POSTS_PER_SUB,
    REPLIES_PER_TOP_COMMENT,
    SUBREDDITS,
    TOP_COMMENTS_PER_POST,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

REDDIT_TOP_URL = "https://www.reddit.com/r/{sub}/top.json"
REDDIT_POST_URL = "https://www.reddit.com{permalink}"
REDDIT_PERMALINK_JSON = "https://www.reddit.com{permalink}.json"

_COMMENT_CHAR_CAP = COMMENT_TOKEN_CAP * 4
_REMOVED_BODIES = {"[removed]", "[deleted]", ""}


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


def _truncate(text: str, limit: int = _COMMENT_CHAR_CAP) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def fetch_comments(
    permalink: str,
    *,
    max_roots: int = TOP_COMMENTS_PER_POST,
    max_replies: int = REPLIES_PER_TOP_COMMENT,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Return top ``max_roots`` comments with up to ``max_replies`` replies each.

    Reddit already sorts top-level comments by its "best" algorithm in the JSON
    response. We respect that order.
    """
    owns_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=15.0
    )

    try:
        try:
            resp = client.get(REDDIT_PERMALINK_JSON.format(permalink=permalink))
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Reddit comments for %s failed: %s", permalink, exc)
            return []

        payload = resp.json()
        if not isinstance(payload, list) or len(payload) < 2:
            return []

        children = (
            payload[1].get("data", {}).get("children", [])
            if isinstance(payload[1], dict)
            else []
        )

        roots: list[dict[str, Any]] = []
        for child in children:
            if len(roots) >= max_roots:
                break
            if child.get("kind") != "t1":
                continue
            data = child.get("data", {})
            body = data.get("body") or ""
            if body.strip() in _REMOVED_BODIES:
                continue

            replies_field = data.get("replies")
            reply_children: list[dict[str, Any]] = []
            if isinstance(replies_field, dict):
                reply_children = (
                    replies_field.get("data", {}).get("children", []) or []
                )

            replies: list[dict[str, Any]] = []
            for sub in reply_children:
                if len(replies) >= max_replies:
                    break
                if sub.get("kind") != "t1":
                    continue
                sub_data = sub.get("data", {})
                sub_body = sub_data.get("body") or ""
                if sub_body.strip() in _REMOVED_BODIES:
                    continue
                replies.append(
                    {
                        "author": sub_data.get("author") or "",
                        "text": _truncate(sub_body),
                    }
                )

            roots.append(
                {
                    "author": data.get("author") or "",
                    "text": _truncate(body),
                    "replies": replies,
                }
            )
        return roots
    finally:
        if owns_client:
            client.close()

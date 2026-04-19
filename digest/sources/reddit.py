"""Reddit candidate fetcher (RSS) + comment-tree fetcher (public JSON).

Uses Reddit's unauthenticated endpoints with an identifying User-Agent.
Set ``REDDIT_USERNAME`` in .env so the UA references your account — that
avoids the generic-scraper 403s. Example UA:

    ai-digest/0.1 by u/yourname

RSS endpoint (``/r/{sub}/top/.rss?t=day``) returns 25 top-today posts but
omits points + comment counts; they show as 0 until we swap in OAuth.
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import httpx

from digest.config import (
    COMMENT_TOKEN_CAP,
    REDDIT_POSTS_PER_SUB,
    REPLIES_PER_TOP_COMMENT,
    SUBREDDITS,
    TOP_COMMENTS_PER_POST,
    yesterday_window_utc,
)

logger = logging.getLogger(__name__)

REDDIT_RSS_URL = "https://www.reddit.com/r/{sub}/top/.rss"
REDDIT_POST_URL = "https://www.reddit.com{permalink}"
REDDIT_PERMALINK_JSON = "https://www.reddit.com{permalink}.json"

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_COMMENT_CHAR_CAP = COMMENT_TOKEN_CAP * 4
_REMOVED_BODIES = {"[removed]", "[deleted]", ""}


def _user_agent() -> str:
    username = (os.getenv("REDDIT_USERNAME") or "").strip().lstrip("u/").lstrip("/")
    if username:
        return f"ai-digest/0.1 by u/{username}"
    return "ai-digest/0.1"


def _build_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": _user_agent()}, timeout=15.0
    )


def _parse_rss(xml_text: str, sub: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Reddit RSS parse error for %s: %s", sub, exc)
        return []

    items: list[dict[str, Any]] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        id_el = entry.find(f"{_ATOM_NS}id")
        raw_id = (id_el.text or "").strip() if id_el is not None else ""
        post_id = raw_id[3:] if raw_id.startswith("t3_") else raw_id
        if not post_id:
            continue

        title_el = entry.find(f"{_ATOM_NS}title")
        title = (title_el.text or "").strip() if title_el is not None else ""

        link_el = entry.find(f"{_ATOM_NS}link")
        reddit_url = link_el.get("href", "") if link_el is not None else ""

        permalink = ""
        if reddit_url.startswith("https://www.reddit.com"):
            permalink = reddit_url[len("https://www.reddit.com"):]

        pub_el = entry.find(f"{_ATOM_NS}published")
        created_at_i = 0
        if pub_el is not None and pub_el.text:
            try:
                dt = datetime.fromisoformat(
                    pub_el.text.replace("Z", "+00:00")
                )
                created_at_i = int(dt.timestamp())
            except ValueError:
                pass

        items.append(
            {
                "id": post_id,
                "title": title,
                "url": reddit_url,
                "points": 0,
                "num_comments": 0,
                "created_at_i": created_at_i,
                "subreddit": sub,
                "permalink": permalink,
                "reddit_discussion_url": reddit_url,
                "source": "reddit",
            }
        )

    return items


def fetch_candidates(
    *,
    subreddits: tuple[str, ...] = SUBREDDITS,
    limit: int = REDDIT_POSTS_PER_SUB,
    window: tuple[int, int] | None = None,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Return each subreddit's posts created during ``window`` (default: yesterday UTC).

    Pulls ``t=week&limit=100`` from the RSS feed — enough cushion that
    yesterday's posts are almost always included — then filters client-side
    to the exact UTC calendar day. Reddit's RSS has no timestamp-range
    filter, so the client-side pass is unavoidable.
    """
    start, end = window or yesterday_window_utc()
    owns_client = client is None
    client = client or _build_client()

    candidates: list[dict[str, Any]] = []
    try:
        for sub in subreddits:
            try:
                resp = client.get(
                    REDDIT_RSS_URL.format(sub=sub),
                    params={"t": "week", "limit": 100},
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Reddit RSS %r failed: %s", sub, exc)
                continue
            in_window = [
                item
                for item in _parse_rss(resp.text, sub)
                if start <= item["created_at_i"] < end
            ]
            candidates.extend(in_window[:limit])
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
    """Return top ``max_roots`` comments with up to ``max_replies`` replies each."""
    owns_client = client is None
    client = client or _build_client()

    try:
        try:
            resp = client.get(
                REDDIT_PERMALINK_JSON.format(permalink=permalink)
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "Reddit comments for %s failed: %s", permalink, exc
            )
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

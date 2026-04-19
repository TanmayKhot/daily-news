"""HackerNews candidate fetcher + comment-tree fetcher."""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

import httpx

from digest.config import (
    AI_KEYWORDS,
    COMMENT_TOKEN_CAP,
    HN_CANDIDATES_WINDOW_HOURS,
    HN_HITS_PER_KEYWORD,
    REPLIES_PER_TOP_COMMENT,
    TOP_COMMENTS_PER_POST,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

ALGOLIA_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"
FIREBASE_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

# Roughly 4 chars/token for English text.
_COMMENT_CHAR_CAP = COMMENT_TOKEN_CAP * 4
_TAG_RE = re.compile(r"<[^>]+>")


def fetch_candidates(
    *,
    keywords: tuple[str, ...] = AI_KEYWORDS,
    window_hours: int = HN_CANDIDATES_WINDOW_HOURS,
    hits_per_keyword: int = HN_HITS_PER_KEYWORD,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Return AI-relevant HN stories posted in the last ``window_hours``.

    One Algolia query per keyword; results are merged and deduped by story id.
    """
    cutoff = int(time.time()) - window_hours * 3600
    owns_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=15.0
    )

    seen: dict[int, dict[str, Any]] = {}
    try:
        for kw in keywords:
            params = {
                "query": kw,
                "tags": "story",
                "numericFilters": f"created_at_i>{cutoff}",
                "hitsPerPage": hits_per_keyword,
            }
            try:
                resp = client.get(ALGOLIA_ENDPOINT, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("HN keyword %r failed: %s", kw, exc)
                continue

            for hit in resp.json().get("hits", []):
                story_id = hit.get("objectID")
                if not story_id:
                    continue
                story_id = int(story_id)
                if story_id in seen:
                    continue
                seen[story_id] = {
                    "id": story_id,
                    "title": hit.get("title") or "",
                    "url": hit.get("url") or HN_ITEM_URL.format(id=story_id),
                    "points": hit.get("points") or 0,
                    "num_comments": hit.get("num_comments") or 0,
                    "created_at_i": hit.get("created_at_i"),
                    "hn_discussion_url": HN_ITEM_URL.format(id=story_id),
                    "source": "hn",
                }
    finally:
        if owns_client:
            client.close()

    return list(seen.values())


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text)).strip()


def _truncate(text: str, limit: int = _COMMENT_CHAR_CAP) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _fetch_item(item_id: int, client: httpx.Client) -> dict[str, Any] | None:
    try:
        resp = client.get(FIREBASE_ITEM.format(id=item_id))
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("HN item %s fetch failed: %s", item_id, exc)
        return None
    data = resp.json()
    if not data or data.get("deleted") or data.get("dead"):
        return None
    return data


def fetch_comments(
    story_id: int,
    *,
    max_roots: int = TOP_COMMENTS_PER_POST,
    max_replies: int = REPLIES_PER_TOP_COMMENT,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Return top ``max_roots`` comments with up to ``max_replies`` replies each.

    HN's kids array is already ordered by HN's ranking, so we take it as-is.
    Each comment's text is truncated to ``COMMENT_TOKEN_CAP`` tokens.
    """
    owns_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=15.0
    )

    try:
        story = _fetch_item(int(story_id), client)
        if not story:
            return []

        roots: list[dict[str, Any]] = []
        for kid_id in (story.get("kids") or []):
            if len(roots) >= max_roots:
                break
            kid = _fetch_item(kid_id, client)
            if not kid or not kid.get("text"):
                continue

            replies: list[dict[str, Any]] = []
            for reply_id in (kid.get("kids") or []):
                if len(replies) >= max_replies:
                    break
                reply = _fetch_item(reply_id, client)
                if not reply or not reply.get("text"):
                    continue
                replies.append(
                    {
                        "author": reply.get("by", ""),
                        "text": _truncate(_clean(reply["text"])),
                    }
                )

            roots.append(
                {
                    "author": kid.get("by", ""),
                    "text": _truncate(_clean(kid["text"])),
                    "replies": replies,
                }
            )
        return roots
    finally:
        if owns_client:
            client.close()

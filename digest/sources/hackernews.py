"""HackerNews candidate fetcher via Algolia's search_by_date API."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from digest.config import (
    AI_KEYWORDS,
    HN_CANDIDATES_WINDOW_HOURS,
    HN_HITS_PER_KEYWORD,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

ALGOLIA_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"


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

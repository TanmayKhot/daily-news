"""Top 5 HN stories over last 24h from /best?h=24 → enriched + summarized."""

from __future__ import annotations

import logging
import re

import httpx
from dotenv import load_dotenv

from digest.config import USER_AGENT
from digest.enrich import default_cache_path, enrich
from digest.summarize import summarize_all

HN_BEST_URL = "https://news.ycombinator.com/best?h=24"
FIREBASE_ITEM = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"

_ATHING_RE = re.compile(
    r'<tr class=["\']athing submission["\'] id=["\'](\d+)["\']'
)


def fetch_best_24h(limit: int = 5) -> list[dict]:
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15.0)
    try:
        resp = client.get(HN_BEST_URL)
        resp.raise_for_status()
        ids = [int(x) for x in _ATHING_RE.findall(resp.text)[:limit]]

        stories: list[dict] = []
        for story_id in ids:
            item_resp = client.get(FIREBASE_ITEM.format(id=story_id))
            item_resp.raise_for_status()
            item = item_resp.json() or {}
            stories.append(
                {
                    "id": story_id,
                    "title": item.get("title") or "",
                    "url": item.get("url") or HN_ITEM_URL.format(id=story_id),
                    "points": item.get("score") or 0,
                    "num_comments": item.get("descendants") or 0,
                    "created_at_i": item.get("time"),
                    "hn_discussion_url": HN_ITEM_URL.format(id=story_id),
                    "source": "hn",
                }
            )
        return stories
    finally:
        client.close()


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()

    top = fetch_best_24h(limit=5)
    enriched = enrich(top, cache_path=default_cache_path())
    summarized = summarize_all(enriched)

    for story in summarized:
        print(story["title"])
        print()
        print(story["hn_discussion_url"])
        print()
        print(story["article_summary"])
        print()
        print(story["discussion_summary"])
        print()
        print()


if __name__ == "__main__":
    main()

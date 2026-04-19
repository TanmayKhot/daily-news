"""Enrich classified stories with article body + comment tree.

Results are cached to ``data/runs/{YYYY-MM-DD}.json`` so reruns during
development don't hammer the source APIs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import trafilatura

from digest.config import USER_AGENT
from digest.sources import hackernews, reddit

logger = logging.getLogger(__name__)

ARTICLE_UNAVAILABLE = "[article body unavailable]"
ARTICLE_MAX_CHARS = 20_000
RUNS_DIR = Path("data/runs")


def fetch_article(url: str) -> str | None:
    """Return clean article text, or None when fetching/extraction fails."""
    if not url:
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as exc:
        logger.warning("article fetch error for %s: %s", url, exc)
        return None
    if not downloaded:
        logger.info("article fetch returned nothing for %s", url)
        return None
    text = trafilatura.extract(downloaded, include_comments=False)
    if not text:
        logger.info("trafilatura extracted nothing from %s", url)
        return None
    return text[:ARTICLE_MAX_CHARS]


def _cache_key(story: dict[str, Any]) -> str:
    return f"{story['source']}:{story['id']}"


def enrich(
    stories: list[dict[str, Any]],
    *,
    cache_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Enrich each story in ``stories`` with article body + comment tree.

    If ``cache_path`` is given, results for each story are read from / written
    to that JSON file keyed by ``"{source}:{id}"``.
    """
    cache: dict[str, Any] = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("could not load cache %s: %s", cache_path, exc)
            cache = {}

    client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15.0)
    enriched: list[dict[str, Any]] = []
    try:
        for story in stories:
            key = _cache_key(story)
            if key in cache:
                logger.info("cache hit %s", key)
                enriched.append(cache[key])
                continue

            body = fetch_article(story.get("url", ""))

            if story["source"] == "hn":
                comments = hackernews.fetch_comments(story["id"], client=client)
            elif story["source"] == "reddit":
                comments = reddit.fetch_comments(story["permalink"], client=client)
            else:
                logger.warning("unknown source %r on story %s", story.get("source"), key)
                comments = []

            merged = {
                **story,
                "article_body": body or ARTICLE_UNAVAILABLE,
                "article_available": body is not None,
                "comments": comments,
            }
            cache[key] = merged
            enriched.append(merged)
    finally:
        client.close()

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False))

    return enriched


def default_cache_path() -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return RUNS_DIR / f"{date}.json"


def main() -> None:
    from dotenv import load_dotenv

    from digest.classify import rank_and_filter
    from digest.sources import hackernews as hn_src
    from digest.sources import reddit as rd_src

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()

    pool = hn_src.fetch_candidates() + rd_src.fetch_candidates()
    top = rank_and_filter(pool)
    print(f"Enriching {len(top)} stories...")
    enriched = enrich(top, cache_path=default_cache_path())

    for story in enriched:
        tag = (
            "[HN]"
            if story["source"] == "hn"
            else f"[r/{story.get('subreddit')}]"
        )
        body = story["article_body"]
        status = "ok" if story["article_available"] else "unavailable"
        print(f"\n{tag} {story['title']}")
        print(f"  article: {status}, {len(body)} chars")
        print(f"  comments: {len(story['comments'])} roots")
        for root in story["comments"][:2]:
            preview = root["text"][:120].replace("\n", " ")
            print(f"    - {root['author']}: {preview}")
            for reply in root.get("replies", [])[:1]:
                rpreview = reply["text"][:100].replace("\n", " ")
                print(f"      > {reply['author']}: {rpreview}")


if __name__ == "__main__":
    main()

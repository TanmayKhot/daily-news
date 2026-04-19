"""Top 5 posts from r/singularity (past 24h) → enriched + summarized."""

from __future__ import annotations

import logging

from dotenv import load_dotenv

from digest.enrich import default_cache_path, enrich
from digest.sources import reddit as rd_src
from digest.summarize import summarize_all


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()

    candidates = rd_src.fetch_candidates(
        subreddits=("singularity",),
        limit=25,
        time_window="day",
    )
    candidates.sort(key=lambda c: c.get("points", 0), reverse=True)
    top = candidates[:5]
    enriched = enrich(top, cache_path=default_cache_path())
    summarized = summarize_all(enriched)

    for story in summarized:
        print(story["title"])
        print()
        print(story["reddit_discussion_url"])
        print()
        print(story["article_summary"])
        print()
        print(story["discussion_summary"])
        print()
        print()


if __name__ == "__main__":
    main()

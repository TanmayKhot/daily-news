"""Summarize articles + discussions concurrently via AsyncAnthropic.

Per story we make two calls: one for the article body, one for the comment
tree. System prompts are marked ``cache_control: ephemeral`` — Haiku's
minimum cacheable prefix is ~4K tokens so these will not actually cache,
but the marker is a no-op when the prefix is too short.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from anthropic import AsyncAnthropic

from digest.config import MODEL_ID

logger = logging.getLogger(__name__)

ARTICLE_UNAVAILABLE_SUMMARY = "[article body unavailable]"
NO_DISCUSSION_PLACEHOLDER = "No discussion yet."
SUMMARY_MAX_TOKENS = 400

ARTICLE_SYSTEM = (
    "You write tight, factual summaries of news articles and posts for a "
    "daily digest. Output 3-5 markdown bullet points (one concrete fact, "
    "claim, number, or announcement per bullet). No heading, no preamble, "
    "no trailing prose, no meta-commentary about whether the piece fits a "
    "topic — just the bullets. Do not restate the title. If the body is "
    "thin or mostly boilerplate, output one or two bullets covering what "
    "little is there."
)

DISCUSSION_SYSTEM = (
    "You summarize discussion threads. Output 3-5 markdown bullet points "
    "covering points of agreement, points of disagreement, and any "
    "notable contrarian or expert takes (one idea per bullet). No "
    "heading, no preamble, no trailing prose. Do not quote comments "
    "verbatim. Do not invent positions that weren't expressed."
)


def _system_with_cache(text: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _format_comments(comments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, root in enumerate(comments, 1):
        lines.append(f"[{i}] {root.get('author', '')}: {root.get('text', '')}")
        for reply in root.get("replies", []):
            lines.append(
                f"    > {reply.get('author', '')}: {reply.get('text', '')}"
            )
    return "\n".join(lines)


async def _summarize_article(
    client: AsyncAnthropic, title: str, url: str, body: str
) -> str:
    user = (
        f"Title: {title}\n"
        f"URL: {url}\n\n"
        f"Article body:\n{body}"
    )
    resp = await client.messages.create(
        model=MODEL_ID,
        max_tokens=SUMMARY_MAX_TOKENS,
        system=_system_with_cache(ARTICLE_SYSTEM),
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


async def _summarize_discussion(
    client: AsyncAnthropic, title: str, comments: list[dict[str, Any]]
) -> str:
    user = (
        f"Story title: {title}\n\n"
        f"Comments:\n{_format_comments(comments)}"
    )
    resp = await client.messages.create(
        model=MODEL_ID,
        max_tokens=SUMMARY_MAX_TOKENS,
        system=_system_with_cache(DISCUSSION_SYSTEM),
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


async def _article_for(
    client: AsyncAnthropic, story: dict[str, Any]
) -> str:
    if not story.get("article_available"):
        return ARTICLE_UNAVAILABLE_SUMMARY
    try:
        return await _summarize_article(
            client,
            story.get("title", ""),
            story.get("url", ""),
            story.get("article_body", ""),
        )
    except Exception as exc:
        logger.warning(
            "article summary failed for %s:%s: %s",
            story.get("source"),
            story.get("id"),
            exc,
        )
        return ARTICLE_UNAVAILABLE_SUMMARY


async def _discussion_for(
    client: AsyncAnthropic, story: dict[str, Any]
) -> str:
    comments = story.get("comments") or []
    if not comments:
        return NO_DISCUSSION_PLACEHOLDER
    try:
        return await _summarize_discussion(
            client, story.get("title", ""), comments
        )
    except Exception as exc:
        logger.warning(
            "discussion summary failed for %s:%s: %s",
            story.get("source"),
            story.get("id"),
            exc,
        )
        return NO_DISCUSSION_PLACEHOLDER


async def summarize_all_async(
    stories: list[dict[str, Any]],
    *,
    client: AsyncAnthropic | None = None,
) -> list[dict[str, Any]]:
    """Summarize all stories concurrently. Each gets ``article_summary`` +
    ``discussion_summary`` added in-place on a copy.
    """
    if not stories:
        return []

    owns_client = client is None
    client = client or AsyncAnthropic()

    try:
        tasks: list[asyncio.Future[str]] = []
        for story in stories:
            tasks.append(asyncio.ensure_future(_article_for(client, story)))
            tasks.append(asyncio.ensure_future(_discussion_for(client, story)))

        results = await asyncio.gather(*tasks)
    finally:
        if owns_client:
            await client.close()

    out: list[dict[str, Any]] = []
    for i, story in enumerate(stories):
        out.append(
            {
                **story,
                "article_summary": results[2 * i],
                "discussion_summary": results[2 * i + 1],
            }
        )
    return out


def summarize_all(
    stories: list[dict[str, Any]],
    *,
    client: AsyncAnthropic | None = None,
) -> list[dict[str, Any]]:
    """Sync wrapper around :func:`summarize_all_async`."""
    return asyncio.run(summarize_all_async(stories, client=client))


def main() -> None:
    from dotenv import load_dotenv

    from digest.classify import rank_and_filter
    from digest.enrich import default_cache_path, enrich
    from digest.sources import hackernews as hn_src
    from digest.sources import reddit as rd_src

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()

    pool = hn_src.fetch_candidates() + rd_src.fetch_candidates()
    top = rank_and_filter(pool)
    enriched = enrich(top, cache_path=default_cache_path())
    print(f"Summarizing {len(enriched)} stories...")
    summarized = summarize_all(enriched)

    for story in summarized:
        tag = (
            "[HN]"
            if story["source"] == "hn"
            else f"[r/{story.get('subreddit')}]"
        )
        print(f"\n{tag} {story['title']}")
        print(f"  article:    {story['article_summary']}")
        print(f"  discussion: {story['discussion_summary']}")


if __name__ == "__main__":
    main()

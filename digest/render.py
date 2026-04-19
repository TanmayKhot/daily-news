"""Render digest stories into an HTML email + generate the top-of-email TL;DR."""

from __future__ import annotations

import html as html_lib
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from jinja2 import Environment, FileSystemLoader, select_autoescape

from digest.config import MODEL_ID

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
SUBJECT_TITLE_MAX = 70

TLDR_SYSTEM = (
    "You write a tight 3-bullet TL;DR for a daily tech digest. Given the "
    "list of story summaries below, produce exactly 3 markdown bullet "
    "points capturing the most important overall signals for the day "
    "(new releases, notable benchmarks, business moves, shifts in "
    "discussion). No heading, no preamble, no trailing prose. One "
    "concrete signal per bullet."
)


def _format_stories_for_tldr(stories: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, s in enumerate(stories, 1):
        lines.append(f"{i}. [{_source_tag(s)}] {s['title']}")
        lines.append(f"   article: {s.get('article_summary', '')}")
        lines.append(f"   discussion: {s.get('discussion_summary', '')}")
        lines.append("")
    return "\n".join(lines)


def generate_tldr(
    stories: list[dict[str, Any]],
    *,
    client: Anthropic | None = None,
) -> list[str]:
    """Call Haiku once over the full summary set → 3 markdown bullets."""
    if not stories:
        return []
    client = client or Anthropic()
    resp = client.messages.create(
        model=MODEL_ID,
        max_tokens=600,
        system=TLDR_SYSTEM,
        messages=[
            {"role": "user", "content": _format_stories_for_tldr(stories)}
        ],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    bullets = [
        line[2:].strip()
        for line in text.split("\n")
        if line.strip().startswith("- ")
    ]
    return bullets[:3]


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")


def _inline_md(s: str) -> str:
    escaped = html_lib.escape(s, quote=False)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = _CODE_RE.sub(
        r"<code style='background:#f4f4f4;padding:1px 4px;border-radius:3px;'>\1</code>",
        escaped,
    )
    return escaped


def _md_to_html(md: str) -> str:
    """Turn bullet-heavy markdown into a <ul> (or <p> fallback)."""
    if not md:
        return ""
    lines = [l.rstrip() for l in md.strip().split("\n") if l.strip()]
    if lines and all(l.lstrip().startswith("- ") for l in lines):
        items = [_inline_md(l.lstrip()[2:].strip()) for l in lines]
        return (
            "<ul style='padding-left: 20px; margin: 4px 0 0;'>"
            + "".join(
                f"<li style='margin-bottom:6px;'>{i}</li>" for i in items
            )
            + "</ul>"
        )
    return f"<p style='margin:4px 0 0;'>{_inline_md(' '.join(lines))}</p>"


def _source_tag(story: dict[str, Any]) -> str:
    if story.get("source") == "hn":
        return "[HN]"
    return f"[r/{story.get('subreddit', '?')}]"


def _discussion_url(story: dict[str, Any]) -> str:
    return (
        story.get("hn_discussion_url")
        or story.get("reddit_discussion_url")
        or ""
    )


def _age(ts: int | None) -> str:
    if not ts:
        return ""
    delta = int(time.time()) - int(ts)
    if delta < 0:
        return ""
    hours = delta // 3600
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def render_email(
    stories: list[dict[str, Any]],
    tldr: list[str],
    *,
    date: str,
) -> tuple[str, str]:
    """Return ``(subject, html_body)`` ready to ship."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2", "html.j2"]),
    )
    template = env.get_template("email.html.j2")

    prepared = [
        {
            "title": s["title"],
            "url": s.get("url", ""),
            "discussion_url": _discussion_url(s),
            "source_tag": _source_tag(s),
            "points": s.get("points", 0),
            "num_comments": s.get("num_comments", 0),
            "age": _age(s.get("created_at_i")),
            "article_summary_html": _md_to_html(
                s.get("article_summary", "")
            ),
            "discussion_summary_html": _md_to_html(
                s.get("discussion_summary", "")
            ),
        }
        for s in stories
    ]

    top_title = stories[0]["title"] if stories else "(no stories)"
    subject = f"AI Digest — {date} — {top_title[:SUBJECT_TITLE_MAX]}"

    html_body = template.render(
        date=date,
        tldr=tldr,
        stories=prepared,
        generated_at=datetime.now(tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        ),
    )
    return subject, html_body

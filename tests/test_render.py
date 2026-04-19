"""Unit tests for render: no network, no Anthropic calls."""

from __future__ import annotations

from digest.render import _md_to_html, render_email


def test_md_to_html_bullets():
    md = "- first bullet\n- second **bold** bullet\n- third"
    html = _md_to_html(md)
    assert html.startswith("<ul")
    assert "<li" in html
    assert "<strong>bold</strong>" in html
    assert "third" in html


def test_md_to_html_escapes_html():
    md = "- <script>alert(1)</script>"
    html = _md_to_html(md)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_md_to_html_non_bullets_fallback():
    md = "This is a single paragraph with no bullets."
    html = _md_to_html(md)
    assert html.startswith("<p")
    assert "single paragraph" in html


def test_md_to_html_empty():
    assert _md_to_html("") == ""


def _story(
    source: str,
    title: str,
    *,
    story_id: int = 1,
    subreddit: str | None = None,
    article: str = "- article bullet",
    discussion: str = "- discussion bullet",
) -> dict:
    return {
        "id": story_id,
        "source": source,
        "title": title,
        "url": f"https://example.com/{story_id}",
        "points": 123,
        "num_comments": 45,
        "created_at_i": None,
        "hn_discussion_url": (
            f"https://news.ycombinator.com/item?id={story_id}"
            if source == "hn"
            else None
        ),
        "reddit_discussion_url": (
            f"https://reddit.com/r/{subreddit}/comments/x/"
            if source == "reddit"
            else None
        ),
        "subreddit": subreddit,
        "article_summary": article,
        "discussion_summary": discussion,
    }


def test_render_email_contains_core_pieces():
    stories = [
        _story("hn", "Anthropic ships Claude Opus 4.7"),
        _story(
            "reddit",
            "LocalLLaMA: new quantization beats AWQ",
            story_id=2,
            subreddit="LocalLLaMA",
        ),
    ]
    tldr = ["Opus 4.7 released", "New quant released", "Third bullet"]

    subject, body = render_email(stories, tldr, date="2026-04-19")

    assert subject.startswith("AI Digest — 2026-04-19 — ")
    assert "Anthropic ships Claude Opus 4.7" in subject

    assert "TL;DR" in body
    assert "Opus 4.7 released" in body

    assert "[HN]" in body
    assert "[r/LocalLLaMA]" in body
    assert "Anthropic ships Claude Opus 4.7" in body
    assert "LocalLLaMA: new quantization beats AWQ" in body
    assert "news.ycombinator.com/item?id=1" in body
    assert "reddit.com/r/LocalLLaMA" in body
    assert "article bullet" in body
    assert "discussion bullet" in body

    # The HN story title itself must link to the HN discussion URL, not
    # the external article URL on example.com.
    import re

    hn_anchor = re.search(
        r'<a href="([^"]+)"[^>]*>Anthropic ships Claude Opus 4\.7</a>', body
    )
    assert hn_anchor is not None, "HN title anchor not found in body"
    assert "news.ycombinator.com/item?id=1" in hn_anchor.group(1)
    assert "example.com" not in hn_anchor.group(1)


def test_render_email_no_tldr_section_when_empty():
    stories = [_story("hn", "Only story")]
    subject, body = render_email(stories, [], date="2026-04-19")
    assert "Only story" in body
    assert "TL;DR" not in body

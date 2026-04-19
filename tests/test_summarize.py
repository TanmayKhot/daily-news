"""Tests for the summarizer. Empty-comments/no-article paths don't hit the API."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from digest.summarize import (
    ARTICLE_UNAVAILABLE_SUMMARY,
    NO_DISCUSSION_PLACEHOLDER,
    summarize_all,
)

load_dotenv()

_HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))


def test_placeholders_used_without_api_calls():
    """When both article + comments are missing, no API call is needed."""
    stories = [
        {
            "id": 1,
            "source": "hn",
            "title": "Some story",
            "url": "https://example.com/x",
            "article_body": "[article body unavailable]",
            "article_available": False,
            "comments": [],
        }
    ]

    # No client passed — if the code tried to instantiate AsyncAnthropic
    # without an API key it would raise. With _HAS_KEY we still shouldn't
    # actually make network calls; just verify the placeholder outputs.
    if not _HAS_KEY:
        # Can't construct default client without a key.
        pytest.skip("ANTHROPIC_API_KEY not set; skipping constructor path")

    out = summarize_all(stories)
    assert len(out) == 1
    assert out[0]["article_summary"] == ARTICLE_UNAVAILABLE_SUMMARY
    assert out[0]["discussion_summary"] == NO_DISCUSSION_PLACEHOLDER


def test_empty_input_returns_empty():
    assert summarize_all([]) == []


@pytest.mark.skipif(
    not _HAS_KEY, reason="ANTHROPIC_API_KEY not set; skipping live Anthropic test"
)
def test_article_and_discussion_summaries_have_content():
    """End-to-end: real article + comments → non-empty 2-3 sentence summaries."""
    stories = [
        {
            "id": 42,
            "source": "hn",
            "title": "Anthropic releases Claude Opus 4.7",
            "url": "https://example.com/claude-4-7",
            "article_body": (
                "Anthropic today announced Claude Opus 4.7, its most "
                "capable model yet. The release focuses on longer-running "
                "agentic tasks, with new adaptive thinking controls and a "
                "1M-token context window. Benchmarks on SWE-bench Verified "
                "show a 7-point jump over the previous Opus 4.6."
            ),
            "article_available": True,
            "comments": [
                {
                    "author": "alice",
                    "text": "The SWE-bench jump is real; we tested it on our internal repo.",
                    "replies": [
                        {
                            "author": "bob",
                            "text": "Same. Tool use is noticeably more reliable.",
                        }
                    ],
                },
                {
                    "author": "carol",
                    "text": "Price is still steep for high-volume workloads though.",
                    "replies": [],
                },
            ],
        }
    ]

    out = summarize_all(stories)
    assert len(out) == 1
    article = out[0]["article_summary"]
    discussion = out[0]["discussion_summary"]

    assert isinstance(article, str) and len(article) > 40
    assert isinstance(discussion, str) and len(discussion) > 40
    assert article != ARTICLE_UNAVAILABLE_SUMMARY
    assert discussion != NO_DISCUSSION_PLACEHOLDER

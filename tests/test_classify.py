"""Integration test: mixed batch with obvious non-AI stories should be filtered."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from digest.classify import rank_and_filter

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live Anthropic test",
)


MIXED_CANDIDATES = [
    {
        "id": "ai1",
        "title": "Anthropic releases Claude Opus 4.7 with improved reasoning",
        "url": "https://example.com/claude-4-7",
        "points": 800,
        "num_comments": 200,
        "source": "hn",
    },
    {
        "id": "ai2",
        "title": "Paper: mixture-of-experts LLM trained on 2T tokens beats GPT-4 on MMLU",
        "url": "https://arxiv.org/abs/2601.12345",
        "points": 320,
        "num_comments": 90,
        "source": "hn",
    },
    {
        "id": "noise1",
        "title": "New Apple M5 chip announced, also mentions on-device AI in paragraph nine",
        "url": "https://example.com/apple-m5",
        "points": 1200,
        "num_comments": 400,
        "source": "hn",
    },
    {
        "id": "noise2",
        "title": "Stripe raises Series I funding at $90B valuation",
        "url": "https://example.com/stripe",
        "points": 600,
        "num_comments": 150,
        "source": "hn",
    },
    {
        "id": "noise3",
        "title": "Why I switched from Vim to Helix",
        "url": "https://example.com/helix",
        "points": 400,
        "num_comments": 220,
        "source": "hn",
    },
    {
        "id": "ai3",
        "title": "OpenAI announces $10B deal to supply models to the US government",
        "url": "https://example.com/openai-gov",
        "points": 500,
        "num_comments": 180,
        "subreddit": "OpenAI",
        "source": "reddit",
    },
    {
        "id": "noise4",
        "title": "Rust 2.0 roadmap: what's changing in the next edition",
        "url": "https://example.com/rust-2",
        "points": 900,
        "num_comments": 500,
        "source": "hn",
    },
    {
        "id": "ai4",
        "title": "LocalLLaMA: running DeepSeek-V4 on a single 4090 via new quantization",
        "url": "https://reddit.com/r/LocalLLaMA/comments/x",
        "points": 250,
        "num_comments": 80,
        "subreddit": "LocalLLaMA",
        "source": "reddit",
    },
]


def _ids(selected: list[dict]) -> set[str]:
    return {(c["source"], str(c["id"])) for c in selected}


def test_obvious_non_ai_stories_are_filtered():
    top = rank_and_filter(MIXED_CANDIDATES)
    selected = _ids(top)

    # Clearly non-AI stories must not appear.
    for noise in (
        ("hn", "noise1"),  # Apple chip with AI in paragraph nine
        ("hn", "noise2"),  # Stripe funding
        ("hn", "noise3"),  # Vim to Helix
        ("hn", "noise4"),  # Rust 2.0
    ):
        assert noise not in selected, f"{noise} should have been filtered out"

    # AI-genuine stories should be present.
    for ai in (
        ("hn", "ai1"),
        ("hn", "ai2"),
        ("reddit", "ai3"),
        ("reddit", "ai4"),
    ):
        assert ai in selected, f"{ai} should have been ranked into the digest"


def test_empty_candidates_returns_empty():
    assert rank_and_filter([]) == []

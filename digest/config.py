"""Central constants for the digest pipeline."""

from __future__ import annotations

MODEL_ID = "claude-haiku-4-5-20251001"

RECIPIENT_EMAIL = "tnmykhot@gmail.com"

SUBREDDITS: tuple[str, ...] = (
    "MachineLearning",
    "LocalLLaMA",
    "singularity",
    "artificial",
    "OpenAI",
)

AI_KEYWORDS: tuple[str, ...] = (
    "AI",
    "LLM",
    "GPT",
    "Claude",
    "transformer",
    "agent",
    "diffusion",
    "neural",
    "model",
    "Anthropic",
    "OpenAI",
)

USER_AGENT = "ai-digest/0.1 by tnmykhot"

HN_CANDIDATES_WINDOW_HOURS = 24
HN_HITS_PER_KEYWORD = 20

REDDIT_POSTS_PER_SUB = 25

COMMENT_TOKEN_CAP = 500
TOP_COMMENTS_PER_POST = 5
REPLIES_PER_TOP_COMMENT = 2

FINAL_DIGEST_SIZE = 10

BREVO_SMTP_HOST = "smtp-relay.brevo.com"
BREVO_SMTP_PORT = 587

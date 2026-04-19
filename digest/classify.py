"""Score candidate stories for AI relevance via a single Haiku call."""

from __future__ import annotations

import logging
from typing import Any

from anthropic import Anthropic

from digest.config import FINAL_DIGEST_SIZE, MODEL_ID

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 6

SYSTEM_PROMPT = """You score candidate stories for a daily AI-news digest.

Rate each story's RELEVANCE to artificial intelligence, machine learning,
LLMs, or the AI industry on a 0-10 scale:

  0-3  Unrelated to AI, or only mentions AI incidentally
  4-5  Has an AI angle but that isn't the main point
  6-7  Genuinely about AI; moderate significance
  8-9  Notable AI news: release, benchmark, paper, acquisition, policy
   10  Major AI development

Heuristics:
- A hardware/chip story that mentions "AI workloads" in one paragraph: NOT AI news.
- A layoffs/business story that blames AI in passing: NOT AI news.
- A new model, paper, agent framework, eval, dataset, or tool: IS AI news.
- AI-industry business news (funding, acquisitions, regulation): IS AI news.

Return a score for EVERY candidate, using the submit_scores tool."""

_TOOL = {
    "name": "submit_scores",
    "description": "Submit AI-relevance scores for all candidate stories.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "source": {
                            "type": "string",
                            "enum": ["hn", "reddit"],
                        },
                        "score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 10,
                        },
                    },
                    "required": ["id", "source", "score"],
                },
            },
        },
        "required": ["scores"],
    },
}


def _format_candidates(candidates: list[dict[str, Any]]) -> str:
    lines = []
    for c in candidates:
        source = c["source"]
        tag = f"r/{c['subreddit']}" if source == "reddit" else "HN"
        url = c.get("url") or ""
        lines.append(
            f"- id={c['id']} source={source} [{tag}] | {c['title']} | {url}"
        )
    return "\n".join(lines)


def rank_and_filter(
    candidates: list[dict[str, Any]],
    *,
    threshold: int = RELEVANCE_THRESHOLD,
    max_results: int = FINAL_DIGEST_SIZE,
    client: Anthropic | None = None,
) -> list[dict[str, Any]]:
    """Score candidates and return the top ``max_results`` with score >= threshold.

    Ranking: primary key = relevance score (desc), tiebreak = upvotes (desc).
    """
    if not candidates:
        return []

    client = client or Anthropic()

    resp = client.messages.create(
        model=MODEL_ID,
        max_tokens=16384,
        system=SYSTEM_PROMPT,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "submit_scores"},
        messages=[
            {
                "role": "user",
                "content": "Candidates:\n" + _format_candidates(candidates),
            }
        ],
    )

    scores_payload: dict[str, Any] | None = None
    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_scores":
            scores_payload = block.input
            break
    if not scores_payload:
        raise RuntimeError(
            f"classify: no submit_scores tool_use in response "
            f"(stop_reason={resp.stop_reason}, blocks={[b.type for b in resp.content]})"
        )

    score_map: dict[tuple[str, str], int] = {}
    for entry in scores_payload.get("scores", []):
        key = (entry["source"], str(entry["id"]))
        score_map[key] = int(entry["score"])

    scored: list[dict[str, Any]] = []
    for c in candidates:
        key = (c["source"], str(c["id"]))
        score = score_map.get(key)
        if score is None:
            logger.warning("no score returned for %s", key)
            continue
        if score < threshold:
            continue
        scored.append({**c, "relevance_score": score})

    scored.sort(
        key=lambda c: (c["relevance_score"], c.get("points", 0)),
        reverse=True,
    )
    return scored[:max_results]


def main() -> None:
    from dotenv import load_dotenv

    from digest.sources import hackernews, reddit

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()

    hn = hackernews.fetch_candidates()
    rd = reddit.fetch_candidates()
    pool = hn + rd
    print(f"Fetched {len(hn)} HN + {len(rd)} Reddit = {len(pool)} candidates")

    top = rank_and_filter(pool)
    print(f"\nTop {len(top)} AI stories (threshold={RELEVANCE_THRESHOLD}):\n")
    for i, c in enumerate(top, 1):
        tag = "[HN]" if c["source"] == "hn" else f"[r/{c.get('subreddit')}]"
        print(
            f"{i:>2}. {tag} score={c['relevance_score']} "
            f"pts={c.get('points', 0)} comments={c.get('num_comments', 0)}"
        )
        print(f"    {c['title']}")
        print(f"    {c.get('url', '')}")


if __name__ == "__main__":
    main()

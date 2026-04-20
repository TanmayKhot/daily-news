# daily-news

A daily AI-news digest pipeline. Fetches yesterday's top posts from Hacker
News and a set of subreddits, ranks them for AI relevance, summarizes the
article + discussion with Claude Haiku, and emails a single HTML digest.

**Live sample:** <https://tanmaykhot.github.io/daily-news/> — a real
rendered digest, exactly as it arrives in the inbox. Source at
[`docs/index.html`](docs/index.html).

## Features

- **LLM summarization** — each story gets two independent summaries: a
  3-5 bullet breakdown of the article itself and a separate summary of
  the comment thread (points of agreement, disagreement, corrections).
  Summaries fan out in parallel via `AsyncAnthropic`, so the full 10-story
  run finishes in seconds.
- **TL;DR at the top** — a second Haiku pass across all 10 summaries
  produces a 3-bullet overview of the day.
- **Modular topics** — edit `config.toml` to change what gets pulled:

  ```toml
  [hackernews]
  topics = ["AI", "LLM", "Claude", "Anthropic", ...]

  [reddit]
  subreddits = ["MachineLearning", "LocalLLaMA", ...]
  ```

  Adding a new keyword or sub requires no code change.
- **Yesterday-only window** — queries are pinned to the previous UTC
  calendar day, so each digest is a clean non-overlapping slice.
- **Dedup across runs** — a local SQLite table records every sent story;
  the next day's run skips anything already delivered.
- **Runs log** — every run (success or failure) is recorded with status +
  error message for after-the-fact debugging.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY + Brevo SMTP creds
```

## Run

```bash
python -m digest.run --dry-run   # render to stdout, no email
python -m digest.run              # send for real
```

## Project layout

```
digest/
  sources/      # hackernews.py, reddit.py
  classify.py   # Haiku-scored ranker
  enrich.py     # article body + comment tree
  summarize.py  # async article + discussion summaries
  render.py     # Jinja2 HTML + TL;DR
  dedup.py      # SQLite seen_stories
  send.py       # Brevo SMTP + run log
  run.py        # orchestrator
config.toml     # user-editable topic + subreddit lists
templates/      # email template
tests/          # pytest, no network
```

Stack: Python 3.11+, Anthropic SDK, httpx, trafilatura, Jinja2, SQLite.

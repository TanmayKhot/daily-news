# CLAUDE.md

Daily AI-news digest pipeline. Cron job → fetch HN + Reddit → summarize via
Claude Haiku → email. See `plan.txt` for design and phase ordering.

## Project structure

```
daily-news/
  digest/
    config.py          # constants (subreddits, keywords, model id, recipient)
    sources/           # one file per source (hackernews.py, reddit.py)
    classify.py        # rank candidates → top 10
    enrich.py          # article body + comment trees
    summarize.py       # article + discussion summaries
    render.py          # Jinja2 → HTML email
    send.py            # SMTP send + log
    dedup.py           # SQLite seen-stories table
    run.py             # orchestrator (entry point)
  templates/           # Jinja2 email templates
  data/                # SQLite + per-run JSON dumps (gitignored)
  tests/               # pytest, fixtures in tests/fixtures/
```

New source integrations go under `digest/sources/`. New LLM-driven steps
go as their own module under `digest/`.

## Conventions

- **Python 3.11+**, type hints on public functions.
- **HTTP:** `httpx`. Always set a User-Agent header (Reddit rejects requests
  without one).
- **LLM calls:** `anthropic` SDK. Use `AsyncAnthropic` + `asyncio.gather` for
  any step that fans out (e.g. summarizer). Always attach `cache_control` to
  reused system prompts.
- **Article extraction:** `trafilatura.extract()`.
- **Secrets:** loaded from `.env` via `python-dotenv`. Never hardcode.
- **Templating:** Jinja2 for email HTML.
- **Storage:** SQLite via stdlib `sqlite3`. No ORM.
- **Logging:** stdlib `logging`, INFO default, DEBUG via `--verbose`.
  No `print()` in library code — only in `run.py` for dry-run output.
- **Tests:** pytest. Live HN/Reddit calls are not allowed in tests; use
  fixtures. Live Anthropic calls in integration tests are fine (cheap on
  Haiku).

## Hard rules

- All code lives inside `daily-news/`. The parent directory
  (`/home/tanmay/Desktop/python-projects/hackernews/`) is for planning files
  only and is not under version control.
- Never commit `.env`, `data/digest.db`, or anything in `data/runs/`.
- Never silently ship a partial digest. If any pipeline step fails, exit
  non-zero and log the reason.
- Never hardcode the recipient email or model ID outside `digest/config.py`.
- Never add: web framework, dashboard, Docker, Playwright, Gmail labeling
  code, or a "future-sources" plugin abstraction. Refactor if/when actually
  needed.

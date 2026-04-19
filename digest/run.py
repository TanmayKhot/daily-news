"""Orchestrator: fetch → classify → enrich → summarize → render → (print|send)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from digest.classify import rank_and_filter
from digest.config import RECIPIENT_EMAIL
from digest.enrich import default_cache_path, enrich
from digest.render import generate_tldr, render_email
from digest.send import SendError, log_run, send_email
from digest.sources import hackernews as hn_src
from digest.sources import reddit as rd_src
from digest.summarize import summarize_all

logger = logging.getLogger(__name__)

FAILED_DIR = Path("data/runs")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the daily AI digest.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render to stdout; skip send and DB log.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable DEBUG logging."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    load_dotenv()

    date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    logger.info("fetching candidates")
    pool = hn_src.fetch_candidates() + rd_src.fetch_candidates()
    logger.info("got %d candidates", len(pool))

    top = rank_and_filter(pool)
    logger.info("classified → %d stories above threshold", len(top))
    if not top:
        logger.error("no stories survived classification; aborting")
        return 1

    enriched = enrich(top, cache_path=default_cache_path())
    summarized = summarize_all(enriched)
    tldr = generate_tldr(summarized)
    subject, html_body = render_email(summarized, tldr, date=date)

    if args.dry_run:
        print(f"Subject: {subject}")
        print()
        print(html_body)
        return 0

    password = os.getenv("GMAIL_APP_PASSWORD")
    sender = os.getenv("GMAIL_SENDER", RECIPIENT_EMAIL)
    if not password:
        logger.error(
            "GMAIL_APP_PASSWORD not set; writing failed-%s.html", date
        )
        FAILED_DIR.mkdir(parents=True, exist_ok=True)
        (FAILED_DIR / f"failed-{date}.html").write_text(
            html_body, encoding="utf-8"
        )
        log_run(
            run_id,
            len(summarized),
            "no_credentials",
            "GMAIL_APP_PASSWORD not set",
        )
        return 1

    try:
        send_email(
            subject,
            html_body,
            recipient=RECIPIENT_EMAIL,
            sender=sender,
            password=password,
        )
    except SendError as exc:
        logger.error("send failed: %s", exc)
        FAILED_DIR.mkdir(parents=True, exist_ok=True)
        (FAILED_DIR / f"failed-{date}.html").write_text(
            html_body, encoding="utf-8"
        )
        log_run(run_id, len(summarized), "failed", str(exc))
        return 1

    log_run(run_id, len(summarized), "sent")
    logger.info("digest sent to %s", RECIPIENT_EMAIL)
    return 0


if __name__ == "__main__":
    sys.exit(main())

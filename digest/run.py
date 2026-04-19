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
from digest.config import FINAL_DIGEST_SIZE, RECIPIENT_EMAIL
from digest.dedup import filter_unseen, mark_sent
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

    ranked = rank_and_filter(pool, max_results=FINAL_DIGEST_SIZE * 3)
    logger.info("classified → %d stories above threshold", len(ranked))
    if not ranked:
        logger.error("no stories survived classification; aborting")
        return 1

    unseen = filter_unseen(ranked)
    top = unseen[:FINAL_DIGEST_SIZE]
    if not top:
        logger.error("all ranked stories were already sent; aborting")
        return 1
    if len(top) < FINAL_DIGEST_SIZE:
        logger.warning(
            "only %d unseen stories available (wanted %d)",
            len(top),
            FINAL_DIGEST_SIZE,
        )

    enriched = enrich(top, cache_path=default_cache_path())
    summarized = summarize_all(enriched)
    tldr = generate_tldr(summarized)
    subject, html_body = render_email(summarized, tldr, date=date)

    if args.dry_run:
        print(f"Subject: {subject}")
        print()
        print(html_body)
        return 0

    smtp_login = os.getenv("BREVO_SMTP_LOGIN")
    smtp_key = os.getenv("BREVO_SMTP_KEY")
    sender = os.getenv("SENDER_EMAIL")
    missing = [
        name
        for name, value in (
            ("BREVO_SMTP_LOGIN", smtp_login),
            ("BREVO_SMTP_KEY", smtp_key),
            ("SENDER_EMAIL", sender),
        )
        if not value
    ]
    if missing:
        logger.error(
            "missing env vars %s; writing failed-%s.html", missing, date
        )
        FAILED_DIR.mkdir(parents=True, exist_ok=True)
        (FAILED_DIR / f"failed-{date}.html").write_text(
            html_body, encoding="utf-8"
        )
        log_run(
            run_id,
            len(summarized),
            "no_credentials",
            f"missing env vars: {missing}",
        )
        return 1

    try:
        send_email(
            subject,
            html_body,
            recipient=RECIPIENT_EMAIL,
            sender=sender,
            smtp_login=smtp_login,
            smtp_password=smtp_key,
        )
    except SendError as exc:
        logger.error("send failed: %s", exc)
        FAILED_DIR.mkdir(parents=True, exist_ok=True)
        (FAILED_DIR / f"failed-{date}.html").write_text(
            html_body, encoding="utf-8"
        )
        log_run(run_id, len(summarized), "failed", str(exc))
        return 1

    mark_sent(summarized)
    log_run(run_id, len(summarized), "sent")
    logger.info("digest sent to %s", RECIPIENT_EMAIL)
    return 0


if __name__ == "__main__":
    sys.exit(main())

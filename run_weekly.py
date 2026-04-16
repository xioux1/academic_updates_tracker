"""
run_weekly.py — Standalone weekly scan script.

Usage:
    python run_weekly.py            # full pipeline
    python run_weekly.py --no-mail  # skip email sending

Can be called manually, from a CI job, or from the Render Shell tab.
The APScheduler in app.py calls the same pipeline automatically every Monday.
"""

import argparse
import logging
import sys

# Load .env when running locally
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import database as db
import scraper
import analyzer
from digest import run_digest
import config as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def main(send_email: bool = True) -> int:
    log.info("=== AcademicRadar weekly scan start ===")

    # 1 — Ensure DB is initialised
    db.init_db(cfg.DB_PATH)
    log.info("DB: %s", cfg.DB_PATH)

    # 2 — Scrape all sources
    log.info("Step 1/3 — Scraping sources…")
    try:
        summary = scraper.run_full_scan(
            cfg.DB_PATH,
            run_metadata={"run_kind": "production", "trigger": "run_weekly.py"},
        )
        db.log_scan(summary, cfg.DB_PATH)
        log.info(
            "Scraper done: %d new findings / %d total | %d errors",
            summary["findings_new"], summary["findings_total"],
            len(summary.get("errors", [])),
        )
        for err in summary.get("errors", [])[:5]:
            log.warning("  Scraper error: %s", err[:200])
    except Exception as e:
        log.error("Scraper failed: %s", e)
        return 1

    # 3 — Analyse with Claude
    log.info("Step 2/3 — Analysing findings with Claude…")
    try:
        result = analyzer.run_analysis(cfg.DB_PATH, batch_size=100)
        log.info(
            "Analysis done: %d analysed, %d failed",
            result["analyzed"], result["failed"],
        )
    except Exception as e:
        log.error("Analysis failed: %s", e)
        # Non-fatal — carry on to digest

    # 4 — Generate and send digest
    log.info("Step 3/3 — Generating digest (email=%s)…", send_email)
    try:
        res = run_digest(cfg.DB_PATH, send_email=send_email)
        stats = res["digest"]["stats"]
        log.info(
            "Digest #%d: %d findings, %d actionable",
            res["digest_id"], stats["total_findings"], stats["actionable_count"],
        )
    except Exception as e:
        log.error("Digest failed: %s", e)

    log.info("=== AcademicRadar weekly scan complete ===")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-mail", action="store_true", help="Skip email sending")
    args = parser.parse_args()
    sys.exit(main(send_email=not args.no_mail))

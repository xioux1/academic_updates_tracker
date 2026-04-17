"""
run_weekly.py — Standalone weekly scan script.

Usage:
    python run_weekly.py            # full pipeline
    python run_weekly.py --no-mail  # skip email sending
    python run_weekly.py --no-alerts  # skip alert email

Can be called manually, from a CI job, or from the Render Shell tab.
The APScheduler in app.py calls the same pipeline automatically every Monday.
"""

import argparse
import logging
import sys
import time

# Load .env when running locally
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import database as db
import scraper
import analyzer
from digest import run_digest, check_and_send_alerts
import config as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def _step(name: str):
    """Context manager that logs step start/end with elapsed time."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        log.info("── %s: start", name)
        t0 = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - t0
            log.info("── %s: done (%.1fs)", name, elapsed)

    return _ctx()


def _warn_consecutive_failures(threshold: int = 3) -> None:
    failing = db.get_consecutive_scan_failures(threshold=threshold, db_path=cfg.DB_PATH)
    if failing:
        log.warning(
            "⚠️  %d error pattern(s) appeared in the last %d consecutive scans:",
            len(failing), threshold,
        )
        for item in failing:
            log.warning("    [%dx] %s", item["consecutive_failures"], item["error_pattern"])


def main(send_email: bool = True, send_alerts: bool = True) -> int:
    t_total = time.monotonic()
    log.info("=== AcademicRadar weekly scan start ===")

    # 1 — Ensure DB is initialised
    db.init_db(cfg.DB_PATH)
    log.info("DB: %s", cfg.DB_PATH)

    # 2 — Scrape all sources
    with _step("Step 1/4 — Scraping sources"):
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
    with _step("Step 2/4 — Analysing findings"):
        try:
            result = analyzer.run_analysis(cfg.DB_PATH, batch_size=100)
            log.info(
                "Analysis done: %d analysed, %d failed",
                result["analyzed"], result["failed"],
            )
        except Exception as e:
            log.error("Analysis failed: %s", e)
            # Non-fatal — carry on to digest

    # 4 — Deadline + sensitive change alerts
    with _step("Step 3/4 — Alerts"):
        try:
            alert = check_and_send_alerts(cfg.DB_PATH, send_email=send_alerts and send_email)
            if alert:
                upcoming_n = len(alert.get("upcoming_deadlines") or [])
                changes_n  = len(alert.get("sensitive_changes") or [])
                log.info("Alert sent: %d deadlines, %d changes.", upcoming_n, changes_n)
        except Exception as e:
            log.error("Alert check failed: %s", e)

    # 5 — Generate and send digest
    with _step("Step 4/4 — Digest"):
        try:
            res = run_digest(cfg.DB_PATH, send_email=send_email)
            stats = res["digest"]["stats"]
            log.info(
                "Digest #%d: %d findings, %d actionable",
                res["digest_id"], stats["total_findings"], stats["actionable_count"],
            )
        except Exception as e:
            log.error("Digest failed: %s", e)

    # 6 — Warn on consecutive source failures
    _warn_consecutive_failures(threshold=3)

    total_elapsed = time.monotonic() - t_total
    log.info("=== AcademicRadar weekly scan complete (%.1fs total) ===", total_elapsed)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-mail",   action="store_true", help="Skip all email sending")
    parser.add_argument("--no-alerts", action="store_true", help="Skip alert email only")
    args = parser.parse_args()
    sys.exit(main(send_email=not args.no_mail, send_alerts=not args.no_alerts))

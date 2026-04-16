"""
run_backfill.py — Ejecutor operativo de backfill histórico con control de carga.

Ejemplos:
    python run_backfill.py
    python run_backfill.py --weeks 8 --sleep-between-runs 20 --no-mail
    python run_backfill.py --max-runs 3 --min-quality 0.6

Comportamiento:
- Ejecuta corridas secuenciales (1 snapshot por ventana semanal).
- Etiqueta snapshots como backfill en run_metadata.
- Persiste y valida change_summary por snapshot para monitorear estabilidad del diff.
- Aplica criterio de corte si la calidad de extracción cae bajo umbral.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

# Load .env when running locally
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import analyzer
import config as cfg
import database as db
import scraper
from digest import run_digest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _quality_ratio(scan_summary: dict) -> float:
    metrics = scan_summary.get("metrics") or {}
    coverage = (metrics.get("coverage") or {}).get("ratio", 0.0)
    freshness = (metrics.get("freshness") or {}).get("ratio", 0.0)
    # Calidad operativa simple: media ponderada cobertura/freshness.
    return round((0.7 * float(coverage)) + (0.3 * float(freshness)), 4)


def _build_windows(weeks: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    windows: list[dict] = []
    for i in range(weeks):
        end = now - timedelta(days=(7 * i))
        start = end - timedelta(days=7)
        windows.append(
            {
                "index": i + 1,
                "window_start": start.strftime("%Y-%m-%d"),
                "window_end": end.strftime("%Y-%m-%d"),
            }
        )
    windows.reverse()
    return windows


def run_backfill(
    *,
    weeks: int,
    send_email: bool,
    sleep_between_runs: float,
    min_quality: float,
    max_runs: int | None,
) -> int:
    log.info("=== AcademicRadar backfill start ===")
    db.init_db(cfg.DB_PATH)
    log.info("DB: %s", cfg.DB_PATH)
    log.info("Ventana definida: últimas %d semanas", weeks)
    log.info("Frecuencia por fuente (semanas): %s", cfg.BACKFILL_SOURCE_FREQUENCIES)

    windows = _build_windows(weeks)
    if max_runs is not None:
        windows = windows[:max_runs]

    executed = 0
    stopped_by_quality = False

    for window in windows:
        run_idx = window["index"]
        log.info(
            "Backfill run %d | ventana %s → %s",
            run_idx,
            window["window_start"],
            window["window_end"],
        )

        run_metadata = {
            "scan_type": "full_scan",
            "run_kind": "backfill",
            "backfill": True,
            "backfill_window_start": window["window_start"],
            "backfill_window_end": window["window_end"],
            "backfill_window_weeks": weeks,
            "source_frequency_weeks": cfg.BACKFILL_SOURCE_FREQUENCIES,
            "trigger": "run_backfill.py",
        }

        try:
            summary = scraper.run_full_scan(cfg.DB_PATH, run_metadata=run_metadata)
            db.log_scan(summary, cfg.DB_PATH)
        except Exception as exc:
            log.error("Scan falló para ventana %s-%s: %s", window["window_start"], window["window_end"], exc)
            return 1

        try:
            analysis = analyzer.run_analysis(cfg.DB_PATH, batch_size=100)
            log.info("Analysis: %d analysed, %d failed", analysis["analyzed"], analysis["failed"])
        except Exception as exc:
            log.warning("Analysis no fatal: %s", exc)

        try:
            digest = run_digest(cfg.DB_PATH, send_email=send_email)
            log.info("Digest generado: id=%s", digest["digest_id"])
        except Exception as exc:
            log.warning("Digest no fatal: %s", exc)

        snapshot_id = summary.get("snapshot_id")
        change_summary = summary.get("change_summary") or {}
        snapshot_record = db.get_scan_snapshot(snapshot_id, cfg.DB_PATH) if snapshot_id else None
        stored_change_summary = ((snapshot_record or {}).get("summary_json") or {}).get("change_summary")
        is_stable = bool(change_summary) and change_summary == stored_change_summary
        if not is_stable:
            log.warning("change_summary inestable en snapshot %s", snapshot_id)
        else:
            log.info("change_summary validado en snapshot %s", snapshot_id)

        quality = _quality_ratio(summary)
        log.info("Calidad de extracción: %.4f (umbral=%.4f)", quality, min_quality)

        executed += 1
        if quality < min_quality:
            stopped_by_quality = True
            log.warning(
                "Corte de backfill: calidad %.4f bajo umbral %.4f en snapshot %s",
                quality,
                min_quality,
                snapshot_id,
            )
            break

        if sleep_between_runs > 0:
            log.info("Esperando %.1fs para control de carga…", sleep_between_runs)
            time.sleep(sleep_between_runs)

    log.info(
        "=== AcademicRadar backfill complete | runs=%d | stopped_by_quality=%s ===",
        executed,
        stopped_by_quality,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=cfg.BACKFILL_WINDOW_WEEKS, help="Ventana de backfill en semanas")
    parser.add_argument("--sleep-between-runs", type=float, default=15.0, help="Segundos de pausa entre corridas")
    parser.add_argument("--min-quality", type=float, default=cfg.BACKFILL_MIN_QUALITY_RATIO, help="Umbral de calidad para criterio de corte")
    parser.add_argument("--max-runs", type=int, default=None, help="Límite opcional de corridas (útil para pruebas)")
    parser.add_argument("--no-mail", action="store_true", help="No enviar email de digest")
    args = parser.parse_args()

    weeks = max(1, args.weeks)
    min_quality = max(0.0, min(1.0, args.min_quality))

    return run_backfill(
        weeks=weeks,
        send_email=not args.no_mail,
        sleep_between_runs=max(0.0, args.sleep_between_runs),
        min_quality=min_quality,
        max_runs=args.max_runs,
    )


if __name__ == "__main__":
    sys.exit(main())

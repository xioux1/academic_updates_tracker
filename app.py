"""
app.py — AcademicRadar Streamlit Dashboard entry point.
Run locally:  streamlit run app.py
Run on Render: startCommand in render.yaml handles the port binding.
"""

# Load .env file when running locally (Render sets env vars natively)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os
import threading
import logging
import streamlit as st
import database as db
import config as cfg

logging.basicConfig(level=logging.INFO)

# Must be first Streamlit call
st.set_page_config(
    page_title="AcademicRadar",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize DB on first run
db.init_db(cfg.DB_PATH)

# ── Background weekly scheduler ─────────────────────────────────────────────
# Uses a PID lock file so only ONE process (across all Streamlit workers)
# ever runs the scheduler. Subsequent workers detect the lock and skip.

_SCHEDULER_LOCK = "/tmp/academic_radar_scheduler.lock"

def _start_scheduler():
    import os, atexit

    # Check if another process already holds the lock
    if os.path.exists(_SCHEDULER_LOCK):
        try:
            with open(_SCHEDULER_LOCK) as f:
                pid = int(f.read().strip())
            # Verify the PID is still alive
            os.kill(pid, 0)
            logging.info("APScheduler already running in PID %d — skipping.", pid)
            return
        except (ValueError, ProcessLookupError, PermissionError):
            # Stale lock — remove and continue
            os.remove(_SCHEDULER_LOCK)

    # Write our PID to the lock file
    with open(_SCHEDULER_LOCK, "w") as f:
        f.write(str(os.getpid()))

    def _remove_lock():
        try:
            os.remove(_SCHEDULER_LOCK)
        except FileNotFoundError:
            pass

    atexit.register(_remove_lock)

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        import scraper, analyzer
        from digest import run_digest

        def weekly_job():
            logging.info("APScheduler: starting weekly scan…")
            try:
                summary = scraper.run_full_scan(cfg.DB_PATH)
                db.log_scan(summary, cfg.DB_PATH)
                analyzer.run_analysis(cfg.DB_PATH, batch_size=100)
                run_digest(cfg.DB_PATH, send_email=bool(cfg.EMAIL_TO))
                logging.info("APScheduler: weekly scan complete.")
            except Exception as e:
                logging.error("APScheduler weekly job error: %s", e)

        scheduler = BackgroundScheduler()
        # Every Monday at 11:00 UTC (08:00 Argentina)
        scheduler.add_job(weekly_job, CronTrigger(day_of_week="mon", hour=11, minute=0))
        scheduler.start()
        logging.info("APScheduler started (PID %d) — weekly job registered.", os.getpid())
    except ImportError:
        logging.warning("apscheduler not installed — weekly background job disabled.")
        _remove_lock()
    except Exception as e:
        logging.error("Failed to start APScheduler: %s", e)
        _remove_lock()

# Start scheduler in a daemon thread so it doesn't block Streamlit startup
threading.Thread(target=_start_scheduler, daemon=True).start()

# ── Dark theme CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background:#11111b; }
  [data-testid="stSidebar"] { background:#1e1e2e; }
  .block-container { padding-top:1.5rem; }
  .metric-card {
    background:#1e1e2e; border:1px solid #313244;
    border-radius:8px; padding:14px 18px; text-align:center;
  }
  .badge-green  { background:#28a745; color:#fff; padding:2px 8px; border-radius:12px; font-size:12px; }
  .badge-yellow { background:#ffc107; color:#111; padding:2px 8px; border-radius:12px; font-size:12px; }
  .badge-red    { background:#dc3545; color:#fff; padding:2px 8px; border-radius:12px; font-size:12px; }
  .badge-blue   { background:#0d6efd; color:#fff; padding:2px 8px; border-radius:12px; font-size:12px; }
  .finding-card {
    background:#1e1e2e; border:1px solid #313244;
    border-radius:8px; padding:14px; margin-bottom:10px;
  }
</style>
""", unsafe_allow_html=True)

# ── Sidebar navigation ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎓 AcademicRadar")
    st.markdown("---")
    page = st.radio(
        "Navegación",
        ["📊 Dashboard", "👨‍🏫 Profesores", "🔑 Keywords",
         "📄 Findings", "📬 Digest", "⚙️ Configuración"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    stats = db.get_stats(cfg.DB_PATH)
    st.metric("Findings sin leer", stats["unread_findings"])
    st.metric("Accionables",        stats["actionable"])
    if stats["last_scan"]:
        st.caption(f"Último scan: {stats['last_scan'][:16]}")


# ── Route to views ──────────────────────────────────────────────────────────
_views_dir = os.path.join(os.path.dirname(__file__), "views")

if   page == "📊 Dashboard":       exec(open(os.path.join(_views_dir, "dashboard.py")).read())
elif page == "👨‍🏫 Profesores":     exec(open(os.path.join(_views_dir, "professors.py")).read())
elif page == "🔑 Keywords":         exec(open(os.path.join(_views_dir, "keywords.py")).read())
elif page == "📄 Findings":         exec(open(os.path.join(_views_dir, "findings.py")).read())
elif page == "📬 Digest":           exec(open(os.path.join(_views_dir, "digest_view.py")).read())
elif page == "⚙️ Configuración":    exec(open(os.path.join(_views_dir, "settings.py")).read())

"""
app.py — AcademicRadar Streamlit Dashboard entry point.
Run with: streamlit run app.py
"""

import streamlit as st
import database as db
import config as cfg

# Must be first Streamlit call
st.set_page_config(
    page_title="AcademicRadar",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize DB on first run
db.init_db(cfg.DB_PATH)

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
if   page == "📊 Dashboard":         exec(open("views/dashboard.py").read())
elif page == "👨‍🏫 Profesores":       exec(open("views/professors.py").read())
elif page == "🔑 Keywords":           exec(open("views/keywords.py").read())
elif page == "📄 Findings":           exec(open("views/findings.py").read())
elif page == "📬 Digest":             exec(open("views/digest_view.py").read())
elif page == "⚙️ Configuración":      exec(open("views/settings.py").read())

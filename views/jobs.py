"""Vista — Historial de ejecución de jobs y observabilidad operacional."""

import json
import threading
import pandas as pd

st.title("🔧 Jobs")

history = db.get_scan_history(cfg.DB_PATH, limit=20)

# ── Últimas ejecuciones ───────────────────────────────────────────────────────
st.subheader("Últimas ejecuciones")

if history:
    rows = []
    for h in history:
        durations = json.loads(h.get("step_durations_json") or "{}")
        rows.append({
            "Fecha":          (h.get("date_ran") or "")[:16],
            "Total (s)":      h.get("total_duration_s") or "—",
            "Findings nuevos": h.get("findings_new", 0),
            "Findings total":  h.get("findings_total", 0),
            "Alertas":         h.get("alerts_count", 0),
            "Análisis falló":  "⚠️" if h.get("analysis_failed") else "✅",
            "Errores":         len(json.loads(h.get("errors_json") or "[]")),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Sin historial de scans todavía.")

st.divider()

# ── Tiempos por paso ──────────────────────────────────────────────────────────
st.subheader("Tiempos por paso (últimos 10 scans)")

STEP_LABELS = {
    "scraping_s":  "Scraping",
    "analysis_s":  "Análisis",
    "alerts_s":    "Alertas",
    "digest_s":    "Digest",
}

chart_rows = []
for h in history[:10]:
    durations = json.loads(h.get("step_durations_json") or "{}")
    if not durations:
        continue
    row = {"Fecha": (h.get("date_ran") or "")[:10]}
    for key, label in STEP_LABELS.items():
        row[label] = durations.get(key, 0)
    chart_rows.append(row)

if chart_rows:
    df_chart = pd.DataFrame(chart_rows).set_index("Fecha")
    if len(df_chart) > 1:
        st.bar_chart(df_chart, height=250)
    st.dataframe(df_chart.reset_index(), use_container_width=True, hide_index=True)
else:
    st.info("Sin datos de timing por paso todavía. Se registran a partir del próximo scan.")

st.divider()

# ── Fallos consecutivos ───────────────────────────────────────────────────────
st.subheader("Patrones de error recurrentes (≥ 3 scans consecutivos)")

failing = db.get_consecutive_scan_failures(threshold=3, db_path=cfg.DB_PATH)
if failing:
    fail_rows = [{"Patrón de error": f["error_pattern"], "Scans consecutivos": f["consecutive_failures"]}
                 for f in failing]
    st.dataframe(pd.DataFrame(fail_rows), use_container_width=True, hide_index=True)
else:
    st.success("Sin patrones de fallo recurrente detectados.")

st.divider()

# ── Acceso rápido ─────────────────────────────────────────────────────────────
st.subheader("Acceso rápido")

col_run, col_info = st.columns([1, 3])
with col_run:
    if st.button("▶ Ejecutar scan ahora", type="primary"):
        import run_weekly
        def _run():
            try:
                run_weekly.main(send_email=False, send_alerts=False)
            except Exception as e:
                pass
        threading.Thread(target=_run, daemon=True).start()
        st.success("Scan iniciado en segundo plano (sin email). Recarga la página en unos minutos para ver resultados.")
with col_info:
    st.caption(
        "El scan completo (con email y alertas) se puede lanzar desde terminal: "
        "`python run_weekly.py`  |  Sin email: `--no-mail`  |  Sin alertas: `--no-alerts`"
    )

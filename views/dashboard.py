"""Vista 1 — Dashboard principal con métricas globales."""

st.title("📊 Dashboard")

stats = db.get_stats(cfg.DB_PATH)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total findings",      stats["total_findings"])
c2.metric("Sin leer",            stats["unread_findings"])
c3.metric("Accionables",         stats["actionable"])
c4.metric("Score promedio",      stats["avg_score"])
c5.metric("Profesores activos",  stats["active_professors"])

st.divider()

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("🔥 Top findings recientes")
    recent = db.get_findings(cfg.DB_PATH, limit=8)
    if not recent:
        st.info("No hay findings todavía. Ejecuta un scan en Configuración.")
    for f in recent:
        score = f.get("relevance_score")
        color = "green" if (score or 0) >= 7 else "orange" if (score or 0) >= 4 else "red"
        badge = f":{color}[{score}/10]" if score else ":gray[N/A]"
        with st.expander(f"{badge} {f['title'][:80]}"):
            st.caption(f"{f.get('source_name','')} · {f.get('date_found','')[:10]}")
            if f.get("summary_claude"):
                st.write(f["summary_claude"])
            if f.get("actionable") and f.get("action_suggestion"):
                st.info(f"▶ {f['action_suggestion']}")
            st.link_button("Abrir fuente", f["url"])

with col_right:
    st.subheader("⚡ Accionables pendientes")
    actionable = db.get_findings(cfg.DB_PATH, actionable=True, read=False, limit=8)
    if not actionable:
        st.info("Sin items accionables sin leer.")
    for f in actionable:
        with st.expander(f"[{f.get('relevance_score','?')}/10] {f['title'][:75]}"):
            st.write(f.get("summary_claude") or "")
            if f.get("action_suggestion"):
                st.success(f["action_suggestion"])
            btnc1, btnc2 = st.columns(2)
            if btnc1.button("Marcar leído", key=f"rl_{f['id']}"):
                db.update_finding(f["id"], {"read": 1}, cfg.DB_PATH)
                st.rerun()
            btnc2.link_button("Abrir", f["url"])

st.divider()
st.subheader("🛟 Vista operativa (P0)")
ops = db.get_operational_metrics(cfg.DB_PATH, limit=12)
latest = ops.get("latest") or {}
latest_summary = latest.get("summary") or {}
latest_metrics = latest_summary.get("metrics", {})
comparison = ops.get("comparison", {})

p0_status = (latest_summary.get("p0_status") or "yellow").lower()
if p0_status == "green":
    p0_label = "🟢 Verde"
elif p0_status == "red":
    p0_label = "🔴 Rojo"
else:
    p0_label = "🟡 Amarillo"

st.metric("Semáforo confiabilidad ranking", p0_label)
for reason in (latest_summary.get("p0_reasons") or []):
    st.caption(f"• {reason}")

mx1, mx2, mx3, mx4 = st.columns(4)
mx1.metric(
    "Cobertura",
    f"{100 * float((latest_metrics.get('coverage') or {}).get('ratio', 0)):.1f}%",
    delta=f"{100 * float(comparison.get('coverage_delta', 0)):+.1f} pp",
)
mx2.metric(
    "Freshness",
    f"{100 * float((latest_metrics.get('freshness') or {}).get('ratio', 0)):.1f}%",
    delta=f"{100 * float(comparison.get('freshness_delta', 0)):+.1f} pp",
)
mx3.metric(
    "Inconsistencias",
    int((latest_metrics.get("inconsistencies") or {}).get("count", 0)),
    delta=int(comparison.get("inconsistency_delta", 0)),
)
mx4.metric(
    "Nulos críticos",
    int((latest_metrics.get("critical_nulls") or {}).get("count", 0)),
    delta=int(comparison.get("critical_nulls_delta", 0)),
)

oc1, oc2, oc3 = st.columns(3)
with oc1:
    st.caption("Errores por fuente")
    st.json(latest_summary.get("errors_by_source") or {})
with oc2:
    st.caption("Éxito/fallo por universidad")
    st.json(latest_summary.get("university_counters") or {})
with oc3:
    st.caption("Éxito/fallo por conector")
    st.json(latest_summary.get("connector_counters") or {})

hist_rows = []
for row in (ops.get("history") or []):
    summary = row.get("summary") or {}
    metrics = summary.get("metrics") or {}
    hist_rows.append(
        {
            "Fecha cierre": (row.get("closed_at") or row.get("started_at") or "")[:16],
            "P0": summary.get("p0_status", "-"),
            "Cobertura %": round(100 * float((metrics.get("coverage") or {}).get("ratio", 0)), 1),
            "Freshness %": round(100 * float((metrics.get("freshness") or {}).get("ratio", 0)), 1),
            "Inconsistencias": int((metrics.get("inconsistencies") or {}).get("count", 0)),
            "Nulos críticos": int((metrics.get("critical_nulls") or {}).get("count", 0)),
        }
    )
if hist_rows:
    import pandas as pd
    st.caption("Comparación histórica semanal (snapshots recientes)")
    st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)

st.divider()
st.subheader("📅 Historial de scans")
history = db.get_scan_history(cfg.DB_PATH, limit=5)
if history:
    import pandas as pd
    df = pd.DataFrame(history)[["date_ran","professors_scanned","keywords_scanned",
                                  "findings_total","findings_new"]]
    df.columns = ["Fecha","Profs","Keywords","Totales","Nuevos"]
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Sin historial de scans.")

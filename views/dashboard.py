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

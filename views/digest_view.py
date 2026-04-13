"""Vista 5 — Digest semanal."""

import json as _json
import digest as _digest

st.title("📬 Digest Semanal")

tab1, tab2 = st.tabs(["📝 Generar / Enviar", "📚 Historial"])

with tab1:
    st.subheader("Generar digest")
    days = st.slider("Período (días atrás)", 1, 30, 7)

    if st.button("🔄 Generar preview"):
        with st.spinner("Generando…"):
            d = _digest.generate_digest(cfg.DB_PATH, days_back=days)
        st.session_state["digest_preview"] = d
        st.success(
            f"Preview generado: {d['stats']['total_findings']} findings, "
            f"{d['stats']['actionable_count']} accionables."
        )

    if "digest_preview" in st.session_state:
        d = st.session_state["digest_preview"]
        stats = d["stats"]

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Findings",   stats["total_findings"])
        sc2.metric("Accionables", stats["actionable_count"])
        sc3.metric("Score ≥ 7",  stats["high_score_count"])
        sc4.metric("Analizados",  stats["analyzed"])

        st.divider()
        st.subheader("⚡ Accionables")
        for f in d["actionable_items"]:
            score = f.get("relevance_score","?")
            with st.expander(f"[{score}/10] {f['title'][:80]}"):
                st.write(f.get("summary_claude") or "")
                if f.get("action_suggestion"):
                    st.success(f["action_suggestion"])
                st.link_button("Abrir", f["url"])

        st.subheader("📄 Top Findings")
        for f in d["top_findings"][:10]:
            score = f.get("relevance_score","?")
            cn = " 🇨🇳" if f.get("is_chinese_source") else ""
            with st.expander(f"[{score}/10]{cn} {f['title'][:80]}"):
                st.caption(f"{f.get('source_name','')} · {(f.get('date_published') or '')[:10]}")
                st.write(f.get("summary_claude") or f.get("summary_original","")[:300])
                st.link_button("Abrir", f["url"])

        st.divider()
        creds = cfg.credentials_ok()
        if not creds["smtp_configured"]:
            st.warning("SMTP no configurado. Configura las variables de entorno en ⚙️ Configuración.")
        elif not creds["email_to"]:
            st.warning("EMAIL_TO no configurado.")
        else:
            if st.button("📧 Enviar por email ahora"):
                with st.spinner("Enviando…"):
                    result = _digest.run_digest(cfg.DB_PATH, send_email=True)
                st.success(f"Digest enviado. ID: {result['digest_id']}")
                del st.session_state["digest_preview"]
                st.rerun()

        if st.button("💾 Guardar sin enviar"):
            result = _digest.run_digest(cfg.DB_PATH, send_email=False)
            st.success(f"Digest guardado. ID: {result['digest_id']}")
            del st.session_state["digest_preview"]
            st.rerun()

with tab2:
    digests = db.get_digests(cfg.DB_PATH)
    if not digests:
        st.info("Sin digests previos.")
    for dig in digests:
        sent = "✅ enviado" if dig.get("email_sent") else "💾 guardado"
        with st.expander(f"{dig['date_generated'][:16]}  —  {dig['findings_count']} findings  ({sent})"):
            if dig.get("content_json"):
                try:
                    data = _json.loads(dig["content_json"])
                    st.json(data["stats"])
                    st.caption(f"Top finding: {data['top_findings'][0]['title'] if data.get('top_findings') else '—'}")
                except Exception:
                    st.code(dig["content_json"][:500])

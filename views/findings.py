"""Vista 4 — Feed principal de findings."""

st.title("📄 Findings")

# ── Filters ──────────────────────────────────────────────────────────────────
fc1, fc2, fc3, fc4 = st.columns(4)
fc5, fc6, fc7 = st.columns(3)

professors   = db.get_all_professors(cfg.DB_PATH)
sources      = db.get_all_sources(cfg.DB_PATH)
prof_opts    = {p["name"]: p["id"] for p in professors}
source_opts  = {s["name"]: s["id"] for s in sources}

sel_prof   = fc1.selectbox("Profesor", ["Todos"] + list(prof_opts.keys()))
sel_source = fc2.selectbox("Fuente",   ["Todas"] + list(source_opts.keys()))
sel_lang   = fc3.selectbox("Idioma",   ["Todos","en","zh"])
sel_score  = fc4.slider("Score mínimo", 1, 10, 1)

sel_read   = fc5.selectbox("Leído",      ["Todos","No leídos","Leídos"])
sel_action = fc6.selectbox("Accionable", ["Todos","Sí","No"])
sort_by    = fc7.selectbox("Ordenar por",["Fecha (reciente)","Score (mayor)"])

# Build filter kwargs
fkw = {"min_score": sel_score if sel_score > 1 else None}
if sel_prof   != "Todos":    fkw["professor_id"] = prof_opts[sel_prof]
if sel_source != "Todas":    fkw["source_id"]    = source_opts[sel_source]
if sel_lang   != "Todos":    fkw["language"]     = sel_lang
if sel_read   == "No leídos": fkw["read"]        = False
elif sel_read == "Leídos":   fkw["read"]         = True
if sel_action == "Sí":       fkw["actionable"]   = True
elif sel_action == "No":     fkw["actionable"]   = False

findings = db.get_findings(cfg.DB_PATH, limit=200, **fkw)

if sort_by == "Score (mayor)":
    findings.sort(key=lambda x: x.get("relevance_score") or 0, reverse=True)

st.markdown(f"**{len(findings)} findings**")

# ── Mark all read button ─────────────────────────────────────────────────────
if st.button("✅ Marcar todos como leídos"):
    for f in findings:
        if not f.get("read"):
            db.update_finding(f["id"], {"read": 1}, cfg.DB_PATH)
    st.rerun()

# ── Finding cards ─────────────────────────────────────────────────────────────
if not findings:
    st.info("Sin findings con los filtros actuales.")
else:
    for f in findings:
        score = f.get("relevance_score")
        color = "green" if (score or 0) >= 7 else "orange" if (score or 0) >= 4 else "red"
        score_str = f":{color}[{score}/10]" if score else ":gray[?]"

        cn_flag  = " 🇨🇳" if f.get("is_chinese_source") else ""
        unread   = " 🔵" if not f.get("read") else ""
        action   = " ⚡" if f.get("actionable") else ""
        title_preview = f["title"][:85]

        with st.expander(f"{score_str}{unread}{action}{cn_flag}  {title_preview}"):
            hc1, hc2 = st.columns([3, 1])
            hc1.caption(
                f"**{f.get('source_name','')}** · "
                f"{f.get('professor_name') or f.get('keyword_text') or 'keyword'} · "
                f"{(f.get('date_published') or f.get('date_found',''))[:10]}"
            )

            # Summary
            if f.get("summary_claude"):
                st.write(f["summary_claude"])
            elif f.get("summary_original"):
                st.caption(f["summary_original"][:400])

            # Relevance reason
            if f.get("relevance_reason"):
                st.caption(f"*{f['relevance_reason']}*")

            # Translation
            if f.get("translation"):
                with st.expander("📖 Traducción"):
                    st.write(f["translation"])

            # Action suggestion
            if f.get("actionable") and f.get("action_suggestion"):
                st.success(f"▶ {f['action_suggestion']}")

            # Notes
            note_val = st.text_input("Nota personal", value=f.get("notes") or "",
                                     key=f"note_{f['id']}", placeholder="Agregar nota…")

            # Action buttons
            bc1, bc2, bc3, bc4 = st.columns(4)
            if bc1.button("✅ Leído" if not f.get("read") else "↩ No leído", key=f"rd_{f['id']}"):
                db.update_finding(f["id"], {"read": int(not f.get("read"))}, cfg.DB_PATH)
                st.rerun()
            if bc2.button("⚡ Accionable" if not f.get("actionable") else "✖ No accionable", key=f"ac_{f['id']}"):
                db.update_finding(f["id"], {"actionable": int(not f.get("actionable"))}, cfg.DB_PATH)
                st.rerun()
            if bc3.button("💾 Guardar nota", key=f"snt_{f['id']}"):
                db.update_finding(f["id"], {"notes": note_val}, cfg.DB_PATH)
                st.success("Nota guardada.")
            bc4.link_button("🔗 Abrir fuente", f["url"])

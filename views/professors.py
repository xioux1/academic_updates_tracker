"""Vista 2 — Gestión de profesores."""

st.title("👨‍🏫 Profesores")

# ── Filters ─────────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns(3)
filter_uni    = fc1.selectbox("Universidad", ["Todas","SUSTech","HITSZ","Otra"])
filter_status = fc2.selectbox("Status", ["Todos","active","watching","discarded"])
filter_search = fc3.text_input("Buscar por nombre / área")

professors = db.get_all_professors(cfg.DB_PATH)

if filter_uni != "Todas":
    professors = [p for p in professors if (p.get("university") or "") == filter_uni]
if filter_status != "Todos":
    professors = [p for p in professors if p.get("status") == filter_status]
if filter_search:
    q = filter_search.lower()
    professors = [p for p in professors
                  if q in (p.get("name") or "").lower()
                  or q in (p.get("name_chinese") or "").lower()
                  or q in (p.get("research_areas") or "").lower()]

# ── Add professor form ───────────────────────────────────────────────────────
with st.expander("➕ Agregar nuevo profesor"):
    with st.form("add_prof"):
        ac1, ac2 = st.columns(2)
        new_name   = ac1.text_input("Nombre (inglés)*")
        new_zh     = ac2.text_input("Nombre chino")
        ac3, ac4   = st.columns(2)
        new_uni    = ac3.text_input("Universidad", value="SUSTech")
        new_dept   = ac4.text_input("Departamento")
        ac5, ac6   = st.columns(2)
        new_email  = ac5.text_input("Email")
        new_status = ac6.selectbox("Status", ["watching","active","discarded"])
        new_areas  = st.text_input("Áreas de investigación (separadas por coma)")
        new_gs     = st.text_input("Google Scholar ID (opcional)")
        new_gh     = st.text_input("GitHub username (opcional)")
        new_notes  = st.text_area("Notas", height=80)
        if st.form_submit_button("Agregar profesor") and new_name:
            db.add_professor({
                "name": new_name, "name_chinese": new_zh,
                "university": new_uni, "department": new_dept,
                "email": new_email, "status": new_status,
                "research_areas": new_areas,
                "google_scholar_id": new_gs or None,
                "github_username": new_gh or None,
                "notes": new_notes,
            }, cfg.DB_PATH)
            st.success(f"Profesor '{new_name}' agregado.")
            st.rerun()

st.markdown(f"**{len(professors)} profesores**")

# ── Professor cards ──────────────────────────────────────────────────────────
STATUS_COLOR = {"active": "green", "watching": "orange", "discarded": "red"}

for p in professors:
    color  = STATUS_COLOR.get(p.get("status",""), "gray")
    badge  = f":{color}[{p.get('status','?')}]"
    last_f = (p.get("last_finding") or "")[:10]
    header = f"{badge} **{p['name']}** {p.get('name_chinese','')}"

    with st.expander(header):
        pc1, pc2, pc3 = st.columns(3)
        pc1.write(f"**Universidad:** {p.get('university','')}")
        pc1.write(f"**Dpto:** {p.get('department','')}")
        pc2.write(f"**Email:** {p.get('email') or '—'}")
        pc2.write(f"**Findings:** {p.get('findings_total',0)} (último: {last_f or '—'})")
        pc3.write(f"**Áreas:** {p.get('research_areas','')}")

        if p.get("notes"):
            st.caption(f"Notas: {p['notes']}")

        act1, act2, act3, act4 = st.columns(4)

        # Change status
        new_s = act1.selectbox("Cambiar status", ["active","watching","discarded"],
                               index=["active","watching","discarded"].index(p.get("status","watching")),
                               key=f"stat_{p['id']}")
        if act1.button("Guardar status", key=f"sv_{p['id']}"):
            db.update_professor(p["id"], {"status": new_s}, cfg.DB_PATH)
            st.rerun()

        # Edit notes
        new_notes = act2.text_input("Notas", value=p.get("notes") or "", key=f"nt_{p['id']}")
        if act2.button("Guardar nota", key=f"sn_{p['id']}"):
            db.update_professor(p["id"], {"notes": new_notes}, cfg.DB_PATH)
            st.rerun()

        # Google Scholar link
        if p.get("google_scholar_id"):
            act3.link_button("Google Scholar",
                f"https://scholar.google.com/citations?user={p['google_scholar_id']}")
        else:
            act3.caption("Sin Scholar ID")

        # Delete
        if act4.button("🗑 Eliminar", key=f"del_{p['id']}"):
            db.delete_professor(p["id"], cfg.DB_PATH)
            st.rerun()

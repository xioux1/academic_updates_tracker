"""Vista 3 — Gestión de keywords."""

st.title("🔑 Keywords")

keywords = db.get_all_keywords(cfg.DB_PATH)

# ── Add keyword form ─────────────────────────────────────────────────────────
with st.expander("➕ Agregar nueva keyword"):
    with st.form("add_kw"):
        kc1, kc2, kc3, kc4 = st.columns(4)
        new_kw   = kc1.text_input("Keyword*")
        new_lang = kc2.selectbox("Idioma", ["en","zh"])
        new_cat  = kc3.selectbox("Categoría", ["topic","professor_name","institution"])
        new_wt   = kc4.slider("Peso", 1, 5, 3)
        if st.form_submit_button("Agregar") and new_kw:
            db.add_keyword({"keyword": new_kw, "language": new_lang,
                            "category": new_cat, "weight": new_wt}, cfg.DB_PATH)
            st.success(f"Keyword '{new_kw}' agregada.")
            st.rerun()

# ── Filters ──────────────────────────────────────────────────────────────────
fc1, fc2 = st.columns(2)
lang_filter   = fc1.selectbox("Idioma", ["Todos","en","zh"])
active_filter = fc2.selectbox("Estado", ["Todos","Activas","Inactivas"])

filtered = keywords
if lang_filter != "Todos":
    filtered = [k for k in filtered if k.get("language") == lang_filter]
if active_filter == "Activas":
    filtered = [k for k in filtered if k.get("active")]
elif active_filter == "Inactivas":
    filtered = [k for k in filtered if not k.get("active")]

st.markdown(f"**{len(filtered)} keywords**")

# ── Language tabs ────────────────────────────────────────────────────────────
tab_en, tab_zh = st.tabs(["🇺🇸 Inglés", "🇨🇳 Chino"])

def render_kw_list(kw_list):
    for k in kw_list:
        stars = "⭐" * k.get("weight", 1)
        active_label = ":green[activa]" if k.get("active") else ":red[inactiva]"
        with st.expander(f"{active_label} **{k['keyword']}** {stars}  ({k.get('findings_count',0)} findings)"):
            ec1, ec2, ec3, ec4 = st.columns(4)

            new_w = ec1.slider("Peso", 1, 5, k.get("weight",3), key=f"wt_{k['id']}")
            if ec1.button("Guardar peso", key=f"sw_{k['id']}"):
                db.update_keyword(k["id"], {"weight": new_w}, cfg.DB_PATH)
                st.rerun()

            cur_active = bool(k.get("active", 1))
            toggle_label = "Desactivar" if cur_active else "Activar"
            if ec2.button(toggle_label, key=f"tog_{k['id']}"):
                db.update_keyword(k["id"], {"active": int(not cur_active)}, cfg.DB_PATH)
                st.rerun()

            ec3.write(f"**Categoría:** {k.get('category','')}")
            ec3.write(f"**Idioma:** {'🇺🇸 EN' if k.get('language')=='en' else '🇨🇳 ZH'}")

            if ec4.button("🗑 Eliminar", key=f"dkw_{k['id']}"):
                db.delete_keyword(k["id"], cfg.DB_PATH)
                st.rerun()

with tab_en:
    en_kws = [k for k in filtered if k.get("language") == "en"]
    if en_kws:
        render_kw_list(en_kws)
    else:
        st.info("Sin keywords en inglés.")

with tab_zh:
    zh_kws = [k for k in filtered if k.get("language") == "zh"]
    if zh_kws:
        render_kw_list(zh_kws)
    else:
        st.info("Sin keywords en chino.")

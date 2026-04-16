"""Vista 6 — Configuración del sistema."""

import json
import re
import subprocess, threading, queue, time
import scraper, analyzer
import scoring

st.title("⚙️ Configuración")

tab_scan, tab_sources, tab_profile, tab_creds = st.tabs(
    ["🔍 Scan", "📡 Fuentes", "👤 Perfil", "🔑 Credenciales"]
)

# ── Tab: Scan ────────────────────────────────────────────────────────────────
with tab_scan:
    st.subheader("Ejecutar scan manual")
    st.write("Corre el scraping completo y el análisis con Claude.")

    col_run, col_info = st.columns([1, 2])
    with col_run:
        run_scraper   = st.checkbox("Scraper", value=True)
        run_analysis  = st.checkbox("Análisis Claude", value=True)
        run_digest_cb = st.checkbox("Generar digest", value=False)

    with col_info:
        history = db.get_scan_history(cfg.DB_PATH, limit=1)
        if history:
            h = history[0]
            st.info(
                f"Último scan: **{h['date_ran'][:16]}**\n\n"
                f"Profs: {h['professors_scanned']} · "
                f"Keywords: {h['keywords_scanned']} · "
                f"Nuevos: {h['findings_new']}"
            )

    if st.button("▶ Iniciar scan", type="primary"):
        progress_bar = st.progress(0, text="Iniciando…")
        status_box   = st.empty()
        log_area     = st.empty()
        logs         = []

        if run_scraper:
            status_box.info("Ejecutando scraper…")
            progress_bar.progress(10, text="Scraping fuentes…")
            try:
                summary = scraper.run_full_scan(cfg.DB_PATH)
                db.log_scan(summary, cfg.DB_PATH)
                logs.append(
                    f"✅ Scraper: {summary['findings_new']} nuevos / "
                    f"{summary['findings_total']} totales"
                )
                if summary.get("errors"):
                    for err in summary["errors"][:5]:
                        logs.append(f"⚠️ {err[:120]}")
            except Exception as e:
                logs.append(f"❌ Error en scraper: {e}")
            log_area.code("\n".join(logs))

        if run_analysis:
            progress_bar.progress(60, text="Analizando con Claude…")
            status_box.info("Analizando findings con Claude API…")
            try:
                result = analyzer.run_analysis(cfg.DB_PATH, batch_size=50)
                logs.append(
                    f"✅ Análisis: {result['analyzed']} analizados, "
                    f"{result['failed']} fallidos"
                )
            except Exception as e:
                logs.append(f"❌ Error en análisis: {e}")
            log_area.code("\n".join(logs))

        if run_digest_cb:
            progress_bar.progress(90, text="Generando digest…")
            try:
                import digest as _digest
                res = _digest.run_digest(cfg.DB_PATH, send_email=False)
                logs.append(f"✅ Digest generado (ID: {res['digest_id']})")
            except Exception as e:
                logs.append(f"❌ Error en digest: {e}")
            log_area.code("\n".join(logs))

        progress_bar.progress(100, text="¡Completado!")
        status_box.success("Scan finalizado.")
        log_area.code("\n".join(logs))

    st.divider()
    st.subheader("Historial de scans recientes")
    history = db.get_scan_history(cfg.DB_PATH, limit=10)
    if history:
        import pandas as pd
        df = pd.DataFrame(history)
        df["errors"] = df["errors_json"].apply(
            lambda x: len(__import__("json").loads(x)) if x else 0
        )
        st.dataframe(
            df[["date_ran","professors_scanned","keywords_scanned",
                "findings_total","findings_new","errors"]],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Sin historial.")


# ── Tab: Fuentes ─────────────────────────────────────────────────────────────
with tab_sources:
    st.subheader("Gestión de fuentes")
    sources = db.get_all_sources(cfg.DB_PATH)
    for s in sources:
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(f"**{s['name']}** — `{s['type']}`")
        c2.write("🇨🇳 China" if s.get("supports_chinese") else "🌐 Int'l")
        is_active = bool(s.get("active", 1))
        label = "✅ Activa" if is_active else "❌ Inactiva"
        if c3.button(label, key=f"src_{s['id']}"):
            db.update_source(s["id"], {"active": int(not is_active)}, cfg.DB_PATH)
            st.rerun()


# ── Tab: Perfil de usuario ────────────────────────────────────────────────────
with tab_profile:
    st.subheader("Perfil que usa Claude para evaluar relevancia")
    current_profile = cfg.get_user_profile()
    new_profile = st.text_area("Perfil", value=current_profile, height=300)
    if st.button("💾 Guardar perfil"):
        cfg.save_user_profile(new_profile)
        st.success("Perfil guardado.")

    st.divider()
    st.subheader("Perfiles de pesos para ranking (`UserProfile.weights`)")
    st.caption(
        "Los pesos se validan con rango [0,1] y suma exacta = 1. "
        "Si falla, el sistema cae a defaults del PRD."
    )

    profiles = db.list_user_profiles(cfg.DB_PATH)
    if not profiles:
        default_weights = dict(scoring.DEFAULT_WEIGHTS)
        db.add_user_profile(
            {
                "user_key": "default_profile",
                "display_name": "Perfil Default",
                "role": "decision_maker",
                "weights": default_weights,
                "weights_version": "v1",
                "is_active": True,
            },
            cfg.DB_PATH,
        )
        profiles = db.list_user_profiles(cfg.DB_PATH)
        st.info("Se creó un perfil default para empezar.")

    def _profile_label(profile: dict) -> str:
        derived = db._json_loads(profile.get("derived_data"))
        marker = "🟢" if int(derived.get("is_active", 0)) == 1 else "⚪"
        name = profile.get("display_name") or profile.get("user_key") or f"perfil_{profile['id']}"
        version = derived.get("weights_version") or "v?"
        return f"{marker} {name} ({version})"

    profile_options = {p["id"]: p for p in profiles}
    active_profile = db.get_active_user_profile(cfg.DB_PATH)
    active_id = active_profile["id"] if active_profile else profiles[0]["id"]

    selected_id = st.selectbox(
        "Perfil de pesos activo",
        options=list(profile_options.keys()),
        index=list(profile_options.keys()).index(active_id),
        format_func=lambda pid: _profile_label(profile_options[pid]),
        help="Selecciona qué perfil se usa para calcular `overall_score`.",
    )
    if selected_id != active_id:
        db.set_active_user_profile(selected_id, cfg.DB_PATH)
        st.success("Perfil activo actualizado.")
        st.rerun()

    selected_profile = profile_options[selected_id]
    selected_derived = db._json_loads(selected_profile.get("derived_data"))
    selected_weights = selected_derived.get("weights") or dict(scoring.DEFAULT_WEIGHTS)
    valid_weights, validation = scoring.validate_weights(selected_weights)

    c1, c2, c3 = st.columns(3)
    with c1:
        profile_name = st.text_input(
            "Nombre visible",
            value=selected_profile.get("display_name") or "",
            key=f"prof_name_{selected_id}",
        )
    with c2:
        profile_key = st.text_input(
            "User key",
            value=selected_profile.get("user_key") or "",
            key=f"prof_key_{selected_id}",
            help="Identificador único sin espacios (ej: simon_a).",
        )
    with c3:
        profile_role = st.text_input(
            "Rol",
            value=selected_profile.get("role") or "",
            key=f"prof_role_{selected_id}",
        )

    st.markdown("**Editar pesos**")
    wc1, wc2, wc3, wc4, wc5 = st.columns(5)
    edited_weights = {
        "strategic_fit": wc1.number_input("Strategic", min_value=0.0, max_value=1.0, value=float(selected_weights.get("strategic_fit", 0.30)), step=0.01, key=f"w_s_{selected_id}"),
        "admission_fit": wc2.number_input("Admission", min_value=0.0, max_value=1.0, value=float(selected_weights.get("admission_fit", 0.25)), step=0.01, key=f"w_a_{selected_id}"),
        "lifestyle_fit": wc3.number_input("Lifestyle", min_value=0.0, max_value=1.0, value=float(selected_weights.get("lifestyle_fit", 0.20)), step=0.01, key=f"w_l_{selected_id}"),
        "contact_leverage": wc4.number_input("Contact", min_value=0.0, max_value=1.0, value=float(selected_weights.get("contact_leverage", 0.15)), step=0.01, key=f"w_c_{selected_id}"),
        "information_confidence": wc5.number_input("Confidence", min_value=0.0, max_value=1.0, value=float(selected_weights.get("information_confidence", 0.10)), step=0.01, key=f"w_i_{selected_id}"),
    }
    edited_sum = sum(float(v) for v in edited_weights.values())
    st.caption(f"Suma actual de pesos: **{edited_sum:.4f}**")
    if not validation["valid"]:
        st.warning(
            f"El perfil guardado tenía pesos inválidos ({validation['reason']}). "
            "Se aplicará fallback a defaults hasta corregirlo."
        )
    else:
        st.success("Pesos guardados válidos.")

    col_save, col_delete = st.columns([1, 1])
    with col_save:
        if st.button("💾 Guardar pesos y perfil", key=f"save_weights_{selected_id}"):
            if not re.match(r"^[a-zA-Z0-9_\-]+$", profile_key or ""):
                st.error("`user_key` debe ser alfanumérico (permitido: _ y -).")
            else:
                resolved_weights, edit_validation = scoring.validate_weights(edited_weights)
                old_version = str(selected_derived.get("weights_version") or "v1")
                match = re.match(r"^v(\d+)$", old_version)
                old_num = int(match.group(1)) if match else 1
                new_version = f"v{old_num + 1}"
                db.update_user_profile(
                    selected_id,
                    {
                        "user_key": profile_key.strip(),
                        "display_name": profile_name.strip(),
                        "role": profile_role.strip(),
                        "weights": resolved_weights,
                        "weights_version": new_version,
                        "is_active": True,
                    },
                    cfg.DB_PATH,
                )
                if edit_validation["valid"]:
                    st.success(f"Perfil guardado con versión {new_version}.")
                else:
                    st.warning(
                        f"Pesos inválidos ({edit_validation['reason']}). "
                        f"Se guardó fallback PRD en {new_version}."
                    )
                st.rerun()
    with col_delete:
        if len(profiles) > 1 and st.button("🗑️ Eliminar perfil", key=f"del_profile_{selected_id}"):
            db.delete_user_profile(selected_id, cfg.DB_PATH)
            st.success("Perfil eliminado.")
            st.rerun()

    with st.expander("➕ Crear nuevo perfil de pesos"):
        new_name = st.text_input("Nombre", value="Perfil B", key="new_profile_name")
        new_key = st.text_input("User key nuevo", value="", key="new_profile_key")
        if st.button("Crear perfil", key="create_profile_btn"):
            clean_key = (new_key or "").strip()
            if not re.match(r"^[a-zA-Z0-9_\-]+$", clean_key):
                st.error("`user_key` inválido. Usa letras, números, `_` o `-`.")
            elif any(p.get("user_key") == clean_key for p in profiles):
                st.error("Ese `user_key` ya existe.")
            else:
                db.add_user_profile(
                    {
                        "user_key": clean_key,
                        "display_name": new_name.strip() or clean_key,
                        "role": "decision_maker",
                        "weights": dict(scoring.DEFAULT_WEIGHTS),
                        "weights_version": "v1",
                        "is_active": False,
                    },
                    cfg.DB_PATH,
                )
                st.success("Perfil creado.")
                st.rerun()

    st.markdown("**Resumen rápido de perfiles**")
    rows = []
    for p in profiles:
        d = db._json_loads(p.get("derived_data"))
        weights, wval = scoring.validate_weights(d.get("weights"))
        rows.append(
            {
                "ID": p["id"],
                "User key": p.get("user_key"),
                "Nombre": p.get("display_name"),
                "Activo": "✅" if int(d.get("is_active", 0)) == 1 else "",
                "Versión": d.get("weights_version") or "v?",
                "Validación": "OK" if wval["valid"] else f"Fallback ({wval['reason']})",
                "Weights": json.dumps(weights, ensure_ascii=False),
            }
        )
    if rows:
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── Tab: Credenciales ─────────────────────────────────────────────────────────
with tab_creds:
    st.subheader("Estado de credenciales")
    st.caption("Las credenciales se leen de variables de entorno. No se guardan en la UI.")

    creds = cfg.credentials_ok()
    for key, ok in creds.items():
        icon = "✅" if ok else "❌"
        st.write(f"{icon} `{key}`")

    st.divider()
    st.subheader("Variables de entorno requeridas")
    st.code("""
ANTHROPIC_API_KEY=sk-ant-...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_TO=you@gmail.com
EMAIL_FROM=you@gmail.com   # opcional
DB_PATH=academic_radar.db  # opcional
    """.strip())
    st.info("Copia `.env.example` a `.env` y completa los valores.")

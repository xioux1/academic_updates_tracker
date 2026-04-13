"""Vista 6 — Configuración del sistema."""

import subprocess, threading, queue, time
import scraper, analyzer

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

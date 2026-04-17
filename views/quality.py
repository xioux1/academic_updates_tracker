"""Vista — Panel de calidad de datos por snapshot."""

import json
import pandas as pd

ops = db.get_operational_metrics(cfg.DB_PATH, limit=20)
history = ops.get("history") or []
latest = ops.get("latest") or {}
comparison = ops.get("comparison", {})

st.title("📈 Calidad de Datos")

# ── Semáforo global ──────────────────────────────────────────────────────────
latest_summary = (latest.get("summary") or {})
p0_status = (latest_summary.get("p0_status") or "yellow").lower()
p0_label = {"green": "🟢 Verde", "red": "🔴 Rojo"}.get(p0_status, "🟡 Amarillo")
latest_metrics = latest_summary.get("metrics") or {}

col_sem, col_snap = st.columns([1, 3])
with col_sem:
    st.metric("Estado ranking (P0)", p0_label)
    for reason in (latest_summary.get("p0_reasons") or []):
        st.caption(f"• {reason}")
with col_snap:
    closed = (latest.get("closed_at") or latest.get("started_at") or "—")[:16]
    meta = latest.get("summary", {}).get("run_metadata") or {}
    st.caption(f"Snapshot más reciente: **{closed}**   |   Tipo: `{meta.get('run_kind', '?')}`")

st.divider()

# ── Métricas del último snapshot ─────────────────────────────────────────────
st.subheader("Métricas — Último snapshot")

def _ratio_pct(d: dict, key: str) -> float:
    return round(100 * float((d.get(key) or {}).get("ratio", 0)), 1)

def _count(d: dict, key: str) -> int:
    return int((d.get(key) or {}).get("count", 0))

cov_pct   = _ratio_pct(latest_metrics, "coverage")
fresh_pct = _ratio_pct(latest_metrics, "freshness")
incon_n   = _count(latest_metrics, "inconsistencies")
nulls_n   = _count(latest_metrics, "critical_nulls")

def _traffic(value: float, good: float = 80.0, warn: float = 60.0) -> str:
    if value >= good:
        return "🟢"
    if value >= warn:
        return "🟡"
    return "🔴"

def _traffic_inv(value: int, ok: int = 0, warn: int = 3) -> str:
    if value <= ok:
        return "🟢"
    if value <= warn:
        return "🟡"
    return "🔴"

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    f"{_traffic(cov_pct)} Cobertura",
    f"{cov_pct:.1f}%",
    delta=f"{100 * float(comparison.get('coverage_delta', 0)):+.1f} pp",
)
m2.metric(
    f"{_traffic(fresh_pct)} Freshness",
    f"{fresh_pct:.1f}%",
    delta=f"{100 * float(comparison.get('freshness_delta', 0)):+.1f} pp",
)
m3.metric(
    f"{_traffic_inv(incon_n, ok=0, warn=5)} Inconsistencias",
    incon_n,
    delta=int(comparison.get("inconsistency_delta", 0)),
    delta_color="inverse",
)
m4.metric(
    f"{_traffic_inv(nulls_n, ok=0, warn=3)} Nulos críticos",
    nulls_n,
    delta=int(comparison.get("critical_nulls_delta", 0)),
    delta_color="inverse",
)

st.divider()

# ── Tendencia histórica ───────────────────────────────────────────────────────
st.subheader("Tendencia histórica (últimos snapshots)")

hist_rows = []
for row in history:
    summary = row.get("summary") or {}
    metrics = summary.get("metrics") or {}
    cov   = round(100 * float((metrics.get("coverage") or {}).get("ratio", 0)), 1)
    fresh = round(100 * float((metrics.get("freshness") or {}).get("ratio", 0)), 1)
    inc   = int((metrics.get("inconsistencies") or {}).get("count", 0))
    nulls = int((metrics.get("critical_nulls") or {}).get("count", 0))
    hist_rows.append({
        "Fecha": (row.get("closed_at") or row.get("started_at") or "")[:16],
        "P0":    (summary.get("p0_status") or "-").upper(),
        "Cobertura %": cov,
        "Freshness %": fresh,
        "Inconsistencias": inc,
        "Nulos críticos": nulls,
    })

if hist_rows:
    df_hist = pd.DataFrame(hist_rows)
    df_chart = df_hist.set_index("Fecha")[["Cobertura %", "Freshness %"]].sort_index()
    if len(df_chart) > 1:
        st.line_chart(df_chart, height=220)
    st.dataframe(df_hist, use_container_width=True, hide_index=True)
else:
    st.info("Sin historial de snapshots cerrados todavía.")

st.divider()

# ── Breakdown por universidad y conector ─────────────────────────────────────
st.subheader("Breakdown — Último snapshot")

bc1, bc2 = st.columns(2)
with bc1:
    st.caption("Éxito/fallo por universidad")
    uni_data = latest_summary.get("university_counters") or {}
    if uni_data:
        uni_rows = [{"Universidad": k, **v} if isinstance(v, dict) else {"Universidad": k, "valor": v}
                    for k, v in uni_data.items()]
        st.dataframe(pd.DataFrame(uni_rows), use_container_width=True, hide_index=True)
    else:
        st.json({})

with bc2:
    st.caption("Éxito/fallo por conector")
    conn_data = latest_summary.get("connector_counters") or {}
    if conn_data:
        conn_rows = [{"Conector": k, **v} if isinstance(v, dict) else {"Conector": k, "valor": v}
                     for k, v in conn_data.items()]
        st.dataframe(pd.DataFrame(conn_rows), use_container_width=True, hide_index=True)
    else:
        st.json({})

st.caption("Errores recientes por fuente")
errors = latest_summary.get("errors_by_source") or {}
if errors:
    err_rows = [{"Fuente": k, "Errores": v} for k, v in errors.items()]
    st.dataframe(pd.DataFrame(err_rows), use_container_width=True, hide_index=True)
else:
    st.success("Sin errores registrados en el último snapshot.")

st.divider()

# ── Programas con inconsistencias ─────────────────────────────────────────────
st.subheader("Programas con inconsistencias activas")

conn_db = db.get_connection(cfg.DB_PATH)
try:
    incon_rows = conn_db.execute(
        """SELECT p.id, p.name, u.name AS university, p.updated_at,
                  p.derived_data, p.official_data
           FROM programs p
           JOIN universities u ON u.id = p.university_id
           WHERE p.inconsistency_flag = 1
           ORDER BY p.updated_at DESC
           LIMIT 30"""
    ).fetchall()
    incon_programs = [dict(r) for r in incon_rows]
finally:
    conn_db.close()

if incon_programs:
    for prog in incon_programs:
        derived = json.loads(prog.get("derived_data") or "{}")
        src_vals = derived.get("source_values") or {}
        with st.expander(f"⚠️ {prog['university']} — {prog['name']} (actualizado {prog['updated_at'][:10]})"):
            if src_vals:
                for field, sources in src_vals.items():
                    if isinstance(sources, dict) and len({str(v).strip() for v in sources.values() if str(v).strip()}) > 1:
                        st.markdown(f"**{field}** — valores contradictorios:")
                        for url, val in sources.items():
                            short_url = url[:60] + "…" if len(url) > 60 else url
                            st.caption(f"  `{short_url}` → `{val}`")
else:
    st.success("Sin programas con inconsistencias activas.")

st.divider()

# ── Auditoría reciente ────────────────────────────────────────────────────────
st.subheader("Cambios de campos sensibles (últimos 14 días)")

conn_db = db.get_connection(cfg.DB_PATH)
try:
    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
    audit_rows = conn_db.execute(
        """SELECT ar.id, ar.entity_type, ar.entity_id, ar.change_type,
                  ar.detected_at, ar.details,
                  COALESCE(p.name, '') AS program_name,
                  COALESCE(u.name, '') AS university_name
           FROM audit_records ar
           LEFT JOIN programs p ON ar.entity_type='program' AND p.id = ar.entity_id
           LEFT JOIN universities u ON u.id = p.university_id
           WHERE ar.detected_at >= ?
           ORDER BY ar.detected_at DESC
           LIMIT 50""",
        (since,),
    ).fetchall()
    audit_records = [dict(r) for r in audit_rows]
finally:
    conn_db.close()

if audit_records:
    for rec in audit_records:
        details = json.loads(rec.get("details") or "{}")
        entity_label = (
            f"{rec['university_name']} — {rec['program_name']}"
            if rec.get("program_name") else f"{rec['entity_type']} #{rec['entity_id']}"
        )
        change_type = rec.get("change_type", "")
        badge = "🔴" if change_type in ("sensitive_change", "inconsistency") else "🔵"
        with st.expander(f"{badge} {entity_label} · {change_type} · {rec['detected_at'][:10]}"):
            if details:
                st.json(details)
else:
    st.info("Sin cambios de campos sensibles en los últimos 14 días.")

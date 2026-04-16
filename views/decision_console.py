"""Vista — Consola de decisión para priorizar programas y contactos."""

import json
import re
from datetime import datetime, timezone

import pandas as pd


st.title("🧭 Decision Console")
st.caption("Priorización de programas, cambios recientes y docentes recomendados con explicabilidad.")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _loads(raw):
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_dt(value):
    if not value:
        return None
    value = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_deadline(program):
    official = _loads(program.get("official_data"))
    derived = _loads(program.get("derived_data"))

    for candidate in (
        official.get("deadline"),
        official.get("application_deadline"),
        official.get("deadlines"),
        derived.get("deadline"),
        derived.get("application_deadline"),
    ):
        if isinstance(candidate, list) and candidate:
            for item in candidate:
                dt = _to_dt(item)
                if dt:
                    return dt
        dt = _to_dt(candidate)
        if dt:
            return dt
    return None


def _extract_language(program):
    official = _loads(program.get("official_data"))
    inferred = _loads(program.get("inferred_data"))
    lang = (
        official.get("language")
        or official.get("program_language")
        or inferred.get("language")
        or "unknown"
    )
    return str(lang).lower()


def _extract_evidence_url(program):
    derived = _loads(program.get("derived_data"))
    official = _loads(program.get("official_data"))
    return (
        derived.get("last_source_url")
        or derived.get("source_url")
        or official.get("url")
        or official.get("website")
        or ""
    )


def _find_confidence(components):
    for key in ("information_confidence", "confidence_score", "confidence"):
        if key in components:
            return _to_float(components.get(key), default=0.0)
    return 0.0


def _ranking_guard(components):
    return {
        "blocked": bool(components.get("ranking_blocked", False)),
        "reason": str(components.get("ranking_block_reason") or "").strip(),
        "primary_issue": str(components.get("ranking_primary_issue") or "").strip(),
        "threshold": _to_float(components.get("ranking_min_confidence_threshold"), default=cfg.get_min_confidence_to_rank()),
    }


# -----------------------------------------------------------------------------
# Carga base
# -----------------------------------------------------------------------------
conn = db.get_connection(cfg.DB_PATH)
try:
    programs = [dict(r) for r in conn.execute(
        """
        SELECT p.*, u.name AS university_name
        FROM programs p
        JOIN universities u ON u.id = p.university_id
        ORDER BY p.updated_at DESC
        """
    ).fetchall()]

    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT
                entity_id,
                total_score,
                components,
                computed_at,
                ROW_NUMBER() OVER (
                    PARTITION BY entity_id
                    ORDER BY computed_at DESC, id DESC
                ) AS rn
            FROM score_breakdowns
            WHERE entity_type='program' AND score_name='overall_score'
        )
        SELECT
            entity_id,
            MAX(CASE WHEN rn=1 THEN total_score END) AS latest_score,
            MAX(CASE WHEN rn=1 THEN components END) AS latest_components,
            MAX(CASE WHEN rn=1 THEN computed_at END) AS latest_at,
            MAX(CASE WHEN rn=2 THEN total_score END) AS previous_score,
            MAX(CASE WHEN rn=2 THEN computed_at END) AS previous_at
        FROM ranked
        GROUP BY entity_id
        """
    ).fetchall()
    score_map = {r["entity_id"]: dict(r) for r in rows}

    change_rows = conn.execute(
        """
        SELECT entity_id, detected_at, details
        FROM audit_records
        WHERE entity_type='program'
          AND change_type IN ('sensitive_fields_changed', 'source_inconsistency')
        ORDER BY detected_at DESC
        """
    ).fetchall()
    reasons_map = {}
    for row in change_rows:
        details = _loads(row["details"])
        reason = ""
        if row["detected_at"]:
            reason = f"{row['detected_at'][:16]} · "

        if row["change_type"] == "source_inconsistency":
            reason += "Inconsistencia entre fuentes"
        else:
            changed_fields = sorted((details.get("fields") or {}).keys())
            reason += (
                "Cambios sensibles: " + ", ".join(changed_fields)
                if changed_fields else
                "Cambios sensibles detectados"
            )
        reasons_map.setdefault(row["entity_id"], []).append(reason)

    faculty_rows = [dict(r) for r in conn.execute(
        """
        SELECT f.*, u.name AS university_name
        FROM faculty f
        JOIN universities u ON u.id = f.university_id
        ORDER BY f.updated_at DESC
        """
    ).fetchall()]

    # confianza por docente desde evidencia
    fac_conf = {}
    for row in conn.execute(
        """
        SELECT entity_id, AVG(confidence_score) AS avg_conf
        FROM evidence_snippets
        WHERE entity_type='faculty' AND confidence_score IS NOT NULL
        GROUP BY entity_id
        """
    ).fetchall():
        fac_conf[row["entity_id"]] = _to_float(row["avg_conf"])

    latest_snapshot = conn.execute(
        "SELECT id, closed_at, started_at FROM scan_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
finally:
    conn.close()

if not programs:
    st.info("No hay programas cargados todavía. Ejecuta un scan primero.")
    st.stop()

# -----------------------------------------------------------------------------
# Filtros globales
# -----------------------------------------------------------------------------
langs = sorted({(_extract_language(p) or "unknown") for p in programs})
unis = sorted({p.get("university_name") for p in programs if p.get("university_name")})

f1, f2, f3, f4, f5, f6 = st.columns([1.1, 1.3, 1.2, 1.4, 1.4, 1.6])
with f1:
    lang_filter = st.selectbox("Idioma", ["all"] + langs, format_func=lambda x: "Todos" if x == "all" else x.upper())
with f2:
    uni_filter = st.selectbox("Universidad", ["all"] + unis, format_func=lambda x: "Todas" if x == "all" else x)
with f3:
    deadline_days = st.slider("Deadline ≤ días", min_value=0, max_value=365, value=120)
with f4:
    min_conf = st.slider(
        "Confianza mínima",
        min_value=0.0,
        max_value=1.0,
        value=cfg.get_min_confidence_to_rank(),
        step=0.05,
    )
with f5:
    top_n = st.slider("Top-N", min_value=3, max_value=30, value=10)
with f6:
    show_blocked = st.checkbox("Mostrar bloqueados", value=False)

now = datetime.now(timezone.utc)
filtered_programs = []
blocked_programs_count = 0
for p in programs:
    pid = p["id"]
    score_info = score_map.get(pid, {})
    components = _loads(score_info.get("latest_components"))
    confidence = _find_confidence(components)
    guard = _ranking_guard(components)
    deadline = _extract_deadline(p)
    lang = _extract_language(p)

    if lang_filter != "all" and lang != lang_filter:
        continue
    if uni_filter != "all" and p.get("university_name") != uni_filter:
        continue
    if confidence < min_conf:
        continue
    if guard["blocked"]:
        blocked_programs_count += 1
    if deadline:
        days_left = (deadline - now).days
        if days_left > deadline_days:
            continue

    filtered_programs.append(p)

# -----------------------------------------------------------------------------
# Freshness indicator
# -----------------------------------------------------------------------------
critical_dates = []
for p in filtered_programs:
    for dt_value in (p.get("updated_at"),):
        dt_obj = _to_dt(dt_value)
        if dt_obj:
            critical_dates.append(dt_obj)
for sc in score_map.values():
    dt_obj = _to_dt(sc.get("latest_at"))
    if dt_obj:
        critical_dates.append(dt_obj)
if latest_snapshot:
    snapshot_dt = _to_dt(latest_snapshot["closed_at"] or latest_snapshot["started_at"])
    if snapshot_dt:
        critical_dates.append(snapshot_dt)

if critical_dates:
    newest = max(critical_dates)
    freshness_days = (now - newest).days
    freshness_label = "🟢 Fresco" if freshness_days <= 7 else "🟡 Moderado" if freshness_days <= 30 else "🔴 Envejecido"
    st.metric("Freshness (datos críticos)", f"{freshness_days} días", freshness_label)
else:
    st.warning("No hay timestamps suficientes para estimar freshness.")

st.divider()

# -----------------------------------------------------------------------------
# Top-N programas por overall_score
# -----------------------------------------------------------------------------
st.subheader("🏆 Top-N programas actuales")
if blocked_programs_count > 0 and not show_blocked:
    st.info(
        f"Hay {blocked_programs_count} programas bloqueados por baja information_confidence. "
        "Activa “Mostrar bloqueados” para inspeccionarlos."
    )

ranked = []
for p in filtered_programs:
    pid = p["id"]
    score_info = score_map.get(pid, {})
    latest_score = _to_float(score_info.get("latest_score"), default=0.0)
    prev_score = _to_float(score_info.get("previous_score"), default=0.0)
    delta = latest_score - prev_score if score_info.get("previous_score") is not None else 0.0
    components = _loads(score_info.get("latest_components"))
    confidence = _find_confidence(components)
    guard = _ranking_guard(components)
    evidence_url = _extract_evidence_url(p)
    deadline = _extract_deadline(p)
    if guard["blocked"] and not show_blocked:
        continue
    ranked.append({
        "program_id": pid,
        "program": p.get("name"),
        "university": p.get("university_name"),
        "overall_score": round(latest_score, 3),
        "delta": round(delta, 3),
        "confidence": round(confidence, 3),
        "deadline": deadline.strftime("%Y-%m-%d") if deadline else "N/A",
        "evidence": evidence_url,
        "blocked": guard["blocked"],
        "block_reason": guard["reason"],
        "primary_issue": guard["primary_issue"],
        "threshold": round(guard["threshold"], 3),
        "sub_scores": components,
    })

ranked = sorted(ranked, key=lambda x: x["overall_score"], reverse=True)[:top_n]
if not ranked:
    st.info("No hay programas que cumplan los filtros.")
else:
    df_top = pd.DataFrame([
        {
            "Programa": r["program"],
            "Universidad": r["university"],
            "Overall": r["overall_score"],
            "Δ": r["delta"],
            "Confianza": r["confidence"],
            "Estado ranking": "🚫 Bloqueado" if r["blocked"] else "✅ Habilitado",
            "Deadline": r["deadline"],
        }
        for r in ranked
    ])
    st.dataframe(df_top, use_container_width=True, hide_index=True)

    st.markdown("**Explicabilidad por fila**")
    for i, row in enumerate(ranked, start=1):
        with st.expander(f"#{i} · {row['program']} ({row['university']})"):
            st.write(f"**Overall score:** {row['overall_score']} · **Confianza:** {row['confidence']}")
            if row["blocked"]:
                st.error(
                    "Programa bloqueado para ranking. "
                    f"Razón: {row['block_reason'] or 'Sin razón detallada.'} "
                    f"Campo principal: {row['primary_issue'] or 'information_confidence'}."
                )
            else:
                st.success("Programa habilitado para ranking.")
            sub_scores = row["sub_scores"] or {}
            visible_sub = {
                k: v for k, v in sub_scores.items()
                if k not in {"confidence", "confidence_score", "source_confidence", "evidence_confidence"}
            }
            if visible_sub:
                st.json(visible_sub)
            else:
                st.caption("Sin sub-scores detallados en components.")

            if row["evidence"]:
                st.link_button("Abrir evidencia", row["evidence"], key=f"ev_{row['program_id']}")
            else:
                st.caption("Sin enlace de evidencia disponible.")

st.divider()

# -----------------------------------------------------------------------------
# Cambios desde último snapshot (subidas / bajadas con motivo)
# -----------------------------------------------------------------------------
st.subheader("📈 Cambios desde último snapshot")
changes = []
for r in ranked:
    pid = r["program_id"]
    delta = r["delta"]
    direction = "subida" if delta > 0 else "bajada" if delta < 0 else "sin cambio"
    reasons = reasons_map.get(pid, [])
    reason = reasons[0] if reasons else "Sin motivo estructurado (solo variación de score)."
    if direction != "sin cambio":
        changes.append({
            "Programa": r["program"],
            "Universidad": r["university"],
            "Dirección": direction,
            "Δ score": delta,
            "Motivo": reason,
        })

if not changes:
    st.info("No se detectaron subidas o bajadas en el último corte disponible.")
else:
    st.dataframe(pd.DataFrame(changes), use_container_width=True, hide_index=True)

st.divider()

# -----------------------------------------------------------------------------
# Mejores docentes por objetivo
# -----------------------------------------------------------------------------
st.subheader("👩‍🏫 Mejores docentes para contactar por objetivo")
objective = st.text_input(
    "Objetivo",
    value="robotics manufacturing",
    help="Ejemplo: 'automation control', 'computer vision', 'scholarship opportunities'.",
)

objective_tokens = [
    tok.lower()
    for tok in re.split(r"[^a-zA-Z0-9áéíóúñü]+", objective)
    if tok and len(tok) > 2
]

faculty_rank = []
for f in faculty_rows:
    official = _loads(f.get("official_data"))
    inferred = _loads(f.get("inferred_data"))
    haystack = " ".join(
        str(x) for x in [
            f.get("name"),
            f.get("title"),
            f.get("university_name"),
            official.get("research_areas"),
            official.get("interests"),
            inferred.get("interests"),
            inferred.get("summary"),
        ] if x
    ).lower()

    overlap = sum(1 for tok in objective_tokens if tok in haystack)
    heuristic = overlap / max(len(objective_tokens), 1)
    confidence = fac_conf.get(f["id"], 0.0)
    final_score = (0.7 * heuristic) + (0.3 * confidence)

    profile = f.get("profile_url") or official.get("url") or ""
    faculty_rank.append({
        "Docente": f.get("name"),
        "Universidad": f.get("university_name"),
        "Fit objetivo": round(heuristic, 3),
        "Confianza": round(confidence, 3),
        "Score contacto": round(final_score, 3),
        "Perfil": profile,
    })

faculty_rank = sorted(faculty_rank, key=lambda x: x["Score contacto"], reverse=True)[:10]
if not faculty_rank:
    st.info("No hay docentes cargados.")
else:
    st.dataframe(
        pd.DataFrame([{k: v for k, v in row.items() if k != "Perfil"} for row in faculty_rank]),
        use_container_width=True,
        hide_index=True,
    )
    for idx, row in enumerate(faculty_rank, start=1):
        if row["Perfil"]:
            st.link_button(f"#{idx} {row['Docente']} · abrir perfil", row["Perfil"], key=f"profile_{idx}")

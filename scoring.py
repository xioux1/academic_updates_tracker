"""
scoring.py — Orquestación de scoring para programas por snapshot.
"""

from __future__ import annotations

import json
from typing import Optional

import database as db
import config as cfg

DEFAULT_WEIGHTS = {
    "strategic_fit": 0.30,
    "admission_fit": 0.25,
    "lifestyle_fit": 0.20,
    "contact_leverage": 0.15,
    "information_confidence": 0.10,
}

WEIGHT_KEYS = tuple(DEFAULT_WEIGHTS.keys())


def _loads(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def validate_weights(raw_weights: Optional[dict]) -> tuple[dict, dict]:
    if not isinstance(raw_weights, dict):
        return dict(DEFAULT_WEIGHTS), {"valid": False, "reason": "missing_weights"}

    normalized: dict[str, float] = {}
    for key in WEIGHT_KEYS:
        if key not in raw_weights:
            return dict(DEFAULT_WEIGHTS), {"valid": False, "reason": f"missing_key:{key}"}
        try:
            value = float(raw_weights[key])
        except (TypeError, ValueError):
            return dict(DEFAULT_WEIGHTS), {"valid": False, "reason": f"invalid_number:{key}"}
        if value < 0.0 or value > 1.0:
            return dict(DEFAULT_WEIGHTS), {"valid": False, "reason": f"out_of_range:{key}"}
        normalized[key] = value

    total = sum(normalized.values())
    if abs(total - 1.0) > 0.0001:
        return dict(DEFAULT_WEIGHTS), {"valid": False, "reason": f"sum_must_be_1:{total:.6f}"}

    rounded = {k: round(v, 4) for k, v in normalized.items()}
    return rounded, {"valid": True, "reason": "ok"}


def resolve_weights_for_profile(profile: Optional[dict]) -> tuple[dict, dict]:
    if not profile:
        return dict(DEFAULT_WEIGHTS), {
            "profile_id": None,
            "profile_key": "default",
            "weights_version": "default-v1",
            "fallback_used": True,
            "validation": {"valid": False, "reason": "missing_profile"},
        }
    derived = _loads(profile.get("derived_data"))
    weights, validation = validate_weights(derived.get("weights"))
    version = str(derived.get("weights_version") or "v1")
    metadata = {
        "profile_id": profile.get("id"),
        "profile_key": profile.get("user_key"),
        "weights_version": version,
        "fallback_used": not validation.get("valid"),
        "validation": validation,
    }
    return weights, metadata


def compute_overall_score(components: dict, weights: dict) -> float:
    total = 0.0
    for key in WEIGHT_KEYS:
        total += float(weights.get(key, 0.0)) * _clip(float(components.get(key, 0.0)))
    return round(total, 4)


def admission_fit(program: dict) -> float:
    official = _loads(program.get("official_data"))
    language = str(official.get("language") or "").lower()
    requirements = str(official.get("requirements") or "").strip()
    deadline = str(official.get("deadlines") or official.get("deadline") or "").strip()

    score = 0.35
    if "english" in language:
        score += 0.30
    elif language:
        score += 0.15
    if requirements:
        score += 0.20
    if deadline:
        score += 0.15
    return _clip(score)


def strategic_fit(program: dict) -> float:
    name = str(program.get("name") or "").lower()
    inferred = _loads(program.get("inferred_data"))
    tags = " ".join(str(v).lower() for v in inferred.values() if isinstance(v, (str, int, float)))

    score = 0.20
    for token in ("automation", "robot", "manufactur", "intelligent", "control", "ai"):
        if token in name or token in tags:
            score += 0.12
    return _clip(score)


def lifestyle_fit(program: dict) -> float:
    derived = _loads(program.get("derived_data"))
    tuition_raw = str(derived.get("tuition") or _loads(program.get("official_data")).get("tuition") or "")
    tuition_digits = "".join(ch for ch in tuition_raw if ch.isdigit())
    tuition = int(tuition_digits) if tuition_digits else None

    score = 0.55
    if tuition is not None:
        if tuition <= 60000:
            score += 0.25
        elif tuition <= 120000:
            score += 0.15
        else:
            score -= 0.10
    return _clip(score)


def contact_leverage(program: dict, faculty_count: int) -> float:
    official = _loads(program.get("official_data"))
    supervisor_required = str(official.get("supervisor_required") or "").lower()

    score = 0.25
    if faculty_count >= 8:
        score += 0.50
    elif faculty_count >= 3:
        score += 0.35
    elif faculty_count > 0:
        score += 0.20
    if supervisor_required in ("yes", "true", "1"):
        score += 0.10
    return _clip(score)


def information_confidence(program: dict, evidence_count: int, inconsistent: bool) -> float:
    derived = _loads(program.get("derived_data"))
    source_values = derived.get("source_values") if isinstance(derived.get("source_values"), dict) else {}
    corroborated_fields = 0
    for values in source_values.values():
        if isinstance(values, dict) and len([v for v in values.values() if v not in (None, "")]) >= 2:
            corroborated_fields += 1

    score = 0.20
    if evidence_count >= 6:
        score += 0.45
    elif evidence_count >= 3:
        score += 0.30
    elif evidence_count >= 1:
        score += 0.18
    score += min(corroborated_fields * 0.06, 0.24)
    if inconsistent:
        score -= 0.30
    return _clip(score)


def _build_rankability_metadata(
    confidence_score: float,
    evidence_count: int,
    inconsistent: bool,
) -> dict:
    threshold = cfg.get_min_confidence_to_rank()
    blocked = confidence_score < threshold

    if not blocked:
        return {
            "ranking_blocked": False,
            "ranking_block_reason": "",
            "ranking_primary_issue": "",
            "ranking_min_confidence_threshold": round(threshold, 4),
        }

    if inconsistent:
        reason = (
            f"Bloqueado para ranking: information_confidence={confidence_score:.3f} "
            f"está bajo el umbral {threshold:.3f} y hay conflicto entre fuentes."
        )
        primary_issue = "source_inconsistency"
    elif evidence_count <= 0:
        reason = (
            f"Bloqueado para ranking: information_confidence={confidence_score:.3f} "
            f"está bajo el umbral {threshold:.3f} por falta de evidencia."
        )
        primary_issue = "evidence_count"
    else:
        reason = (
            f"Bloqueado para ranking: information_confidence={confidence_score:.3f} "
            f"está bajo el umbral {threshold:.3f}."
        )
        primary_issue = "information_confidence"

    return {
        "ranking_blocked": True,
        "ranking_block_reason": reason,
        "ranking_primary_issue": primary_issue,
        "ranking_min_confidence_threshold": round(threshold, 4),
    }


def score_snapshot(snapshot_id: int, db_path: str) -> dict:
    conn = db.get_connection(db_path)
    results = {
        "snapshot_id": snapshot_id,
        "programs_scored": 0,
        "programs_omitted": 0,
        "omitted_cases": [],
    }
    try:
        programs = [dict(r) for r in conn.execute("SELECT * FROM programs").fetchall()]
        if not programs:
            return results

        faculty_by_uni = {
            r["university_id"]: r["cnt"]
            for r in conn.execute(
                "SELECT university_id, COUNT(*) AS cnt FROM faculty GROUP BY university_id"
            ).fetchall()
        }

        evidence_by_program = {
            r["entity_id"]: r["cnt"]
            for r in conn.execute(
                """SELECT entity_id, COUNT(*) AS cnt
                   FROM evidence_snippets
                   WHERE entity_type='program'
                   GROUP BY entity_id"""
            ).fetchall()
        }
    finally:
        conn.close()

    active_profile = db.get_active_user_profile(db_path)
    active_weights, weights_meta = resolve_weights_for_profile(active_profile)

    for program in programs:
        program_id = program["id"]
        if str(program.get("status") or "active").lower() not in ("active", ""):
            results["programs_omitted"] += 1
            results["omitted_cases"].append({"program_id": program_id, "reason": "status_not_active"})
            continue

        a_fit = admission_fit(program)
        s_fit = strategic_fit(program)
        l_fit = lifestyle_fit(program)
        c_lev = contact_leverage(program, faculty_by_uni.get(program["university_id"], 0))
        inconsistent = bool(program.get("inconsistency_flag"))
        evidence_count = evidence_by_program.get(program_id, 0)
        i_conf = information_confidence(program, evidence_count, inconsistent)
        rankability = _build_rankability_metadata(i_conf, evidence_count, inconsistent)

        sub_scores = {
            "admission_fit": round(a_fit, 4),
            "strategic_fit": round(s_fit, 4),
            "lifestyle_fit": round(l_fit, 4),
            "contact_leverage": round(c_lev, 4),
            "information_confidence": round(i_conf, 4),
        }
        overall = compute_overall_score(sub_scores, active_weights)
        components = {
            **sub_scores,
            "confidence_score": round(i_conf, 4),
            "evidence_count": evidence_count,
            "weights_used": active_weights,
            "weights_profile_id": weights_meta["profile_id"],
            "weights_profile_key": weights_meta["profile_key"],
            "weights_version": weights_meta["weights_version"],
            "weights_fallback_used": weights_meta["fallback_used"],
            "weights_validation": weights_meta["validation"],
            **rankability,
        }
        explanation = (
            "Weighted blend of admission, strategic, lifestyle, contact leverage, "
            "and information confidence sub-scores."
        )
        explanation += (
            f" Weights profile={weights_meta['profile_key'] or 'default'}"
            f" version={weights_meta['weights_version']}."
        )
        if rankability["ranking_blocked"]:
            explanation += f" {rankability['ranking_block_reason']}"

        db.upsert_score_breakdown(
            entity_type="program",
            entity_id=program_id,
            score_name="overall_score",
            snapshot_id=snapshot_id,
            score_value=round(overall, 4),
            components=components,
            explanation=explanation,
            confidence_score=round(i_conf, 4),
            weights_profile_id=weights_meta["profile_id"],
            weights_version=weights_meta["weights_version"],
            db_path=db_path,
        )
        results["programs_scored"] += 1

    return results

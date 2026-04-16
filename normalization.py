"""Normalization helpers for scraped academic program metadata.

This module keeps raw extractor outputs untouched and derives normalized values
with explicit ambiguity markers for downstream persistence and auditing.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

LANGUAGE_TAXONOMY = {"en", "zh", "bilingual", "unknown"}

_LANGUAGE_VARIANTS: dict[str, str] = {
    "english": "en",
    "en": "en",
    "chinese": "zh",
    "zh": "zh",
    "中文": "zh",
    "汉语": "zh",
    "bilingual": "bilingual",
    "english/chinese": "bilingual",
    "chinese/english": "bilingual",
    "中英": "bilingual",
    "中英双语": "bilingual",
}

PROGRAM_NAME_VARIANTS: dict[str, str] = {
    "master program in computer science": "MSc Computer Science",
    "m.sc. in computer science": "MSc Computer Science",
    "msc computer science": "MSc Computer Science",
    "master program in data science": "MSc Data Science",
    "m.sc. in data science": "MSc Data Science",
    "msc data science": "MSc Data Science",
}

DEPARTMENT_NAME_VARIANTS: dict[str, str] = {
    "dept. of computer science": "Department of Computer Science",
    "department of computer science and engineering": "Department of Computer Science",
    "school of computer science and engineering": "School of Computer Science",
}


_MONTH_FORMATS = ("%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y/%m/%d")


def normalize_language(raw_value: Optional[str]) -> dict[str, Any]:
    raw = (raw_value or "").strip()
    key = raw.lower()
    normalized = _LANGUAGE_VARIANTS.get(key)
    ambiguous = normalized is None
    if not normalized:
        normalized = "unknown"
    return {"raw": raw_value, "normalized": normalized, "ambiguous": ambiguous}


def normalize_date(raw_value: Optional[str]) -> dict[str, Any]:
    raw = (raw_value or "").strip()
    if not raw:
        return {"raw": raw_value, "normalized": None, "ambiguous": True}

    for fmt in _MONTH_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
            return {"raw": raw_value, "normalized": parsed.strftime("%Y-%m-%d"), "ambiguous": False}
        except ValueError:
            continue

    ambiguous_tokens = {"rolling basis", "tbd", "to be announced"}
    if raw.lower() in ambiguous_tokens:
        return {"raw": raw_value, "normalized": None, "ambiguous": True}

    return {"raw": raw_value, "normalized": None, "ambiguous": True}


def normalize_tuition(raw_value: Optional[str]) -> dict[str, Any]:
    raw = (raw_value or "").strip()
    if not raw:
        return {"raw": raw_value, "normalized": None, "ambiguous": True}

    currency = None
    if re.search(r"\b(?:rmb|cny)\b|¥|元", raw, flags=re.IGNORECASE):
        currency = "CNY"
    elif re.search(r"\b(?:usd)\b|\$", raw, flags=re.IGNORECASE):
        currency = "USD"

    amount_match = re.search(r"(\d[\d,]*(?:\.\d+)?)", raw)
    amount_value: Optional[float] = None
    if amount_match:
        amount_value = float(amount_match.group(1).replace(",", ""))

    periodicity = "annual" if re.search(r"per\s*year|/year|annual", raw, flags=re.IGNORECASE) else None

    ambiguous = currency is None or amount_value is None
    normalized = None
    if not ambiguous:
        normalized = {
            "amount": amount_value,
            "currency": currency,
            "periodicity": periodicity,
        }
    return {"raw": raw_value, "normalized": normalized, "ambiguous": ambiguous}


def _normalize_variant(raw_name: Optional[str], mapping: dict[str, str]) -> dict[str, Any]:
    raw = (raw_name or "").strip()
    key = raw.lower()
    normalized = mapping.get(key, raw if raw else None)
    ambiguous = bool(raw) and key not in mapping
    return {"raw": raw_name, "normalized": normalized, "ambiguous": ambiguous}


def normalize_program_name(raw_name: Optional[str]) -> dict[str, Any]:
    return _normalize_variant(raw_name, PROGRAM_NAME_VARIANTS)


def normalize_department_name(raw_name: Optional[str]) -> dict[str, Any]:
    return _normalize_variant(raw_name, DEPARTMENT_NAME_VARIANTS)


def normalize_program_payload(program: dict[str, Any]) -> dict[str, Any]:
    critical_fields = program.get("critical_fields", {})
    language = normalize_language(critical_fields.get("language"))
    deadlines = normalize_date(critical_fields.get("deadlines"))
    tuition = normalize_tuition(critical_fields.get("tuition"))
    program_name = normalize_program_name(program.get("name"))
    department_name = normalize_department_name(program.get("department_name"))

    ambiguity = {
        "language": language["ambiguous"],
        "deadlines": deadlines["ambiguous"],
        "tuition": tuition["ambiguous"],
        "program_name": program_name["ambiguous"],
        "department_name": department_name["ambiguous"],
    }

    return {
        "canonical_name": program_name["normalized"] or program.get("name"),
        "official_data": {
            "program_name": {"raw": program.get("name")},
            "department_name": {"raw": program.get("department_name")},
            "critical_fields": {
                "language": {"raw": critical_fields.get("language")},
                "deadlines": {"raw": critical_fields.get("deadlines")},
                "tuition": {"raw": critical_fields.get("tuition")},
            },
        },
        "derived_data": {
            "program_name": program_name,
            "department_name": department_name,
            "critical_fields": {
                "language": language,
                "deadlines": deadlines,
                "tuition": tuition,
            },
            "ambiguity_flags": ambiguity,
            "normalization_confident": not any(ambiguity.values()),
            "language_taxonomy": sorted(LANGUAGE_TAXONOMY),
        },
    }

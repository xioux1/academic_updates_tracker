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
    "英语": "en",
    "chinese": "zh",
    "zh": "zh",
    "中文": "zh",
    "汉语": "zh",
    "中文授课": "zh",
    "bilingual": "bilingual",
    "english/chinese": "bilingual",
    "chinese/english": "bilingual",
    "english / chinese": "bilingual",
    "chinese / english": "bilingual",
    "english and chinese": "bilingual",
    "chinese and english": "bilingual",
    "中英": "bilingual",
    "中英双语": "bilingual",
    "双语": "bilingual",
}

PROGRAM_NAME_VARIANTS: dict[str, str] = {
    "master program in computer science": "MSc Computer Science",
    "m.sc. in computer science": "MSc Computer Science",
    "msc computer science": "MSc Computer Science",
    "master of science in computer science": "MSc Computer Science",
    "computer science master program": "MSc Computer Science",
    "master program in data science": "MSc Data Science",
    "m.sc. in data science": "MSc Data Science",
    "msc data science": "MSc Data Science",
    "master of science in data science": "MSc Data Science",
    "data science master program": "MSc Data Science",
    "master of engineering in electronic information": "MEng Electronic Information",
    "m.eng. in electronic information": "MEng Electronic Information",
    "electronic information master of engineering": "MEng Electronic Information",
    "电子信息工程硕士": "MEng Electronic Information",
    "master program in artificial intelligence": "MSc Artificial Intelligence",
    "master of science in artificial intelligence": "MSc Artificial Intelligence",
    "artificial intelligence master program": "MSc Artificial Intelligence",
    "人工智能硕士": "MSc Artificial Intelligence",
}

DEPARTMENT_NAME_VARIANTS: dict[str, str] = {
    "dept. of computer science": "Department of Computer Science",
    "department of computer science": "Department of Computer Science",
    "department of computer science and engineering": "Department of Computer Science",
    "computer science and engineering department": "Department of Computer Science",
    "school of computer science and engineering": "School of Computer Science",
    "school of computer science & engineering": "School of Computer Science",
    "school of computer and information engineering": "School of Computer Science",
    "计算机科学与工程学院": "School of Computer Science",
    "电子与信息工程学院": "School of Electronic and Information Engineering",
    "电子信息与电气工程学院": "School of Electronic and Information Engineering",
}


_MONTH_FORMATS = ("%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y/%m/%d")
_CHINESE_DATE_PATTERNS = (
    r"^\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*$",
    r"^\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*$",
    r"^\s*(\d{4})[-/]\s*(\d{1,2})[-/]\s*(\d{1,2})\s*$",
)


def _normalize_lookup_key(raw_value: Optional[str]) -> str:
    raw = (raw_value or "").strip().lower()
    if not raw:
        return ""
    key = re.sub(r"[()（）\[\]【】,，;；]+", " ", raw)
    key = key.replace("&", " and ").replace("/", " / ")
    return re.sub(r"\s+", " ", key).strip()


def normalize_language(raw_value: Optional[str]) -> dict[str, Any]:
    raw = (raw_value or "").strip()
    key = _normalize_lookup_key(raw)
    normalized = _LANGUAGE_VARIANTS.get(key)
    ambiguous = normalized is None
    if not normalized:
        normalized = "unknown"
    return {"raw": raw_value, "normalized": normalized, "ambiguous": ambiguous}


def normalize_date(raw_value: Optional[str]) -> dict[str, Any]:
    raw = (raw_value or "").strip()
    if not raw:
        return {"raw": raw_value, "normalized": None, "ambiguous": True}

    compact_range = re.search(r"(\d{4}[./-]\d{1,2}[./-]\d{1,2})\s*(?:to|~|–|-|至)\s*(\d{4}[./-]\d{1,2}[./-]\d{1,2})", raw)
    if compact_range:
        return {"raw": raw_value, "normalized": None, "ambiguous": True}

    for pattern in _CHINESE_DATE_PATTERNS:
        match = re.match(pattern, raw)
        if match:
            year, month, day = (int(v) for v in match.groups())
            return {"raw": raw_value, "normalized": f"{year:04d}-{month:02d}-{day:02d}", "ambiguous": False}

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

    if re.search(r"\b(?:or|and)\b|至|~|–|-", raw, flags=re.IGNORECASE):
        numeric_tokens = re.findall(r"\d[\d,]*(?:\.\d+)?", raw)
        if len(numeric_tokens) > 1:
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

    if re.search(r"per\s*year|/year|annual|每年|每学年", raw, flags=re.IGNORECASE):
        periodicity = "annual"
    elif re.search(r"per\s*semester|/semester|semester|每学期", raw, flags=re.IGNORECASE):
        periodicity = "semester"
    elif re.search(r"total|in total|总计", raw, flags=re.IGNORECASE):
        periodicity = "total"
    else:
        periodicity = None

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
    key = _normalize_lookup_key(raw)
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

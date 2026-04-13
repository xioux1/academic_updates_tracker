"""
analyzer.py — Claude API relevance analysis for AcademicRadar.

For each unanalyzed finding, calls Claude with the user's profile as system context,
and stores the structured JSON result back in the database.
"""

import json
import logging
import time
from typing import Optional

import anthropic

import database as db
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, get_user_profile

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

ANALYSIS_USER_TEMPLATE = """
Analiza el siguiente resultado académico y evalúa su relevancia para Simon.

TÍTULO: {title}
FUENTE: {source}
FECHA PUBLICACIÓN: {date_published}
IDIOMA ORIGINAL: {language}
ES FUENTE CHINA: {is_chinese}

CONTENIDO ORIGINAL:
{content}

Responde ÚNICAMENTE con un objeto JSON válido con este esquema exacto (sin markdown, sin texto extra):
{{
  "summary": "resumen en español de 2-3 oraciones del contenido",
  "relevance_score": <entero 1-10>,
  "relevance_reason": "explicación de por qué es o no es relevante para Simon",
  "actionable": <true o false>,
  "action_suggestion": "qué acción concreta puede hacer Simon, o null si no es actionable",
  "translation": "traducción al español del contenido original si estaba en chino, o null si ya estaba en inglés"
}}
""".strip()


# ---------------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------------

def analyze_finding(finding: dict) -> Optional[dict]:
    """
    Send a single finding to Claude for relevance analysis.
    Returns the parsed analysis dict, or None on failure.
    """
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY is not set — skipping analysis")
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    content_text = (finding.get("summary_original") or finding.get("title") or "")[:3000]
    language_label = "Chino" if finding.get("language") == "zh" else "Inglés"
    is_chinese_label = "Sí" if finding.get("is_chinese_source") else "No"

    user_msg = ANALYSIS_USER_TEMPLATE.format(
        title=finding.get("title", "Sin título"),
        source=finding.get("source_name", "Desconocida"),
        date_published=finding.get("date_published") or "Desconocida",
        language=language_label,
        is_chinese=is_chinese_label,
        content=content_text or "(sin contenido disponible)",
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=get_user_profile(),
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        analysis = json.loads(raw)

        # Validate / coerce expected fields
        score = int(analysis.get("relevance_score", 5))
        analysis["relevance_score"] = max(1, min(10, score))
        analysis["actionable"] = bool(analysis.get("actionable", False))
        if not analysis.get("action_suggestion"):
            analysis["action_suggestion"] = None
        if not analysis.get("translation"):
            analysis["translation"] = None

        return analysis

    except json.JSONDecodeError as e:
        log.error("Claude returned invalid JSON for finding %s: %s | raw=%s",
                  finding.get("id"), e, raw[:200])
        return None
    except anthropic.RateLimitError:
        log.warning("Claude rate limit hit — sleeping 60s")
        time.sleep(60)
        return None
    except anthropic.APIError as e:
        log.error("Claude API error for finding %s: %s", finding.get("id"), e)
        return None
    except Exception as e:
        log.error("Unexpected error analyzing finding %s: %s", finding.get("id"), e)
        return None


# ---------------------------------------------------------------------------
# Batch analysis runner
# ---------------------------------------------------------------------------

def run_analysis(
    db_path: str = None,
    batch_size: int = 50,
    delay_between_calls: float = 1.0,
    progress_callback=None,
) -> dict:
    """
    Analyze all unanalyzed findings in the database.

    Args:
        db_path: Path to the SQLite database.
        batch_size: Maximum number of findings to process per run.
        delay_between_calls: Seconds to wait between Claude API calls.
        progress_callback: Optional callable(current, total, finding_title) for UI progress.

    Returns:
        dict with 'analyzed', 'failed', 'skipped' counts.
    """
    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    results = {"analyzed": 0, "failed": 0, "skipped": 0}

    unanalyzed = db.get_findings(
        db_path=db_path,
        unanalyzed=True,
        limit=batch_size,
    )

    total = len(unanalyzed)
    log.info("Starting analysis of %d unanalyzed findings", total)

    for i, finding in enumerate(unanalyzed):
        if progress_callback:
            try:
                progress_callback(i + 1, total, finding.get("title", ""))
            except Exception:
                pass

        analysis = analyze_finding(finding)

        if analysis:
            try:
                db.update_finding_analysis(finding["id"], analysis, db_path)
                results["analyzed"] += 1
                log.info(
                    "Analyzed finding %d — score %s, actionable=%s",
                    finding["id"], analysis["relevance_score"], analysis["actionable"],
                )
            except Exception as e:
                log.error("Failed to save analysis for finding %d: %s", finding["id"], e)
                results["failed"] += 1
        else:
            results["failed"] += 1

        if i < total - 1:
            time.sleep(delay_between_calls)

    log.info(
        "Analysis complete: %d analyzed, %d failed, %d skipped",
        results["analyzed"], results["failed"], results["skipped"],
    )
    return results

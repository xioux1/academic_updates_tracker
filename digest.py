"""
digest.py — Weekly digest generation and SMTP email sending for AcademicRadar.

The digest includes:
- Summary statistics for the week
- Top findings sorted by relevance score
- Actionable items highlighted
- Findings grouped by professor
"""

import logging
import smtplib
import json
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import database as db
from config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    EMAIL_TO, EMAIL_FROM, EMAIL_SUBJECT_PREFIX,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Digest generation
# ---------------------------------------------------------------------------

def generate_digest(
    db_path: str = None,
    days_back: int = 7,
) -> dict:
    """
    Build the digest data structure for the past `days_back` days.
    Returns a dict that can be serialized to JSON and also rendered as HTML/text.
    """
    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    conn = db.get_connection(db_path)
    try:
        # All findings from the period
        rows = conn.execute(
            """SELECT f.*,
                      p.name AS professor_name,
                      p.name_chinese AS professor_name_chinese,
                      s.name AS source_name
               FROM findings f
               LEFT JOIN professors p ON p.id = f.professor_id
               LEFT JOIN sources    s ON s.id = f.source_id
               WHERE f.date_found >= ?
               ORDER BY COALESCE(f.relevance_score, 0) DESC, f.date_found DESC""",
            (cutoff_str,),
        ).fetchall()
        findings = [dict(r) for r in rows]

        # Stats
        total = len(findings)
        analyzed = sum(1 for f in findings if f.get("relevance_score") is not None)
        actionable = [f for f in findings if f.get("actionable")]
        high_score = [f for f in findings if (f.get("relevance_score") or 0) >= 7]

        # Group by professor
        by_professor: dict[str, list] = {}
        unlinked = []
        for f in findings:
            prof = f.get("professor_name") or "Sin profesor asignado"
            if f.get("professor_id"):
                by_professor.setdefault(prof, []).append(f)
            else:
                unlinked.append(f)

        scan_history = db.get_scan_history(db_path, limit=1)
        last_scan = scan_history[0]["date_ran"] if scan_history else "N/A"

    finally:
        conn.close()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_days": days_back,
        "cutoff_date": cutoff_str,
        "stats": {
            "total_findings": total,
            "analyzed": analyzed,
            "actionable_count": len(actionable),
            "high_score_count": len(high_score),
            "last_scan": last_scan,
        },
        "top_findings": findings[:20],
        "actionable_items": actionable[:10],
        "by_professor": {prof: items[:5] for prof, items in by_professor.items()},
        "unlinked_findings": unlinked[:10],
    }


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _score_badge(score: Optional[int]) -> str:
    if score is None:
        return '<span style="background:#555;color:#fff;padding:2px 6px;border-radius:4px;font-size:12px">N/A</span>'
    color = "#28a745" if score >= 7 else "#ffc107" if score >= 4 else "#dc3545"
    return f'<span style="background:{color};color:#fff;padding:2px 6px;border-radius:4px;font-size:12px">{score}/10</span>'


def _finding_html(f: dict) -> str:
    score_html = _score_badge(f.get("relevance_score"))
    source = f.get("source_name", "")
    cn_badge = ' <span style="background:#c00;color:#fff;padding:1px 4px;border-radius:3px;font-size:11px">🇨🇳 Fuente china</span>' if f.get("is_chinese_source") else ""
    action_html = ""
    if f.get("actionable") and f.get("action_suggestion"):
        action_html = f'<p style="color:#0d6efd;font-size:13px">▶ <strong>Acción sugerida:</strong> {f["action_suggestion"]}</p>'

    summary = f.get("summary_claude") or f.get("summary_original") or ""
    if summary and len(summary) > 300:
        summary = summary[:300] + "…"

    return f"""
<div style="border:1px solid #333;border-radius:6px;padding:12px;margin-bottom:12px;background:#1e1e2e;">
  <p style="margin:0 0 6px 0;">
    {score_html} &nbsp;
    <strong><a href="{f.get('url','#')}" style="color:#7aa2f7;text-decoration:none;">{f.get('title','Sin título')}</a></strong>
    {cn_badge}
  </p>
  <p style="margin:0 0 4px 0;color:#888;font-size:12px;">{source} · {f.get('date_published') or f.get('date_found','')}</p>
  {f'<p style="color:#cdd6f4;font-size:13px;margin:6px 0;">{summary}</p>' if summary else ''}
  {f'<p style="color:#aaa;font-size:12px;font-style:italic;">{f.get("relevance_reason","")}</p>' if f.get("relevance_reason") else ''}
  {action_html}
</div>
""".strip()


def render_html(digest: dict) -> str:
    stats = digest["stats"]
    generated = digest["generated_at"][:10]

    # Top section
    top_html = "\n".join(_finding_html(f) for f in digest["top_findings"][:15])

    # Actionable section
    if digest["actionable_items"]:
        action_html = "\n".join(_finding_html(f) for f in digest["actionable_items"])
        action_section = f"""
<h2 style="color:#f38ba8;border-bottom:1px solid #333;padding-bottom:6px;">
  ⚡ Items Accionables ({stats['actionable_count']})
</h2>
{action_html}
"""
    else:
        action_section = ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ background:#11111b; color:#cdd6f4; font-family:'Segoe UI',sans-serif;
          max-width:800px; margin:0 auto; padding:24px; }}
  h1 {{ color:#cba6f7; }}
  h2 {{ color:#89b4fa; }}
  a  {{ color:#7aa2f7; }}
</style>
</head>
<body>
<h1>🎓 AcademicRadar — Digest Semanal</h1>
<p style="color:#888;">Generado: {generated} &nbsp;|&nbsp; Período: últimos {digest['period_days']} días</p>

<div style="background:#1e1e2e;border-radius:8px;padding:16px;margin:16px 0;display:flex;gap:24px;flex-wrap:wrap;">
  <div><strong style="font-size:24px;color:#a6e3a1;">{stats['total_findings']}</strong><br><span style="color:#888;font-size:12px;">Findings totales</span></div>
  <div><strong style="font-size:24px;color:#f38ba8;">{stats['actionable_count']}</strong><br><span style="color:#888;font-size:12px;">Accionables</span></div>
  <div><strong style="font-size:24px;color:#fab387;">{stats['high_score_count']}</strong><br><span style="color:#888;font-size:12px;">Score ≥ 7</span></div>
  <div><strong style="font-size:24px;color:#89dceb;">{stats['analyzed']}</strong><br><span style="color:#888;font-size:12px;">Analizados</span></div>
</div>

{action_section}

<h2 style="color:#89b4fa;border-bottom:1px solid #333;padding-bottom:6px;">
  📄 Top Findings por Relevancia
</h2>
{top_html}

<hr style="border-color:#333;margin:24px 0;">
<p style="color:#555;font-size:11px;text-align:center;">
  AcademicRadar · Último scan: {stats['last_scan']}
</p>
</body>
</html>"""


def render_plaintext(digest: dict) -> str:
    stats = digest["stats"]
    lines = [
        "=" * 60,
        "ACADEMICRADAR — DIGEST SEMANAL",
        f"Generado: {digest['generated_at'][:10]}  |  Período: {digest['period_days']} días",
        "=" * 60,
        f"Findings totales: {stats['total_findings']}",
        f"Accionables:      {stats['actionable_count']}",
        f"Score >= 7:       {stats['high_score_count']}",
        f"Analizados:       {stats['analyzed']}",
        f"Último scan:      {stats['last_scan']}",
        "",
    ]

    if digest["actionable_items"]:
        lines.append("⚡ ITEMS ACCIONABLES")
        lines.append("-" * 40)
        for f in digest["actionable_items"]:
            score = f.get("relevance_score") or "?"
            lines.append(f"[{score}/10] {f.get('title','')}")
            lines.append(f"  URL: {f.get('url','')}")
            if f.get("action_suggestion"):
                lines.append(f"  → {f['action_suggestion']}")
            lines.append("")

    lines.append("📄 TOP FINDINGS")
    lines.append("-" * 40)
    for f in digest["top_findings"][:15]:
        score = f.get("relevance_score") or "?"
        lines.append(f"[{score}/10] {f.get('title','')}")
        lines.append(f"  {f.get('source_name','')} · {f.get('date_published') or ''}")
        lines.append(f"  URL: {f.get('url','')}")
        if f.get("summary_claude"):
            summary = f["summary_claude"][:200]
            lines.append(f"  {summary}…" if len(f["summary_claude"]) > 200 else f"  {summary}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------

def send_digest_email(digest: dict, to_address: str = EMAIL_TO) -> bool:
    """
    Send the digest as a multipart HTML + plaintext email.
    Returns True on success, False on failure.
    """
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, to_address]):
        log.error("SMTP not fully configured — cannot send email")
        return False

    stats = digest["stats"]
    subject = (
        f"{EMAIL_SUBJECT_PREFIX} Digest Semanal — "
        f"{stats['total_findings']} findings, "
        f"{stats['actionable_count']} accionables"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM or SMTP_USER
    msg["To"] = to_address

    part_text = MIMEText(render_plaintext(digest), "plain", "utf-8")
    part_html = MIMEText(render_html(digest), "html", "utf-8")
    msg.attach(part_text)
    msg.attach(part_html)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(msg["From"], [to_address], msg.as_string())
        log.info("Digest email sent to %s", to_address)
        return True
    except Exception as e:
        log.error("Failed to send digest email: %s", e)
        return False


# ---------------------------------------------------------------------------
# Main entrypoint used by GitHub Actions and the dashboard
# ---------------------------------------------------------------------------

def run_digest(db_path: str = None, send_email: bool = True) -> dict:
    """
    Generate and optionally email the weekly digest.
    Returns the saved digest record.
    """
    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    log.info("Generating weekly digest…")
    digest = generate_digest(db_path=db_path)

    digest_id = db.save_digest(
        content=digest,
        findings_count=digest["stats"]["total_findings"],
        db_path=db_path,
    )

    if send_email and EMAIL_TO:
        sent = send_digest_email(digest, to_address=EMAIL_TO)
        if sent:
            db.mark_digest_sent(digest_id, db_path)
    else:
        log.info("Email sending skipped (send_email=%s, EMAIL_TO=%r)", send_email, EMAIL_TO)

    return {"digest_id": digest_id, "digest": digest}

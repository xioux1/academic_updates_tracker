"""
config.py — Global configuration, environment variables, and user profile.
All secrets are read from env vars; no hard-coded credentials.
"""

import os
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

# ---------------------------------------------------------------------------
# SMTP / Email
# ---------------------------------------------------------------------------

SMTP_HOST: str  = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int  = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER: str  = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")
EMAIL_TO: str   = os.environ.get("EMAIL_TO", "")
EMAIL_FROM: str = os.environ.get("EMAIL_FROM", SMTP_USER)
EMAIL_SUBJECT_PREFIX: str = "[AcademicRadar]"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get("DB_PATH", "academic_radar.db")

# ---------------------------------------------------------------------------
# Scraper behaviour
# ---------------------------------------------------------------------------

SCRAPER_DELAY_SECONDS: float = float(os.environ.get("SCRAPER_DELAY", "2.0"))
ARXIV_MAX_RESULTS: int = int(os.environ.get("ARXIV_MAX_RESULTS", "30"))
SCHOLAR_MAX_RESULTS: int = int(os.environ.get("SCHOLAR_MAX_RESULTS", "10"))
DAYS_LOOKBACK: int = int(os.environ.get("DAYS_LOOKBACK", "30"))

# arXiv categories of interest
ARXIV_CATEGORIES: list[str] = ["cs.RO", "cs.SY", "eess.SY", "cs.AI", "eess.SP"]

# Browser-like headers for Chinese sources
BROWSER_HEADERS: dict = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ---------------------------------------------------------------------------
# User profile (passed to Claude as system context)
# This can be overridden at runtime via the dashboard's Config view.
# ---------------------------------------------------------------------------

DEFAULT_USER_PROFILE: str = """
Eres un asistente de investigación académica para un ingeniero argentino llamado Simon que está evaluando profesores para hacer un master en automatización industrial en Shenzhen, China.

Su perfil: estudiante de ingeniería de sistemas, con proyectos reales en hardware (máquina expendedora con sistemas mecánicos, electrónicos y software) y software (app de estudio con IA). Trabaja en una panificadora familiar hace 6 años. Su objetivo es hacer un master en automatización/manufactura inteligente, aprender de la industria china, y volver a Argentina a importar y diseñar maquinaria industrial, con foco inicial en equipamiento para panificación.

Para evaluar relevancia considera:
- ¿El trabajo se relaciona con automatización industrial, robótica aplicada, control de sistemas, diseño de maquinaria, manufactura inteligente, o procesamiento de alimentos?
- ¿Hay aplicación práctica a industria manufacturera real (no solo robótica académica)?
- ¿El profesor o laboratorio tiene vínculos con empresas de Shenzhen?
- ¿Hay algo específico que Simon podría mencionar en un mail de contacto?
- ¿Hay alguna oportunidad de colaboración, proyecto, o posición de estudiante?

Si el contenido está en chino, tradúcelo primero y luego analízalo.
""".strip()

USER_PROFILE_FILE: str = "user_profile.txt"


def get_user_profile() -> str:
    """Load user profile from file if it exists, otherwise return default."""
    if os.path.exists(USER_PROFILE_FILE):
        with open(USER_PROFILE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content
    return DEFAULT_USER_PROFILE


def save_user_profile(profile: str) -> None:
    with open(USER_PROFILE_FILE, "w", encoding="utf-8") as f:
        f.write(profile)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def credentials_ok() -> dict[str, bool]:
    """Return a dict of which required credentials are configured."""
    return {
        "anthropic_api_key": bool(ANTHROPIC_API_KEY),
        "smtp_configured":   bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD),
        "email_to":          bool(EMAIL_TO),
    }

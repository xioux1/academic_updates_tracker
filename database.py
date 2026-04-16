"""
database.py — All SQLite operations for AcademicRadar.
Handles schema creation, seeding, and CRUD for every table.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "academic_radar.db")


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS professors (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    name_chinese     TEXT,
    university       TEXT,
    department       TEXT,
    email            TEXT,
    google_scholar_id TEXT,
    github_username  TEXT,
    research_areas   TEXT,          -- comma-separated
    status           TEXT NOT NULL DEFAULT 'watching'
                         CHECK(status IN ('active','discarded','watching')),
    notes            TEXT,
    date_added       TEXT NOT NULL,
    date_modified    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS keywords (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT NOT NULL,
    language    TEXT NOT NULL DEFAULT 'en'
                    CHECK(language IN ('en','zh')),
    category    TEXT NOT NULL DEFAULT 'topic'
                    CHECK(category IN ('professor_name','topic','institution')),
    weight      INTEGER NOT NULL DEFAULT 3
                    CHECK(weight BETWEEN 1 AND 5),
    active      INTEGER NOT NULL DEFAULT 1,
    date_added  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    url_pattern       TEXT,
    type              TEXT NOT NULL
                          CHECK(type IN ('google_scholar','arxiv','github',
                                         'cnki','baidu_scholar','rss')),
    active            INTEGER NOT NULL DEFAULT 1,
    supports_chinese  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS findings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    professor_id     INTEGER REFERENCES professors(id) ON DELETE SET NULL,
    keyword_id       INTEGER REFERENCES keywords(id) ON DELETE SET NULL,
    source_id        INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    title            TEXT NOT NULL,
    url              TEXT UNIQUE NOT NULL,
    date_published   TEXT,
    date_found       TEXT NOT NULL,
    summary_original TEXT,
    summary_claude   TEXT,
    relevance_score  INTEGER CHECK(relevance_score BETWEEN 1 AND 10),
    language         TEXT NOT NULL DEFAULT 'en'
                         CHECK(language IN ('en','zh')),
    is_chinese_source INTEGER NOT NULL DEFAULT 0,
    read             INTEGER NOT NULL DEFAULT 0,
    actionable       INTEGER NOT NULL DEFAULT 0,
    notes            TEXT,
    relevance_reason TEXT,
    action_suggestion TEXT,
    translation      TEXT
);

CREATE TABLE IF NOT EXISTS digests (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    date_generated TEXT NOT NULL,
    content_json   TEXT,
    email_sent     INTEGER NOT NULL DEFAULT 0,
    findings_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date_ran            TEXT NOT NULL,
    professors_scanned  INTEGER NOT NULL DEFAULT 0,
    keywords_scanned    INTEGER NOT NULL DEFAULT 0,
    findings_total      INTEGER NOT NULL DEFAULT 0,
    findings_new        INTEGER NOT NULL DEFAULT 0,
    errors_json         TEXT
);

CREATE TABLE IF NOT EXISTS universities (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    slug             TEXT UNIQUE,
    country          TEXT,
    city             TEXT,
    website          TEXT,
    official_data    TEXT NOT NULL DEFAULT '{}',
    derived_data     TEXT NOT NULL DEFAULT '{}',
    inferred_data    TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schools_departments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id    INTEGER NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    type             TEXT NOT NULL DEFAULT 'department'
                       CHECK(type IN ('school','department','institute','center')),
    official_data    TEXT NOT NULL DEFAULT '{}',
    derived_data     TEXT NOT NULL DEFAULT '{}',
    inferred_data    TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE(university_id, name)
);

CREATE TABLE IF NOT EXISTS programs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id    INTEGER NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    school_id        INTEGER REFERENCES schools_departments(id) ON DELETE SET NULL,
    name             TEXT NOT NULL,
    degree_level     TEXT,
    delivery_mode    TEXT,
    status           TEXT,
    official_data    TEXT NOT NULL DEFAULT '{}',
    derived_data     TEXT NOT NULL DEFAULT '{}',
    inferred_data    TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE(university_id, school_id, name)
);

CREATE TABLE IF NOT EXISTS faculty (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id    INTEGER NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    school_id        INTEGER REFERENCES schools_departments(id) ON DELETE SET NULL,
    name             TEXT NOT NULL,
    title            TEXT,
    email            TEXT,
    profile_url      TEXT,
    official_data    TEXT NOT NULL DEFAULT '{}',
    derived_data     TEXT NOT NULL DEFAULT '{}',
    inferred_data    TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE(university_id, school_id, name)
);

CREATE TABLE IF NOT EXISTS source_documents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type      TEXT NOT NULL,
    entity_id        INTEGER NOT NULL,
    source_name      TEXT,
    source_url       TEXT NOT NULL,
    checksum         TEXT,
    source_priority  INTEGER NOT NULL DEFAULT 0,
    content_hash     TEXT,
    official_data    TEXT NOT NULL DEFAULT '{}',
    derived_data     TEXT NOT NULL DEFAULT '{}',
    inferred_data    TEXT NOT NULL DEFAULT '{}',
    fetched_at       TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_snippets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    entity_type      TEXT NOT NULL,
    entity_id        INTEGER NOT NULL,
    snippet_text     TEXT NOT NULL,
    locator          TEXT,
    confidence_score REAL,
    official_data    TEXT NOT NULL DEFAULT '{}',
    derived_data     TEXT NOT NULL DEFAULT '{}',
    inferred_data    TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type      TEXT NOT NULL,
    entity_id        INTEGER NOT NULL,
    payload          TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type      TEXT NOT NULL,
    entity_id        INTEGER NOT NULL,
    change_type      TEXT NOT NULL,
    detected_at      TEXT NOT NULL,
    details          TEXT,
    official_data    TEXT NOT NULL DEFAULT '{}',
    derived_data     TEXT NOT NULL DEFAULT '{}',
    inferred_data    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS score_breakdowns (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type      TEXT NOT NULL,
    entity_id        INTEGER NOT NULL,
    score_name       TEXT NOT NULL,
    total_score      REAL,
    components       TEXT NOT NULL DEFAULT '{}',
    computed_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key         TEXT NOT NULL UNIQUE,
    display_name     TEXT,
    email            TEXT,
    role             TEXT,
    official_data    TEXT NOT NULL DEFAULT '{}',
    derived_data     TEXT NOT NULL DEFAULT '{}',
    inferred_data    TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_programs_uni_school_name
    ON programs(university_id, school_id, name);

CREATE INDEX IF NOT EXISTS idx_faculty_uni_school_name
    ON faculty(university_id, school_id, name);

CREATE INDEX IF NOT EXISTS idx_audit_entity_detected
    ON audit_records(entity_type, entity_id, detected_at);

CREATE INDEX IF NOT EXISTS idx_snapshots_created_at
    ON snapshots(created_at);
"""

SEED_PROFESSORS = [
    {
        "name": "Zhang Wei",
        "name_chinese": "张巍",
        "university": "SUSTech",
        "department": "Automation and Intelligent Manufacturing",
        "email": "zhangw3@sustech.edu.cn",
        "google_scholar_id": None,
        "github_username": None,
        "research_areas": "control systems,robotics,automation",
        "status": "active",
    },
    {
        "name": "XIONG Yi",
        "name_chinese": "熊异",
        "university": "SUSTech",
        "department": "Automation and Intelligent Manufacturing",
        "email": None,
        "google_scholar_id": None,
        "github_username": None,
        "research_areas": "computational design,additive manufacturing,intelligent manufacturing systems",
        "status": "active",
    },
    {
        "name": "DING Kemi",
        "name_chinese": "丁可敏",
        "university": "SUSTech",
        "department": "Automation and Intelligent Manufacturing",
        "email": None,
        "google_scholar_id": None,
        "github_username": None,
        "research_areas": "automation",
        "status": "watching",
    },
    {
        "name": "DAI Jiansheng",
        "name_chinese": "戴建生",
        "university": "SUSTech",
        "department": "Mechanical and Energy Engineering",
        "email": None,
        "google_scholar_id": None,
        "github_username": None,
        "research_areas": "robotics,kinematics,smart manufacturing",
        "status": "watching",
    },
    {
        "name": "Liangming Chen",
        "name_chinese": "陈良明",
        "university": "SUSTech",
        "department": "Automation and Intelligent Manufacturing",
        "email": None,
        "google_scholar_id": None,
        "github_username": None,
        "research_areas": "multi-agent systems,formation control",
        "status": "watching",
    },
]

SEED_KEYWORDS = [
    # English keywords
    {"keyword": "industrial automation Shenzhen",  "language": "en", "category": "topic",          "weight": 5},
    {"keyword": "intelligent manufacturing SUSTech","language": "en", "category": "institution",    "weight": 5},
    {"keyword": "robotics control engineering",     "language": "en", "category": "topic",          "weight": 4},
    {"keyword": "food processing machinery automation","language":"en","category": "topic",          "weight": 5},
    {"keyword": "mechanical system design China",   "language": "en", "category": "topic",          "weight": 4},
    {"keyword": "factory automation Greater Bay Area","language":"en","category": "topic",          "weight": 4},
    {"keyword": "Zhang Wei SUSTech robotics",       "language": "en", "category": "professor_name", "weight": 5},
    {"keyword": "XIONG Yi intelligent manufacturing","language":"en", "category": "professor_name", "weight": 5},
    # Chinese keywords
    {"keyword": "工业自动化 深圳",  "language": "zh", "category": "topic",          "weight": 5},
    {"keyword": "智能制造 南科大",  "language": "zh", "category": "institution",    "weight": 5},
    {"keyword": "机器人 控制工程",  "language": "zh", "category": "topic",          "weight": 4},
    {"keyword": "食品机械 自动化",  "language": "zh", "category": "topic",          "weight": 5},
    {"keyword": "机械系统设计",     "language": "zh", "category": "topic",          "weight": 3},
    {"keyword": "张巍 南科大",      "language": "zh", "category": "professor_name", "weight": 5},
    {"keyword": "熊异 智能制造",    "language": "zh", "category": "professor_name", "weight": 4},
    {"keyword": "哈工大深圳 自动化","language": "zh", "category": "institution",    "weight": 4},
]

SEED_SOURCES = [
    {"name": "Google Scholar",         "url_pattern": "https://scholar.google.com",           "type": "google_scholar",  "active": 1, "supports_chinese": 0},
    {"name": "arXiv",                  "url_pattern": "https://arxiv.org",                    "type": "arxiv",           "active": 1, "supports_chinese": 0},
    {"name": "GitHub",                 "url_pattern": "https://github.com",                   "type": "github",          "active": 1, "supports_chinese": 0},
    {"name": "CNKI 知网",              "url_pattern": "https://www.cnki.net",                 "type": "cnki",            "active": 1, "supports_chinese": 1},
    {"name": "Baidu Scholar 百度学术", "url_pattern": "https://xueshu.baidu.com",             "type": "baidu_scholar",   "active": 1, "supports_chinese": 1},
]


def init_db(db_path: str = DB_PATH) -> None:
    """Create schema and seed data if the database is new."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        # Lightweight forward-compatible migrations for existing DB files.
        _ensure_column(conn, "source_documents", "source_priority", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "source_documents", "content_hash", "TEXT")
        conn.commit()

        # Only seed if tables are empty
        cur = conn.execute("SELECT COUNT(*) FROM professors")
        if cur.fetchone()[0] == 0:
            _seed_professors(conn)
            _seed_keywords(conn)
            _seed_sources(conn)
            conn.commit()
    finally:
        conn.close()


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {c["name"] for c in columns}
    if column_name not in existing:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _seed_professors(conn: sqlite3.Connection) -> None:
    ts = now_iso()
    for p in SEED_PROFESSORS:
        conn.execute(
            """INSERT INTO professors
               (name, name_chinese, university, department, email,
                google_scholar_id, github_username, research_areas,
                status, date_added, date_modified)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (p["name"], p["name_chinese"], p["university"], p["department"],
             p.get("email"), p.get("google_scholar_id"), p.get("github_username"),
             p["research_areas"], p["status"], ts, ts),
        )


def _seed_keywords(conn: sqlite3.Connection) -> None:
    ts = now_iso()
    for k in SEED_KEYWORDS:
        conn.execute(
            """INSERT INTO keywords (keyword, language, category, weight, active, date_added)
               VALUES (?,?,?,?,1,?)""",
            (k["keyword"], k["language"], k["category"], k["weight"], ts),
        )


def _seed_sources(conn: sqlite3.Connection) -> None:
    for s in SEED_SOURCES:
        conn.execute(
            """INSERT INTO sources (name, url_pattern, type, active, supports_chinese)
               VALUES (?,?,?,?,?)""",
            (s["name"], s["url_pattern"], s["type"], s["active"], s["supports_chinese"]),
        )


# ---------------------------------------------------------------------------
# PRD entities CRUD
# ---------------------------------------------------------------------------

def _json_blob(data: Optional[dict]) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def add_university(data: dict, db_path: str = DB_PATH) -> int:
    ts = now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO universities
               (name, slug, country, city, website,
                official_data, derived_data, inferred_data,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                data["name"],
                data.get("slug"),
                data.get("country"),
                data.get("city"),
                data.get("website"),
                _json_blob(data.get("official_data")),
                _json_blob(data.get("derived_data")),
                _json_blob(data.get("inferred_data")),
                ts,
                ts,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_universities(db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM universities ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_program(data: dict, db_path: str = DB_PATH) -> int:
    ts = now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO programs
               (university_id, school_id, name, degree_level, delivery_mode, status,
                official_data, derived_data, inferred_data, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["university_id"],
                data.get("school_id"),
                data["name"],
                data.get("degree_level"),
                data.get("delivery_mode"),
                data.get("status"),
                _json_blob(data.get("official_data")),
                _json_blob(data.get("derived_data")),
                _json_blob(data.get("inferred_data")),
                ts,
                ts,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_programs(db_path: str = DB_PATH, university_id: Optional[int] = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        if university_id is None:
            rows = conn.execute("SELECT * FROM programs ORDER BY name").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM programs WHERE university_id=? ORDER BY name",
                (university_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_faculty(data: dict, db_path: str = DB_PATH) -> int:
    ts = now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO faculty
               (university_id, school_id, name, title, email, profile_url,
                official_data, derived_data, inferred_data, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["university_id"],
                data.get("school_id"),
                data["name"],
                data.get("title"),
                data.get("email"),
                data.get("profile_url"),
                _json_blob(data.get("official_data")),
                _json_blob(data.get("derived_data")),
                _json_blob(data.get("inferred_data")),
                ts,
                ts,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_faculty(db_path: str = DB_PATH, university_id: Optional[int] = None) -> list[dict]:
    conn = get_connection(db_path)
    try:
        if university_id is None:
            rows = conn.execute("SELECT * FROM faculty ORDER BY name").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM faculty WHERE university_id=? ORDER BY name",
                (university_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_snapshot(data: dict, db_path: str = DB_PATH) -> int:
    ts = data.get("created_at") or now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO snapshots (entity_type, entity_id, payload, created_at)
               VALUES (?,?,?,?)""",
            (
                data["entity_type"],
                data["entity_id"],
                _json_blob(data.get("payload")),
                ts,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_snapshots(entity_type: str, entity_id: int, db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM snapshots
               WHERE entity_type=? AND entity_id=?
               ORDER BY created_at DESC""",
            (entity_type, entity_id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Professors CRUD
# ---------------------------------------------------------------------------

def get_all_professors(db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT p.*,
                      COUNT(f.id)      AS findings_total,
                      MAX(f.date_found) AS last_finding
               FROM professors p
               LEFT JOIN findings f ON f.professor_id = p.id
               GROUP BY p.id
               ORDER BY p.name"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_professor(prof_id: int, db_path: str = DB_PATH) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM professors WHERE id=?", (prof_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_professor(data: dict, db_path: str = DB_PATH) -> int:
    ts = now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO professors
               (name, name_chinese, university, department, email,
                google_scholar_id, github_username, research_areas,
                status, notes, date_added, date_modified)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data.get("name"), data.get("name_chinese"), data.get("university"),
             data.get("department"), data.get("email"), data.get("google_scholar_id"),
             data.get("github_username"), data.get("research_areas"),
             data.get("status", "watching"), data.get("notes"), ts, ts),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_professor(prof_id: int, data: dict, db_path: str = DB_PATH) -> None:
    ts = now_iso()
    fields = ["name", "name_chinese", "university", "department", "email",
              "google_scholar_id", "github_username", "research_areas", "status", "notes"]
    set_clauses = ", ".join(f"{f}=?" for f in fields if f in data)
    values = [data[f] for f in fields if f in data]
    if not set_clauses:
        return
    conn = get_connection(db_path)
    try:
        conn.execute(
            f"UPDATE professors SET {set_clauses}, date_modified=? WHERE id=?",
            (*values, ts, prof_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_professor(prof_id: int, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM professors WHERE id=?", (prof_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Keywords CRUD
# ---------------------------------------------------------------------------

def get_all_keywords(db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT k.*,
                      COUNT(f.id) AS findings_count
               FROM keywords k
               LEFT JOIN findings f ON f.keyword_id = k.id
               GROUP BY k.id
               ORDER BY k.weight DESC, k.keyword"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_keyword(data: dict, db_path: str = DB_PATH) -> int:
    ts = now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO keywords (keyword, language, category, weight, active, date_added) VALUES (?,?,?,?,1,?)",
            (data["keyword"], data.get("language", "en"), data.get("category", "topic"),
             data.get("weight", 3), ts),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_keyword(kw_id: int, data: dict, db_path: str = DB_PATH) -> None:
    fields = ["keyword", "language", "category", "weight", "active"]
    set_clauses = ", ".join(f"{f}=?" for f in fields if f in data)
    values = [data[f] for f in fields if f in data]
    if not set_clauses:
        return
    conn = get_connection(db_path)
    try:
        conn.execute(f"UPDATE keywords SET {set_clauses} WHERE id=?", (*values, kw_id))
        conn.commit()
    finally:
        conn.close()


def delete_keyword(kw_id: int, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM keywords WHERE id=?", (kw_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sources CRUD
# ---------------------------------------------------------------------------

def get_all_sources(db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM sources ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_source(src_id: int, data: dict, db_path: str = DB_PATH) -> None:
    fields = ["name", "url_pattern", "type", "active", "supports_chinese"]
    set_clauses = ", ".join(f"{f}=?" for f in fields if f in data)
    values = [data[f] for f in fields if f in data]
    if not set_clauses:
        return
    conn = get_connection(db_path)
    try:
        conn.execute(f"UPDATE sources SET {set_clauses} WHERE id=?", (*values, src_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Findings CRUD
# ---------------------------------------------------------------------------

def url_exists(url: str, db_path: str = DB_PATH) -> bool:
    """Deduplication check — returns True if URL is already in findings."""
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT 1 FROM findings WHERE url=?", (url,)).fetchone()
        return row is not None
    finally:
        conn.close()


def add_finding(data: dict, db_path: str = DB_PATH) -> Optional[int]:
    """Insert a new finding. Returns rowid or None if URL already exists."""
    if url_exists(data["url"], db_path):
        return None
    ts = now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO findings
               (professor_id, keyword_id, source_id, title, url,
                date_published, date_found, summary_original,
                language, is_chinese_source)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (data.get("professor_id"), data.get("keyword_id"), data.get("source_id"),
             data["title"], data["url"], data.get("date_published"), ts,
             data.get("summary_original"), data.get("language", "en"),
             int(data.get("is_chinese_source", False))),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_finding_analysis(finding_id: int, analysis: dict, db_path: str = DB_PATH) -> None:
    """Store Claude's analysis result on an existing finding."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """UPDATE findings SET
               summary_claude=?, relevance_score=?, relevance_reason=?,
               actionable=?, action_suggestion=?, translation=?
               WHERE id=?""",
            (analysis.get("summary"), analysis.get("relevance_score"),
             analysis.get("relevance_reason"), int(analysis.get("actionable", False)),
             analysis.get("action_suggestion"), analysis.get("translation"),
             finding_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_findings(
    db_path: str = DB_PATH,
    professor_id: Optional[int] = None,
    source_id: Optional[int] = None,
    language: Optional[str] = None,
    min_score: Optional[int] = None,
    read: Optional[bool] = None,
    actionable: Optional[bool] = None,
    unanalyzed: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conditions = []
    params: list = []

    if professor_id is not None:
        conditions.append("f.professor_id=?")
        params.append(professor_id)
    if source_id is not None:
        conditions.append("f.source_id=?")
        params.append(source_id)
    if language is not None:
        conditions.append("f.language=?")
        params.append(language)
    if min_score is not None:
        conditions.append("f.relevance_score >= ?")
        params.append(min_score)
    if read is not None:
        conditions.append("f.read=?")
        params.append(int(read))
    if actionable is not None:
        conditions.append("f.actionable=?")
        params.append(int(actionable))
    if unanalyzed:
        conditions.append("f.summary_claude IS NULL")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT f.*,
               p.name  AS professor_name,
               p.name_chinese AS professor_name_chinese,
               s.name  AS source_name,
               k.keyword AS keyword_text
        FROM findings f
        LEFT JOIN professors p ON p.id = f.professor_id
        LEFT JOIN sources    s ON s.id = f.source_id
        LEFT JOIN keywords   k ON k.id = f.keyword_id
        {where}
        ORDER BY f.date_found DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    conn = get_connection(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_finding(finding_id: int, data: dict, db_path: str = DB_PATH) -> None:
    fields = ["read", "actionable", "notes", "relevance_score"]
    set_clauses = ", ".join(f"{f}=?" for f in fields if f in data)
    values = [data[f] for f in fields if f in data]
    if not set_clauses:
        return
    conn = get_connection(db_path)
    try:
        conn.execute(f"UPDATE findings SET {set_clauses} WHERE id=?", (*values, finding_id))
        conn.commit()
    finally:
        conn.close()


def get_finding(finding_id: int, db_path: str = DB_PATH) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM findings WHERE id=?", (finding_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_findings(db_path: str = DB_PATH, **kwargs) -> int:
    """Count findings matching the same filter criteria as get_findings."""
    return len(get_findings(db_path=db_path, limit=100_000, **kwargs))


# ---------------------------------------------------------------------------
# Digests
# ---------------------------------------------------------------------------

def save_digest(content: dict, findings_count: int, db_path: str = DB_PATH) -> int:
    ts = now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO digests (date_generated, content_json, email_sent, findings_count) VALUES (?,?,0,?)",
            (ts, json.dumps(content, ensure_ascii=False), findings_count),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def mark_digest_sent(digest_id: int, db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("UPDATE digests SET email_sent=1 WHERE id=?", (digest_id,))
        conn.commit()
    finally:
        conn.close()


def get_digests(db_path: str = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM digests ORDER BY date_generated DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scan history
# ---------------------------------------------------------------------------

def log_scan(data: dict, db_path: str = DB_PATH) -> int:
    ts = now_iso()
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO scan_history
               (date_ran, professors_scanned, keywords_scanned,
                findings_total, findings_new, errors_json)
               VALUES (?,?,?,?,?,?)""",
            (ts, data.get("professors_scanned", 0), data.get("keywords_scanned", 0),
             data.get("findings_total", 0), data.get("findings_new", 0),
             json.dumps(data.get("errors", []), ensure_ascii=False)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_scan_history(db_path: str = DB_PATH, limit: int = 20) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM scan_history ORDER BY date_ran DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Stats helpers used by the dashboard
# ---------------------------------------------------------------------------

def get_stats(db_path: str = DB_PATH) -> dict:
    conn = get_connection(db_path)
    try:
        def scalar(sql):
            return conn.execute(sql).fetchone()[0] or 0

        return {
            "total_findings":    scalar("SELECT COUNT(*) FROM findings"),
            "unread_findings":   scalar("SELECT COUNT(*) FROM findings WHERE read=0"),
            "actionable":        scalar("SELECT COUNT(*) FROM findings WHERE actionable=1"),
            "avg_score":         conn.execute(
                "SELECT ROUND(AVG(relevance_score),1) FROM findings WHERE relevance_score IS NOT NULL"
            ).fetchone()[0] or 0,
            "total_professors":  scalar("SELECT COUNT(*) FROM professors"),
            "active_professors": scalar("SELECT COUNT(*) FROM professors WHERE status='active'"),
            "total_keywords":    scalar("SELECT COUNT(*) FROM keywords WHERE active=1"),
            "last_scan": (conn.execute(
                "SELECT date_ran FROM scan_history ORDER BY date_ran DESC LIMIT 1"
            ).fetchone() or [None])[0],
        }
    finally:
        conn.close()

"""
scraper.py — Web scraping module for AcademicRadar.

Sources:
  - Google Scholar  (via scholarly)
  - arXiv           (via arxiv library)
  - GitHub          (via REST API)
  - CNKI 知网        (HTML scraping with fallback)
  - Baidu Scholar   (HTML scraping with fallback)
  - RSS feeds

Each scraper function yields dicts compatible with database.add_finding().
All errors are caught and logged; a single source failure never crashes the run.
"""

import time
import logging
import re
import json
import traceback
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional
from urllib.parse import quote_plus, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import feedparser
import arxiv

import os

from config import (
    BROWSER_HEADERS,
    ARXIV_CATEGORIES,
    ARXIV_MAX_RESULTS,
    SCHOLAR_MAX_RESULTS,
    DAYS_LOOKBACK,
    SCRAPER_DELAY_SECONDS,
    UNIVERSITY_SOURCE_SEEDS,
)

log = logging.getLogger(__name__)

# Disable scholarly on cloud environments where Google blocks server IPs.
# Set ENABLE_SCHOLARLY=1 to force-enable (e.g. when running locally with a VPN).
ENABLE_SCHOLARLY: bool = os.environ.get("ENABLE_SCHOLARLY", "0") == "1"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _sleep(seconds: float = SCRAPER_DELAY_SECONDS) -> None:
    time.sleep(seconds)


def _get(url: str, headers: Optional[dict] = None, timeout: int = 15) -> Optional[requests.Response]:
    try:
        h = {**BROWSER_HEADERS, **(headers or {})}
        resp = requests.get(url, headers=h, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as exc:
        log.warning("GET %s failed: %s", url, exc)
        return None


def _cutoff_date() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _upsert_source_document(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    source_name: str,
    source_url: str,
    content_text: str,
    source_priority: int,
) -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    content_hash = _content_hash(content_text)
    row = conn.execute(
        """SELECT id FROM source_documents
           WHERE entity_type=? AND entity_id=? AND source_url=?
           ORDER BY id DESC LIMIT 1""",
        (entity_type, entity_id, source_url),
    ).fetchone()
    if row:
        conn.execute(
            """UPDATE source_documents
               SET source_name=?, checksum=?, source_priority=?, content_hash=?,
                   official_data=?, fetched_at=?
               WHERE id=?""",
            (
                source_name,
                content_hash,
                source_priority,
                content_hash,
                json.dumps({"content_preview": content_text[:500]}, ensure_ascii=False),
                ts,
                row["id"],
            ),
        )
        return row["id"]

    cur = conn.execute(
        """INSERT INTO source_documents
           (entity_type, entity_id, source_name, source_url, checksum,
            source_priority, content_hash, official_data, fetched_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            entity_type,
            entity_id,
            source_name,
            source_url,
            content_hash,
            source_priority,
            content_hash,
            json.dumps({"content_preview": content_text[:500]}, ensure_ascii=False),
            ts,
            ts,
        ),
    )
    return cur.lastrowid


def _insert_evidence_snippet(
    conn: sqlite3.Connection,
    source_document_id: int,
    entity_type: str,
    entity_id: int,
    field_name: str,
    snippet_text: str,
    source_url: str,
    locator: str,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """INSERT INTO evidence_snippets
           (source_document_id, entity_type, entity_id, snippet_text, locator,
            confidence_score, official_data, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            source_document_id,
            entity_type,
            entity_id,
            snippet_text[:1000],
            json.dumps({"url": source_url, "selector_or_location": locator}, ensure_ascii=False),
            0.8,
            json.dumps({"field": field_name}, ensure_ascii=False),
            ts,
        ),
    )


def discover_university_sources(seed_list: Optional[list[dict]] = None) -> list[dict]:
    """
    Discover likely admissions/program pages from configured university seeds.
    """
    seeds = seed_list or UNIVERSITY_SOURCE_SEEDS
    discovered: list[dict] = []
    keyword_hints = ("admission", "admissions", "graduate", "master", "program", "apply", "international")

    for seed in seeds:
        name = seed.get("name", "Unknown University")
        base_urls = seed.get("base_urls", [])
        links: set[str] = set(base_urls)
        for base_url in base_urls:
            resp = _get(base_url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for anchor in soup.select("a[href]"):
                href = anchor.get("href", "")
                full_url = urljoin(base_url, href)
                lower = full_url.lower()
                if any(k in lower for k in keyword_hints):
                    if urlparse(full_url).netloc == urlparse(base_url).netloc:
                        links.add(full_url)
            _sleep(0.4)

        discovered.append(
            {
                "name": name,
                "base_urls": base_urls,
                "candidate_urls": sorted(links),
            }
        )

    return discovered


def extract_programs_from_admission_pages(
    page_text: str,
    source_url: str,
) -> list[dict]:
    """
    Extract program-level critical fields from admissions text.
    """
    normalized = _normalize_whitespace(page_text)
    if not normalized:
        return []

    specs: dict[str, tuple[str, str]] = {
        "idioma": (r"(language of instruction|teaching language|语言).*?(english|chinese|bilingual)", "language"),
        "duración": (r"(duration|length of study|学制).*?(\d+\s*(?:year|years|semester|semesters|年))", "duration"),
        "tuition": (r"(tuition|fee|学费).*?((?:rmb|cny|\$|usd)?\s?\d[\d,\.]*)", "tuition"),
        "requisitos": (r"(requirements?|eligibility|admission criteria|申请条件)\s*[:：]?\s*([^.;]{10,220})", "requirements"),
        "deadlines": (r"(deadline|application due|截止日期)\s*[:：]?\s*([^.;]{3,120})", "deadlines"),
        "portal": (r"(apply|application portal|online application|申请系统).*?(https?://[^\s)]+)", "portal"),
        "supervisor_required": (r"(supervisor|advisor|导师).{0,60}(required|must|必要|需要)", "supervisor_required"),
        "interview_required": (r"(interview|面试).{0,60}(required|must|必要|需要)", "interview_required"),
    }

    extracted: dict[str, Optional[str]] = {
        "language": None,
        "duration": None,
        "tuition": None,
        "requirements": None,
        "deadlines": None,
        "portal": None,
        "supervisor_required": "no",
        "interview_required": "no",
    }
    evidences: dict[str, dict] = {}

    for _, (pattern, field_key) in specs.items():
        m = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not m:
            continue
        snippet = _normalize_whitespace(m.group(0))
        value = _normalize_whitespace(m.group(m.lastindex or 0))
        if field_key in ("supervisor_required", "interview_required"):
            value = "yes"
        extracted[field_key] = value
        evidences[field_key] = {
            "snippet": snippet,
            "url": source_url,
            "locator": "regex_match",
        }

    if not any(v for k, v in extracted.items() if k not in ("supervisor_required", "interview_required")):
        return []

    title_match = re.search(
        r"(Master(?:'s)?\s+Program[^.]{0,120}|Graduate Program[^.]{0,120}|硕士[^。]{0,120})",
        normalized,
        flags=re.IGNORECASE,
    )
    program_name = _normalize_whitespace(title_match.group(0)) if title_match else f"Program from {urlparse(source_url).netloc}"

    return [
        {
            "name": program_name[:200],
            "degree_level": "master",
            "delivery_mode": None,
            "status": "active",
            "critical_fields": extracted,
            "evidence": evidences,
            "source_url": source_url,
        }
    ]


def scrape_university_pages(
    university: dict,
    db_path: Optional[str] = None,
    snapshot_id: Optional[int] = None,
) -> dict:
    """
    Scrape university candidate pages, persist source_documents/evidence, and create programs.
    """
    import database as db

    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    conn = db.get_connection(db_path)
    created_programs = 0
    updated_programs = 0
    unchanged_programs = 0
    inconsistent_programs = 0
    processed_urls = 0

    try:
        uni_name = university["name"]
        base_url = (university.get("base_urls") or [None])[0]
        existing_uni = None
        for row in db.get_universities(db_path):
            if row["name"].lower() == uni_name.lower():
                existing_uni = row
                break
        if not existing_uni:
            uni_id = db.add_university(
                {"name": uni_name, "slug": re.sub(r"[^a-z0-9]+", "-", uni_name.lower()).strip("-"), "website": base_url},
                db_path,
            )
        else:
            uni_id = existing_uni["id"]

        for idx, url in enumerate(university.get("candidate_urls", []), start=1):
            resp = _get(url, timeout=20)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = _normalize_whitespace(soup.get_text(" ", strip=True))
            if not page_text:
                continue

            processed_urls += 1
            source_doc_id = _upsert_source_document(
                conn=conn,
                entity_type="university",
                entity_id=uni_id,
                source_name=uni_name,
                source_url=url,
                content_text=page_text,
                source_priority=max(1, 100 - idx),
            )
            programs = extract_programs_from_admission_pages(page_text, url)
            for program in programs:
                p_data = {
                    "university_id": uni_id,
                    "name": program["name"],
                    "degree_level": program["degree_level"],
                    "delivery_mode": program["delivery_mode"],
                    "status": program["status"],
                    "official_data": program["critical_fields"],
                    "derived_data": {"source_url": url},
                }
                program_id, change_type, inconsistency_flag = db.upsert_program_with_audit(
                    p_data,
                    snapshot_id=snapshot_id,
                    db_path=db_path,
                )
                if change_type == "new":
                    created_programs += 1
                elif change_type == "updated":
                    updated_programs += 1
                else:
                    unchanged_programs += 1
                if inconsistency_flag:
                    inconsistent_programs += 1

                for field_name, ev in program["evidence"].items():
                    _insert_evidence_snippet(
                        conn=conn,
                        source_document_id=source_doc_id,
                        entity_type="program",
                        entity_id=program_id,
                        field_name=field_name,
                        snippet_text=ev["snippet"],
                        source_url=ev["url"],
                        locator=ev["locator"],
                    )
            _sleep(0.4)

        conn.commit()
        return {
            "university": uni_name,
            "processed_urls": processed_urls,
            "programs_created": created_programs,
            "programs_updated": updated_programs,
            "programs_unchanged": unchanged_programs,
            "programs_with_inconsistency": inconsistent_programs,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Google Scholar
# ---------------------------------------------------------------------------

def scrape_google_scholar_professor(
    professor: dict,
    source_id: int,
) -> Generator[dict, None, None]:
    """
    Fetch recent publications for a professor who has a google_scholar_id.
    Falls back to keyword search by name if no ID is set.
    Disabled by default on cloud servers (Google blocks them); set ENABLE_SCHOLARLY=1 to force.
    """
    if not ENABLE_SCHOLARLY:
        log.info("Scholar skipped for %s (ENABLE_SCHOLARLY=0)", professor["name"])
        return
    try:
        from scholarly import scholarly as _scholarly, ProxyGenerator
    except ImportError:
        log.error("scholarly not installed — skipping Google Scholar")
        return

    name = professor["name"]
    scholar_id = professor.get("google_scholar_id")

    try:
        if scholar_id:
            log.info("Scholar: fetching profile for %s (id=%s)", name, scholar_id)
            author = _scholarly.fill(_scholarly.search_author_id(scholar_id))
            publications = author.get("publications", [])[:SCHOLAR_MAX_RESULTS]
            for pub in publications:
                try:
                    filled = _scholarly.fill(pub)
                    bib = filled.get("bib", {})
                    year = str(bib.get("pub_year", ""))
                    if year and int(year) < datetime.now().year - 1:
                        continue
                    url = filled.get("pub_url") or f"https://scholar.google.com/scholar?q={quote_plus(bib.get('title',''))}"
                    title = bib.get("title", "Untitled")
                    abstract = bib.get("abstract", "")
                    yield {
                        "professor_id": professor["id"],
                        "source_id": source_id,
                        "title": title,
                        "url": url,
                        "date_published": f"{year}-01-01" if year else None,
                        "summary_original": abstract[:2000] if abstract else None,
                        "language": "en",
                        "is_chinese_source": False,
                    }
                    _sleep(1)
                except Exception as e:
                    log.warning("Scholar pub error for %s: %s", name, e)
                    continue
        else:
            log.info("Scholar: keyword search for professor %s", name)
            query = f"{name} {professor.get('university', '')} {professor.get('research_areas', '').split(',')[0]}"
            results = _scholarly.search_pubs(query)
            count = 0
            for pub in results:
                if count >= SCHOLAR_MAX_RESULTS:
                    break
                try:
                    bib = pub.get("bib", {})
                    year = str(bib.get("pub_year", ""))
                    title = bib.get("title", "Untitled")
                    url = pub.get("pub_url") or f"https://scholar.google.com/scholar?q={quote_plus(title)}"
                    abstract = bib.get("abstract", "")
                    yield {
                        "professor_id": professor["id"],
                        "source_id": source_id,
                        "title": title,
                        "url": url,
                        "date_published": f"{year}-01-01" if year else None,
                        "summary_original": abstract[:2000] if abstract else None,
                        "language": "en",
                        "is_chinese_source": False,
                    }
                    count += 1
                    _sleep(2)
                except Exception as e:
                    log.warning("Scholar search item error: %s", e)
                    continue
    except Exception as exc:
        log.error("Google Scholar error for %s: %s", name, exc)


def scrape_google_scholar_keyword(
    keyword: dict,
    source_id: int,
) -> Generator[dict, None, None]:
    """Search Google Scholar for a keyword alert. Disabled on cloud by default."""
    if not ENABLE_SCHOLARLY:
        return
    try:
        from scholarly import scholarly as _scholarly
    except ImportError:
        return

    kw = keyword["keyword"]
    log.info("Scholar keyword search: %s", kw)
    try:
        results = _scholarly.search_pubs(kw)
        count = 0
        for pub in results:
            if count >= SCHOLAR_MAX_RESULTS:
                break
            try:
                bib = pub.get("bib", {})
                year = str(bib.get("pub_year", ""))
                title = bib.get("title", "Untitled")
                url = pub.get("pub_url") or f"https://scholar.google.com/scholar?q={quote_plus(title)}"
                abstract = bib.get("abstract", "")
                yield {
                    "keyword_id": keyword["id"],
                    "source_id": source_id,
                    "title": title,
                    "url": url,
                    "date_published": f"{year}-01-01" if year else None,
                    "summary_original": abstract[:2000] if abstract else None,
                    "language": keyword.get("language", "en"),
                    "is_chinese_source": False,
                }
                count += 1
                _sleep(2)
            except Exception as e:
                log.warning("Scholar keyword item error: %s", e)
                continue
    except Exception as exc:
        log.error("Scholar keyword search error (%s): %s", kw, exc)


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

def scrape_arxiv_keywords(
    keywords: list[dict],
    source_id: int,
) -> Generator[dict, None, None]:
    """
    Search arXiv across target categories using English keywords.
    Uses the official arxiv Python client.
    """
    cutoff = _cutoff_date()
    en_keywords = [k for k in keywords if k.get("language", "en") == "en" and k.get("active", 1)]

    for kw in en_keywords:
        query_str = kw["keyword"]
        log.info("arXiv search: %s", query_str)
        try:
            # Build a multi-category query
            cat_filter = " OR ".join(f"cat:{c}" for c in ARXIV_CATEGORIES)
            full_query = f"({query_str}) AND ({cat_filter})"
            client = arxiv.Client()
            search = arxiv.Search(
                query=full_query,
                max_results=ARXIV_MAX_RESULTS,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            for result in client.results(search):
                pub_date = result.published.replace(tzinfo=timezone.utc) if result.published else None
                if pub_date and pub_date < cutoff:
                    break
                title = result.title
                url = result.entry_id
                abstract = result.summary[:2000] if result.summary else ""
                authors = ", ".join(str(a) for a in result.authors[:5])
                summary = f"Authors: {authors}\n\n{abstract}"
                date_str = pub_date.strftime("%Y-%m-%d") if pub_date else None
                yield {
                    "keyword_id": kw["id"],
                    "source_id": source_id,
                    "title": title,
                    "url": url,
                    "date_published": date_str,
                    "summary_original": summary,
                    "language": "en",
                    "is_chinese_source": False,
                }
                _sleep(0.5)
        except Exception as exc:
            log.error("arXiv error for keyword '%s': %s", query_str, exc)
        _sleep(SCRAPER_DELAY_SECONDS)


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def scrape_github_professor(
    professor: dict,
    source_id: int,
) -> Generator[dict, None, None]:
    """Fetch recent GitHub activity for a professor with a github_username."""
    username = professor.get("github_username")
    if not username:
        return

    log.info("GitHub: scanning repos for %s", username)
    cutoff = _cutoff_date()
    url = f"{GITHUB_API}/users/{username}/repos?sort=updated&per_page=30"
    resp = _get(url, headers=GITHUB_HEADERS)
    if not resp:
        return

    try:
        repos = resp.json()
    except Exception:
        return

    for repo in repos:
        updated = repo.get("updated_at", "")
        try:
            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except Exception:
            continue
        if updated_dt < cutoff:
            continue

        title = f"[GitHub] {username}/{repo['name']}"
        repo_url = repo.get("html_url", "")
        description = repo.get("description", "") or ""
        topics = ", ".join(repo.get("topics", []))
        summary = f"Stars: {repo.get('stargazers_count',0)} | Language: {repo.get('language','?')}\n{description}"
        if topics:
            summary += f"\nTopics: {topics}"

        yield {
            "professor_id": professor["id"],
            "source_id": source_id,
            "title": title,
            "url": repo_url,
            "date_published": updated_dt.strftime("%Y-%m-%d"),
            "summary_original": summary,
            "language": "en",
            "is_chinese_source": False,
        }
        _sleep(0.5)


def scrape_github_keyword(
    keyword: dict,
    source_id: int,
) -> Generator[dict, None, None]:
    """Search GitHub repositories for a keyword."""
    kw = keyword["keyword"]
    if keyword.get("language") == "zh":
        return  # GitHub search works better with English

    log.info("GitHub keyword search: %s", kw)
    params = urlencode({"q": kw, "sort": "updated", "order": "desc", "per_page": 10})
    url = f"{GITHUB_API}/search/repositories?{params}"
    resp = _get(url, headers=GITHUB_HEADERS)
    if not resp:
        return

    try:
        data = resp.json()
        items = data.get("items", [])
    except Exception:
        return

    cutoff = _cutoff_date()
    for repo in items:
        updated = repo.get("updated_at", "")
        try:
            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except Exception:
            continue
        if updated_dt < cutoff:
            continue

        full_name = repo.get("full_name", "")
        title = f"[GitHub] {full_name}"
        repo_url = repo.get("html_url", "")
        description = repo.get("description", "") or ""
        summary = f"Stars: {repo.get('stargazers_count',0)} | Language: {repo.get('language','?')}\n{description}"

        yield {
            "keyword_id": keyword["id"],
            "source_id": source_id,
            "title": title,
            "url": repo_url,
            "date_published": updated_dt.strftime("%Y-%m-%d"),
            "summary_original": summary,
            "language": "en",
            "is_chinese_source": False,
        }
        _sleep(0.5)


# ---------------------------------------------------------------------------
# CNKI 知网
# ---------------------------------------------------------------------------

CNKI_SEARCH_URL = "https://www.cnki.net/kns/defaultresult/index"
CNKI_ALT_URL = "https://kns.cnki.net/kns8/defaultresult/index"


def scrape_cnki(
    keyword: dict,
    source_id: int,
) -> Generator[dict, None, None]:
    """
    Basic CNKI search scraping.
    CNKI is heavily protected; this makes a best-effort attempt with browser headers.
    Falls back gracefully on block/error.
    """
    kw = keyword["keyword"]
    log.info("CNKI search: %s", kw)
    params = {
        "SEARCHTYPE": "SUM",
        "ORDERTYPE": "relevant",
        "SEARCHLANGUAGE": "gbk",
        "QueryJson": json.dumps({
            "Platform": "",
            "Resource": "CROSSDBTHREAD",
            "Classifid": "ZZJS",
            "Products": "",
            "QNode": {"QGroup": [{"Key": "Subject", "Title": "",
                                   "Logic": 1, "Items": [{"Title": kw, "Name": "SU", "Value": kw,
                                                           "Operate": "%", "BlurType": ""}],
                                   "ChildItems": []}]},
        }, ensure_ascii=False),
    }
    # Try both URLs
    for base_url in [CNKI_ALT_URL, CNKI_SEARCH_URL]:
        try:
            url = base_url + "?" + urlencode({"kw": kw})
            resp = _get(url, timeout=20)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            results = _parse_cnki_results(soup, kw)
            if results:
                for r in results:
                    r["keyword_id"] = keyword["id"]
                    r["source_id"] = source_id
                    r["language"] = "zh"
                    r["is_chinese_source"] = True
                    yield r
                return
        except Exception as exc:
            log.warning("CNKI parse error for '%s': %s", kw, exc)
        _sleep(SCRAPER_DELAY_SECONDS)


def _parse_cnki_results(soup: BeautifulSoup, kw: str) -> list[dict]:
    results = []
    # Try multiple selectors since CNKI changes its markup
    selectors = [
        ("div.result-item", "a.fz14"),
        ("tr.odd,tr.even", "td.name a"),
        ("li.item", "a"),
    ]
    for container_sel, link_sel in selectors:
        items = soup.select(container_sel)
        if not items:
            continue
        for item in items[:10]:
            try:
                link = item.select_one(link_sel)
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.cnki.net" + href
                # Try to get abstract
                abstract_el = item.select_one(".abstract,.brief,.c-abstract")
                abstract = abstract_el.get_text(strip=True) if abstract_el else ""
                # Authors
                authors_el = item.select_one(".author,.creator")
                authors = authors_el.get_text(strip=True) if authors_el else ""
                if title and href:
                    results.append({
                        "title": title,
                        "url": href,
                        "date_published": None,
                        "summary_original": f"作者: {authors}\n{abstract}" if authors or abstract else None,
                    })
            except Exception:
                continue
        if results:
            break
    return results


# ---------------------------------------------------------------------------
# Baidu Scholar 百度学术
# ---------------------------------------------------------------------------

BAIDU_SCHOLAR_URL = "https://xueshu.baidu.com/s"


def scrape_baidu_scholar(
    keyword: dict,
    source_id: int,
) -> Generator[dict, None, None]:
    """
    Scrape Baidu Scholar search results.
    Baidu returns Chinese academic papers.
    """
    kw = keyword["keyword"]
    log.info("Baidu Scholar search: %s", kw)
    params = {"wd": kw, "ie": "utf-8", "tn": "SE_baiduxueshu_c1gjeupa", "rsv_dl": "sh_1"}
    url = BAIDU_SCHOLAR_URL + "?" + urlencode(params)
    resp = _get(url, timeout=20)
    if not resp:
        return

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("div.sc_default_result") or soup.select("div.result") or soup.select("div.c-result")
        if not items:
            # Try broader search for result cards
            items = soup.select("[class*='result']")[:10]

        for item in items[:10]:
            try:
                link = item.select_one("h3 a") or item.select_one("a.c-title-link") or item.select_one("a")
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not href:
                    continue
                if not href.startswith("http"):
                    href = "https://xueshu.baidu.com" + href

                abstract_el = item.select_one(".c-abstract,.abstract,.summary")
                abstract = abstract_el.get_text(strip=True) if abstract_el else ""

                authors_el = item.select_one(".author_text,.c-author,.author")
                authors = authors_el.get_text(strip=True) if authors_el else ""

                if title and href:
                    yield {
                        "keyword_id": keyword["id"],
                        "source_id": source_id,
                        "title": title,
                        "url": href,
                        "date_published": None,
                        "summary_original": f"作者: {authors}\n{abstract}" if authors or abstract else None,
                        "language": "zh",
                        "is_chinese_source": True,
                    }
            except Exception as e:
                log.warning("Baidu Scholar item error: %s", e)
                continue
    except Exception as exc:
        log.error("Baidu Scholar error for '%s': %s", kw, exc)
    _sleep(SCRAPER_DELAY_SECONDS)


# ---------------------------------------------------------------------------
# RSS feeds
# ---------------------------------------------------------------------------

def scrape_rss_feed(
    feed_url: str,
    source_id: int,
    professor_id: Optional[int] = None,
    keyword_id: Optional[int] = None,
    is_chinese: bool = False,
) -> Generator[dict, None, None]:
    """Parse an RSS/Atom feed and yield new entries."""
    log.info("RSS: fetching %s", feed_url)
    cutoff = _cutoff_date()
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            try:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                if published and published < cutoff:
                    continue

                title = getattr(entry, "title", "Untitled")
                url = getattr(entry, "link", "")
                summary = getattr(entry, "summary", "") or ""
                summary = re.sub(r"<[^>]+>", "", summary)[:2000]
                date_str = published.strftime("%Y-%m-%d") if published else None

                if not url:
                    continue

                yield {
                    "professor_id": professor_id,
                    "keyword_id": keyword_id,
                    "source_id": source_id,
                    "title": title,
                    "url": url,
                    "date_published": date_str,
                    "summary_original": summary or None,
                    "language": "zh" if is_chinese else "en",
                    "is_chinese_source": is_chinese,
                }
            except Exception as e:
                log.warning("RSS entry error: %s", e)
                continue
    except Exception as exc:
        log.error("RSS feed error (%s): %s", feed_url, exc)
    _sleep(SCRAPER_DELAY_SECONDS)


# ---------------------------------------------------------------------------
# Main scan entry point
# ---------------------------------------------------------------------------

def run_full_scan(db_path: str = None) -> dict:
    """
    Execute a complete scan across all active sources and professors.
    Returns a summary dict with counts and error list.
    """
    import database as db

    if db_path is None:
        from config import DB_PATH
        db_path = DB_PATH

    summary = {
        "professors_scanned": 0,
        "keywords_scanned": 0,
        "findings_total": 0,
        "findings_new": 0,
        "entities_created": 0,
        "entities_updated": 0,
        "entities_removed": 0,
        "entity_changes_by_type": {},
        "inconsistencies_detected": 0,
        "errors": [],
    }
    snapshot_id = db.create_snapshot(
        {
            "scan_type": "full_scan",
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        },
        db_path,
    )
    summary["snapshot_id"] = snapshot_id

    professors = db.get_all_professors(db_path)
    keywords = db.get_all_keywords(db_path)
    sources = {s["type"]: s for s in db.get_all_sources(db_path) if s["active"]}

    active_profs = [p for p in professors if p["status"] in ("active", "watching")]
    active_kws   = [k for k in keywords  if k["active"]]

    def safe_add(finding: dict) -> bool:
        try:
            result = db.add_finding(finding, db_path)
            summary["findings_total"] += 1
            if result:
                summary["findings_new"] += 1
                return True
            return False
        except Exception as e:
            log.error("DB error adding finding: %s", e)
            summary["errors"].append(str(e))
            return False

    # --- Google Scholar: professors ---
    if "google_scholar" in sources:
        src_id = sources["google_scholar"]["id"]
        for prof in active_profs:
            try:
                for finding in scrape_google_scholar_professor(prof, src_id):
                    safe_add(finding)
                    _sleep(1)
            except Exception as e:
                msg = f"Scholar professor {prof['name']}: {traceback.format_exc()}"
                log.error(msg)
                summary["errors"].append(msg)
            summary["professors_scanned"] += 1
            _sleep(SCRAPER_DELAY_SECONDS)

    # --- Google Scholar: keywords ---
    if "google_scholar" in sources:
        src_id = sources["google_scholar"]["id"]
        for kw in active_kws:
            try:
                for finding in scrape_google_scholar_keyword(kw, src_id):
                    safe_add(finding)
            except Exception as e:
                msg = f"Scholar keyword {kw['keyword']}: {e}"
                log.error(msg)
                summary["errors"].append(msg)
            _sleep(SCRAPER_DELAY_SECONDS)

    # --- arXiv ---
    if "arxiv" in sources:
        src_id = sources["arxiv"]["id"]
        try:
            for finding in scrape_arxiv_keywords(active_kws, src_id):
                safe_add(finding)
        except Exception as e:
            msg = f"arXiv scan: {e}"
            log.error(msg)
            summary["errors"].append(msg)

    # --- GitHub: professors ---
    if "github" in sources:
        src_id = sources["github"]["id"]
        for prof in active_profs:
            try:
                for finding in scrape_github_professor(prof, src_id):
                    safe_add(finding)
            except Exception as e:
                msg = f"GitHub professor {prof['name']}: {e}"
                log.error(msg)
                summary["errors"].append(msg)
            _sleep(1)

    # --- GitHub: keywords ---
    if "github" in sources:
        src_id = sources["github"]["id"]
        for kw in active_kws:
            try:
                for finding in scrape_github_keyword(kw, src_id):
                    safe_add(finding)
            except Exception as e:
                msg = f"GitHub keyword {kw['keyword']}: {e}"
                log.error(msg)
                summary["errors"].append(msg)
            _sleep(1)

    # --- CNKI ---
    if "cnki" in sources:
        src_id = sources["cnki"]["id"]
        zh_kws = [k for k in active_kws if k.get("language") == "zh"]
        for kw in zh_kws:
            try:
                for finding in scrape_cnki(kw, src_id):
                    safe_add(finding)
            except Exception as e:
                msg = f"CNKI keyword {kw['keyword']}: {e}"
                log.error(msg)
                summary["errors"].append(msg)
            _sleep(SCRAPER_DELAY_SECONDS * 2)

    # --- Baidu Scholar ---
    if "baidu_scholar" in sources:
        src_id = sources["baidu_scholar"]["id"]
        for kw in active_kws:
            try:
                for finding in scrape_baidu_scholar(kw, src_id):
                    safe_add(finding)
            except Exception as e:
                msg = f"Baidu Scholar keyword {kw['keyword']}: {e}"
                log.error(msg)
                summary["errors"].append(msg)
            _sleep(SCRAPER_DELAY_SECONDS)

    # --- University admissions intelligence ---
    try:
        discovered = discover_university_sources()
        for uni in discovered:
            uni_summary = scrape_university_pages(uni, db_path=db_path, snapshot_id=snapshot_id)
            summary["entities_created"] += uni_summary.get("programs_created", 0)
            summary["entities_updated"] += uni_summary.get("programs_updated", 0)
            summary["inconsistencies_detected"] += uni_summary.get("programs_with_inconsistency", 0)
    except Exception as e:
        msg = f"University intelligence scan: {e}"
        log.error(msg)
        summary["errors"].append(msg)

    summary["keywords_scanned"] = len(active_kws)

    change_summary = db.get_change_summary_for_ui(snapshot_id=snapshot_id, db_path=db_path)
    summary["entities_created"] = change_summary["totals"]["added"]
    summary["entities_updated"] = change_summary["totals"]["modified"]
    summary["entities_removed"] = change_summary["totals"]["removed"]
    summary["entity_changes_by_type"] = change_summary["by_entity"]
    db.close_snapshot(snapshot_id, db_path)
    return summary

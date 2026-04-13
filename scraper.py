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
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional
from urllib.parse import quote_plus, urlencode

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
        "errors": [],
    }

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

    summary["keywords_scanned"] = len(active_kws)
    return summary

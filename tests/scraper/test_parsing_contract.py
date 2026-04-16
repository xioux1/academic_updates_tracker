from pathlib import Path

from bs4 import BeautifulSoup

from scraper import (
    CRITICAL_FIELD_KEYS,
    _build_program_contract,
    _evidence_rows_for_program,
    _fetch_page_with_retry,
    _extract_critical_fields_from_text,
    _extract_programs_with_connector,
    _extract_with_regex,
    _extract_with_table_fallback,
    _normalize_table_rows,
    _retry_policy_for_url,
    DOMAIN_RETRY_POLICY,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_extract_critical_fields_sustech_fixture():
    text = _read_fixture("sustech_program.txt")

    fields, evidence = _extract_critical_fields_from_text(text, "https://www.sustech.edu.cn/program")

    assert fields["language"].lower() == "english"
    assert fields["duration"].lower() == "2 years"
    assert fields["tuition"].lower().startswith("rmb 80,000")
    assert "bachelor degree" in fields["requirements"].lower()
    assert fields["deadlines"] == "2026-12-15"
    assert fields["portal"] == "https://apply.sustech.edu.cn/graduate"
    assert fields["supervisor_required"] == "yes"
    assert fields["interview_required"] == "yes"
    for field in ("language", "duration", "tuition", "requirements", "deadlines", "portal"):
        assert evidence[field]["snippet"] != "not_found"


def test_extract_critical_fields_hitsz_fixture_alternative_formats():
    text = _read_fixture("hitsz_program.txt")

    fields, _ = _extract_critical_fields_from_text(text, "https://www.hitsz.edu.cn/admissions")

    assert fields["language"].lower() == "chinese"
    assert fields["duration"] == "3 年"
    assert fields["tuition"].startswith("¥45,000")
    assert fields["deadlines"] == "15 Jan 2027"
    assert fields["supervisor_required"] == "yes"


def test_table_fallback_extracts_currency_and_date_regression_cases():
    html = _read_fixture("sustech_table.html")
    soup = BeautifulSoup(html, "html.parser")

    rows = _normalize_table_rows(soup)
    programs = _extract_with_table_fallback(
        "Graduate Program details",
        "https://www.sustech.edu.cn/table",
        rows,
    )

    assert len(programs) == 1
    fields = programs[0]["critical_fields"]
    assert fields["language"] == "English"
    assert fields["duration"] == "2 years"
    assert fields["tuition"] == "USD 12,500 /year"
    assert fields["deadlines"] == "January 5, 2027"


def test_contract_has_evidence_for_all_critical_fields():
    text = _read_fixture("sustech_program.txt")
    programs = _extract_with_regex(text, "https://www.sustech.edu.cn/program")

    assert len(programs) == 1
    program = programs[0]

    assert sorted(program["evidence_by_field"].keys()) == sorted(CRITICAL_FIELD_KEYS)



def test_evidence_rows_contract_maps_all_critical_fields_to_evidence_snippets_rows():
    program_contract = _build_program_contract(
        source_url="https://www.example.edu/program",
        program_name="Master Program in Data Science",
        critical_fields={
            "language": "English",
            "duration": "2 years",
            "tuition": "USD 12,500 /year",
            "requirements": "Bachelor degree",
            "deadlines": "January 5, 2027",
            "portal": "https://apply.example.edu",
            "supervisor_required": "yes",
            "interview_required": "no",
        },
        evidence={
            "language": {"snippet": "Language: English", "url": "https://www.example.edu/program", "locator": "regex_match"},
        },
    )[0]

    rows = _evidence_rows_for_program(
        program_contract,
        source_document_id=9,
        entity_type="program",
        entity_id=10,
    )

    assert len(rows) == len(CRITICAL_FIELD_KEYS)
    assert {row["field_name"] for row in rows} == set(CRITICAL_FIELD_KEYS)
    assert all(row["source_document_id"] == 9 for row in rows)
    assert all(row["entity_id"] == 10 for row in rows)


def test_szu_connector_uses_dedicated_selectors_and_extracts_program_fields():
    html = _read_fixture("szu_program.html")
    soup = BeautifulSoup(html, "html.parser")

    programs, metadata = _extract_programs_with_connector(
        "Shenzhen University",
        soup,
        "https://www.szu.edu.cn/en/graduate-program",
    )

    assert programs
    fields = programs[0]["critical_fields"]
    assert fields["language"].lower() == "english"
    assert fields["duration"].lower() == "2 years"
    assert fields["tuition"].lower().startswith("rmb 56,000")
    assert fields["deadlines"] == "March 18, 2027"
    assert metadata["selectors_used"] == ["#vsb_content"]


def test_retry_policy_includes_shenzhen_university_domain_profile():
    assert "www.szu.edu.cn" in DOMAIN_RETRY_POLICY
    assert DOMAIN_RETRY_POLICY["www.szu.edu.cn"]["attempts"] >= 3
    assert DOMAIN_RETRY_POLICY["www.szu.edu.cn"]["backoff_factor"] > 1


def test_retry_policy_selection_uses_hostname_profile():
    domain, policy = _retry_policy_for_url("https://www.hitsz.edu.cn/admissions/graduate")
    assert domain == "www.hitsz.edu.cn"
    assert policy["attempts"] == DOMAIN_RETRY_POLICY["www.hitsz.edu.cn"]["attempts"]
    assert policy["backoff_factor"] == DOMAIN_RETRY_POLICY["www.hitsz.edu.cn"]["backoff_factor"]


def test_fetch_retry_enforces_minimum_attempts(monkeypatch):
    class _FakeResponse:
        def __init__(self, status_code=200, text="ok"):
            self.status_code = status_code
            self.history = []
            self.text = text

        def raise_for_status(self):
            return None

    calls = {"count": 0, "sleep": 0}
    original_policy = DOMAIN_RETRY_POLICY.get("example.edu")
    DOMAIN_RETRY_POLICY["example.edu"] = {"attempts": 1, "backoff_factor": 1.0, "base_delay": 0.0, "jitter_seconds": 0.0}

    def _fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("temporary timeout")
        return _FakeResponse()

    def _fake_sleep(_seconds):
        calls["sleep"] += 1

    monkeypatch.setattr("scraper.requests.get", _fake_get)
    monkeypatch.setattr("scraper.time.sleep", _fake_sleep)
    monkeypatch.setattr("scraper.random.uniform", lambda _a, _b: 0.0)

    result = _fetch_page_with_retry("https://example.edu/program", timeout=3)

    assert result is not None
    assert calls["count"] == 2
    assert calls["sleep"] == 1
    assert result["attempts_used"] == 2
    assert result["final_status"] == "success"
    if original_policy is None:
        del DOMAIN_RETRY_POLICY["example.edu"]
    else:
        DOMAIN_RETRY_POLICY["example.edu"] = original_policy


def test_tsinghua_sigs_connector_prefers_selector_chain_and_emits_connector_metadata():
    html = _read_fixture("tsinghua_sigs_program.html")
    soup = BeautifulSoup(html, "html.parser")

    programs, metadata = _extract_programs_with_connector(
        "Tsinghua Shenzhen International Graduate School",
        soup,
        "https://www.sigs.tsinghua.edu.cn/en/admissions/master-program",
    )

    assert programs
    fields = programs[0]["critical_fields"]
    assert fields["language"].lower() == "english"
    assert fields["duration"].lower() == "2 years"
    assert fields["tuition"].lower().startswith("rmb 88,000")
    assert fields["deadlines"] == "2027-03-25"
    assert fields["portal"] == "https://apply.sigs.tsinghua.edu.cn/graduate"
    assert metadata["normalizer_used"] == "selector"
    assert metadata["connector_version"]
    assert metadata["selectors_used"] == ["main"]


def test_pku_sgs_connector_falls_back_to_table_parser():
    html = _read_fixture("pku_sgs_program.html")
    soup = BeautifulSoup(html, "html.parser")

    programs, metadata = _extract_programs_with_connector(
        "Peking University Shenzhen Graduate School",
        soup,
        "https://www.sgs.pku.edu.cn/english/admissions/master",
    )

    assert programs
    fields = programs[0]["critical_fields"]
    assert fields["language"] == "English"
    assert fields["duration"] == "2 years"
    assert fields["tuition"] == "RMB 72,000 /year"
    assert fields["deadlines"] == "April 10, 2027"
    assert fields["portal"] == "https://apply.sgs.pku.edu.cn/master"
    assert metadata["normalizer_used"] == "table"


def test_retry_policy_includes_tsinghua_and_pku_shenzhen_domain_profiles():
    assert "www.sigs.tsinghua.edu.cn" in DOMAIN_RETRY_POLICY
    assert DOMAIN_RETRY_POLICY["www.sigs.tsinghua.edu.cn"]["attempts"] >= 4
    assert "www.sgs.pku.edu.cn" in DOMAIN_RETRY_POLICY
    assert DOMAIN_RETRY_POLICY["www.sgs.pku.edu.cn"]["backoff_factor"] > 1

import database as db
import scraper


def test_run_full_scan_generates_extraction_quality_snapshot_smoke(tmp_path, monkeypatch):
    db_path = str(tmp_path / "smoke_quality.db")
    db.init_db(db_path)

    monkeypatch.setattr(db, "get_all_sources", lambda _db_path: [])
    monkeypatch.setattr(scraper, "discover_university_sources", lambda: [{"name": "Smoke U", "candidate_urls": ["https://example.edu/admissions"]}])
    monkeypatch.setattr(
        scraper,
        "scrape_university_pages",
        lambda *_args, **_kwargs: {
            "university": "Smoke U",
            "attempted_urls": 3,
            "processed_urls": 2,
            "programs_created": 1,
            "programs_updated": 1,
            "programs_unchanged": 0,
            "programs_with_inconsistency": 1,
            "connector_name": "smoke_connector",
            "connector_success": 2,
            "connector_fail": 1,
            "critical_fields_expected": 8,
            "critical_fields_complete": 6,
            "critical_field_completeness_pct": 75.0,
            "null_field_count": 2,
            "errors": [],
        },
    )
    monkeypatch.setattr(scraper, "score_snapshot", lambda **_kwargs: {"programs_scored": 1, "programs_omitted": 0, "omitted_cases": []})

    summary = scraper.run_full_scan(db_path=db_path, run_metadata={"trigger": "smoke_test"})
    assert summary["extraction_quality_snapshot"] == {
        "attempted_urls": 3,
        "successful_parses": 2,
        "critical_field_completeness_pct": 75.0,
        "null_field_count": 2,
        "inconsistency_flags": 1,
    }

    snapshot = db.get_scan_snapshot(summary["snapshot_id"], db_path=db_path)
    assert snapshot is not None
    assert snapshot["run_metadata"]["extraction_quality_snapshot"] == summary["extraction_quality_snapshot"]
    assert snapshot["summary_json"]["extraction_quality_snapshot"] == summary["extraction_quality_snapshot"]

    latest_quality = db.get_latest_extraction_quality_snapshot(db_path=db_path)
    assert latest_quality["snapshot_id"] == summary["snapshot_id"]
    assert latest_quality["extraction_quality_snapshot"] == summary["extraction_quality_snapshot"]

import json
from pathlib import Path

import pytest

from src.ingestion import job, theirstack
from src.ingestion.models import IngestRequest

# The example payload the frontend sends
PAYLOAD = {
    "posted_at_max_age_days": 7,
    "job_location_or": [{"id": 6251999}],
    "job_title_or": ["databricks data engineer"],
    "limit": 10,
}


@pytest.fixture(autouse=True)
def small_pages(monkeypatch):
    """page_size 2 / max_pages 5, no sleeping."""
    from src.ingestion.config import Settings
    monkeypatch.setattr(job, "Settings", lambda theirstack_api_key: Settings(theirstack_api_key, page_size=2, max_pages=5))
    monkeypatch.setattr("src.ingestion.theirstack.time.sleep", lambda s: None)


def fake_pages(pages):
    return lambda settings, req, page, page_limit: pages[page] if page < len(pages) else []


def run(tmp_path, payload=PAYLOAD, **kw):
    return job.run(payload, str(tmp_path), "key", **kw)


def read_ndjson(path):
    return [json.loads(line) for line in open(path)]


def job_rec(i, place, desc="Build pipelines on Databricks", title="Senior Data Engineer", company="acme"):
    return {"id": i, "job_title": title, "description": desc, "company_domain": company, "long_location": place}


# ---- landing -------------------------------------------------------------------------------------

def test_lands_pages_and_manifest_in_a_session_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(theirstack, "fetch_page", fake_pages([[{"id": 1}, {"id": 2}], [{"id": 3}]]))
    st = run(tmp_path)
    folder = Path(st["volume_path"])
    assert st["status"] == "succeeded" and (st["records_written"], st["pages_written"]) == (3, 2)
    assert read_ndjson(folder / "theirstack_page000.json") == [{"id": 1}, {"id": 2}]
    assert json.load(open(folder / "_manifest.json"))["status"] == "succeeded"


def test_each_run_gets_its_own_folder_and_session_id_can_be_supplied(tmp_path, monkeypatch):
    monkeypatch.setattr(theirstack, "fetch_page", fake_pages([]))
    a, b = run(tmp_path), run(tmp_path)
    assert a["volume_path"] != b["volume_path"]
    assert run(tmp_path, session_id="from-frontend")["volume_path"].endswith("/raw/session_id=from-frontend")


def test_failure_is_recorded_in_manifest(tmp_path, monkeypatch):
    def boom(*a):
        raise RuntimeError("api down")
    monkeypatch.setattr(theirstack, "fetch_page", boom)
    st = run(tmp_path)
    assert st["status"] == "failed" and "api down" in st["error"]
    assert json.load(open(Path(st["volume_path"]) / "_manifest.json"))["status"] == "failed"


def test_theirstack_error_body_is_surfaced(tmp_path, monkeypatch):
    class Resp:
        ok, status_code, text = False, 422, '{"detail":"bad filter value"}'
    monkeypatch.setattr("src.ingestion.theirstack.requests.post", lambda *a, **k: Resp())
    assert "bad filter value" in run(tmp_path)["error"]


# ---- spend controls ------------------------------------------------------------------------------

def test_page_cap_is_server_side(tmp_path, monkeypatch):
    monkeypatch.setattr(theirstack, "fetch_page", lambda s, r, p, n: [{"id": 10 * p}, {"id": 10 * p + 1}])
    st = run(tmp_path, {**PAYLOAD, "limit": 10_000})
    assert (st["pages_written"], st["records_written"]) == (5, 10)  # max_pages * page_size


def test_limit_trims_and_sets_page_size(tmp_path, monkeypatch):
    seen = []

    def fetch(s, r, p, n):
        seen.append(n)
        return [{"id": 10 * p + i} for i in range(n)]
    monkeypatch.setattr(theirstack, "fetch_page", fetch)
    assert run(tmp_path, {**PAYLOAD, "limit": 3})["records_written"] == 3
    assert seen == [2, 1]  # page_size, then only the 1 record still needed


# ---- filters -------------------------------------------------------------------------------------

def test_extra_filters_are_forwarded_and_server_fields_win():
    req = IngestRequest(**PAYLOAD, company_name_or=["Databricks"], min_employee_count=50)
    body = theirstack.build_payload(req, page=3, page_limit=7)
    assert body["company_name_or"] == ["Databricks"] and body["min_employee_count"] == 50
    assert body["job_location_or"] == [{"id": 6251999}]
    assert (body["page"], body["limit"], body["blur_company_data"], body["include_total_results"]) == (3, 7, False, False)


@pytest.mark.parametrize("override", [
    {"made_up_filter": 1},  # typo / unknown
    {"page": 99},  # server-owned
    {"include_total_results": True},
    {"limit": 0},
])
def test_invalid_or_server_owned_fields_rejected_before_any_fetch(tmp_path, monkeypatch, override):
    monkeypatch.setattr(theirstack, "fetch_page", lambda *a: pytest.fail("must not call TheirStack"))
    with pytest.raises(ValueError):
        run(tmp_path, {**PAYLOAD, **override})
    assert list(tmp_path.iterdir()) == []


def test_requires_a_mandatory_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(theirstack, "fetch_page", fake_pages([]))
    with pytest.raises(ValueError):
        run(tmp_path, {"job_title_or": ["x"]})
    assert run(tmp_path, {"company_name_or": ["Databricks"]})["status"] == "succeeded"


# ---- dedup ---------------------------------------------------------------------------------------

def test_same_posting_in_many_provinces_lands_once(tmp_path, monkeypatch):
    pages = [[job_rec(1, "Ottawa, Ontario"), job_rec(2, "Halifax, Nova Scotia")], [job_rec(3, "Calgary,  Alberta ")]]
    monkeypatch.setattr(theirstack, "fetch_page", fake_pages(pages))
    st = run(tmp_path, {**PAYLOAD, "limit": 3})
    assert (st["records_fetched"], st["records_written"], st["duplicates_dropped"]) == (3, 1, 2)
    folder = Path(st["volume_path"])
    assert read_ndjson(folder / "theirstack_page000.json") == [job_rec(1, "Ottawa, Ontario")]
    assert not (folder / "theirstack_page001.json").exists()  # all-duplicate page writes nothing
    assert json.load(open(folder / "_duplicates.json"))["1"] == {
        "duplicate_job_ids": [2, 3],
        "locations": ["Ottawa, Ontario", "Halifax, Nova Scotia", "Calgary,  Alberta "],
    }


def test_different_description_title_or_company_are_kept(tmp_path, monkeypatch):
    jobs = [job_rec(1, "A"), job_rec(2, "B", desc="Different text"), job_rec(3, "C", title="Data Analyst"),
            job_rec(4, "D", company="other")]
    monkeypatch.setattr(theirstack, "fetch_page", fake_pages([jobs]))
    assert run(tmp_path, {**PAYLOAD, "limit": 4})["duplicates_dropped"] == 0


def test_jobs_without_description_are_never_merged(tmp_path, monkeypatch):
    jobs = [{"id": 1, "job_title": "x", "company_domain": "a"}, {"id": 2, "job_title": "x", "company_domain": "a"}]
    monkeypatch.setattr(theirstack, "fetch_page", fake_pages([jobs]))
    assert run(tmp_path, {**PAYLOAD, "limit": 2})["records_written"] == 2


def test_same_id_across_pages_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(theirstack, "fetch_page", fake_pages([[{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 3}]]))
    st = run(tmp_path, {**PAYLOAD, "limit": 4})
    assert (st["records_written"], st["duplicates_dropped"]) == (3, 1)


# ---- layout --------------------------------------------------------------------------------------

def test_session_lands_under_raw_with_session_id_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(theirstack, "fetch_page", fake_pages([[{"id": 1}]]))
    st = run(tmp_path, session_id="abc123")
    assert st["volume_path"] == f"{tmp_path}/raw/session_id=abc123"
    assert (tmp_path / "raw" / "session_id=abc123" / "_manifest.json").exists()
    assert [p.name for p in tmp_path.iterdir()] == ["raw"]  # nothing else at the volume root

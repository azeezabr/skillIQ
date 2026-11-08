import json

import pytest
from fastapi.testclient import TestClient

from src.ingestion import api, service, theirstack
from src.ingestion.models import IngestRequest
from src.ingestion.config import Settings


# The example payload from the frontend
PAYLOAD = {
    "posted_at_max_age_days": 7,
    "job_location_or": [{"id": 6251999}],
    "job_title_or": ["databricks data engineer"],
    "limit": 10,
}


class FakeWriter:
    def __init__(self):
        self.files = {}

    def session_dir(self, sid):
        return f"/Volumes/c/s/v/session_id={sid}"

    def write_ndjson(self, path, records):
        self.files[path] = records

    def write_json(self, path, obj):
        self.files[path] = obj


@pytest.fixture
def client(monkeypatch):
    s = Settings("key", "http://x", "h", "t", "c", "s", "v", [], page_size=2, max_pages=5)
    writer = FakeWriter()
    monkeypatch.setattr(api, "settings", s)
    monkeypatch.setattr(api, "_writer", writer)
    return TestClient(api.app), writer


def fake_pages(pages):
    def _fetch(settings, req, page, page_limit):
        return pages[page] if page < len(pages) else []
    return _fetch


def test_session_lands_pages_and_manifest(client, monkeypatch):
    c, writer = client
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", fake_pages([[{"id": 1}, {"id": 2}], [{"id": 3}]]))
    monkeypatch.setattr("src.ingestion.theirstack.time.sleep", lambda s: None)

    r = c.post("/api/ingest/sessions", json=PAYLOAD)
    assert r.status_code == 202
    sid = r.json()["session_id"]

    st = c.get(f"/api/ingest/sessions/{sid}").json()  # TestClient runs background task before returning
    assert st["status"] == "succeeded"
    assert (st["pages_written"], st["records_written"]) == (2, 3)
    base = f"/Volumes/c/s/v/session_id={sid}"
    assert writer.files[f"{base}/theirstack_page000.json"] == [{"id": 1}, {"id": 2}]
    assert writer.files[f"{base}/_manifest.json"]["status"] == "succeeded"


def test_two_sessions_get_separate_paths(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", fake_pages([]))
    a = c.post("/api/ingest/sessions", json=PAYLOAD).json()
    b = c.post("/api/ingest/sessions", json=PAYLOAD).json()
    assert a["volume_path"] != b["volume_path"]


def test_failure_is_recorded_in_manifest(client, monkeypatch):
    c, writer = client

    def boom(*a):
        raise RuntimeError("api down")
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", boom)
    sid = c.post("/api/ingest/sessions", json=PAYLOAD).json()["session_id"]
    st = c.get(f"/api/ingest/sessions/{sid}").json()
    assert st["status"] == "failed" and "api down" in st["error"]
    assert writer.files[f"/Volumes/c/s/v/session_id={sid}/_manifest.json"]["status"] == "failed"


def test_page_cap_is_server_side(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", lambda s, r, p, n: [{"id": 10 * p}, {"id": 10 * p + 1}])
    monkeypatch.setattr("src.ingestion.theirstack.time.sleep", lambda s: None)
    sid = c.post("/api/ingest/sessions", json={**PAYLOAD, "limit": 10_000}).json()["session_id"]
    st = c.get(f"/api/ingest/sessions/{sid}").json()
    assert st["pages_written"] == 5 and st["records_written"] == 10  # max_pages * page_size(2)


def test_limit_trims_and_sets_page_size(client, monkeypatch):
    c, writer = client
    seen = []

    def fetch(s, r, p, n):
        seen.append(n)
        return [{"id": 10 * p + i} for i in range(n)]
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", fetch)
    monkeypatch.setattr("src.ingestion.theirstack.time.sleep", lambda s: None)
    sid = c.post("/api/ingest/sessions", json={**PAYLOAD, "limit": 3}).json()["session_id"]
    assert seen == [2, 1]  # page_size 2, then only the 1 record still needed
    assert c.get(f"/api/ingest/sessions/{sid}").json()["records_written"] == 3


# ---- filters -------------------------------------------------------------------------------------

def test_extra_filters_are_forwarded_and_server_fields_win():
    req = IngestRequest(**PAYLOAD, company_name_or=["Databricks"], min_employee_count=50)
    body = theirstack.build_payload(req, page=3, page_limit=7)
    assert body["company_name_or"] == ["Databricks"] and body["min_employee_count"] == 50
    assert body["job_location_or"] == [{"id": 6251999}]
    assert (body["page"], body["limit"], body["blur_company_data"], body["include_total_results"]) == (3, 7, False, False)
    assert "limit" in body and "company_name_or" in body


@pytest.mark.parametrize("override", [
    {"made_up_filter": 1},          # typo / unknown
    {"page": 99},                   # server-owned
    {"include_total_results": True},
    {"limit": 0},
])
def test_invalid_or_server_owned_fields_rejected(client, override):
    assert client[0].post("/api/ingest/sessions", json={**PAYLOAD, **override}).status_code == 422


def test_requires_a_mandatory_filter(client):
    c, _ = client
    assert c.post("/api/ingest/sessions", json={"job_title_or": ["x"]}).status_code == 422
    assert c.post("/api/ingest/sessions", json={"company_name_or": ["Databricks"]}).status_code == 202


def test_theirstack_error_body_is_surfaced(client, monkeypatch):
    c, _ = client

    class Resp:
        ok, status_code, text = False, 422, '{"detail":"bad filter value"}'
    monkeypatch.setattr("src.ingestion.theirstack.requests.post", lambda *a, **k: Resp())
    sid = c.post("/api/ingest/sessions", json=PAYLOAD).json()["session_id"]
    assert "bad filter value" in c.get(f"/api/ingest/sessions/{sid}").json()["error"]


# ---- dedup ---------------------------------------------------------------------------------------

def job(i, place, desc="Build pipelines on Databricks", title="Senior Data Engineer", company="acme"):
    return {"id": i, "job_title": title, "description": desc, "company_domain": company, "long_location": place}


def test_same_posting_in_many_provinces_lands_once(client, monkeypatch):
    c, writer = client
    pages = [[job(1, "Ottawa, Ontario"), job(2, "Halifax, Nova Scotia")], [job(3, "Calgary,  Alberta ")]]
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", fake_pages(pages))
    monkeypatch.setattr("src.ingestion.theirstack.time.sleep", lambda s: None)
    sid = c.post("/api/ingest/sessions", json={**PAYLOAD, "limit": 3}).json()["session_id"]
    st = c.get(f"/api/ingest/sessions/{sid}").json()
    assert (st["records_fetched"], st["records_written"], st["duplicates_dropped"]) == (3, 1, 2)
    base = f"/Volumes/c/s/v/session_id={sid}"
    assert writer.files[f"{base}/theirstack_page000.json"] == [job(1, "Ottawa, Ontario")]
    assert f"{base}/theirstack_page001.json" not in writer.files  # all-duplicate page writes nothing
    assert writer.files[f"{base}/_duplicates.json"]["1"] == {
        "duplicate_job_ids": [2, 3],
        "locations": ["Ottawa, Ontario", "Halifax, Nova Scotia", "Calgary,  Alberta "],
    }


def test_different_description_title_or_company_are_kept(client, monkeypatch):
    c, _ = client
    jobs = [job(1, "A"), job(2, "B", desc="Different text"), job(3, "C", title="Data Analyst"), job(4, "D", company="other")]
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", fake_pages([jobs]))
    sid = c.post("/api/ingest/sessions", json={**PAYLOAD, "limit": 4}).json()["session_id"]
    assert c.get(f"/api/ingest/sessions/{sid}").json()["duplicates_dropped"] == 0


def test_jobs_without_description_are_never_merged(client, monkeypatch):
    c, _ = client
    jobs = [{"id": 1, "job_title": "x", "company_domain": "a"}, {"id": 2, "job_title": "x", "company_domain": "a"}]
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", fake_pages([jobs]))
    sid = c.post("/api/ingest/sessions", json={**PAYLOAD, "limit": 2}).json()["session_id"]
    assert c.get(f"/api/ingest/sessions/{sid}").json()["records_written"] == 2


def test_same_id_across_pages_is_dropped(client, monkeypatch):
    c, _ = client
    pages = [[{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 3}]]
    monkeypatch.setattr("src.ingestion.theirstack.fetch_page", fake_pages(pages))
    monkeypatch.setattr("src.ingestion.theirstack.time.sleep", lambda s: None)
    sid = c.post("/api/ingest/sessions", json={**PAYLOAD, "limit": 4}).json()["session_id"]
    st = c.get(f"/api/ingest/sessions/{sid}").json()
    assert (st["records_written"], st["duplicates_dropped"]) == (3, 1)

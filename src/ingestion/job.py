"""One ingestion session: TheirStack search -> dedupe -> new session folder in the volume.

Called by the Databricks notebook (databricks/ingest_theirstack.py) or from a terminal:
    THEIRSTACK_API_KEY=... python -m src.ingestion.job --payload '{...}' --volume-root /some/dir
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from .config import Settings
from .dedupe import Deduper
from .models import IngestRequest, SessionStatus
from .theirstack import iter_pages
from .volume import FileWriter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(payload: dict, volume_root: str, api_key: str, session_id: str = "") -> dict:
    """Run one session synchronously and return its final status (also written to _manifest.json).

    Never raises for a failed pull — check result["status"]. Raises only for an invalid payload,
    before anything is fetched or written.
    """
    settings = Settings(theirstack_api_key=api_key)
    req = IngestRequest(**payload)  # validates filters; raises before any credits are spent
    writer = FileWriter(volume_root)
    session_id = session_id or uuid.uuid4().hex
    status = SessionStatus(
        session_id=session_id,
        status="running",
        volume_path=writer.session_dir(session_id),
        params=req.model_dump(),
        started_at=_now(),
    )
    deduper = Deduper()
    try:
        for page, jobs in iter_pages(settings, req):
            status.records_fetched += len(jobs)
            unique = deduper.split(jobs)
            status.duplicates_dropped = status.records_fetched - (status.records_written + len(unique))
            if unique:
                writer.write_ndjson(f"{status.volume_path}/theirstack_page{page:03d}.json", unique)
                status.pages_written += 1
                status.records_written += len(unique)
        duplicates = deduper.duplicate_report()
        if duplicates:  # which copies were collapsed and every location each posting appeared in
            writer.write_json(f"{status.volume_path}/_duplicates.json", duplicates)
        status.status = "succeeded"
    except Exception as exc:
        status.status = "failed"
        status.error = f"{type(exc).__name__}: {exc}"
    finally:
        status.finished_at = _now()
        try:
            writer.write_json(f"{status.volume_path}/_manifest.json", status.model_dump())
        except Exception as exc:
            if status.status != "failed":
                status.status = "failed"
                status.error = f"manifest write failed: {exc}"
    return status.model_dump()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run one TheirStack ingestion session")
    ap.add_argument("--payload", required=True, help="JSON search payload (any allowed TheirStack filter + limit)")
    ap.add_argument("--volume-root", required=True)
    ap.add_argument("--session-id", default="")
    a = ap.parse_args()
    result = run(json.loads(a.payload), a.volume_root, os.environ["THEIRSTACK_API_KEY"], a.session_id)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "succeeded" else 1)

import uuid
from datetime import datetime, timezone
from typing import Dict

from .config import Settings
from .dedupe import Deduper
from .models import IngestRequest, SessionStatus
from .theirstack import iter_pages

# In-memory registry; the _manifest.json in the volume is the durable record once a session finishes.
_sessions: Dict[str, SessionStatus] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(settings: Settings, writer, req: IngestRequest, session_id: str = None) -> SessionStatus:
    session_id = session_id or uuid.uuid4().hex
    status = SessionStatus(
        session_id=session_id,
        status="running",
        volume_path=writer.session_dir(session_id),
        params=req.model_dump(),
        started_at=_now(),
    )
    _sessions[session_id] = status
    return status


def get_session(session_id: str):
    return _sessions.get(session_id)


def run_session(settings: Settings, writer, req: IngestRequest, session_id: str) -> None:
    status = _sessions[session_id]
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
    except Exception as exc:  # surface any failure in status + manifest rather than losing it in a background task
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

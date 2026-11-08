from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import service
from .config import get_settings
from .models import IngestRequest, SessionStatus
from .volume import VolumeWriter

settings = get_settings()
app = FastAPI(title="Skill IQ ingestion")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_writer = None


def get_writer() -> VolumeWriter:
    global _writer
    if _writer is None:
        _writer = VolumeWriter(settings)
    return _writer


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/ingest/sessions", response_model=SessionStatus, status_code=202)
def start_session(req: IngestRequest, background: BackgroundTasks):
    missing = [
        name for name, val in {
            "THEIRSTACK_API_KEY": settings.theirstack_api_key,
            "DATABRICKS_HOST": settings.databricks_host,
            "DATABRICKS_TOKEN": settings.databricks_token,
        }.items() if not val
    ]
    if missing:
        raise HTTPException(500, f"Server not configured: missing {', '.join(missing)}")
    writer = get_writer()
    status = service.create_session(settings, writer, req)
    background.add_task(service.run_session, settings, writer, req, status.session_id)
    return status


@app.get("/api/ingest/sessions/{session_id}", response_model=SessionStatus)
def session_status(session_id: str):
    status = service.get_session(session_id)
    if status is None:
        raise HTTPException(404, "Unknown session")
    return status

"""Entry point for a scheduled run (Databricks job) or a local run. Same code path as the API."""
import argparse
import json
import os
import sys
import uuid
from dataclasses import replace

from . import service
from .config import get_settings
from .models import IngestRequest
from .volume import FileWriter


def run(payload: dict, volume_root: str, api_key: str, session_id: str = "") -> dict:
    """Run one ingestion session synchronously. Returns the final status (also written as _manifest.json)."""
    settings = replace(get_settings(), theirstack_api_key=api_key)
    req = IngestRequest(**payload)
    writer = FileWriter(volume_root)
    status = service.create_session(settings, writer, req, session_id=session_id or None)
    service.run_session(settings, writer, req, status.session_id)
    return status.model_dump()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run one TheirStack ingestion session")
    ap.add_argument("--payload", required=True, help="JSON search payload (same as the frontend sends)")
    ap.add_argument("--volume-root", required=True)
    ap.add_argument("--session-id", default="")
    a = ap.parse_args()
    result = run(json.loads(a.payload), a.volume_root, os.environ["THEIRSTACK_API_KEY"], a.session_id)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "succeeded" else 1)

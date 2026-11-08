import io
import json
import os
from typing import List

from .config import Settings


class VolumeWriter:
    """Writes files into a Unity Catalog Volume through the Files API (works from outside Databricks)."""

    def __init__(self, settings: Settings):
        self.root = settings.volume_root
        from databricks.sdk import WorkspaceClient  # only needed when running outside Databricks

        self._client = WorkspaceClient(host=settings.databricks_host, token=settings.databricks_token)

    def session_dir(self, session_id: str) -> str:
        return f"{self.root}/session_id={session_id}"

    def write_ndjson(self, path: str, records: List[dict]) -> None:
        body = "".join(json.dumps(r, default=str) + "\n" for r in records).encode("utf-8")
        self._client.files.upload(path, io.BytesIO(body), overwrite=True)

    def write_json(self, path: str, obj: dict) -> None:
        body = json.dumps(obj, indent=2, default=str).encode("utf-8")
        self._client.files.upload(path, io.BytesIO(body), overwrite=True)


class FileWriter:
    """Writes to a plain filesystem path. Inside Databricks, /Volumes/... is mounted, so this is all a job needs."""

    def __init__(self, root: str):
        self.root = root

    def session_dir(self, session_id: str) -> str:
        return f"{self.root}/session_id={session_id}"

    def _put(self, path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def write_ndjson(self, path: str, records: List[dict]) -> None:
        self._put(path, "".join(json.dumps(r, default=str) + "\n" for r in records))

    def write_json(self, path: str, obj: dict) -> None:
        self._put(path, json.dumps(obj, indent=2, default=str))

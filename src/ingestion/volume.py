import json
import os
from typing import List


class FileWriter:
    """Writes to a filesystem path. On Databricks, /Volumes/... is mounted, so a plain open() lands in the volume."""

    def __init__(self, root: str):
        self.root = root

    def session_dir(self, session_id: str) -> str:
        # raw/ holds landed data; _system/ (sibling, created by Auto Loader later) holds checkpoints and schemas
        return f"{self.root}/raw/session_id={session_id}"

    def _put(self, path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def write_ndjson(self, path: str, records: List[dict]) -> None:
        self._put(path, "".join(json.dumps(r, default=str) + "\n" for r in records))

    def write_json(self, path: str, obj: dict) -> None:
        self._put(path, json.dumps(obj, indent=2, default=str))

import hashlib
import re
from typing import Dict, List, Optional


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _company(job: dict) -> str:
    co = job.get("company_object") or {}
    return _norm(co.get("id") or job.get("company_domain") or co.get("domain") or job.get("company") or co.get("name"))


def content_key(job: dict) -> Optional[str]:
    """Same company + title + description = same posting republished per city/province.

    Returns None when there is nothing safe to compare, so those jobs are never merged.
    """
    description, company = _norm(job.get("description")), _company(job)
    if not description or not company:
        return None
    digest = hashlib.sha256(description.encode("utf-8")).hexdigest()
    return f"{company}|{_norm(job.get('job_title'))}|{digest}"


def _place(job: dict) -> Optional[str]:
    return job.get("long_location") or job.get("location") or job.get("short_location")


class Deduper:
    """Keeps the first copy of each posting; everything else is recorded in `groups` instead of landed."""

    def __init__(self):
        self._seen_ids = set()
        self._by_key: Dict[str, object] = {}  # content key -> canonical job id
        self.groups: Dict[str, dict] = {}  # canonical job id -> {duplicate_job_ids, locations}

    def split(self, jobs: List[dict]) -> List[dict]:
        unique = []
        for job in jobs:
            job_id = job.get("id")
            if job_id is not None and job_id in self._seen_ids:  # same id again, e.g. pagination shift
                continue
            key = content_key(job)
            canonical = self._by_key.get(key) if key else None
            if canonical is None:
                if key:
                    self._by_key[key] = job_id
                if job_id is not None:
                    self._seen_ids.add(job_id)
                self.groups[str(job_id)] = {"duplicate_job_ids": [], "locations": [p for p in [_place(job)] if p]}
                unique.append(job)
            else:
                group = self.groups[str(canonical)]
                group["duplicate_job_ids"].append(job_id)
                place = _place(job)
                if place and place not in group["locations"]:
                    group["locations"].append(place)
                if job_id is not None:
                    self._seen_ids.add(job_id)
        return unique

    def duplicate_report(self) -> dict:
        return {k: v for k, v in self.groups.items() if v["duplicate_job_ids"]}

import time
from typing import Iterator, List, Tuple

import requests

from .config import Settings
from .models import IngestRequest


def build_payload(req: IngestRequest, page: int, page_limit: int) -> dict:
    """User filters first, then server-owned fields — the user can never override page/limit/billing flags."""
    return {
        **req.filters,
        "include_total_results": False,
        "blur_company_data": False,
        "page": page,
        "limit": page_limit,
    }


def fetch_page(settings: Settings, req: IngestRequest, page: int, page_limit: int) -> List[dict]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.theirstack_api_key}",
    }
    resp = requests.post(
        settings.theirstack_url, headers=headers, json=build_payload(req, page, page_limit), timeout=30
    )
    if not resp.ok:  # TheirStack explains 4xx errors (bad filter value, 402 no credits) in the body
        raise RuntimeError(f"TheirStack {resp.status_code}: {resp.text[:500]}")
    return resp.json().get("data", [])


def iter_pages(settings: Settings, req: IngestRequest) -> Iterator[Tuple[int, List[dict]]]:
    """Yield (page_number, jobs) until req.limit records, an empty/short page, or the server page cap.

    The user's `limit` is clamped to page_size * max_pages so a caller cannot raise the spend.
    """
    remaining = min(req.limit, settings.page_size * settings.max_pages)
    for page in range(settings.max_pages):
        page_limit = min(remaining, settings.page_size)
        jobs = fetch_page(settings, req, page, page_limit)
        if not jobs:
            return
        jobs = jobs[:remaining]
        yield page, jobs
        remaining -= len(jobs)
        if remaining <= 0 or len(jobs) < page_limit:  # done, or short page = last page
            return
        time.sleep(0.3)

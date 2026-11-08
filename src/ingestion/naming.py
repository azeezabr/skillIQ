import re
from datetime import datetime, timezone
from typing import List, Optional

from .models import IngestRequest

# Filters that name a specific company target (ids are opaque, so they are not used in the folder name)
_COMPANY_FILTERS = ("company_name_or", "company_name_case_insensitive_or", "company_name_partial_match_or",
                    "company_domain_or")
_MAX_SLUG = 30
_MAX_PARTS = 3


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:_MAX_SLUG].strip("-")


def _join(values: Optional[List], fallback: str) -> str:
    slugs = [s for s in (slug(v) for v in values or []) if s]
    if not slugs:
        return fallback
    extra = len(slugs) - _MAX_PARTS
    return "+".join(slugs[:_MAX_PARTS]) + (f"+{extra}more" if extra > 0 else "")


def folder_name(req: IngestRequest, session_id: str, today: Optional[str] = None) -> str:
    """<date>_<job titles>[_<company>]_<session_id>, e.g. 2026-11-08_data-engineer+data-architect_databricks_ab12…

    The company part appears only when the payload targets specific companies.
    """
    parts = [today or datetime.now(timezone.utc).date().isoformat(), _join(req.filters.get("job_title_or"), "all-titles")]
    companies = [v for f in _COMPANY_FILTERS for v in (req.filters.get(f) or [])]
    if companies and _join(companies, ""):
        parts.append(_join(companies, ""))
    parts.append(session_id)
    return "_".join(parts)

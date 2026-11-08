from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .filters import ALLOWED_FILTERS, REQUIRED_ONE_OF


class IngestRequest(BaseModel):
    """Frontend payload: any TheirStack search filter in `filters.ALLOWED_FILTERS`, plus `limit`.

    Filter values are forwarded as sent; TheirStack validates their shape and we surface its error.
    """

    model_config = ConfigDict(extra="allow")

    limit: int = Field(25, ge=1)  # total records wanted across all pages; clamped to the server cap

    @model_validator(mode="after")
    def _check_filters(self):
        filters = self.filters
        unknown = sorted(set(filters) - ALLOWED_FILTERS)
        if unknown:
            raise ValueError(f"Unsupported filter(s): {', '.join(unknown)}")
        if not REQUIRED_ONE_OF & set(filters):
            raise ValueError("Add at least one of: " + ", ".join(sorted(REQUIRED_ONE_OF)))
        return self

    @property
    def filters(self) -> dict:
        return {k: v for k, v in (self.model_extra or {}).items() if v is not None}


class SessionStatus(BaseModel):
    session_id: str
    status: str  # running | succeeded | failed
    volume_path: str
    params: dict
    records_fetched: int = 0  # what TheirStack returned (and billed for)
    records_written: int = 0  # unique jobs landed in the volume
    duplicates_dropped: int = 0
    pages_written: int = 0
    started_at: str
    finished_at: Optional[str] = None
    error: Optional[str] = None

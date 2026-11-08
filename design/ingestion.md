# Ingestion — Session-based landing

> Supersedes the weekly "TheirStack → ADLS Gen2" pull described in `architecture.md` / `solution-overview.md` for the **landing step only**. Bronze/Silver/Gold are unchanged and out of scope here.

## Flow

```
Frontend (user sets params → Proceed)
   │  POST /api/ingest/sessions   { posted_at_max_age_days, job_location_or, job_title_or, limit }
   ▼
FastAPI (src/ingestion)
   │  validates + clamps params, mints session_id, returns 202 immediately
   │  background task: page through TheirStack /v1/jobs/search
   ▼
Databricks Volume  (Files API)
   /Volumes/<catalog>/<schema>/<volume>/session_id=<uuid>/
        theirstack_page000.json   NDJSON, one raw job per line, untouched
        theirstack_page001.json
        _duplicates.json          only if duplicates were collapsed
        _manifest.json            params, counts, status, timestamps (written last)
```

One user click = one session = one new folder. Sessions never overwrite each other, so there is no wipe/re-run logic.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/ingest/sessions` | Start a session. Returns `202 { session_id, status: "running", volume_path }` |
| `GET /api/ingest/sessions/{session_id}` | Poll status: `running` / `succeeded` / `failed`, pages + records so far |
| `GET /api/health` | Liveness |

## Request payload

The frontend sends the TheirStack `/v1/jobs/search` body. **Any filter in `src/ingestion/filters.py` is accepted and forwarded as-is** (company, salary, seniority, technology, description, etc. — ~90 filters taken from the TheirStack docs). Example:

```json
{
  "posted_at_max_age_days": 7,
  "job_location_or": [{ "id": 6251999 }],
  "job_title_or": ["databricks data engineer"],
  "company_name_or": ["Databricks"],
  "limit": 10
}
```

Rules:

- **New filter** = add its name to `ALLOWED_FILTERS`. Nothing else changes. Values are not re-validated by us; TheirStack validates them and its error message is returned in the session's `error`.
- **Unknown filter** → 422 naming it (a typo must not silently widen a billed search).
- **At least one** of `posted_at_*`, `job_id_or`, or a `company_*` identifier is required (TheirStack's own rule), else 422.
- **Server-owned, rejected if sent:** `page`, `offset`, `cursor`, `order_by`, `include_total_results`, `blur_company_data`.
- `limit` (default 25) = **total records wanted across all pages**, clamped to `page_size × max_pages` (25 × 20 = 500). The last page asks only for what is still needed.

> The filter list was assembled from the docs page, which could only be partly read. Filters marked deprecated were left out. Confirm with a real call if one is rejected that you expect to work.

## Deduplication

**Constraint:** TheirStack bills **1 credit per job returned**, with no free preview and no caching. A job's `description` only arrives with the billed record, so identical postings (same job republished per city/province) **cannot be filtered out before they are fetched**.

What we do:

1. **After fetch, before write** — collapse repeats so the landing zone (and the Agent Bricks extraction downstream, the expensive step) sees each posting once.
   - Key = company (`company_object.id` → `company_domain` → name) + normalised title + SHA-256 of the whitespace/case-normalised `description`.
   - Same `id` seen twice (pagination shift) is also dropped.
   - Jobs with no description or no company are **never merged**.
   - The first copy is landed untouched. The rest go to `_duplicates.json`: `{canonical_job_id: {duplicate_job_ids, locations[]}}`, so every province a posting appeared in is kept for later.
2. **Credits still spent on duplicates** — `records_fetched` vs `records_written` / `duplicates_dropped` in the manifest shows exactly how many.

Ways to cut credits before the call (not built yet):

- `job_id_not` — skip IDs already landed in earlier sessions. Needs a seen-IDs store (decision pending: file in the Volume vs a Delta table).
- A pre-flight count: `include_total_results=true` + `limit=1` costs at most 1 credit and returns `total_results`, so the frontend could show the expected cost before **Proceed**.

## Config (`.env`, never committed)

`THEIRSTACK_API_KEY`, `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_CATALOG` (`dev_catalog`), `DATABRICKS_SCHEMA` (`landing` — **unconfirmed**), `DATABRICKS_VOLUME` (`skillediq`), `CORS_ORIGINS`. See `.env.example`.

## Notes / limits

- Session status is held in memory (lost on restart) and a `_manifest.json` is the durable record once a session finishes. Fine for one API instance; revisit if the Container App scales out.
- A failed session still writes `_manifest.json` with `status: "failed"` and any pages already landed stay in the folder.

## Scheduled run on Databricks

`databricks/ingest_theirstack.py` is a notebook-format script that wraps `src/ingestion/job.py`. Same code path as the API (filters, limit clamp, dedup, manifest), but writes straight to `/Volumes/...` — no token or Files API needed inside the workspace.

Parameters: `payload` (JSON, same shape as the frontend sends), `catalog`, `schema`, `volume`, `secret_scope`, `secret_key`, `session_id` (blank = generated). The task raises if the session fails, so the job run shows failed and alerts.

TheirStack key: secret `theirstack/api_key` (`databricks secrets put-secret theirstack api_key`).

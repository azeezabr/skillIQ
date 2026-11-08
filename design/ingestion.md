# Ingestion — Session-based landing

> Supersedes the weekly "TheirStack → ADLS Gen2" pull described in `architecture.md` / `solution-overview.md` for the **landing step only**. Bronze/Silver/Gold are unchanged and out of scope here.

## Flow

```
Frontend (user sets params → Proceed)
   │  Databricks Jobs API  run-now  { job_parameters: { payload: "<json>", session_id: "<id>" } }
   ▼
Databricks Job  →  notebook databricks/ingest_theirstack.py
   │  validates the payload (before any credits are spent), pages through TheirStack /v1/jobs/search,
   │  dedupes, writes — all inside src/ingestion/job.py
   ▼
Unity Catalog Volume  /Volumes/dev_catalog/bronze/vol-skilliq/<date>_<titles>[_<company>]_<session_id>/
        theirstack_page000.json   NDJSON, one raw job per line, untouched
        theirstack_page001.json
        _duplicates.json          only if duplicates were collapsed
        _manifest.json            params, counts, status, timestamps (written last)
```

One run = one session = one new folder, so runs never overwrite each other.

Folder name: `<date UTC>_<job titles>[_<company>]_<session_id>`, e.g. `2026-11-08_data-engineer+data-architect_databricks_ab12…`.
- Titles come from `job_title_or` (`all-titles` if absent), slugged, first 3 then `+Nmore`.
- The company part appears **only** when the payload targets companies (`company_name_*` or `company_domain_or`; opaque ids are skipped).
- The full params are always in `_manifest.json`; the name is for humans browsing the volume.
- To find a run by session id: match the folder ending in `_<session_id>`. The frontend can pass its own `session_id` to know which folder a run wrote; blank = generated.

There is no API service: the frontend triggers the job directly and reads status from the Jobs API (run state) or the folder's `_manifest.json`.

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

## The Databricks job

`databricks/ingest_theirstack.py` is a thin notebook around `src/ingestion/job.py`. It writes straight to `/Volumes/...` (mounted inside the workspace), so no token or Files API is involved.

Job parameters: **only** `payload` (JSON, the search body above; `limit` optional, default 25) and `session_id` (blank = generated). Volume (`dev_catalog.bronze.vol-skilliq`) and the secret (Unity Catalog secret `dev_catalog.bronze.theirstack_api_key`, read with `dbutils.secrets.get(catalog, schema, key)`; needs serverless environment v4+ and READ SECRET) are constants in the notebook.

The task raises when the session fails, so the run shows failed and can alert. An invalid payload fails the task before any TheirStack call.

TheirStack key: Unity Catalog secret, not a secret scope. The running identity needs `READ SECRET` on it plus `USE SCHEMA`/`USE CATALOG`.

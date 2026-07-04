# Data Model — Skill IQ (Databricks Medallion)

> Pipeline: Databricks (Delta Lake). Serving: Databricks SQL Warehouse → Next.js API routes.

---

## Layer overview

```
Source API (JSON)
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  BRONZE  skilliq.bronze                                         │
│  Raw ingestion — append-only, partition by _source_date         │
│  • raw_job_postings                                             │
└─────────────────────────────────────────────────────────────────┘
      │  parse + normalise + classify
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  SILVER  skilliq.silver                                         │
│  Cleaned, deduplicated, relational                              │
│  • dim_roles            • dim_skills                            │
│  • dim_companies        • dim_locations                         │
│  • fact_job_postings    • bridge_job_skills                     │
│                         • bridge_job_locations                  │
└─────────────────────────────────────────────────────────────────┘
      │  aggregate + trend
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  GOLD  skilliq.gold                                             │
│  Pre-aggregated to daily grain, fully filterable by SQL         │
│  • fact_skill_daily     • fact_role_daily                       │
└─────────────────────────────────────────────────────────────────┘
      │  Databricks SQL Warehouse
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  API  (Next.js API routes)                                      │
│  GET /api/skills   GET /api/filters                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## BRONZE — `skilliq.bronze`

### `raw_job_postings`

Append-only. Never mutated after write. One row = one API response record.

| Column | Type | Notes |
|---|---|---|
| `_id` | BIGINT | Source `id` field |
| `_source_date` | DATE | The date param used when calling the source API |
| `_ingestion_timestamp` | TIMESTAMP | `current_timestamp()` at write time |
| `_batch_id` | STRING | UUID for the ingestion run |
| `_raw_payload` | STRING | Full JSON blob |
| `date_posted` | DATE | Extracted for partition pruning |
| `country_code` | STRING | Extracted for partition pruning |

**Partition by:** `_source_date`
**Primary key (logical):** `_id, _source_date` (same job can be re-ingested on different source dates)

---

## SILVER — `skilliq.silver`

### `dim_roles`

Lookup table — seed data, not derived from API.

| Column | Type | Notes |
|---|---|---|
| `role_id` | INT | Surrogate key |
| `role_slug` | STRING | `data_engineer`, `data_scientist`, `ml_engineer`, `data_analyst`, `software_engineer` |
| `display_name` | STRING | "Data Engineer" |
| `match_keywords` | ARRAY<STRING> | Keyword list for classification |
| `sort_order` | INT | Tab display order |

Seed rows (5 roles + 1 catch-all):
```
1  data_engineer      Data Engineer        [...]  1
2  data_scientist     Data Scientist       [...]  2
3  ml_engineer        ML Engineer          [...]  3
4  data_analyst       Data Analyst         [...]  4
5  software_engineer  Software Engineer    [...]  5
99 other              Other                []     99
```

---

### `dim_skills`

| Column | Type | Notes |
|---|---|---|
| `skill_id` | INT | Surrogate key |
| `slug` | STRING | Source slug, e.g. `postgresql` |
| `display_name` | STRING | Human-readable, e.g. "PostgreSQL" |
| `category` | STRING | `technology`, `platform`, `methodology`, `excluded` |
| `canonical_slug` | STRING | For alias dedup (e.g. `postgres` → `postgresql`) |

`category = 'excluded'` rows are filtered out during `bridge_job_skills` build.
New slugs not in this table are added with `category = 'unknown'` and surfaced for review.

---

### `dim_companies`

SCD Type 1 — last-seen values win.

| Column | Type | Notes |
|---|---|---|
| `company_id` | STRING | Source `company_object.id` |
| `name` | STRING | |
| `domain` | STRING | |
| `industry` | STRING | From `company_object.industry` — **filter dimension** |
| `industry_id` | INT | |
| `employee_count` | INT | |
| `employee_count_range` | STRING | |
| `country` | STRING | HQ country |
| `city` | STRING | HQ city |
| `is_recruiting_agency` | BOOLEAN | Exclude from app filters |
| `_updated_at` | TIMESTAMP | Last seen in a batch |

---

### `dim_locations`

Distinct city-level locations from the `locations[]` array on each posting.

| Column | Type | Notes |
|---|---|---|
| `location_id` | INT | Source GeoNames `id` |
| `name` | STRING | City name |
| `display_name` | STRING | Full display |
| `type` | STRING | `city`, `region` |
| `state` | STRING | |
| `state_code` | STRING | |
| `country_name` | STRING | |
| `country_code` | STRING | ISO-2 — **filter dimension** |
| `continent_code` | STRING | 2-letter, e.g. `NA` |
| `continent_name` | STRING | "North America" — **filter dimension** |
| `latitude` | DOUBLE | |
| `longitude` | DOUBLE | |

---

### `fact_job_postings`

One row per unique job posting (deduplicated by `job_id`). Updated if a newer ingestion of the same `job_id` arrives (SCD Type 1).

| Column | Type | Notes |
|---|---|---|
| `job_id` | BIGINT | Source `id` — natural key |
| `role_id` | INT | FK → `dim_roles` |
| `company_id` | STRING | FK → `dim_companies` |
| `primary_location_id` | INT | FK → `dim_locations` (primary location only) |
| `job_title` | STRING | Original title |
| `normalized_title` | STRING | API-provided |
| `seniority` | STRING | |
| `date_posted` | DATE | **Partition + filter column** |
| `date_reposted` | DATE | |
| `closed_at` | TIMESTAMP | NULL = open |
| `is_open` | BOOLEAN | Derived: `closed_at IS NULL` |
| `remote` | BOOLEAN | |
| `hybrid` | BOOLEAN | |
| `employment_status` | STRING | First value of `employment_statuses[]` |
| `min_salary_usd` | INT | |
| `max_salary_usd` | INT | |
| `avg_salary_usd` | INT | Used for median calc in gold |
| `salary_currency` | STRING | |
| `_first_seen_date` | DATE | Earliest `_source_date` in bronze |
| `_last_updated_date` | DATE | Latest `_source_date` in bronze |

**Partition by:** `date_posted` (year/month)

---

### `bridge_job_skills`

Many-to-many: one row per (job, skill). A skill appearing in both `keyword_slugs` and `technology_slugs` produces **one row** (deduped).

| Column | Type | Notes |
|---|---|---|
| `job_id` | BIGINT | FK → `fact_job_postings` |
| `skill_id` | INT | FK → `dim_skills` |
| `sources` | ARRAY<STRING> | `["keyword", "technology"]` — which arrays it appeared in |
| `date_posted` | DATE | Denormalised for partition pruning |

**Partition by:** `date_posted`

---

### `bridge_job_locations`

Many-to-many: one row per (job, location). Exploded from `locations[]`.

| Column | Type | Notes |
|---|---|---|
| `job_id` | BIGINT | FK → `fact_job_postings` |
| `location_id` | INT | FK → `dim_locations` |
| `date_posted` | DATE | Denormalised for partition pruning |

**Partition by:** `date_posted`

---

## GOLD — `skilliq.gold`

### `fact_skill_daily`

Daily grain. One row per (role, skill, date, country, continent, industry). Drives the skills ranked list and trend calculation.

| Column | Type | Notes |
|---|---|---|
| `role_slug` | STRING | From `dim_roles` |
| `skill_slug` | STRING | From `dim_skills.slug` |
| `skill_display_name` | STRING | Denormalised |
| `skill_category` | STRING | Denormalised |
| `date_posted` | DATE | **Partition + primary filter** |
| `country_code` | STRING | **Filter dimension** |
| `continent_name` | STRING | **Filter dimension** |
| `industry` | STRING | From `dim_companies` — **filter dimension** |
| `posting_count` | BIGINT | Jobs for this role+skill on this date |
| `total_role_postings` | BIGINT | Total jobs for this role on this date (denominator) |

**Partition by:** `date_posted`

**Occurrence % at query time:**
```sql
SUM(posting_count) / SUM(total_role_postings) * 100 AS occurrence_pct
```

**Trend at query time:**
```sql
-- Split [start_date, today] into two equal halves
-- half_a = older half, half_b = newer half
occurrence_pct_half_b - occurrence_pct_half_a AS trend_delta_pp
-- > +5pp  → 'trending'
-- < -5pp  → 'declining'
-- else    → 'stable'
```

---

### `fact_role_daily`

Daily grain. One row per (role, date, country, continent, industry). Drives the KPI metric cards.

| Column | Type | Notes |
|---|---|---|
| `role_slug` | STRING | |
| `date_posted` | DATE | **Partition + primary filter** |
| `country_code` | STRING | **Filter dimension** |
| `continent_name` | STRING | **Filter dimension** |
| `industry` | STRING | **Filter dimension** |
| `job_postings_count` | BIGINT | Total postings |
| `open_roles_count` | BIGINT | Where `is_open = TRUE` |
| `salary_usd_p25` | DOUBLE | 25th percentile of `avg_salary_usd` |
| `salary_usd_p50` | DOUBLE | Median salary (P50) — shown in UI |
| `salary_usd_p75` | DOUBLE | 75th percentile |

**Partition by:** `date_posted`

---

## Refresh strategy

```
Bronze (incremental append, daily)
  └─► Silver dims (MERGE / upsert, daily)
       └─► Silver facts (MERGE on job_id, daily)
            └─► Gold (full overwrite for affected date partitions, daily)
```

Trigger: Databricks Workflow, scheduled daily after API pull.
On user date filter change: gold tables are already populated — no re-run needed. API queries gold dynamically.

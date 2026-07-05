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
      │  parse + normalise + classify + AI skill/cert extraction
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  SILVER  skilliq.silver                               (10 tbls) │
│  Cleaned, deduplicated, relational                              │
│  • dim_roles              • dim_skills                          │
│  • dim_companies          • dim_locations                       │
│  • dim_certifications                                           │
│  • fact_job_postings      • bridge_job_skills                   │
│                           • bridge_job_locations                │
│                           • bridge_job_certifications           │
└─────────────────────────────────────────────────────────────────┘
      │  aggregate to daily grain
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  GOLD  skilliq.gold                                    (3 tbls) │
│  Pre-aggregated, fully filterable by SQL at query time          │
│  • fact_skill_daily                                             │
│  • fact_certification_daily                                     │
│  • fact_role_daily                                              │
└─────────────────────────────────────────────────────────────────┘
      │  Databricks SQL Warehouse
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  API  (Next.js API routes)                             (4 APIs) │
│  GET /api/filters (cascaded)   GET /api/skills                  │
│  GET /api/certifications       GET /api/jobs (queries Silver)   │
└─────────────────────────────────────────────────────────────────┘
```

**Total: 14 tables** (1 bronze + 10 silver + 3 gold)

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
**Primary key (logical):** `_id, _source_date`

---

## SILVER — `skilliq.silver`

### `dim_roles`

Seed table — 5 roles + 1 catch-all. Loaded once; used by the AI agent as a reference for valid role definitions. The agent reads this table at runtime so its classifications stay aligned with what the app exposes.

| Column | Type | Notes |
|---|---|---|
| `role_id` | INT | Surrogate key |
| `role_slug` | STRING | `data_engineer`, `data_scientist`, `ml_engineer`, `data_analyst`, `software_engineer` |
| `display_name` | STRING | "Data Engineer" |
| `description` | STRING | Plain-language role definition provided to the agent as context |
| `sort_order` | INT | Dropdown display order |

```
1  data_engineer      Data Engineer        "Builds and maintains data pipelines..."   1
2  data_scientist     Data Scientist       "Builds models and analyses data..."        2
3  ml_engineer        ML Engineer          "Productionises ML models and infra..."     3
4  data_analyst       Data Analyst         "Queries and visualises data for insights"  4
5  software_engineer  Software Engineer    "Builds software products and services..."  5
99 other              Other                ""                                          99
```

---

### `dim_skills`

Populated by AI extraction from `keyword_slugs` + `technology_slugs`. No manual seed required.

| Column | Type | Notes |
|---|---|---|
| `skill_id` | INT | Surrogate key |
| `slug` | STRING | Source slug, e.g. `postgresql` |
| `display_name` | STRING | AI-resolved human name, e.g. "PostgreSQL" |
| `category` | STRING | `technology`, `platform`, `methodology`, `excluded` |
| `canonical_slug` | STRING | Alias dedup (e.g. `postgres` → `postgresql`) |

`category = 'excluded'` rows are filtered out when building `bridge_job_skills`.

---

### `dim_certifications`

AI-extracted from job description `description` field. One row per unique certification name.

| Column | Type | Notes |
|---|---|---|
| `cert_id` | INT | Surrogate key |
| `display_name` | STRING | Full cert name, e.g. "AWS Certified Data Engineer" |
| `slug` | STRING | Normalised slug, e.g. `aws-certified-data-engineer` |
| `provider` | STRING | Issuing body, e.g. "AWS", "Databricks", "Microsoft", "Google", "Snowflake" |
| `_first_seen_date` | DATE | When first extracted |

---

### `dim_companies`

SCD Type 1 — last-seen values win.

| Column | Type | Notes |
|---|---|---|
| `company_id` | STRING | Source `company_object.id` |
| `name` | STRING | |
| `domain` | STRING | |
| `industry` | STRING | From `company_object.industry` — **UI filter dimension** |
| `industry_id` | INT | |
| `employee_count` | INT | |
| `employee_count_range` | STRING | |
| `country` | STRING | HQ country |
| `city` | STRING | HQ city |
| `_updated_at` | TIMESTAMP | Last seen in a batch |

---

### `dim_locations`

Distinct city-level locations from the `locations[]` array on each posting. Retained for data completeness; not exposed as a UI filter in MVP.

| Column | Type | Notes |
|---|---|---|
| `location_id` | INT | Source GeoNames `id` |
| `name` | STRING | City name |
| `display_name` | STRING | Full display |
| `type` | STRING | `city`, `region` |
| `state` | STRING | |
| `state_code` | STRING | |
| `country_name` | STRING | |
| `country_code` | STRING | ISO-2 |
| `continent_code` | STRING | 2-letter, e.g. `NA` |
| `continent_name` | STRING | "North America" |
| `latitude` | DOUBLE | |
| `longitude` | DOUBLE | |

---

### `fact_job_postings`

One row per unique job posting. SCD Type 1 on `job_id`.

| Column | Type | Notes |
|---|---|---|
| `job_id` | BIGINT | Source `id` — natural key |
| `role_id` | INT | FK → `dim_roles` |
| `company_id` | STRING | FK → `dim_companies` |
| `primary_location_id` | INT | FK → `dim_locations` |
| `job_title` | STRING | |
| `normalized_title` | STRING | |
| `seniority` | STRING | |
| `date_posted` | DATE | **Partition column** |
| `date_reposted` | DATE | |
| `closed_at` | TIMESTAMP | NULL = open |
| `is_open` | BOOLEAN | Derived: `closed_at IS NULL` |
| `remote` | BOOLEAN | |
| `hybrid` | BOOLEAN | |
| `employment_status` | STRING | First value of `employment_statuses[]` |
| `min_salary_usd` | INT | |
| `max_salary_usd` | INT | |
| `avg_salary_usd` | INT | Used for P50 in gold |
| `salary_currency` | STRING | |
| `_first_seen_date` | DATE | |
| `_last_updated_date` | DATE | |

**Partition by:** `date_posted` (year/month)
**Z-ORDER BY:** `(role_id, date_posted)` — optimises the `/api/jobs` drill-down query

---

### `bridge_job_skills`

One row per (job, skill). Deduped across `keyword_slugs` and `technology_slugs`.

| Column | Type | Notes |
|---|---|---|
| `job_id` | BIGINT | FK → `fact_job_postings` |
| `skill_id` | INT | FK → `dim_skills` |
| `sources` | ARRAY<STRING> | `["keyword", "technology"]` |
| `date_posted` | DATE | Denormalised for partition pruning |

**Partition by:** `date_posted`
**Z-ORDER BY:** `(skill_id, date_posted)` — optimises the `/api/jobs` drill-down query

---

### `bridge_job_certifications`

One row per (job, certification). AI-extracted from job `description`.

| Column | Type | Notes |
|---|---|---|
| `job_id` | BIGINT | FK → `fact_job_postings` |
| `cert_id` | INT | FK → `dim_certifications` |
| `date_posted` | DATE | Denormalised for partition pruning |

**Partition by:** `date_posted`

---

### `bridge_job_locations`

One row per (job, location). Exploded from `locations[]`.

| Column | Type | Notes |
|---|---|---|
| `job_id` | BIGINT | FK → `fact_job_postings` |
| `location_id` | INT | FK → `dim_locations` |
| `date_posted` | DATE | Denormalised for partition pruning |

**Partition by:** `date_posted`

---

## GOLD — `skilliq.gold`

### `fact_skill_daily`

Daily grain. Drives the skills ranked list + trend badges.

| Column | Type | Notes |
|---|---|---|
| `role_slug` | STRING | |
| `skill_slug` | STRING | |
| `skill_display_name` | STRING | Denormalised |
| `skill_category` | STRING | Denormalised |
| `date_posted` | DATE | **Partition column** |
| `industry` | STRING | **UI filter dimension** |
| `posting_count` | BIGINT | Jobs for this role+skill on this date |
| `total_role_postings` | BIGINT | Total jobs for this role on this date (denominator) |

**Partition by:** `date_posted`

---

### `fact_certification_daily`

Daily grain. Drives the Top Certifications panel + demand badges.

| Column | Type | Notes |
|---|---|---|
| `role_slug` | STRING | |
| `cert_slug` | STRING | |
| `cert_display_name` | STRING | Denormalised |
| `cert_provider` | STRING | Denormalised |
| `date_posted` | DATE | **Partition column** |
| `industry` | STRING | **UI filter dimension** |
| `posting_count` | BIGINT | Jobs for this role+cert on this date |
| `total_role_postings` | BIGINT | Total jobs for this role on this date (denominator) |

**Partition by:** `date_posted`

**Demand badge at query time:**
```
occurrence_pct >= 15%  → 'High'
occurrence_pct 5–14%   → 'Medium'
occurrence_pct < 5%    → 'Low'
```

---

### `fact_role_daily`

Daily grain. Drives the 4 KPI cards and the Hiring Trend line chart.

| Column | Type | Notes |
|---|---|---|
| `role_slug` | STRING | |
| `date_posted` | DATE | **Partition column** |
| `industry` | STRING | **UI filter dimension** |
| `job_postings_count` | BIGINT | Total postings |
| `open_roles_count` | BIGINT | Where `is_open = TRUE` |
| `salary_usd_p25` | DOUBLE | |
| `salary_usd_p50` | DOUBLE | Median — shown in UI |
| `salary_usd_p75` | DOUBLE | |

**Partition by:** `date_posted`

**KPI delta (period-over-period) at query time:**
Compare the current window (`date_range`) to the immediately preceding window of equal length.
```
date_range=90d  → current: [today-90, today]   prior: [today-180, today-91]
date_range=all  → no prior period; delta fields return null
```

**Hiring Trend label + signal at query time (4th KPI card):**
```
hiring_trend_label  = percentile of open_roles_count vs all roles in same window
                      top 33%    → 'High'
                      mid 33%    → 'Medium'
                      bottom 33% → 'Low'

hiring_trend_signal = period-over-period % change in job_postings_count
                      > +10%  → 'Strong'
                      0–10%   → 'Moderate'
                      < 0%    → 'Weak'
```

---

## Refresh strategy

```
Databricks Lakeflow Jobs (weekly)
  Task 1: pull_api          → fetch from TheirStack API → land JSON in ADLS Gen2
  Task 2: ingest_bronze     → parse JSON → append to bronze.raw_job_postings
  Task 3: run_agent         → Databricks AI agent (Agent Bricks) processes each new posting:
                                 (a) role classification  → role_slug per job
                                 (b) skill extraction     → normalised skill list per job
                                 (c) cert extraction      → certification list per job
                              Agent output written to a staging table; traced via MLflow
  Task 4: build_silver_dims → MERGE dim_companies, dim_locations, dim_skills, dim_certifications
  Task 5: build_silver_facts→ MERGE fact_job_postings (including agent role_slug), bridges
  Task 6: build_gold        → overwrite affected date partitions in all 4 gold tables
  Task 7: validate          → row count + null rate + agent confidence checks;
                              fail workflow if classification confidence falls below threshold
```

# Data Schema — Skill IQ

> **Status: FINAL** — based on source API payload confirmed by user.

---

## Source API — raw payload fields

### Top-level job posting object

| Field | Type | Nullable | Notes |
|---|---|---|---|
| `id` | int | No | Unique job posting identifier |
| `job_title` | string | No | Free-text title, e.g. "Senior Data Engineer" |
| `normalized_title` | string | Yes | API-normalised title (may be sparse) |
| `seniority` | string | Yes | `c_level`, `manager`, `senior`, `mid`, `junior` |
| `description` | string | Yes | Full markdown job description |
| `date_posted` | date | No | When the posting went live `YYYY-MM-DD` |
| `date_reposted` | date | Yes | Repost date if applicable |
| `discovered_at` | timestamp | No | When the API ingested it |
| `closed_at` | timestamp | Yes | NULL = still open |
| `reposted` | bool | No | |
| `easy_apply` | bool | No | |
| `remote` | bool | No | |
| `hybrid` | bool | No | |
| `employment_statuses` | string[] | No | e.g. `["full_time"]` |
| `source_url` | string | Yes | Original posting URL |
| `final_url` | string | Yes | Canonical URL |
| `url` | string | Yes | |
| `keyword_slugs` | string[] | No | **Primary skill signal** — tech/tool slugs |
| `technology_slugs` | string[] | No | **Primary skill signal** — overlaps keyword_slugs |
| `company` | string | Yes | Company name (denormalised) |
| `company_domain` | string | Yes | |
| `location` | string | Yes | Primary location string |
| `long_location` | string | Yes | Full location string |
| `short_location` | string | Yes | Short city, state |
| `latitude` | float | Yes | |
| `longitude` | float | Yes | |
| `country` | string | Yes | Primary country name |
| `country_code` | string | Yes | ISO-2, e.g. "US" |
| `state_code` | string | Yes | |
| `postal_code` | string | Yes | |
| `cities` | string[] | Yes | All cities for this posting |
| `countries` | string[] | Yes | All countries |
| `country_codes` | string[] | Yes | All country codes |
| `continents` | string[] | Yes | e.g. `["North America", "Europe"]` |
| `min_annual_salary` | int | Yes | In local currency |
| `max_annual_salary` | int | Yes | In local currency |
| `min_annual_salary_usd` | int | Yes | Normalised to USD |
| `max_annual_salary_usd` | int | Yes | Normalised to USD |
| `avg_annual_salary_usd` | int | Yes | Normalised to USD |
| `salary_currency` | string | Yes | e.g. "USD" |
| `salary_string` | string | Yes | Human-readable, e.g. "$100K–$120K" |
| `manager_roles` | string[] | Yes | |
| `matching_phrases` | string[] | Yes | |
| `matching_words` | string[] | Yes | |
| `hiring_team` | object[] | Yes | See below |

### `hiring_team[]` object

| Field | Type |
|---|---|
| `first_name` | string |
| `full_name` | string |
| `image_url` | string |
| `linkedin_url` | string |
| `role` | string |

### `company_object` (nested)

| Field | Type | Notes |
|---|---|---|
| `id` | string | Company identifier |
| `name` | string | |
| `domain` | string | |
| `industry` | string | **Filter dimension** — e.g. "internet" |
| `industry_id` | int | |
| `country` | string | |
| `city` | string | HQ city |
| `employee_count` | int | |
| `employee_count_range` | string | e.g. "1001-5000" |
| `founded_year` | int | |
| `is_recruiting_agency` | bool | Flag to exclude agency postings |
| `num_jobs` | int | Total jobs at company |
| `num_jobs_last_30_days` | int | |
| `technology_names` | string[] | Tech stack |
| `technology_slugs` | string[] | |
| `keyword_slugs` | string[] | |
| `alexa_ranking` | int | |
| `annual_revenue_usd` | int | |
| `publicly_traded_symbol` | string | |
| `publicly_traded_exchange` | string | |
| `funding_stage` | string | |
| `total_funding_usd` | int | |
| `linkedin_url` | string | |
| `logo` | string | Logo URL |

### `locations[]` object (detailed, multi-value)

| Field | Type | Notes |
|---|---|---|
| `id` | int | GeoNames ID |
| `name` | string | City name |
| `display_name` | string | Full display, e.g. "Live Oak, California, United States" |
| `type` | string | `city`, `region`, etc. |
| `country_code` | string | ISO-2 |
| `country_name` | string | |
| `state` | string | |
| `state_code` | string | |
| `continent` | string | 2-letter code, e.g. "NA" |
| `latitude` | float | |
| `longitude` | float | |

### `metadata` (response envelope)

| Field | Type | Notes |
|---|---|---|
| `total_results` | int | Total postings matching the API query |
| `total_companies` | int | |
| `truncated_results` | int | |
| `truncated_companies` | int | |

---

## AI agent — extraction and classification

All three extraction tasks are handled by a single **Databricks AI agent** (built with Agent Bricks, powered by Claude). The agent processes each new job posting in one pass and returns a structured output covering skills, certifications, and role classification.

### Why an agent, not a direct model call

- **Tracing**: Every agent invocation is traced end-to-end via MLflow — inputs, outputs, token counts, and latency are recorded per posting, making debugging and auditing straightforward.
- **Evaluation**: Agent outputs can be assessed against a labelled evaluation set to measure extraction precision/recall and classification accuracy. Quality can be tracked over time and across agent versions.
- **Guardrails**: The agent can express low-confidence classifications (e.g. returning `other` with a reason) rather than hallucinating a role slug.
- **Versioning**: Agent versions are deployed independently, allowing quality improvements without touching the pipeline code.

### Agent inputs (per posting)

```
job_title         string   — primary classification signal
normalized_title  string   — API-provided normalisation (may be sparse)
description       string   — full job description (truncated to token budget)
keyword_slugs     string[] — structured skill signals from source API
technology_slugs  string[] — structured technology signals from source API
```

### Agent output (structured, typed)

```json
{
  "role_slug":       "data_engineer",   // one of 5 target slugs, or "other"
  "skills":          ["python", "dbt", "apache-spark"],
  "certifications":  ["aws-certified-data-engineer"],
  "confidence":      0.92               // agent self-reported confidence for classification
}
```

### Task 1 — Role classification

The agent reads `job_title`, `normalized_title`, and `description` and maps the posting to one of five target roles:

| role_slug | Examples the agent should recognise |
|---|---|
| `data_engineer` | Data Engineer, Data Platform Engineer, ETL Developer, Analytics Engineer (pipeline-focused) |
| `data_scientist` | Data Scientist, Applied Scientist, Research Scientist |
| `ml_engineer` | ML Engineer, Machine Learning Engineer, MLOps Engineer, AI Engineer |
| `data_analyst` | Data Analyst, BI Analyst, Business Analyst, Analytics Engineer (reporting-focused) |
| `software_engineer` | Software Engineer, Backend Engineer, Full-Stack Developer |

If the agent cannot confidently assign a role → `role_slug = 'other'` (excluded from the app).
The agent has access to `dim_roles` as a reference table so its definitions stay aligned with the app.

### Task 2 — Skill extraction

The agent unions `keyword_slugs` + `technology_slugs` and supplements with skills parsed from `description`. It deduplicates and normalises slugs (e.g. `postgres` → `postgresql`) and filters out non-technical terms (marketing, sales, business buzzwords).

### Task 3 — Certification extraction

The agent scans `description` for certification names and maps them to normalised provider + display name pairs. Source API fields do not contain certification data — description is the only input.

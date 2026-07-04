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

## Skill extraction rules

Skills are extracted from **two structured arrays per posting**. NLP on `description` is out of scope for MVP.

```
job.skills = UNION(keyword_slugs, technology_slugs)
             DEDUPLICATED per job
             FILTERED through dim_skills (exclude non-tech slugs)
```

Slugs like `lead-generation`, `seo`, `social-media` are marketing terms — excluded via `dim_skills.category = 'excluded'`.

---

## Role classification

`job_title` → `role_slug` mapping (applied in Silver transformation):

| role_slug | Match keywords (case-insensitive, in job_title) |
|---|---|
| `data_engineer` | data engineer, data platform engineer, data infrastructure, etl developer |
| `data_scientist` | data scientist, data science, applied scientist |
| `ml_engineer` | machine learning engineer, ml engineer, ai engineer, mlops engineer, applied ml |
| `data_analyst` | data analyst, analytics engineer, business analyst, bi analyst |
| `software_engineer` | software engineer, software developer, backend engineer, fullstack, full-stack |

Postings that match no rule → `role_slug = 'other'` (excluded from app).
Postings matching multiple rules → first match wins (order above is priority order).

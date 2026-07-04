# API Contract — Skill IQ

> Next.js API routes → Databricks SQL Warehouse via `@databricks/sql` connector.

---

## Base URL
`/api` (relative — same origin as the Next.js app)

## Date range reference

The `date_range` param is an enum shared across all endpoints:

| Value | Window | Prior period (for delta) |
|---|---|---|
| `30d` | Last 30 days | Days 31–60 ago |
| `60d` | Last 60 days | Days 61–120 ago |
| `90d` | Last 90 days (default) | Days 91–180 ago |
| `6m` | Last 180 days | Days 181–360 ago |
| `1y` | Last 365 days | Days 366–730 ago |
| `2y` | Last 730 days | Days 731–1460 ago |
| `all` | All available data | No prior period (delta = null) |

---

## Endpoints

### 1. `GET /api/filters`

Populates all dropdowns on page load. Called once; cached 24h.

#### Query parameters
None.

#### SQL executed

```sql
-- Industries
SELECT DISTINCT industry
FROM skilliq.gold.fact_skill_daily
WHERE industry IS NOT NULL
ORDER BY industry;
```

#### Response body

```jsonc
{
  "roles": [
    { "value": "data_engineer",     "label": "Data Engineer" },
    { "value": "data_scientist",    "label": "Data Scientist" },
    { "value": "ml_engineer",       "label": "ML Engineer" },
    { "value": "data_analyst",      "label": "Data Analyst" },
    { "value": "software_engineer", "label": "Software Engineer" }
  ],
  "date_ranges": [
    { "value": "30d",  "label": "Last 30 Days" },
    { "value": "60d",  "label": "Last 60 Days" },
    { "value": "90d",  "label": "Last 90 Days" },
    { "value": "6m",   "label": "Last 6 Months" },
    { "value": "1y",   "label": "Last Year" },
    { "value": "2y",   "label": "Last 2 Years" },
    { "value": "all",  "label": "All Time" }
  ],
  "industries": [
    { "value": "all",      "label": "All Industries" },
    { "value": "internet", "label": "Internet" },
    { "value": "finance",  "label": "Finance" }
    // ...alphabetical
  ]
}
```

---

### 2. `GET /api/skills`

Returns ranked skills + all 4 KPI cards for the selected role and filters. Called on every **Analyze** click.

#### Query parameters

| Param | Type | Required | Default | Values |
|---|---|---|---|---|
| `role` | string | Yes | — | `data_engineer` \| `data_scientist` \| `ml_engineer` \| `data_analyst` \| `software_engineer` |
| `date_range` | string | No | `90d` | See date range reference above |
| `industry` | string | No | `all` | Industry slug or `all` |
| `sort` | string | No | `occurrence` | `occurrence` \| `trending` |
| `limit` | int | No | `20` | 1–50 |

#### Date window SQL helper

```sql
-- Resolved in the API layer before binding
current_start  = CURRENT_DATE() - <days for date_range>   -- or '1900-01-01' for 'all'
prior_start    = CURRENT_DATE() - <days * 2>
prior_end      = current_start - 1                        -- null for 'all'
```

#### SQL — skills ranked list

```sql
WITH skill_agg AS (
  SELECT
    skill_slug,
    skill_display_name,
    SUM(posting_count)       AS skill_postings,
    SUM(total_role_postings) AS role_postings
  FROM skilliq.gold.fact_skill_daily
  WHERE role_slug    = :role
    AND date_posted >= :current_start
    AND (:industry = 'all' OR industry = :industry)
  GROUP BY skill_slug, skill_display_name
),
trend_halves AS (
  SELECT
    skill_slug,
    SUM(CASE WHEN date_posted < :midpoint THEN posting_count       ELSE 0 END) AS old_count,
    SUM(CASE WHEN date_posted < :midpoint THEN total_role_postings ELSE 0 END) AS old_total,
    SUM(CASE WHEN date_posted >= :midpoint THEN posting_count      ELSE 0 END) AS new_count,
    SUM(CASE WHEN date_posted >= :midpoint THEN total_role_postings ELSE 0 END) AS new_total
  FROM skilliq.gold.fact_skill_daily
  WHERE role_slug    = :role
    AND date_posted >= :current_start
    AND (:industry = 'all' OR industry = :industry)
  GROUP BY skill_slug
)
SELECT
  a.skill_slug,
  a.skill_display_name,
  ROUND(a.skill_postings * 100.0 / NULLIF(a.role_postings, 0), 1) AS occurrence_pct,
  ROUND(
    (t.new_count * 100.0 / NULLIF(t.new_total, 0)) -
    (t.old_count * 100.0 / NULLIF(t.old_total, 0)), 1)            AS trend_delta_pp,
  CASE
    WHEN (t.new_count * 100.0 / NULLIF(t.new_total, 0)) -
         (t.old_count * 100.0 / NULLIF(t.old_total, 0)) >  5 THEN 'trending'
    WHEN (t.new_count * 100.0 / NULLIF(t.new_total, 0)) -
         (t.old_count * 100.0 / NULLIF(t.old_total, 0)) < -5 THEN 'declining'
    ELSE 'stable'
  END                                                              AS trend
FROM skill_agg a
JOIN trend_halves t ON a.skill_slug = t.skill_slug
ORDER BY
  CASE WHEN :sort = 'trending' THEN trend_delta_pp END DESC,
  occurrence_pct DESC
LIMIT :limit
```

#### SQL — KPI cards (runs alongside skills query)

```sql
WITH current_window AS (
  SELECT
    SUM(job_postings_count) AS job_postings,
    SUM(open_roles_count)   AS open_roles,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_usd_p50) AS median_salary
  FROM skilliq.gold.fact_role_daily
  WHERE role_slug    = :role
    AND date_posted >= :current_start
    AND (:industry = 'all' OR industry = :industry)
),
prior_window AS (
  SELECT
    SUM(job_postings_count) AS job_postings,
    SUM(open_roles_count)   AS open_roles,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_usd_p50) AS median_salary
  FROM skilliq.gold.fact_role_daily
  WHERE role_slug   = :role
    AND date_posted BETWEEN :prior_start AND :prior_end   -- NULL for 'all'
    AND (:industry = 'all' OR industry = :industry)
),
all_roles_current AS (
  -- For hiring trend label: rank this role's open_roles vs all roles
  SELECT
    role_slug,
    SUM(open_roles_count) AS open_roles,
    PERCENT_RANK() OVER (ORDER BY SUM(open_roles_count)) AS pct_rank
  FROM skilliq.gold.fact_role_daily
  WHERE date_posted >= :current_start
    AND (:industry = 'all' OR industry = :industry)
  GROUP BY role_slug
)
SELECT
  c.job_postings,
  c.open_roles,
  ROUND(c.median_salary)                                                AS median_salary_usd,
  ROUND((c.job_postings - p.job_postings) * 100.0 / NULLIF(p.job_postings, 0), 1) AS postings_delta_pct,
  ROUND((c.open_roles   - p.open_roles)   * 100.0 / NULLIF(p.open_roles,   0), 1) AS open_roles_delta_pct,
  ROUND((c.median_salary - p.median_salary) * 100.0 / NULLIF(p.median_salary, 0), 1) AS salary_delta_pct,
  CASE
    WHEN ar.pct_rank >= 0.67 THEN 'High'
    WHEN ar.pct_rank >= 0.33 THEN 'Medium'
    ELSE 'Low'
  END AS hiring_trend_label,
  CASE
    WHEN (c.job_postings - p.job_postings) * 100.0 / NULLIF(p.job_postings, 0) > 10 THEN 'Strong'
    WHEN (c.job_postings - p.job_postings) * 100.0 / NULLIF(p.job_postings, 0) >= 0  THEN 'Moderate'
    ELSE 'Weak'
  END AS hiring_trend_signal
FROM current_window c
LEFT JOIN prior_window p ON 1=1
LEFT JOIN all_roles_current ar ON ar.role_slug = :role
```

#### Response body

```jsonc
{
  "role": "data_engineer",
  "filters": { "date_range": "90d", "industry": "all" },
  "metrics": {
    "job_postings":        { "value": 4210,   "delta_pct": 12.0 },
    "open_roles":          { "value": 387,    "delta_pct": 8.0  },
    "median_salary_usd":   { "value": 112000, "delta_pct": 6.0  },
    "hiring_trend": {
      "label":  "High",    // "High" | "Medium" | "Low"
      "signal": "Strong"   // "Strong" | "Moderate" | "Weak"
    }
  },
  "skills": [
    {
      "rank": 1,
      "slug": "python",
      "name": "Python",
      "occurrence_pct": 89.2,
      "trend": "trending",
      "trend_delta_pp": 7.3
    }
  ],
  "meta": {
    "generated_at": "2026-07-04T12:00:00Z",
    "window_start": "2026-04-05",
    "window_end":   "2026-07-04",
    "window_midpoint": "2026-05-20"
  }
}
```

#### Error responses

| Status | Condition |
|---|---|
| `400` | Invalid `role`, invalid `date_range`, invalid `industry` |
| `500` | Databricks query failure |

---

### 3. `GET /api/certifications`

Returns ranked certifications with demand badges for the selected role and filters. Drives the Top Certifications panel.

#### Query parameters

| Param | Type | Required | Default |
|---|---|---|---|
| `role` | string | Yes | — |
| `date_range` | string | No | `90d` |
| `industry` | string | No | `all` |
| `limit` | int | No | `5` |

#### SQL executed

```sql
WITH cert_agg AS (
  SELECT
    cert_slug,
    cert_display_name,
    cert_provider,
    SUM(posting_count)       AS cert_postings,
    SUM(total_role_postings) AS role_postings,
    ROUND(SUM(posting_count) * 100.0 / NULLIF(SUM(total_role_postings), 0), 1) AS occurrence_pct
  FROM skilliq.gold.fact_certification_daily
  WHERE role_slug    = :role
    AND date_posted >= :current_start
    AND (:industry = 'all' OR industry = :industry)
  GROUP BY cert_slug, cert_display_name, cert_provider
)
SELECT
  cert_slug,
  cert_display_name,
  cert_provider,
  occurrence_pct,
  CASE
    WHEN occurrence_pct >= 15 THEN 'High'
    WHEN occurrence_pct >=  5 THEN 'Medium'
    ELSE 'Low'
  END AS demand_badge
FROM cert_agg
ORDER BY occurrence_pct DESC
LIMIT :limit
```

#### Response body

```jsonc
{
  "role": "data_engineer",
  "filters": { "date_range": "90d", "industry": "all" },
  "certifications": [
    {
      "rank": 1,
      "slug": "aws-certified-data-engineer",
      "name": "AWS Certified Data Engineer",
      "provider": "AWS",
      "occurrence_pct": 22.4,
      "demand_badge": "High"   // "High" | "Medium" | "Low"
    },
    {
      "rank": 2,
      "slug": "databricks-certified-data-engineer",
      "name": "Databricks Certified Data Engineer",
      "provider": "Databricks",
      "occurrence_pct": 18.1,
      "demand_badge": "High"
    }
  ]
}
```

---

### 4. `GET /api/hiring-trend`

Returns the time-series data for the Hiring Trend line chart.

#### Query parameters

| Param | Type | Required | Default | Notes |
|---|---|---|---|---|
| `role` | string | Yes | — | |
| `date_range` | string | No | `90d` | |
| `industry` | string | No | `all` | |
| `granularity` | string | No | `daily` | `daily` \| `weekly` \| `monthly` |

#### SQL executed

```sql
SELECT
  CASE :granularity
    WHEN 'weekly'  THEN DATE_TRUNC('week',  date_posted)
    WHEN 'monthly' THEN DATE_TRUNC('month', date_posted)
    ELSE                date_posted
  END                              AS period,
  SUM(job_postings_count)          AS postings_count,
  SUM(open_roles_count)            AS open_roles_count
FROM skilliq.gold.fact_role_daily
WHERE role_slug    = :role
  AND date_posted >= :current_start
  AND (:industry = 'all' OR industry = :industry)
GROUP BY 1
ORDER BY 1
```

#### Response body

```jsonc
{
  "role": "data_engineer",
  "filters": { "date_range": "90d", "industry": "all", "granularity": "daily" },
  "series": [
    { "date": "2026-04-05", "postings_count": 42,  "open_roles_count": 38 },
    { "date": "2026-04-06", "postings_count": 55,  "open_roles_count": 51 },
    { "date": "2026-07-04", "postings_count": 287, "open_roles_count": 261 }
  ]
}
```

---

## Databricks connection

```
DATABRICKS_HOST=<workspace-url>
DATABRICKS_TOKEN=<personal-access-token>
DATABRICKS_HTTP_PATH=<sql-warehouse-http-path>
```

All query parameters are **named bindings** (never string-interpolated).

---

## Caching strategy

| Endpoint | Cache TTL | Cache key |
|---|---|---|
| `GET /api/filters` | 24h (CDN) | static |
| `GET /api/skills` | 5 min (server) | `role:date_range:industry:sort:limit` |
| `GET /api/certifications` | 5 min (server) | `role:date_range:industry:limit` |
| `GET /api/hiring-trend` | 5 min (server) | `role:date_range:industry:granularity` |

# API Contract — Skill IQ

> Next.js API routes → Databricks SQL Warehouse via the Databricks SQL Connector.

---

## Base URL
`/api` (relative — same origin as the Next.js app)

---

## Endpoints

### `GET /api/skills`

Returns ranked skills and KPI metrics for a role + filter combination. This is the primary endpoint the UI calls when the user clicks **Analyze**.

#### Query parameters

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `role` | string | Yes | — | `data_engineer` \| `data_scientist` \| `ml_engineer` \| `data_analyst` \| `software_engineer` |
| `start_date` | ISO date | Yes | — | User-selected start date (e.g. `2024-01-01`). Data window: `[start_date, today]` |
| `location` | string | No | `all` | Country code (`US`, `GB`, …), continent name (`North America`, …), or `all` |
| `industry` | string | No | `all` | Industry slug (e.g. `internet`, `finance`) or `all` |
| `sort` | string | No | `occurrence` | `occurrence` \| `trending` |
| `limit` | int | No | `20` | Max skills returned (1–50) |

#### SQL executed against Gold layer

```sql
-- Step 1: base skill aggregation across the full window
WITH skill_agg AS (
  SELECT
    skill_slug,
    skill_display_name,
    SUM(posting_count)      AS skill_postings,
    SUM(total_role_postings) AS role_postings
  FROM skilliq.gold.fact_skill_daily
  WHERE role_slug     = :role
    AND date_posted  >= :start_date
    AND (:location = 'all' OR country_code = :location OR continent_name = :location)
    AND (:industry = 'all' OR industry = :industry)
  GROUP BY skill_slug, skill_display_name
),

-- Step 2: half-window trend
midpoint AS (
  SELECT DATE_ADD(:start_date, DATEDIFF(CURRENT_DATE(), :start_date) / 2) AS mid
),
trend_halves AS (
  SELECT
    skill_slug,
    SUM(CASE WHEN date_posted < (SELECT mid FROM midpoint) THEN posting_count ELSE 0 END) AS old_count,
    SUM(CASE WHEN date_posted < (SELECT mid FROM midpoint) THEN total_role_postings ELSE 0 END) AS old_total,
    SUM(CASE WHEN date_posted >= (SELECT mid FROM midpoint) THEN posting_count ELSE 0 END) AS new_count,
    SUM(CASE WHEN date_posted >= (SELECT mid FROM midpoint) THEN total_role_postings ELSE 0 END) AS new_total
  FROM skilliq.gold.fact_skill_daily
  WHERE role_slug     = :role
    AND date_posted  >= :start_date
    AND (:location = 'all' OR country_code = :location OR continent_name = :location)
    AND (:industry = 'all' OR industry = :industry)
  GROUP BY skill_slug
)

SELECT
  a.skill_slug,
  a.skill_display_name,
  ROUND(a.skill_postings * 100.0 / NULLIF(a.role_postings, 0), 1)  AS occurrence_pct,
  ROUND(
    (t.new_count * 100.0 / NULLIF(t.new_total, 0)) -
    (t.old_count * 100.0 / NULLIF(t.old_total, 0))
  , 1)                                                               AS trend_delta_pp,
  CASE
    WHEN (t.new_count * 100.0 / NULLIF(t.new_total, 0)) -
         (t.old_count * 100.0 / NULLIF(t.old_total, 0)) >  5 THEN 'trending'
    WHEN (t.new_count * 100.0 / NULLIF(t.new_total, 0)) -
         (t.old_count * 100.0 / NULLIF(t.old_total, 0)) < -5 THEN 'declining'
    ELSE 'stable'
  END                                                                AS trend
FROM skill_agg a
JOIN trend_halves t ON a.skill_slug = t.skill_slug
ORDER BY
  CASE WHEN :sort = 'trending' THEN trend_delta_pp END DESC,
  occurrence_pct DESC
LIMIT :limit
```

#### Response body

```jsonc
{
  "role": "data_engineer",
  "filters": {
    "start_date": "2024-01-01",
    "location": "all",
    "industry": "all"
  },
  "metrics": {
    "job_postings": 4210,        // SUM(job_postings_count) from fact_role_daily
    "open_roles": 387,            // SUM(open_roles_count) from fact_role_daily
    "median_salary_usd": 112000   // weighted P50 from fact_role_daily
  },
  "skills": [
    {
      "rank": 1,
      "slug": "python",
      "name": "Python",
      "occurrence_pct": 89.2,     // % of role postings that mention this skill
      "trend": "trending",         // "trending" | "stable" | "declining"
      "trend_delta_pp": 7.3        // pp change: new half - old half (signed)
    },
    {
      "rank": 2,
      "slug": "sql",
      "name": "SQL",
      "occurrence_pct": 85.0,
      "trend": "stable",
      "trend_delta_pp": 1.1
    }
  ],
  "meta": {
    "generated_at": "2026-07-04T12:00:00Z",
    "window_start": "2024-01-01",
    "window_end": "2026-07-04",
    "window_midpoint": "2025-04-03"
  }
}
```

#### Error responses

| Status | Condition |
|---|---|
| `400` | Missing required param (`role`, `start_date`), invalid `role` value, invalid `start_date` format |
| `500` | Databricks query failure |

---

### `GET /api/filters`

Returns the available filter options to populate the UI dropdowns. Called once on page load.

#### Query parameters
None.

#### SQL executed

```sql
-- Locations
SELECT DISTINCT country_code, continent_name
FROM skilliq.gold.fact_skill_daily
ORDER BY country_code;

-- Industries
SELECT DISTINCT industry
FROM skilliq.gold.fact_skill_daily
WHERE industry IS NOT NULL
ORDER BY industry;

-- Date range
SELECT MIN(date_posted) AS earliest_date
FROM skilliq.gold.fact_skill_daily;
```

#### Response body

```jsonc
{
  "locations": [
    { "value": "all",           "label": "All locations",    "type": "all" },
    { "value": "North America", "label": "North America",    "type": "continent" },
    { "value": "Europe",        "label": "Europe",           "type": "continent" },
    { "value": "US",            "label": "United States",    "type": "country" },
    { "value": "GB",            "label": "United Kingdom",   "type": "country" }
    // ...sorted: continents first, then countries alphabetically
  ],
  "industries": [
    { "value": "all",      "label": "All industries" },
    { "value": "internet", "label": "Internet" },
    { "value": "finance",  "label": "Finance" }
    // ...alphabetical
  ],
  "date_constraints": {
    "earliest_date": "2021-01-01",   // earliest date_posted in gold
    "latest_date":   "2026-07-04"    // today
  }
}
```

---

## Databricks connection

The Next.js API routes connect using the official Databricks SQL Connector for Node.js (`@databricks/sql`).

Environment variables required:
```
DATABRICKS_HOST=<workspace-url>
DATABRICKS_TOKEN=<personal-access-token>
DATABRICKS_HTTP_PATH=<sql-warehouse-http-path>
```

All query parameters are passed as named bindings (never string-interpolated) to prevent SQL injection.

---

## Caching strategy

| Endpoint | Cache | Rationale |
|---|---|---|
| `GET /api/filters` | 24h (CDN + server) | Filter options change only on daily data refresh |
| `GET /api/skills` | 5 min (server-side) | Per unique query param combo; data is daily not real-time |

Cache key for `/api/skills`: `${role}:${start_date}:${location}:${industry}:${sort}:${limit}`

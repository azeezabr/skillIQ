# API Reference — Skill IQ

> Quick reference: request params and response shapes only.
> For SQL, caching, and implementation detail see `api-contract.md`.

---

## `GET /api/filters`

Populates role and industry dropdowns. Re-called on each filter change to cascade options.

### Request

| Param | Type | Required | Description |
|---|---|---|---|
| `role` | string | No | If provided, returns only industries that have postings for this role |
| `industry` | string | No | If provided, returns only roles that have postings in this industry |

### Response

```jsonc
{
  "roles": [
    { "value": "data_engineer",     "label": "Data Engineer" },
    { "value": "data_scientist",    "label": "Data Scientist" },
    { "value": "ml_engineer",       "label": "ML Engineer" },
    { "value": "data_analyst",      "label": "Data Analyst" },
    { "value": "software_engineer", "label": "Software Engineer" }
  ],
  "industries": [
    { "value": "all",      "label": "All Industries" },
    { "value": "finance",  "label": "Finance" },
    { "value": "internet", "label": "Internet" }
    // ...alphabetical, scoped to selected role if role param provided
  ]
}
```

### Cascade behaviour

| State | Call | Effect |
|---|---|---|
| Page load | `GET /api/filters` | All roles + all industries |
| Role selected | `GET /api/filters?role=data_engineer` | All roles + industries that have data engineer postings |
| Industry selected | `GET /api/filters?industry=internet` | Roles that have internet postings + all industries |

---

## `GET /api/skills`

Returns ranked skills list + all 4 KPI cards.

### Request

| Param | Type | Required | Default | Values |
|---|---|---|---|---|
| `role` | string | Yes | — | `data_engineer` \| `data_scientist` \| `ml_engineer` \| `data_analyst` \| `software_engineer` |
| `date_range` | string | No | `90d` | `30d` \| `60d` \| `90d` \| `6m` \| `1y` \| `2y` \| `all` |
| `industry` | string | No | `all` | Industry slug or `all` |
| `sort` | string | No | `occurrence` | `occurrence` \| `trending` |
| `limit` | int | No | `20` | 1–50 |

### Response

```jsonc
{
  "role": "data_engineer",
  "filters": { "date_range": "90d", "industry": "all" },
  "metrics": {
    "job_postings":      { "value": 4210,   "delta_pct": 12.0 },
    "open_roles":        { "value": 387,    "delta_pct": 8.0  },
    "median_salary_usd": { "value": 112000, "delta_pct": 6.0  },
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
      "trend": "trending",      // "trending" | "stable" | "declining"
      "trend_delta_pp": 7.3
    }
  ],
  "meta": {
    "generated_at": "2026-07-05T00:00:00Z",
    "window_start": "2026-04-06",
    "window_end":   "2026-07-05",
    "window_midpoint": "2026-05-21"
  }
}
```

### Errors

| Status | Reason |
|---|---|
| `400` | Missing `role`, invalid `date_range` or `sort` value |
| `500` | Databricks query failure |

---

## `GET /api/certifications`

Returns ranked certifications with demand badges.

### Request

| Param | Type | Required | Default |
|---|---|---|---|
| `role` | string | Yes | — |
| `date_range` | string | No | `90d` |
| `industry` | string | No | `all` |
| `limit` | int | No | `5` |

### Response

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
      "demand_badge": "High"    // "High" | "Medium" | "Low"
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

### Errors

| Status | Reason |
|---|---|
| `400` | Missing `role`, invalid `date_range` |
| `500` | Databricks query failure |

---

## `GET /api/jobs`

Paginated job listings that a skill's stats were derived from. Queries Silver (record-level), not Gold.

### Request

| Param | Type | Required | Default | Notes |
|---|---|---|---|---|
| `role` | string | Yes | — | |
| `skill_slug` | string | Yes | — | e.g. `python` |
| `date_range` | string | No | `90d` | |
| `industry` | string | No | `all` | |
| `page` | int | No | `1` | |
| `page_size` | int | No | `20` | Max 50 |

### Response

```jsonc
{
  "role": "data_engineer",
  "skill": { "slug": "python", "name": "Python" },
  "filters": { "date_range": "90d", "industry": "all" },
  "pagination": {
    "total": 3750,
    "page": 1,
    "page_size": 20,
    "total_pages": 188
  },
  "jobs": [
    {
      "job_id": 1234,
      "title": "Senior Data Engineer",
      "company": "Google",
      "company_domain": "google.com",
      "seniority": "senior",
      "remote": true,
      "hybrid": false,
      "min_salary_usd": 120000,
      "max_salary_usd": 160000,
      "date_posted": "2026-06-15",
      "url": "https://..."
    }
  ]
}
```

### Errors

| Status | Reason |
|---|---|
| `400` | Missing `role` or `skill_slug`, invalid `date_range`, `page_size` > 50 |
| `500` | Databricks query failure |

# Architecture — Skill IQ

## Overview

Dynamic single-page app. Analytics queries run live against a **Databricks SQL Warehouse** backed by pre-aggregated Gold Delta tables. No static JSON files — filters (including user-selected start date) are applied at query time in SQL.

```
┌─────────────────────────────────────────────────────┐
│                   Browser (SPA)                     │
│                                                     │
│  Role tabs → date picker → dropdowns → Analyze btn  │
│       ↓                                             │
│  KPI cards   +   Skills ranked list                 │
└─────────────────────┬───────────────────────────────┘
                      │  GET /api/skills?role=&start_date=&location=&industry=&sort=
                      │  GET /api/filters  (once on load)
                      ▼
┌─────────────────────────────────────────────────────┐
│            Next.js API Routes                       │
│  Parameterised SQL via @databricks/sql connector    │
│  5-min server-side cache per query combo            │
└─────────────────────┬───────────────────────────────┘
                      │  SQL over JDBC/HTTP
                      ▼
┌─────────────────────────────────────────────────────┐
│         Databricks SQL Warehouse                    │
│                                                     │
│  skilliq.gold.fact_skill_daily                      │
│  skilliq.gold.fact_role_daily                       │
└─────────────────────┬───────────────────────────────┘
                      │  daily Workflow
                      ▼
┌─────────────────────────────────────────────────────┐
│         Databricks Medallion Pipeline               │
│                                                     │
│  bronze.raw_job_postings  (append-only, Delta)      │
│       ↓ parse + classify                            │
│  silver.dim_* + silver.fact_* + silver.bridge_*     │
│       ↓ aggregate to daily grain                    │
│  gold.fact_skill_daily + gold.fact_role_daily       │
└─────────────────────┬───────────────────────────────┘
                      │  scheduled API pull
                      ▼
┌─────────────────────────────────────────────────────┐
│              Source API (job postings)              │
└─────────────────────────────────────────────────────┘
```

## Component hierarchy (frontend)

```
Page
├── RoleTabs                        ← 5 role buttons
├── FilterBar
│   ├── DatePicker                  ← start_date (user types/selects a date)
│   ├── LocationDropdown            ← continent or country_code or "all"
│   ├── IndustryDropdown            ← industry slug or "all"
│   └── AnalyzeButton               ← triggers /api/skills fetch
├── MetricCards
│   ├── KPICard  (Job postings)
│   ├── KPICard  (Open roles)
│   └── KPICard  (Median salary)
└── SkillsPanel
    ├── PanelHeader  (title + Occurrence / Trending toggle)
    └── SkillRow × N  (rank, name, bar, %, trend badge)
```

## Data flow — runtime

1. Page loads → `GET /api/filters` → populates dropdowns, sets `earliest_date` constraint on date picker
2. Default state: first role tab, `start_date = 90 days ago`, location = all, industry = all → `GET /api/skills`
3. User changes any filter → clicks **Analyze** → new `GET /api/skills` with updated params
4. API route checks server cache; on miss, queries Databricks SQL Warehouse
5. Response updates KPI cards and skills list in place

## Data flow — pipeline (daily)

```
Databricks Workflow (daily, e.g. 02:00 UTC)
  Task 1: pull_api        → writes to bronze.raw_job_postings (append)
  Task 2: build_silver    → MERGE dims + facts from bronze
  Task 3: build_gold      → overwrite affected date partitions in gold tables
  Task 4: validate        → row count + null checks; fail workflow if thresholds missed
```

## Key decisions (confirmed)

| Decision | Choice | Reason |
|---|---|---|
| Pipeline | Databricks (Delta Lake, PySpark) | User requirement |
| Serving | Databricks SQL Warehouse | Avoids exporting data; filter-at-query-time |
| Date filter | User-supplied `start_date`, dynamic SQL | Replaces static date-range dropdown |
| Skill extraction | `keyword_slugs` ∪ `technology_slugs` (structured) | No NLP on description for MVP |
| Role classification | Keyword match on `job_title` (priority list) | `normalized_title` is sparse in source API |
| Caching | 5-min server-side cache on API route | Gold data is daily; no real-time requirement |
| Auth | None (public read-only app) | MVP constraint |

## Open decisions

- [ ] Deployment target for Next.js (Vercel recommended — edge caching + env var secrets)
- [ ] Databricks workspace region (should co-locate with API server for latency)
- [ ] `dim_skills` seed data — who maintains the slug → display name mapping?
- [ ] Recruiting agency exclusion — default on or off?

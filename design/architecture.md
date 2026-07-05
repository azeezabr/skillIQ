# Architecture — Skill IQ

## Overview

Dynamic single-page app. Analytics queries run live against a **Databricks SQL Warehouse** backed by pre-aggregated Gold Delta tables. No static JSON files — filters are applied at query time in SQL.

```
┌─────────────────────────────────────────────────────┐
│                   Browser (SPA)                     │
│                                                     │
│  Role dropdown → date range → industry → Analyze   │
│       ↓                                             │
│  4 KPI cards + Skills list + Certifications panel   │
└─────────────────────┬───────────────────────────────┘
                      │  GET /api/filters        (on load + each filter change for cascade)
                      │  GET /api/skills          role, date_range, industry
                      │  GET /api/certifications  role, date_range, industry
                      ▼
┌─────────────────────────────────────────────────────┐
│            Next.js API Routes                       │
│  Parameterised SQL via @databricks/sql connector    │
│  5-min server-side cache per query combo            │
└─────────────────────┬───────────────────────────────┘
                      │  SQL over HTTP
                      ▼
┌─────────────────────────────────────────────────────┐
│         Databricks SQL Warehouse                    │
│                                                     │
│  skilliq.gold.fact_skill_daily                      │
│  skilliq.gold.fact_certification_daily              │
│  skilliq.gold.fact_role_daily                       │
└─────────────────────┬───────────────────────────────┘
                      │  daily Workflow (6 tasks)
                      ▼
┌─────────────────────────────────────────────────────┐
│         Databricks Medallion Pipeline               │
│                                                     │
│  bronze.raw_job_postings  (append-only, Delta)      │
│       ↓ parse + classify + AI cert extraction       │
│  silver.dim_* + silver.fact_* + silver.bridge_*     │
│       ↓ aggregate to daily grain                    │
│  gold.fact_skill_daily                              │
│  gold.fact_certification_daily                      │
│  gold.fact_role_daily                               │
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
├── FilterBar
│   ├── RoleDropdown                ← options from /api/filters; cascades industry list
│   ├── DateRangeDropdown           ← hardcoded: 30d | 60d | 90d | 6m | 1y | 2y | all
│   ├── IndustryDropdown            ← options from /api/filters?role=; scoped to role
│   └── AnalyzeButton
├── MetricCards
│   ├── KPICard  (Job postings  + delta %)
│   ├── KPICard  (Open roles    + delta %)
│   ├── KPICard  (Median salary + delta %)
│   └── KPICard  (Hiring Trend  — label + signal badge)
├── SkillsPanel                     ← left column
│   ├── PanelHeader  (title + Occurrence / Trending toggle)
│   └── SkillRow × N  (rank, name, bar, %, trend badge; click → /api/jobs drill-down)
└── CertificationsPanel             ← right column
    ├── PanelHeader  (title + View all link)
    └── CertRow × 5  (rank, name, bar, demand badge)
```

## Data flow — runtime

1. Page loads → `GET /api/filters` (no params) → populates role + industry dropdowns; date range is hardcoded in UI
2. User changes role → `GET /api/filters?role=data_engineer` → re-scopes industry dropdown to industries with DE postings
3. User changes industry → `GET /api/filters?industry=internet` → re-scopes role dropdown to roles with internet postings
4. User clicks **Analyze** → `GET /api/skills` + `GET /api/certifications` fired in parallel
5. API routes check server cache; on miss, query Databricks SQL Warehouse
6. Response updates KPI cards, skills list, and certifications panel in place
7. User clicks a skill row → `GET /api/jobs?role=&skill_slug=&...` → opens job listing drawer/modal

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
| Date filter | Preset dropdown — 30d / 60d / 90d / 6m / 1y / 2y / all | Confirmed by revised mockup |
| Location filter | Not exposed in UI (data retained in model for future) | Not in revised mockup |
| Skill extraction | AI from `keyword_slugs` + `technology_slugs` | No manual seed required |
| Cert extraction | AI from job `description` field | Only source of structured cert data |
| Role | Dropdown (not tabs) | Confirmed by revised mockup |
| Parallel API calls | Skills + Certs fired together on Analyze | Reduces perceived latency |
| KPI delta | Period-over-period vs equal prior window | Matches "+12% vs previous 90 days" in mockup |
| Auth | None — public read-only | MVP constraint |

## Open decisions

- [ ] Deployment target for Next.js (Vercel recommended — edge caching + env var secrets)
- [ ] Databricks workspace region (co-locate with API server for latency)
- [ ] AI model / prompt for certification extraction from `description`

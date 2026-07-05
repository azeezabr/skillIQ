# Skill IQ — Solution Overview

**Document type:** Developer briefing — read this before any other document in this solution pack.

---

## What we are building

Skill IQ is a market intelligence web application that surfaces in-demand skills, certifications, and hiring signals derived from real job postings. A user selects a job role and a date range, and the app returns a ranked list of the skills and certifications that appear most frequently in adverts for that role — along with trend signals (Trending / Stable / Declining), KPI summary cards, and a drilldown to the actual job postings behind each stat.

The MVP is a single public page. No login is required.

---

## Who uses it

Job seekers and professionals who want to know which skills and certifications are genuinely in demand for a specific data role, based on aggregate evidence from job postings rather than opinion.

---

## System architecture

The system has four stages:

```
TheirStack API  →  ADLS Gen2  →  Databricks (Bronze / Silver / Gold)  →  FastAPI  →  Frontend
   (source)         (landing)         (processing)                       (serving)    (Azure App Service)
```

**Source:** Job posting data is pulled from the TheirStack API (`/v1/jobs/search`) on a **weekly** schedule and landed as raw JSON files in **Azure Data Lake Storage Gen2**.

**Processing:** A **Databricks** platform processes the raw data through a three-layer medallion architecture managed in **Unity Catalog**, orchestrated by **Lakeflow Jobs**. An **Agent Bricks** agent (powered by Claude) handles AI extraction of skills and certifications from job descriptions.

**Serving:** A **FastAPI** application running on **Azure Container App** exposes four REST endpoints that query the Databricks Gold layer directly via Databricks SQL Warehouse.

**Frontend:** A web app hosted on **Azure App Service** calls the FastAPI endpoints and renders the Market Intelligence dashboard.

**Developer tooling:** GitHub for source control, Databricks Asset Bundles for pipeline deployment.

---

## Data model — 14 tables across 3 layers

### Bronze (1 table)
| Table | Description |
|---|---|
| `raw_job_postings` | Raw JSON from TheirStack API. 86 fields. Append-only, partitioned and clustered by posting date. Never mutated. |

### Silver (9 tables)
Cleaned, normalised, and relationally structured. Populated weekly by Lakeflow Jobs.

| Table | Description |
|---|---|
| `roles` | 5 target roles — Data Engineer, Data Scientist, ML Engineer, Data Analyst, Software Engineer |
| `skills` | AI-extracted skills, categorised as technology / platform / methodology |
| `certifications` | AI-extracted certification names and providers |
| `companies` | Company dimension — SCD Type 1 (last-seen wins) |
| `locations` | City-level geography with country and continent codes |
| `job_postings` | One row per unique job posting. Core fact table. |
| `bridge_job_skills` | Many-to-many: job ↔ skill |
| `bridge_job_certifications` | Many-to-many: job ↔ certification |
| `bridge_job_locations` | Many-to-many: job ↔ location |

### Gold (4 tables)
Pre-aggregated to daily grain. These are the only tables the API queries for analytics.

| Table | Description |
|---|---|
| `skill_daily` | Skill occurrence counts per role, industry, and posting date. Drives the ranked skills list and trend badges. |
| `cert_daily` | Certification occurrence counts per role, industry, and posting date. Drives the Top Certifications panel. |
| `role_daily` | Job posting counts, open role counts, and salary stats per role per day. Drives the 4 KPI cards. |
| `job_posting_lines` | Flattened job records for drill-down. Queried when a user clicks a skill or certification to see source postings. |

---

## API — 4 endpoints

All endpoints are served by FastAPI on Azure Container App. All query parameters are bound (never string-interpolated).

| Endpoint | Purpose | Queries |
|---|---|---|
| `GET /api/filters` | Returns roles and available industries. Cascades — passing `role` scopes the returned industries, and vice versa. | Gold |
| `GET /api/skills` | Returns the ranked skills list plus all 4 KPI metric cards (with period-over-period delta %). | Gold |
| `GET /api/certifications` | Returns the ranked certifications list with demand badges (High / Medium / Low). | Gold |
| `GET /api/jobs` | Returns paginated job postings that a skill or certification's stats were derived from. Accepts either `skill` or `certificate` param. | Gold (`job_posting_lines`) |

**Date range** is a hardcoded enum in the frontend: `30d | 60d | 90d | 6m | 1y | 2y | all`. It is not fetched from the API.

---

## Key design decisions

| Decision | Choice |
|---|---|
| Ingestion cadence | Weekly (TheirStack API → ADLS Gen2) |
| Pipeline orchestration | Databricks Lakeflow Jobs |
| Skill & cert extraction | Claude via Agent Bricks — AI reads job descriptions |
| Role classification | Keyword match on job title (priority-ordered rule set) |
| Gold layer | Daily grain — all analytics filters applied at query time in SQL |
| Filter cascade | `/api/filters` re-called on each dropdown change; no full page reload |
| Trend signal | Compares occurrence % in the newer half of the selected window vs the older half |
| KPI delta | Compares current window vs the equal-length prior window |
| Auth | None — public read-only application for MVP |

---

## Document map

| Document | Location |
|---|---|
| Product requirements & user stories | `requirements/PRD.md`, `requirements/user-stories.md` |
| System & component architecture | `design/architecture.md` |
| Raw API field reference | `design/data-schema.md` |
| Full data model (all 14 tables) | `design/data-model.md` |
| API contract with SQL | `design/api-contract.md` |
| API request/response reference | `design/api-reference.md` |
| Execution plan & phase gates | `execution/plan.md` |

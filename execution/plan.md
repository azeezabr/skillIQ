# Execution Plan — Skill IQ

## Phase gate sequence
```
Requirements ✓ → Design ✓ → Data pipeline → Frontend → Integration → Deploy
```

## Phase 1 — Requirements ✓
- [x] PRD written
- [x] User stories defined

## Phase 2 — Design ✓
- [x] Architecture updated (Databricks SQL serving, dynamic date filter)
- [x] Raw API schema documented (all fields mapped)
- [x] Data model designed (Bronze / Silver / Gold — table definitions complete)
- [x] API contract defined (`/api/skills`, `/api/filters` — SQL + response schema)
- [x] Role classification rules defined
- [x] Skill extraction rules defined (keyword_slugs ∪ technology_slugs)
- [ ] `dim_skills` seed data — slug → display name mapping (needs human curation)
- [ ] Open decisions resolved (deployment target, Databricks region)

## Phase 3 — Data pipeline (Databricks)
- [ ] Set up `skilliq` Unity Catalog with `bronze`, `silver`, `gold` schemas
- [ ] Bronze: `raw_job_postings` Delta table + API ingest notebook
- [ ] Silver: `dim_roles` seed load
- [ ] Silver: `dim_skills` seed load (slug → display name, category)
- [ ] Silver: `dim_companies` MERGE notebook
- [ ] Silver: `dim_locations` MERGE notebook
- [ ] Silver: `fact_job_postings` MERGE notebook (incl. role classification)
- [ ] Silver: `bridge_job_skills` notebook (union + dedup keyword/technology slugs)
- [ ] Silver: `bridge_job_locations` notebook (explode locations[])
- [ ] Gold: `fact_skill_daily` aggregation notebook
- [ ] Gold: `fact_role_daily` aggregation notebook
- [ ] Databricks Workflow wiring (tasks 1–4 with dependencies)
- [ ] Data quality checks (row counts, null rates, occurrence % sanity)

## Phase 4 — Frontend (Next.js)
- [ ] Bootstrap Next.js app (`src/app/`)
- [ ] Databricks SQL connector wired up (`src/lib/db.ts`)
- [ ] `/api/filters` route implemented
- [ ] `/api/skills` route implemented (parameterised SQL, 5-min cache)
- [ ] `RoleTabs` component
- [ ] `FilterBar` with `DatePicker`, `LocationDropdown`, `IndustryDropdown`, `AnalyzeButton`
- [ ] `MetricCards` (job postings, open roles, median salary)
- [ ] `SkillsPanel` + `SkillRow` (rank, bar, %, trend badge)
- [ ] Occurrence / Trending toggle
- [ ] Responsive layout + Tailwind styling

## Phase 5 — Integration & QA
- [ ] End-to-end: all 5 role tabs return data
- [ ] Date picker drives correct SQL window
- [ ] All filter combos return valid responses (no SQL errors)
- [ ] Trending sort works correctly
- [ ] Page cold-load < 2s
- [ ] Empty state handled (no results for extreme filter combo)

## Phase 6 — Deploy
- [ ] Deployment target confirmed
- [ ] Env vars (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH`) stored in secrets
- [ ] Production smoke test

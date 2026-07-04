# Skill IQ — Project Context

## What this is
Skill IQ is a single-page analytics app that shows in-demand skills derived from real job postings. Users select a job role and see ranked skills with occurrence rates and trend signals (Trending / Stable / Declining), plus summary metrics (total postings, open roles, median salary).

## Stack (TBD — confirm before execution)
- Frontend: Next.js (App Router) + Tailwind CSS
- Data layer: static JSON or SQLite served via API route
- No auth required — fully public single-page app

## Folder map
| Folder | Purpose |
|---|---|
| `requirements/` | PRD and user stories |
| `design/` | Architecture, data schema, UI specs |
| `execution/` | Implementation plan and task breakdowns |
| `src/` | Application source (app, components, lib, data scripts) |
| `data/raw/` | Source job posting data (original, do not modify) |
| `data/processed/` | Transformed data ready for the app |
| `.agents/` | Agent configs and harness definitions |

## Key decisions
- No login, no backend auth — data is read-only analytics
- Skills are ranked by occurrence % across filtered job postings
- Trending signals are derived by comparing recent vs. prior period occurrence

## Workflow conventions
- Requirements → Design → Execution is the gate sequence; don't skip phases
- Every non-trivial feature starts with a task in `execution/tasks/`
- Data schema lives in `design/data-schema.md` — update it before writing any data code

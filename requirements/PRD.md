# Product Requirements Document — Skill IQ

## Problem statement
Job seekers and career changers struggle to know which skills actually matter for a given role. Job descriptions are inconsistent; this app surfaces ground truth from aggregate posting data.

## Target users
- Job seekers researching a new role
- Professionals upskilling to stay competitive
- Recruiters benchmarking required skills

## Core features (MVP)

### F1 — Role selector
- Tabs across the top: Data Engineer, Data Scientist, ML Engineer, Data Analyst, Software Engineer
- Selecting a tab reloads all panels for that role

### F2 — Filter bar
- **Location** — dropdown (All locations + specific markets)
- **Date range** — dropdown (Last 30 days, Last 90 days, Last 6 months, Last 12 months)
- **Industry** — dropdown (All industries + specific verticals)
- **Analyze** CTA button that applies filters

### F3 — Summary metrics
Three KPI cards:
| Metric | Description |
|---|---|
| Job postings | Total postings matching current filters |
| Open roles | Actively hiring count |
| Median salary | Median quoted salary across postings |

### F4 — Top skills list
- Ranked list (1–N) of skills for the selected role + filters
- Each row: rank, skill name, progress bar (width = occurrence %), occurrence %, trend badge
- Trend badge values: `Trending` (green ↑), `Stable` (grey), `Declining` (red ↓)
- Toggle between **Occurrence** (sorted by %) and **Trending** (sorted by trend momentum)
- Source attribution footer

## Non-goals (MVP)
- User accounts / saved searches
- Email alerts
- Salary breakdown by skill
- Geographic heat maps

## Success metrics
- Page renders with real data in < 2s
- Skills list accurate to within ±2% of raw occurrence in source data

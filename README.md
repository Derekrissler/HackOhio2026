# HackOhio2026

A lightweight, Canvas-style LMS that will host learning analytics for students and instructors.
The architecture and roadmap are in [docs/PHASE1_PLAN.md](docs/PHASE1_PLAN.md).

**Current state: Phase 2.** The Canvas-like shell (global nav, course nav, breadcrumbs, role
switcher) and a small API run end to end. Course pages are placeholders until Phase 3.

| Part | Stack | Folder |
|---|---|---|
| Web | React 18, TypeScript, Vite, InstUI 11.6 (`canvas` theme), React Router, TanStack Query | `apps/web` |
| API | Python 3.14 (tested), FastAPI, SQLAlchemy 2, SQLite | `apps/api` |
| Data | `data/app.db`, created and seeded automatically on first start (gitignored) | `data/` |

## Setup (once)

You need **Node 20+** (tested on 24) and **Python 3.14** (the only version tested; 3.12 should work but is unverified). The commands below are for PowerShell on Windows.
macOS and Linux work the same, except for the venv path (shown in comments).

```powershell
# 1. Python virtualenv for the API
py -3 -m venv apps/api/.venv          # macOS/Linux: python3 -m venv apps/api/.venv

# 2. Install everything (root tools, web packages, API packages)
npm run setup
```

## Run

```powershell
npm run dev
```

This starts both servers:

- Web: <http://localhost:5173>
- API: <http://127.0.0.1:8000> (interactive docs at <http://127.0.0.1:8000/docs>). The web app
  reaches it through Vite's `/api` proxy.

To restart from a clean database, stop the servers, delete `data/app.db` and run `npm run dev` again.

## Test

```powershell
npm test              # API (pytest) and web (Vitest)
npm run test:api      # API only
npm --prefix apps/web run build   # type-check and production build
```

## Demo users

There is no login. Open **Account** in the left navigation and choose who to view the app as.

| Id | Name | Role in STAT 1450 |
|---|---|---|
| 1 | Prof. Dana Rivera | Teacher |
| 2 | Alex Kim | Student |
| 3 | Priya Natarajan | Student |
| 4 | Marcus Bell | Student |

All names are fictional. Teachers see **Instructor Analytics** in the course navigation, and
students see **Learning Insights**. The API enforces the same rule: a student requesting
`/api/courses/1/analytics/summary` gets `403`.

The web app sends the selected user as an `X-Demo-User` header. `apps/api/app/auth.py` is the
only code that reads it, so LTI 1.3 launch can replace it later without touching the routes.

## Licence note

This repo does **not** copy code from Canvas LMS (which is AGPL-3.0). It uses
[InstUI](https://github.com/instructure/instructure-ui) (MIT) for Canvas's look, and re-implements
Canvas's layout patterns. Keep it that way, or the repo would have to be AGPL-licensed
(see PHASE1_PLAN §3).

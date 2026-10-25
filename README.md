# HackOhio2026

A lightweight, Canvas-style LMS that will host learning analytics for students and instructors.
The architecture and roadmap are in [docs/PHASE1_PLAN.md](docs/PHASE1_PLAN.md).

**Current state:** Every Canvas tab (Home, Syllabus, Assignments, Quizzes, Grades,
Files) shows seeded course data for students and the teacher. Instructor Analytics
now has authenticated Supabase ARR retrieval. The first live VIBE 101 score run
was published and verified; user-session dashboard acceptance awaits Supabase
enrollments. Learning Insights remains a placeholder. See
[analytics setup and verification](docs/analytics-dashboard.md) and the
[next integration roadmap](docs/analytics-roadmap.md).
The [error/ML integration guide](docs/analytics-error-integration.md) covers the
implemented handoff, two review stages, authenticated tutor bridge and offline demo.
The [comprehensive project-state audit](docs/project-state-2026-10-24.md) compares
the implementation with the pipeline specification and documents live data,
remaining work, debugging procedures and technical improvements.
The [source repair workflow](docs/analytics-source-repairs.md) adds append-only
evidence repair and explicit error/outcome review without schema changes.

| Part | Stack | Folder |
|---|---|---|
| Web | React 18, TypeScript, Vite, InstUI 11.6 (`canvas` theme), React Router, TanStack Query | `apps/web` |
| API | Python 3.14 (tested), FastAPI, SQLAlchemy 2, SQLite | `apps/api` |
| Seed | Canvas REST API-shaped JSON + manual JSON + PDFs, generated deterministically | `data/seed` |
| Database | `data/app.db`, rebuilt from the seed (gitignored) | `data/` |

## Setup (once)

You need **Node 20+** (tested on 24) and **Python 3.14** (the only version tested; 3.12 should
work but is unverified). The commands below are for PowerShell on Windows; macOS and Linux work
the same, except for the venv path.

```powershell
py -3 -m venv apps/api/.venv          # macOS/Linux: python3 -m venv apps/api/.venv
py -3 -m venv carmen-study-guide/mock-canvas/.venv
npm run setup                         # root tools, web packages, API + Carmen packages
```

Carmen (the mock Canvas with the Study Tutor) also needs `carmen-study-guide/mock-canvas/.env`; see
`carmen-study-guide/mock-canvas/.env.example`. Without its venv, `npm run dev` skips it and runs the rest.

## Run

```powershell
npm run dev
```

- Web: <http://localhost:5173>
- API: <http://127.0.0.1:8000> (interactive docs at <http://127.0.0.1:8000/docs>), reached by
  the web app through Vite's `/api` proxy.
- Carmen mock Canvas: <http://localhost:8001/courses/1001>, with Hue, the study tutor, docked on every course page
  and opened as a full window at <http://localhost:8001/courses/1001/tutor>.

One `Ctrl+C` stops all three. To run only Carmen and the tutor, use `npm run carmen`.

The API builds `data/app.db` from the seed on first start, and again whenever the schema version
changes.

## Seed data

| Command | What it does |
|---|---|
| `npm run seed` | Drop and rebuild `data/app.db` from `data/seed/` (safe while the API is running) |
| `npm run seed:generate` | Regenerate `data/seed/` from `apps/api/seedgen/` (fixed random seed, byte-identical output) |

The seed holds two fictional courses:

- **ISE 3200 – Linear Optimization** (main): 20 students, 6 learning outcomes, 7 assessments
  (3 homeworks, 3 quizzes, a scanned midterm) with 42 scored questions, rubrics, realistic
  mistakes and instructor comments, and 11 lecture/reading PDFs.
- **STAT 1450**: a lightly populated second course.

Data flows through the same ingestion path that live Canvas data will use in Phase 4:

```
data/seed/canvas_json  →  CanvasJsonAdapter ─┐
                                             ├→ canonical models → loader → SQLite
data/seed/manual       →  ManualAdapter ─────┘   (apps/api/app/ingest/)
```

`manual/` holds what Canvas doesn't expose: per-question scores for homework and scanned exams,
question → outcome alignments and material kinds. See [data/seed/README.md](data/seed/README.md).

## Demo users

The mock LMS uses demo identities. Open **Account** in the left navigation, type
a name, and pick who to view the app as. Shared Supabase analytics requires a
separate course-account sign-in on Instructor Analytics.

| Id | Name | Role |
|---|---|---|
| 1 | Prof. Dana Rivera | Teacher of both courses |
| 2 | Alex Kim | Student (average; makes a recurring slack-sign error) |
| 3 | Priya Natarajan | Student (strong) |
| 4 | Marcus Bell | Student (struggling; missed Quiz 2) |
| 5–21 | 17 more students | ISE 3200 only |

The web app sends the selected user as an `X-Demo-User` header. It also sets a `demo_user` cookie,
because PDF iframes can't send headers. [apps/api/app/auth.py](apps/api/app/auth.py) is the only
code that turns either into a user and decides access. Students see only their own submissions,
files and grades: anyone else's are a 404. They see quiz questions only after taking the quiz,
and scores, answer keys and comments only once their work is graded. Teacher-only comments are
never shown to students.

## Test

```powershell
npm test                              # API (pytest) and web (Vitest)
npm --prefix apps/web run build       # type-check and production build
npm run e2e                           # Playwright: click through every tab as teacher and student
```

`npm run e2e` starts its own API (port 8010) and web server (port 5180), uses the installed
Microsoft Edge, and saves screenshots to a temp folder (set `E2E_OUT` to choose one).

## Licence note

This repo does **not** copy code from Canvas LMS (which is AGPL-3.0). It uses
[InstUI](https://github.com/instructure/instructure-ui) (MIT) for Canvas's look and imitates
Canvas's REST response *shapes* for its seed data. Keep it that way, or the repo would have to be
AGPL-licensed (see PHASE1_PLAN §3). All people and course content are fictional.

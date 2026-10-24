# Phase 2 — Canvas Shell Implementation Plan

> **For agentic workers:** Execution method supplied by the user: implement natively, task by task,
> and stop after Phase 2 for review. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable monorepo with a FastAPI backend (health, `/me`, courses, demo auth) and a
React + InstUI frontend that looks like Canvas (global nav, course nav, breadcrumbs, role
switcher) with placeholder pages for every course tab.

**Architecture:** Two apps in `apps/`. The web app talks only to `/api` (Vite proxies it to
`localhost:8000`). The demo user is chosen in the UI and sent as `X-Demo-User: <user id>` on every
request; `apps/api/app/auth.py` is the only place that turns that header into a user and checks
enrollment, so LTI can replace it later.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2, SQLite, pytest · React 18, TypeScript, Vite,
InstUI 11.6.0 (`canvas` theme), React Router, TanStack Query, Vitest + Testing Library.

**Spec:** `docs/PHASE1_PLAN.md` §4, §6 (Phase 2 row) and §7.

## Global Constraints

- Approach B: do **not** copy any file or code from `../canvas-lms` (AGPL). Reuse InstUI (MIT) and
  Canvas's layout ideas only.
- InstUI pinned to `11.6.0` (the version Canvas pins). React 18, not 19.
- SQLite file at `data/app.db`, gitignored, rebuilt from the seed when missing.
- Seed: 1 course, 1 teacher, 3 students. Fictional names only.
- Runs natively on Windows: `npm run dev` at the repo root starts both servers.
- No AI, no analytics computation, no Phase 3 tables.

## Review Focus

1. Missing or non-numeric `X-Demo-User` header → 401, not 500. (Task 2 test)
2. Header naming a user id that doesn't exist → 401. (Task 2 test)
3. Student opens `/courses/1/analytics` by URL → page shows "access denied", API returns 403.
   (Task 2 test + Task 5 component)
4. User not enrolled in a course requests `/api/courses/{id}` → 403; unknown course → 404.
   (Task 2 test)
5. Switching demo user must not show the previous user's cached data → query cache is cleared on
   switch. (Task 4)

---

### Task 1: Repo scaffolding and backend data layer

**Files:**
- Modify: `.gitignore` (add `node_modules/`, `data/app.db`, `.DS_Store`)
- Create: `apps/api/requirements.txt`, `apps/api/app/__init__.py`, `app/db.py`, `app/models.py`,
  `app/seed.py`, `apps/api/tests/conftest.py`
- Remove: empty `apps/api/app/routers/` leftover is reused, not removed

**Interfaces — Produces:**
- `db.py`: `engine`, `SessionLocal`, `Base`, `get_db() -> Iterator[Session]`, `init_db()` (create
  tables, seed if `users` is empty). DB URL from env `DATABASE_URL`, default
  `sqlite:///<repo>/data/app.db`.
- `models.py`: `User(id, name, sortable_name, email)`, `Course(id, code, name, term)`,
  `Enrollment(id, course_id, user_id, role)` with `role in {"student","teacher"}`,
  `UniqueConstraint(course_id, user_id, role)`.
- `seed.py`: `seed(session) -> None`. Teacher id 1 = "Prof. Dana Rivera"; students 2–4 =
  "Alex Kim", "Priya Natarajan", "Marcus Bell"; course 1 = `STAT 1450` "Introduction to
  Statistical Reasoning", term "Autumn 2026".

- [ ] Write `conftest.py` fixture `client` (in-memory SQLite via `StaticPool`, overrides `get_db`,
  runs `seed`).
- [ ] Commit `feat(api): Add SQLite data layer with demo seed`.

### Task 2: Backend endpoints and demo auth

**Files:** Create `app/auth.py`, `app/main.py`, `app/routers/{courses,demo,analytics}.py`,
`tests/test_api.py`.

**Interfaces — Produces (HTTP):**
- `GET /api/health` → `{"status": "ok"}` (no auth)
- `GET /api/demo/users` → `[{id, name, role_summary}]` (no auth; feeds the role switcher)
- `GET /api/me` → `{id, name, email, enrollments: [{course_id, role}]}`
- `GET /api/courses` → `[{id, code, name, term, role}]` for the caller's enrollments
- `GET /api/courses/{id}` → `{id, code, name, term, role}`; 404 unknown, 403 not enrolled
- `GET /api/courses/{id}/analytics/summary` → `{course_id, status: "coming_in_phase_7"}`;
  teacher only
- `auth.py`: `current_user(x_demo_user: str | None = Header(None), db) -> User` (401 on
  missing/invalid/unknown), `require_enrolled(course_id, user, db) -> Enrollment`,
  `require_teacher(course_id, user, db) -> Enrollment`.

- [ ] Write tests first: health 200; `/api/me` without header → 401; header `"abc"` → 401;
  header `"999"` → 401; teacher `/api/courses` returns one course with `role == "teacher"`;
  student 2 sees `role == "student"`; student → analytics 403, teacher → 200; course 999 → 404;
  a second course created in-test that student 2 isn't in → 403.
- [ ] Run `pytest` → fails (no app). Implement. Run `pytest` → all pass.
- [ ] Commit `feat(api): Add health, me, courses and demo auth endpoints`.

### Task 3: Web app skeleton with InstUI theme and API client

**Files:** Create `apps/web/{package.json,index.html,vite.config.ts,tsconfig.json}`,
`src/main.tsx`, `src/App.tsx`, `src/api/{types.ts,client.ts,hooks.ts}`,
`src/shell/demoUser.tsx`. Root `package.json` + `scripts/dev-api.mjs` (spawns
`apps/api/.venv` python → `uvicorn app.main:app --reload --port 8000`, picks `Scripts/` on
Windows, `bin/` elsewhere). `concurrently` runs web + api for `npm run dev`.

**Interfaces — Produces:**
- `api/client.ts`: `apiGet<T>(path: string): Promise<T>`; throws `ApiError {status}`; adds
  `X-Demo-User` from `getDemoUserId()`.
- `api/hooks.ts`: `useDemoUsers()`, `useMe()`, `useCourses()`, `useCourse(id)`,
  `useAnalyticsSummary(id)`.
- `shell/demoUser.tsx`: `DemoUserProvider`, `useDemoUser() -> {userId, setUserId}`; persists in
  `localStorage` key `demoUserId` (default `1`), and `setUserId` calls `queryClient.clear()`.

- [ ] `npx tsc --noEmit` and `npm run build` pass. Commit
  `feat(web): Scaffold Vite app with InstUI canvas theme`.

### Task 4: Canvas shell — GlobalNav, CourseNav, Breadcrumbs, RoleSwitcher, routes

**Files:** Create `src/shell/{AppLayout,GlobalNav,CourseLayout,CourseNav,Breadcrumbs,RoleSwitcher}.tsx`.

- Routes: `/`, `/courses/:courseId`, `/courses/:courseId/{syllabus,assignments,quizzes,grades,files,insights,analytics}`, `*` → NotFound.
- `GlobalNav`: InstUI `SideNavBar` (dark rail) — Account (opens Tray with `RoleSwitcher`),
  Dashboard, Courses (opens Tray listing courses).
- `CourseNav`: `getCourseNavItems(role) -> {label, path}[]`: Home, Syllabus, Assignments,
  Quizzes, Grades, Files, then **Learning Insights** if student or **Instructor Analytics** if
  teacher.
- `Breadcrumbs`: course code › current tab label.

- [ ] Vitest: `getCourseNavItems("student")` includes "Learning Insights" and not "Instructor
  Analytics"; teacher is the reverse. Rendered `CourseNav` for a student has no analytics link.
- [ ] Commit `feat(web): Add Canvas-style navigation shell and role switcher`.

### Task 5: Pages

**Files:** Create `src/pages/{Dashboard,CourseHome,PlaceholderPage,InstructorAnalytics,NotFound}.tsx`.

- Dashboard: real course cards from `useCourses()` (loading, error, empty states).
- Each course tab: `PlaceholderPage` with title and "Coming in Phase N" (Syllabus/Assignments/
  Quizzes/Grades/Files → 3, Learning Insights → 6, Instructor Analytics → 7).
- InstructorAnalytics fetches the summary; 403 → "Access denied" alert.

- [ ] Vitest: InstructorAnalytics renders "Access denied" when the API returns 403.
- [ ] Commit `feat(web): Add dashboard and placeholder course pages`.

### Task 6: Docs and end-to-end verification

**Files:** Rewrite `README.md` (Windows setup + run steps, licence note); create `.env.example`.

- [ ] `npm run dev` from the root; via the Vite proxy: `/api/health` 200; student analytics 403.
- [ ] Headless browser screenshots of dashboard, course home (teacher and student).
- [ ] Commit `docs: Add setup and run instructions`.

---

## Implementation notes (deviations found while executing)

- **Review Focus 5:** instead of `queryClient.clear()` on switch, every user-scoped query key
  includes the demo user id (`api/hooks.ts`). A switch then fetches fresh data and cached
  responses can never cross users. Clearing the cache would not refetch for mounted observers.
- `getCourseNavItems` and the tab list live in `src/shell/courseTabs.ts` so routes, nav and
  breadcrumbs share one source.
- `scripts/dev-api.mjs` became `scripts/api-python.mjs`, which forwards its arguments to the venv
  Python, so it serves both `dev:api` (uvicorn) and `test:api` (pytest).
- `httpx` → `httpx2`: Starlette 1.10's TestClient deprecates httpx.
- InstUI `Breadcrumb` draws a separator after every child but the last, `false` children
  included. Pass only real children.

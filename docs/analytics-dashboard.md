# Phase 7: authenticated analytics dashboard

The existing Instructor Analytics page now reads saved schema 1.1 ARRs through
the guarded analytics service. It does not calculate statistics in the browser,
run analysis on page load, or write to Supabase. The mock Canvas continues to use
SQLite. No migrations or shared-database changes are part of this phase.

## Files and boundaries

- `apps/api/app/analytics/access.py`: verify the bearer token with Supabase Auth,
  read the verified user's enrollment with their JWT, enforce staff/student scope.
- `apps/api/app/analytics/dashboard.py`: discover the newest visible result run,
  check publication and source freshness, project private ARR documents to public
  display DTOs. No raw answers, dependency/evidence UUID lists, private manifests,
  cluster excerpts, or student identities are returned by these DTOs.
- `apps/api/app/routers/analytics.py`: existing mock teacher guard plus separate
  UUID/JWT endpoints. Demo headers and cookies never authorize Supabase reads.
- `apps/web/src/api/supabase.ts`: official Supabase JS client, public URL/key only,
  in-memory authentication, automatic refresh, no URL session detection.
- `apps/web/src/pages/InstructorAnalytics.tsx`: course-account sign-in, authorized
  course selector, class outcomes, question statistics, optional mistake groups,
  and explicit unavailable/stale/suppressed states.
- `apps/api/app/analytics/cli.py`: adds read-only `courses` discovery.

## Setup and use

Install optional analytics persistence dependencies into the API environment:

```powershell
python -m pip install -r apps/api/requirements-persistence.txt
npm --prefix apps/web ci
```

`apps/api/.env` needs `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and the privately
supplied `SUPABASE_SECRET_KEY`. Keep `DATABASE_URL` unset: it is for the mock
Canvas SQLite database, never Supabase. `apps/web/.env.local` contains only
`VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`, matching `.env.example`.
Restart Vite after changing its env file. Real env files remain gitignored.

Open Instructor Analytics as a mock teacher, then sign in with an **existing
Supabase course account**. This is a separate identity from the demo picker.
Account creation and enrollment belong to the auth/database owner. The page
suggests a course only when exactly one enrolled staff course has a persisted
`courses.canvas_id` matching the local course integer. Otherwise explicitly select
the shared course. The selected course's real code/title are always shown.
Names, emails and matching numeric IDs are never used to infer a learner identity.

Auth tokens are kept in memory, sent only in Authorization headers, and excluded
from query keys. A new auth event gets a new random cache scope and removes prior
analytics queries. Signing out or changing demo identity clears the display and
cache. Reloading the page requires signing in again. Passwords go to Supabase
through its official SDK and are not sent to the application API or persisted.

## HTTP contract

All shared analytics endpoints require `Authorization: Bearer USER_ACCESS_TOKEN`:

| GET endpoint | Access | Response |
|---|---|---|
| `/api/analytics/courses` | Verified Supabase user | Their enrolled UUID courses and roles |
| `/api/analytics/courses/{uuid}/summary` | Course instructor or TA | Aggregate performance and sanitized mistake groups |
| `/api/analytics/courses/{uuid}/my-results` | Course member with own learner identity | Own student-outcome performance only |

The last two accept an optional `run_id` UUID to inspect an authorized historical
run, still subject to freshness checks. `my-results` resolves learner identity
from `learner_identities` using the verified user UUID and course UUID; it accepts
no caller-selected learner filter. A student dashboard page is not added here.

The original `/api/courses/{integer}/analytics/summary` remains a mock teacher-only
entry check returning `supabase_sign_in_required`; it returns no shared data.
Real endpoints never use the demo header or the local course database for access.
Responses containing analytics or enrollment data use `Cache-Control: no-store`.

JWT/RLS reads happen before any service-role control query. The server-only
client is used for restricted publication metadata and source fingerprint checks;
the result payload is always read with the caller's JWT. Read endpoints never
publish, refresh, mark stale, or otherwise modify database rows.

Newest visible results are selected including stale rows. Stale or unfinished
results block display rather than silently falling back to a prior run. A final
stale-flag recheck catches ordinary concurrent invalidation. These separate REST
reads are not a transactional snapshot; the serialization limitations documented
in [analytics-persistence.md](analytics-persistence.md) still apply.

Display states: `ready`, `no_results`, `stale`, `incomplete`, and
`insufficient_evidence`. Missing configuration or upstream failures return safe
503 messages, invalid sessions 401, and missing enrollment/staff role 403.
Null metrics display as unavailable, not zero. Small-cohort fields stay null.
Mean student score and pooled points score remain distinct server-provided values.
Scores describe observed performance, not mastery or enrollment-wide coverage.

## Live acceptance checklist

Implementation attempted read-only course discovery on this workstation. The
local API environment was incomplete or still contained placeholder credentials,
so **no live course rows were read and no shared rows were written**. Current
verification uses fictional source evidence and simulated SDK/RLS responses,
plus real SDK construction tests from Phase 6. It does not prove live RLS or
end-to-end integration with the team's current data.

Once configured, run from `apps/api`:

```powershell
python -m app.analytics.cli courses
python -m app.analytics.cli readiness --course COURSE-UUID
python -m app.analytics.cli analyze --course COURSE-UUID --save-bundle
```

Before publication, review the readiness counts and a hand-calculated sample.
Confirm the extraction owner's `payload.analytics_v1` contract, authoritative
outcome weights, assistance fields, and explicit error-to-outcome attribution.
Source ingestion alone does not imply usable current LERs exist. Missing data
must be supplied upstream; do not create analytical facts to fill a gap.

For a controlled shared-data trial, arrange exclusive course access by pausing
or serializing ingestion and metadata writers, then publish the reviewed
**live-source** bundle using the Phase 6 CLI. Offline fixture bundles cannot be
published. No publication was attempted during implementation because live
readiness and the serialization prerequisite could not be established.

Verify authorized staff readback, student A's own results, student B isolation,
denial of staff scopes to students, retry behavior, and new-run history. Test
corrections and stale propagation only with fictional/isolated evidence; never
change real grades for verification. Keep all secrets and user tokens local.

## Regression checks

Backend tests cover HTTP JWT enforcement, verified enrollment, learner identity,
sanitized DTOs, distinct mean/pooled values, suppression, source changes, newest
stale runs, historical run selection, and invalidation during a read. The
fictional pipeline test runs evidence loading, analysis, staged persistence, and
HTTP retrieval. Frontend tests cover sign-in/out, bearer headers, explicit course
selection, identity changes, safe errors, unknown values, and hidden stale or
suppressed results. Model evaluation remains synthetic and local-only.

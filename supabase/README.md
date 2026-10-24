# Supabase schema

Project `besxavsdjolmxbdcbclw` (us-east-1, Postgres 17). Migrations in `migrations/` are applied in filename order.

| Migration | What it does |
|---|---|
| `core_schema` | All tables from spec §7: identity, outcomes/documents/`resource_chunks` (pgvector 1536 + generated `fts`), assessments → responses, evidence, `lers` + child tables, `analytics_runs`/`analytics_results` (ARR), `insight_records` (IR), tutor/practice, jobs/audit. |
| `lineage_triggers` | LERs are append-only. Inserting a LER for the same `response_id`/`practice_attempt_id` supersedes the previous one (`revision`+1). Superseded LER, new LER, or changed grade → linked ARRs `is_stale` → linked IRs `is_stale`. |
| `rls` | RLS on every table, read-only for `authenticated`. Students: own learner rows, own `student_outcome` ARRs, own student IRs, released + `student_visible` chunks. Staff (instructor/ta): whole course, incl. `question_answer_keys`. Private buckets `source-files`, `course-materials`. |
| `hybrid_search` | `search_resource_chunks(course, query, embedding?, outcome_ids, k, student_safe=true)`: RRF of vector + full-text, +0.02 outcome boost, keyword-only when `embedding` is null. |
| `hardening` | Pinned `search_path` on trigger functions; FK indexes used by RLS. |
| `auto_profile` | Creating an auth user auto-creates its `profiles` row (`display_name` from user metadata, else email). |

## Conventions for the pipeline

- **Writes use the service role** (server only, never the browser). Browsers use the anon key + user JWT and only `select`.
- **Tutor retrieval:** call `search_resource_chunks` with the *student's* JWT so RLS applies; leave `p_student_safe` true.
- **Corrections:** never update a LER, insert a new one; to re-analyze, the analytics job recomputes ARRs where `is_stale`, then IRs where `is_stale`.
- **Pseudonyms:** analytics tables key on `learners.id`; the real user mapping is only in `learner_identities`.
- **Demo auth:** seed `auth.users` + `profiles` + `enrollments` + `learner_identities` for one instructor and the synthetic students.

## Verified

- Lineage: in-place LER edit rejected; revision supersedes; ARR and IR go stale.
- RLS: student sees 1/2 LERs, 0 answer keys, 1/2 chunks (answer-key chunk hidden even with `p_student_safe=false`); instructor sees all.

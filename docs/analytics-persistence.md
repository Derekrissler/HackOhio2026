# Phase 6: ARR generation and Supabase persistence

The implementation uses existing `analytics_runs`, `analytics_results` and
`arr_ler_links`. It does not run migrations, change RLS, start background jobs,
alter the mock Canvas SQLite configuration, or add dashboard routes.

```
Supabase current LER revisions + related facts
  -> readiness / validated inputs
  -> canonical manifest and statistical + optional clustering results
  -> typed ARR 1.1 documents
  -> staged writes, dependency links, verification, publication
  -> JWT/RLS reader plus private freshness check
```

## Files and boundaries

All Python files below are in `apps/api/app/analytics/`:

| File | Role |
|---|---|
| `supabase_clients.py` | Lazy, separate pipeline and user-session SDK clients |
| `evidence_repository.py` | Paginated course-scoped joins and loading issues |
| `provenance.py` | Canonical content hashes and runtime/method identity |
| `arr_generation.py` | Typed ARR 1.1 documents, SQL row encoding/decoding |
| `repository.py` | Staged persistence and read-only result queries |
| `service.py` | Readiness, dry-run bundles, publication and guarded retrieval |
| `cli.py` | Explicit readiness, analyze and publish commands |

Install `apps/api/requirements-persistence.txt` in the API environment. It includes
the statistical requirements and evaluated Supabase 2.33.0 / python-dotenv 1.2.4.
Clustering remains optional via `requirements-clustering.txt`. SDK construction
uses `SyncClientOptions` with session persistence/refresh disabled. Imports and
offline fixture analysis do not read env files or initialize an SDK client.

Pipeline access reads `SUPABASE_URL` and `SUPABASE_SECRET_KEY` from `apps/api/.env`.
User clients read the URL and `SUPABASE_PUBLISHABLE_KEY` plus a required access JWT.
Secrets and raw upstream error messages are never included in CLI output, bundles,
or published ARRs. `DATABASE_URL` is neither read nor changed by this package.
Supabase credentials are never passed into the mock LMS SQLAlchemy engine.

## Upstream metadata contract

The reader reuses the existing tables. It requests only selected scored/identity
fields and `analytics_metadata:payload->analytics_v1` from each LER, not entire LER
payloads, student answers, feedback text, names, or answer keys. The LER developer
must agree to this proposed versioned JSON namespace before live integration:

```json
{
  "analytics_v1": {
    "schema_version": "1.0",
    "errors_analyzed": true,
    "outcome_weights": {"OUTCOME-UUID": 1.0},
    "error_outcomes": {"LER-ERROR-UUID": ["OUTCOME-UUID"]}
  }
}
```

This object belongs **inside `lers.payload`**; placeholders above must be actual
UUIDs. `errors_analyzed` must be an actual JSON boolean, not an inferred absence
of rows. If missing, error classification stays unknown while valid scored
evidence can still contribute to performance. The namespace is a proposed adapter
contract, not a claim that existing LER payloads already implement it.

If `ler_outcomes` exists for a LER, use its outcome set; otherwise use the question's
mapping set. Weights come first from matching `question_outcomes.weight`; a
LER-only mapping needs an explicit `outcome_weights` entry. Confidence never acts
as weight. Missing weights produce an issue and exclude that outcome contribution.
Error-to-outcome associations must be explicit, belong to included mappings and
remain unknown when unavailable. Approved clustering excerpts are supplied
separately through the Phase 5 contract; a database misconception string is not
automatically privacy-approved.

Reads are course-scoped, ordered, paginated, and ID batches are capped. Ownership
and join consistency are validated across learners, courses, outcomes, source refs,
responses, attempts and practice. Missing referenced rows quarantine that join.
Practice source hints cannot contradict independently classified LER metadata.
No synthetic LERs or default independence are created to make a readiness count pass.

## Snapshots, versioning and evidence

Every intentional analysis gets a new run UUID. Its canonical input hash covers
normalized analytical facts, source fingerprint, exclusions/readiness, configuration,
period, method/runtime versions and optional model/prepared-text metadata. Order of
input records or set-like references does not determine the hash. Execution IDs
and timestamps are separate from this input hash.

The frozen minimal manifest is stored in staff-only `analytics_runs.params`, with
the optional complete clustering report (including noise/unavailable states).
It contains pseudonymous analytical facts and approved excerpts, not arbitrary raw
submissions. Normalized records can replay the statistical calculation. Original
invalid values remain in their source store; issues/normalized nulls are retained.

New ARRs use schema **1.1**, preserving the complete typed Phase 4 statistical
metrics and Phase 5 group/membership metrics. The old schema 1.0 models in
`contracts.py` remain for compatibility; generated 1.1 documents live in
`arr_generation.py`. No SQL schema change is necessary because metrics/provenance
already have JSONB storage. The reader intentionally selects schema 1.1 for an
explicit course/run; it does not reinterpret another producer's legacy ARRs.

`analytics_results.metrics.document` contains the full validated ARR. Actual SQL
columns retain IDs, indexed dimensions, numerator/denominator, period, limits and
stale state. Decoding checks that those columns agree with the document. Student
point columns hold weighted earned/possible; class/question columns describe the
mean student ratio using sum-of-student-ratios / student count. Pooled points and
prevalence retain their own separate metrics/denominators. Mastery remains null.

Metric-specific evidence sets describe facts actually counted. `dependency_ler_ids`
and `arr_ler_links` additionally cover candidate evidence that can change eligibility
after correction. Dependencies are deliberately conservative (all normalized input
for that course, restricted to the subject for student ARRs); they do not inflate
the reported observation counts. Bundle validation prevents cross-learner student
links. Full source fingerprints also cover quarantined or missing-source cases.

Suppressed aggregate ARRs retain no measurements, counts or identifying links.
Detailed dependencies remain in restricted run metadata, and guarded retrieval
checks the full course fingerprint. Small-cohort cluster groups are omitted from
published ARRs under the same configured student threshold; their detailed
assignments remain only in restricted run metadata. This metadata is not a
dashboard response. There are no generated longitudinal ARRs yet.

## Publication, retries and concurrency

`analyze_course` is read-only. `persist_analysis` requires an explicit
`exclusive_course_access=True` precondition: all ingestion/metadata writers for
that course must be paused or serialized by the caller. This flag is an attestation,
**not** an implemented distributed lock. Multi-call reads/writes are not one
transaction; before/post checks do not eliminate every concurrent-write race.
Production atomic publication requires an owner-provided transaction/locking RPC.
No such function or migration is installed by this workstream.

Publication checks the source fingerprint, writes run state, stages stale ARRs,
writes dependency links, verifies exact stored rows/links, checks the source again,
publishes the run's rows in one update, rechecks the source, then records completion.
Failures attempt to leave all new results stale and preserve sanitized failure
codes. An outage may prevent cleanup; default guarded readers reject incomplete
runs. This is staged recovery, not transactional rollback.

Retry the **same saved bundle** so run IDs, document IDs and content remain stable.
Changed content under an existing run ID is rejected. Completed history is never
overwritten or republished, including when old results have become stale. New
intentional computations use new run IDs. Independent runs are preserved.

Existing SQL triggers handle LER supersession and changed grades linked to ARRs.
They do not cover every question/mapping edit or privacy-redacted dependency.
`retrieve_current_results` therefore performs the user/RLS read first, privately
checks completed run metadata and compares the full current source fingerprint.
Stale/incomplete data is not returned by this service. It never returns the
staff-only manifest to students and performs no automatic database writes.

Always use this guarded service for current results; directly querying a
nonstale row is not a full freshness guarantee. Supabase remains responsible for
JWT authorization/RLS. The mock LMS's demo identity is not a Supabase session.
Dashboard auth/route wiring is described in [analytics-dashboard.md](analytics-dashboard.md).
Its display endpoints verify a real Supabase JWT and course enrollment, read ARR
payloads with the user's JWT, and keep private control metadata server-only.

## Usage from apps/api

Readiness is read-only; use a real course UUID, not a local integer Canvas ID:

```powershell
python -m app.analytics.cli readiness --course COURSE-UUID
python -m app.analytics.cli analyze --course COURSE-UUID --save-bundle
```

Offline analysis accepts an array of the joined envelopes demonstrated in
`tests/analytics/fixtures/ler.json`. No SDK/secret is needed:

```powershell
python -m app.analytics.cli analyze --course COURSE-UUID --input fictional-envelopes.json --save-bundle
```

Default output contains readiness and ARR counts, not student rows. Saved bundles
go to gitignored `data/analytics-runs/<run-uuid>.json`; treat them as private
analytical artifacts. Offline-fixture bundles cannot be published to the shared
database. Optional flags: `--config config.json`, `--period-start`/`--period-end`,
`--cluster --excerpts approved-excerpts.json --model-cache CACHE-DIRECTORY`.
Model loading is local-only; this command never auto-downloads a model.

After reviewing a live-source bundle and arranging exclusive course access,
publication is a separate write operation (not executed as part of implementation):

```powershell
python -m app.analytics.cli publish --bundle ../../data/analytics-runs/RUN-UUID.json --exclusive-course-access
```

Retrieval in trusted server code uses separate clients:

```python
control = SupabaseAnalysisRepository(create_pipeline_client())
reader = SupabaseARRReader(create_user_client(student_access_token))
results = retrieve_current_results(control, reader, course_uuid, run_uuid,
                                   scope="student_outcome", learner_id=learner_uuid)
```

Never attach a user session to the privileged client. Tutor resource retrieval
continues to use the student's session and `search_resource_chunks`; this phase
does not change that path.

## Verification scope

Tests simulate the Supabase SDK/table responses and RLS visibility without calling
the shared database. They cover pagination/joins, missing upstream contracts,
readiness, known-answer statistics, snapshots/replay, column roundtrips, privacy,
candidate dependencies, retries, partial writes, source changes, completed history,
user-scope retrieval, cluster generation and CLI dry-run behavior. A real SDK smoke
test constructs clients with fictional credentials and makes no requests.
These tests do not claim live RLS or database integration verification. The next
live step is a course-selected readiness report, followed by an inspected dry run.

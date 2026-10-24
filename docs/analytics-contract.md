# Analytics boundary contract (Phase 2)

This package is independent of the mock Canvas SQLAlchemy database. It makes no
network requests and does not generate LERs, compute aggregates, or persist ARRs.
Use Supabase UUIDs, not local SQLite integer IDs. No schema migration is needed.

## Input adapter

`app.analytics.ler_adapter.adapt_ler(envelope)` accepts explicitly joined rows:

- `ler`: the existing `lers` row, including schema version, identity, revision,
  current status, assessment origin, classification status and assistance fields.
- `response`, `question`, `attempt`, `assessment`: related rows for graded evidence.
  Scores come from `responses.points_earned` and `questions.points_possible`;
  observation time comes from `attempts.submitted_at`, never LER creation time.
- `practice`: the related `practice_attempts` row for practice evidence. Its
  `created_at` is observation time. Practice correctness is not invented as a score.
- `outcome_mappings`: explicit outcome UUID, nonnegative weight, provenance and
  review flag. Join authoritative question mappings upstream. `ler_outcomes`
  confidence is not a weight. Missing weights are not silently defaulted to one.
- `errors`: structured code, review status, optional misconception, evidence UUIDs
  and explicit outcome associations when known. Rejected/unreviewed status is
  retained for later policy filtering. Duplicate tags are retained until Phase 3.
- `evidence_ref_ids`: all original evidence UUIDs used by this record.
- `errors_analyzed`: true = classification completed (empty list means no detected
  error); false = not classified; null = unavailable. This is adapter metadata to
  agree with the extraction owner, not a new database column.

The fixture in `apps/api/tests/analytics/fixtures/ler.json` is fictional and uses no
personally identifying information. Production adapters must whitelist fields;
raw student answers, names and arbitrary `lers.payload` content are not copied.

The result contains a normalized record plus structured issue codes. Invalid
identity, weights or joins quarantine the record. Missing/invalid scores and
timestamps become null plus issues, preserving qualitative evidence. Keep the
original envelope in its authorized source store: normalized nulls do not replace
the source. Validation errors never echo input values. Missing assistance is
unknown; only the explicitly agreed `independent`/`assisted` vocabulary is mapped.

`is_current=false` and `analysis_status=insufficient` are retained and flagged;
Phase 3 must enforce metric-specific eligibility. Missing score halves must never
be summed independently. Timestamp-dependent metrics require an aware timestamp.
Records are not deduplicated or selected by this contract-only phase.

## ARR and run contracts

Use `ARR_ADAPTER.validate_python(...)` for the scope-discriminated union:

| Scope | Required dimensions | Metrics |
|---|---|---|
| student_outcome | subject_learner_id, outcome_id | PerformanceMetrics |
| class_outcome | outcome_id | ClassMetrics |
| assessment_question | assessment_id, question_id | ClassMetrics |
| misconception_cluster | run-local cluster_id in metrics | ClusterMetrics |
| longitudinal_trend | outcome_id | TrendMetrics |

All ARRs include UUID identity, run/course IDs, schema version, source LER UUIDs,
metric-specific evidence sets, numerator/denominator definitions, inclusion rule,
optional period, limits and timestamp. Source IDs must equal the distinct union
of metric evidence sets. Student score observation count equals selected score
LER count; cluster members must match cluster evidence. Mastery is always null.
Extra fields are rejected, including subject identity on aggregate/trend scopes.
Trend windows are nonoverlapping half-open intervals with descriptive change only.

These are internal evidence-bearing contracts, not public response models.
Suppressed results require a separate redacted delivery contract before serving
dashboards; validation currently rejects suppressed internal ARRs to prevent
accidentally publishing evidence or identifiable small-cohort counts. In Phase 4,
extend metrics with typed error/prevalence and practice score summaries alongside
their calculations. No dashboard should derive these itself.

Persistence in Phase 6 maps IDs and dimensions to `analytics_results`, nested
evidence sets/definitions to a versioned metrics payload, and the union of LER IDs
to `arr_ler_links`. Run metadata maps to `analytics_runs`; configuration and model
information belong in `params`. These DTOs must not be inserted verbatim as SQL rows.
Run IDs are generated metadata, separate from deterministic analytical content.
Snapshot hashes must cover actual scores, possible points, mappings, evidence
revisions and ordering, not just LER IDs. Snapshot generation is not yet implemented.

## Approved initial policies

`AnalyticsConfig` records the latest-valid attempt policy, normalized question
weights, parts-preferred/no-overlap question policy, minimum two questions per
student outcome, recurring errors after two observations, minimum five students
per aggregate, and observed score threshold 0.70. These are configurable prototype
policies, not validated mastery thresholds. Core calculations are Phase 3/4 work.

Clustering remains optional at runtime: minimum six observations, DBSCAN cosine
epsilon 0.25, minimum samples three are proposed starting settings, not evaluated
model quality claims. No embedding packages or models are installed in Phase 2.
Resolve Sentence Transformers' dependency footprint against the PyTorch exclusion
before adding the optional embedding environment.

## Verification

Run from `apps/api` with Pydantic v2 and pytest:

```sh
python -m pytest --confcutdir tests/analytics tests/analytics -q
```

`--confcutdir` isolates boundary tests from the parent conftest that imports the
whole mock LMS and SQLAlchemy. Run the existing application suite when backend
integration starts. No test here contacts Supabase or reads a secret/env file.

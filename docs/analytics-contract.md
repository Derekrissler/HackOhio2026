# Analytics contracts and pipeline (Phases 2–5)

This package is independent of the mock Canvas SQLAlchemy database. It validates
evidence, prepares features and calculates descriptive statistics. Phase 5 adds
optional local semantic grouping; only explicitly opted-in public model downloads
use the network. It does not generate LERs or persist ARRs. Use Supabase UUIDs, not
local SQLite integer IDs. No schema migration is needed.

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

## Phase 3 feature tables

`app.analytics.features.build_features(records, config=None, period=None)` returns
Pandas DataFrames in a `FeatureTables` object. Use `requirements-analytics.txt` for
the optional backend analytics dependencies (Pandas and NumPy). The core mock LMS
does not import this module or need these packages to start.

- `observations`: one retained question-attempt/practice observation, normalized
  score, assistance, timestamp, evidence IDs and primary selection flags.
- `outcomes`: one row per positive outcome mapping, normalized weight and weighted
  points. Join to observations on `ler_id`; do not sum every history row as primary.
- `errors`: one event per retained LER and error code, with unique source refs,
  explicit outcome associations, identity dimensions and primary error flag.
- `practice`: all distinct eligible practice attempts, with independence, hints,
  correctness, outcomes and evidence. Never pooled into primary assessment scores.
- `exclusions`: LER ID, processing stage and reason. Some reasons exclude only a
  particular metric; history can remain present. Duplicate collapse is recorded.

Input order does not decide results. Conflicting copies of a LER ID or logical
question-attempt are quarantined; identical duplicates collapse deterministically.
Superseded and insufficient LERs do not enter feature tables. Assessment-score
candidates require explicitly independent performance and a valid complete score.
NumPy checks floating-point representability; unrepresentable points do not become
infinite metrics. Numeric scored/weighted columns are null for an incomplete pair.
`source_points_earned` and `source_points_possible` retain available normalized
Decimal values as exact strings, including values too large for floating point.
Original invalid input remains in the source envelope, not these DTOs.

Primary score and primary error selections are independent: an unscored latest
attempt with reliable error classification can inform errors while an earlier
valid score supplies performance. Primary errors require completed classification
and independent graded evidence. Error history includes eligible assisted/practice
evidence, with assistance/origin labels. Rejected errors are removed; unreviewed
errors follow configuration. Repeated tags merge their distinct source refs and
explicit outcome links. An unknown error-outcome association stays empty rather
than attributing that error to every question outcome.

For each course/learner/assessment/question, use latest valid submission time when
all candidate timestamps exist; explicit attempt number resolves equal times. If
some timestamps are missing, use attempt numbers only when all candidates supply
them. Unresolved ties/missing ordering exclude primary selection, not history.
A single candidate needs no ordering comparison. Timestamps remain necessary for
trends and bounded analyses; supplied periods use `[start, end)` and exclude missing
timestamps. Missing times are never filled with LER creation time.

For each metric separately, if selected `rubric_question_part` evidence exists for
an assessment/student, exclude selected `assignment_level` evidence from that metric.
This applies across attempts and may yield incomplete coverage; it does not invent
missing question-part points. Whole evidence stays in history. Ordinary questions
remain separate and unmapped/zero-weight observations can still support question
analytics. Positive outcome weights normalize per question, using Decimal division
before conversion to numerical features. Confidence never substitutes for weight.

Verification review strengthened these boundaries: normalized weights are scaled
before summation to avoid Decimal overflow, and nested evidence-reference ordering
does not create false duplicate conflicts. Practice attempt identity is independent
of its claimed origin; conflicting origins quarantine that attempt instead of
counting it twice. ARR performance ratios must match their weighted numerator and
denominator (absolute tolerance 1e-12), and distinct counts cannot exceed their
supporting scored observation counts.

Feature engineering itself performs no aggregation or clustering. Phase 4 consumes
these selections for the statistics described below. Feature history is restricted
internal data, never a browser response or a privacy-suppressed aggregate.

## Phase 4 descriptive statistics

`app.analytics.statistics.analyze_statistics(records, config=None, period=None)`
returns a validated, JSON-serializable `StatisticsResult` containing student-outcome,
class-outcome and assessment-question statistics. Configuration and period are
included. These are intermediate analytical DTOs, not generated ARRs, database
rows, natural-language interpretations, or authorized dashboard responses.

Student outcome ratios use sums of eligible weighted earned/possible points, not
the mean of question ratios. At least `student_min_questions` distinct selected
questions are required; otherwise the ratio is null while counts, points and LER
references remain available. Actual zero scores remain zero. Practice evidence
does not contribute to these assessment totals.

Class means average the sufficient student ratios with equal student weight.
Pooled ratios use weighted points from that same sufficient-student cohort, and
are reported separately. Counts distinguish observed assessed students, students
with any valid independent scores, and students meeting the evidence minimum.
Threshold counts use only the last cohort. Ratios require at least
`class_min_students` sufficient students even when privacy suppression is off.
Question statistics require one selected question per student, without requiring
outcome mappings. Class outcomes include assessment-specific breakdowns, recomputed
within each assessment using the same minimum-question rule.

Coverage is sufficient students / observed assessed students. The observed cohort
contains eligible analyzed graded input, including records with missing scores or
unknown assistance. It excludes upstream insufficient/quarantined LERs; it is not
an enrollment denominator or a claim about the entire class. Aggregate supporting
LER IDs include the observed cohort so counts and coverage remain traceable.

Errors use latest eligible independent classifications, separately from latest
valid score selection. Event counts deduplicate tags per LER; recurrence uses the
configured number of distinct selected observations. Counts distinguish events,
questions, assessment/practice attempts, and students. Outcome error denominators
require completed usable classification plus known attribution for every accepted
tag in that observation. Unknown attribution is reported in student statistics;
it is never treated as absence of an outcome error. Question error statistics do
not need outcome attribution. Rejected errors are omitted. If unreviewed errors
are excluded by policy, that observation cannot establish an error-free denominator;
`error_policy_complete` records this separately from upstream classification status.

Prevalence is unique eligible students with the category / unique students with
eligible error evidence, retaining numerator, denominator, definitions and source
LER links. Multiple errors by one student do not increase the numerator. No tags
means no discovered category row, rather than fabricated zero prevalence for every
possible taxonomy category.

Default privacy suppression clears small-cohort performance counts, ratios,
weighted points, evidence IDs, categories and assessment breakdowns. It also applies
when the valid-scored or sufficient-student subset is nonzero but below the minimum.
A separately small error denominator hides error categories, counts and links even
if score statistics have enough students. Disabling suppression reveals diagnostic
counts, not unsupported ratios. Cohort dimensions and suppression flags remain.
Student results and unsuppressed evidence links remain restricted internal data;
the whole result bundle must not be returned directly to a student or browser.

Practice has independent/assisted/unknown buckets with distinct attempt counts,
known hint counts/totals, evidence, and separate scores if actually supplied.
Missing hints are not zero. `independent_correctness` is summarized only in the
independent bucket; it does not establish assisted-answer correctness. Practice
ratios require `practice_min_attempts` known observations (default two). There is
no assistance penalty, fabricated correctness, improvement claim, or trend model.
Decimal totals avoid floating-point overflow in pooled points; proportions remain
ordinary bounded floats. Stable group/order rules make results reproducible under
input permutation.

The statistical tests use fictional records with manually verified unequal-point
examples, class versus pooled means, unique-student prevalence, recurrence,
missing classifications, privacy suppression, practice separation, and periods.
No live Supabase call, auth change, migration, UI change or persistence occurs.

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
Phase 5 resolves the PyTorch exclusion by running the model's published ONNX
artifact directly, without installing the Sentence Transformers Python package.
See [analytics-clustering.md](analytics-clustering.md) for the runtime decision,
approved-excerpt input, provenance, synthetic evaluation and optional requirements.

## Verification

Run from `apps/api` with Pydantic v2 and pytest:

```sh
python -m pytest --confcutdir tests/analytics tests/analytics -q
```

`--confcutdir` isolates boundary tests from the parent conftest that imports the
whole mock LMS and SQLAlchemy. Run the existing application suite when backend
integration starts. No test here contacts Supabase or reads a secret/env file.

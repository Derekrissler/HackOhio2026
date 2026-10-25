# ML clustering integration plan

Implementation checkpoint: the D-side handoff/review/readiness/publication
integration and tutor compatibility boundary are implemented; operational details
are in [analytics-error-integration.md](analytics-error-integration.md). The real
B producer, course-specific semantic validation and provisioned user acceptance
remain required before claiming live ML delivery.

Status: proposed implementation plan; no pipeline changes or database writes are
authorized by this document itself. It is based on the user-provided
`Hackathon_Learning_Analytics_Pipeline_Specification.docx`, sections 6, 8, 9, 14
and 15. Section 8 makes text embeddings optional; evidence-backed error patterns
remain part of the core insights. Workstream B owns extraction/LER production,
D owns analytics/ARRs, E owns interpretation/UI, and G supports integration QA.

## Goal and definition of done

For one course, ingest explicitly classified, evidence-linked mistakes; embed
reviewed short descriptions locally; discover candidate semantic groups; review
their meaning; publish approved groups as versioned `misconception_cluster` ARRs;
and show authorized instructor summaries and approved exemplars with provenance.
Existing statistics must remain available when clustering has no usable input,
no groups, missing model files, or rejected groups. Similarity is not proof of a
misconception, causal diagnosis, or calibrated mastery.

Done requires a reviewed course-data evaluation, a successful controlled
publication/readback, and real user-session access verification. A synthetic
fixture proves integration mechanics, not live course readiness or model quality.

## Current state and first dependency

Already implemented:

- `text_preparation.py`: error eligibility, evidence checks, text normalization,
  one observation per LER/error code, and explicit privacy-review attestation.
- `embeddings.py`: pinned MiniLM model artifacts, CPU ONNX inference, local-only
  loading by default, pooling/normalization, hashes and bounded in-memory caching.
- `clustering.py`: cosine DBSCAN, partitions, distinct-LER thresholds, medoid
  exemplars, assignments/noise, descriptive diagnostics and provenance.
- `service.py`, `arr_generation.py`, `repository.py`: optional clustering within
  versioned bundles, cluster ARRs, suppression and staged publication.
- `dashboard.py` and `InstructorAnalytics.tsx`: staff aggregate summaries of
  published groups; raw exemplars are currently omitted from HTTP DTOs.

Read-only live preflight on 2026-10-24 for VIBE 101
(`94c2f9d7-6940-463f-aa55-f09f66a35835`) found 555 current LERs, **zero
`ler_errors` rows**, zero error-evidence links, and zero versioned analytics
metadata/completed classification indicators recognized by the current adapter.
This is an upstream data gap, not only a field-renaming issue. No raw student
text was retrieved for this inventory. The previously published score run remains
historical output; ML will use a new run and current source revisions.

The requested main pull reconciled local Phase 7 commit `b3bb285` with remote
`714ad76`, preserving the existing README/dashboard notes. The new tutor introduces
ARR schema and student-session retrieval handoffs that must be resolved before
live delivery; see [analytics-roadmap.md](analytics-roadmap.md). No force-push,
schema execution or shared database write was part of the pull.

## Milestone 1: agree and validate the B-to-D handoff

Deliverable: one versioned error handoff contract, positive/negative fixtures,
and an adapter to the analytics models already present. Confirm the producer's
actual format before changing its writer; `payload.analytics_v1` is our proposed
namespace, not a requirement imposed by the specification.

| Input | Producer responsibility | Analytics validation |
|---|---|---|
| Classification completion | Explicit completed/not-completed/unknown semantics | Do not equate missing tags or a score with completed classification |
| Error record | Stable error UUID, current LER UUID, taxonomy code, review status | Code and joins exist; rejected errors excluded; unreviewed policy explicit |
| Error evidence | References to original question/feedback evidence | Same course and learner ownership; references belong to the error |
| Outcome association | Explicit outcome IDs when known | Validate mapping membership; do not infer attribution from the question alone |
| Description candidate | Short grounded error description or permitted feedback excerpt | Treat as unreviewed until the text review below is completed |
| Revision and provenance | Extraction/model version, source revision and status | Preserve current/superseded semantics and source freshness |

Workstream B must actually classify the relevant evidence and write validated
`ler_errors` / `ler_error_evidence` records through server code. Do not generate
errors from low grades alone, set completion flags just to pass preflight, or
create new taxonomy codes without the agreed taxonomy process. Existing analyzed
LERs must be corrected through **new append-only LER revisions**, not edited in
place. Coordinate these writes with the database owner; no migrations, resets or
reapplication of existing SQL are needed for the planned integration.

The adapter should support the agreed version and reject unknown/conflicting
versions clearly. If B adopts `analytics_v1`, preserve its explicit boolean and
`error_outcomes` semantics. If B already has equivalent fields, translate them
through a documented adapter rather than demanding duplicate metadata.
Keep outcome attribution unknown where unavailable: text grouping may still be
possible, but outcome-specific error prevalence cannot be fabricated.

If B's producer is not ready, use an offline, explicitly fictional fixture to
implement this milestone and subsequent mechanics. Do not publish invented
errors into the shared course or claim those fixtures are live extraction.

## Milestone 2: reviewed description export

Deliverable: a versioned, private JSON export accepted by the existing
`--excerpts` entry point, plus validation and an example using fictional IDs.
For the MVP, use a local review/export process rather than build a new web review
application. Candidate text may come from a specifically selected
`ler_errors.misconception` or authorized feedback field; never bulk-load arbitrary
LER payloads or automatically treat model-generated prose as approved.

Proposed wrapper fields:

- `schema_version`, `course_id`, `extraction_version`, opaque `reviewer_ref`,
  timezone-aware `reviewed_at`, and `review_revision`.
- `entries`, each containing `ler_error_id`, `ler_revision`, and the existing
  `ApprovedErrorText` fields: `ler_id`, `error_code`, `text`, `source_kind`,
  `evidence_ref_ids`, `privacy_reviewed: true`.

Validate each entry against the current LER/error/evidence joins, including its
revision. Convert valid entries into existing `ApprovedErrorText` objects for
the engine. Use at most one semantic observation per LER/error code; multiple
snippets/tags cannot manufacture cluster density or inflate prevalence.

The reviewer checks source grounding, removes unnecessary identifiers and
protected answer content, and preserves mathematical symbols and negation.
This is a deliberate review with attribution, not an automatic PII guarantee.
An opaque reviewer reference is attribution supplied by the trusted operator,
not independent proof of an authenticated reviewer identity.

Compute the export digest from validated content; do not trust a caller-supplied
checksum. Retain the review revision/digest and approved text in restricted run
provenance; never expose reviewer identity or private manifests in dashboard DTOs.
Store live exports under gitignored `data/analytics-runs/`; commit only fictional
examples. Preserve legacy excerpt arrays for fixture/local dry runs, but require
the versioned reviewed export for new live cluster publication.

Corrections or revocations of source text/review after publication must go
through B as a new LER revision and a new export. A local JSON edit alone is not
a database invalidation mechanism. This revision rule is part of the handoff;
a separate centrally revocable review store is outside this MVP.

## Milestone 3: ML readiness and candidate analysis

Extend the CLI with:

```text
readiness --course COURSE-UUID --cluster --excerpts REVIEWED-EXPORT --model-cache CACHE
analyze   --course COURSE-UUID --cluster --excerpts REVIEWED-EXPORT --model-cache CACHE --save-bundle
```

The first is a proposed extension; the analyze command's core flags already
exist. Readiness reports counts and safe reason codes, including classification
coverage, eligible distinct LERs/students, accepted/rejected excerpts, partition
sizes, model/dependency availability, and expected publication eligibility.
It performs no model downloads, embeddings or database writes. Do not label a
missing input/model as an empty successful ML result. A valid run with no density
groups is different from a run that could not execute.

Reuse existing defaults initially:

- Pinned `sentence-transformers/all-MiniLM-L6-v2` artifacts with local ONNX CPU
  inference; no new embedding provider, training job, PyTorch or GPU dependency.
- Course/origin/assistance partitions; independent graded evidence separate from
  practice. Preserve latest eligible classification and duplicate handling.
- DBSCAN cosine distance, `eps=0.25`, `min_samples=3`; at least six distinct LERs
  per partition; at most 2,000 texts. Keep noise unassigned.
- Groups need at least three distinct LERs to be internal candidates. Publication
  additionally requires at least five distinct students by the current cohort
  suppression policy. Five snippets from one student do not meet that rule.
- Existing representative error code plus medoid excerpt; membership can span
  codes when the text supports similarity. Do not cluster on taxonomy labels
  alone or force every mistake into a group.

Print only summaries in CLI output. Save candidate members/exemplars privately
for review. Attach model artifacts, preprocessing/configuration, excerpt digest,
review revision and source snapshot to provenance. Keep score-only bundle format
and hashes compatible; add optional ML provenance only to new clustering runs.

## Milestone 4: evaluate and review cluster meaning

Create a reviewed course-specific evaluation set, targeting 20–40 short fictional
or authorized excerpts with paraphrases, unrelated mistakes, opposite meanings,
near-duplicate wording, symbols and negation. Include enough distinct learners
and LERs to exercise the real thresholds. Keep development examples separate
from acceptance examples; hold out questions/learners where feasible. If data are
too sparse, report limited evidence instead of claiming validated model quality.

Tune on the development set only; freeze per-run configuration before acceptance.
The previous seven-comment synthetic test is a smoke test and cannot choose the
course threshold on its own. Report pairwise precision/recall against reviewed
relationships, noise coverage, false mergers, split groups, group-size/student
counts and runtime. Silhouette/cohesion are descriptive checks, not semantic
ground truth or educational confidence. Prioritize avoiding false mergers;
high noise is acceptable, but an all-noise result does not demonstrate useful
clustering. The reviewed acceptance fixture must recover at least one intended
family without joining the explicitly opposed/unrelated examples to it.

Text privacy review and cluster interpretation review are separate. For the
controlled course run, a reviewer inspects every proposed published group and
its supporting excerpts and records approved/rejected decisions. No LLM naming
or recommendation generator is needed in this integration.

Implement a private cluster-review manifest/template containing source,
validated excerpt, configuration and model digests, reviewer attribution/time,
and decisions keyed by a deterministic group-content digest. The content key
uses member observation identities and partition/model/config identity, never
run-local cluster UUIDs alone. Pending groups cannot be published as findings.

Workflow: analyze candidates -> review the generated template -> analyze again
with `--cluster-review REVIEW-DECISIONS` -> inspect the final publishable bundle.
The second run gets a new run UUID, verifies all reviewed input/group digests,
and includes only approved groups. Changed sources, snippets, model, config or
membership require renewed review; there is no fuzzy reuse of old approvals.
Validate review scope and decisions before freezing the final snapshot/ARRs;
do not hand-edit persisted bundles or silently change a completed run's content.

## Milestone 5: publish, retrieve and display

Extend live cluster publication validation to require valid excerpt and cluster
review provenance for every cluster ARR. Score-only publication remains supported.
Preserve current publication serialization, staging, exact lineage verification,
idempotent retries and historical runs. Obtain fresh confirmation that course
writers are paused for the new publication; earlier trial approval is not a
standing claim that writers remain paused. No schema or RLS changes are planned.

Use existing `analytics_runs`, `analytics_results` and `arr_ler_links`. Save
approved groups as `misconception_cluster` results, keeping noise, candidate
diagnostics and rejected/pending groups in restricted run metadata. Report
unique-student counts separately from text/error/observation counts. A cluster's
student count is not automatically a prevalence rate; that needs an explicit
assessed denominator. Membership supports evidence of similarity, not causation.

Extend staff display DTOs/UI with an approved representative excerpt,
descriptive group label/code, distinct counts, outcome context and interpretation
limits. Keep source IDs/private manifests out of summary payloads. Add a separate
JWT-authorized staff evidence endpoint for drill-down to permitted source refs;
retrieve evidence with the user session, never serve unrestricted service-role
rows. Do not expose course-wide clusters to student accounts. Student-specific
IR/tutor explanations remain a separate E/F handoff.

Add real instructor/TA/student enrollments and correct identity mappings via the
auth/database owner before user-session acceptance. These are access prerequisites,
not substitutes for ML training data. Verify student A/B isolation, staff-only
cluster access, suppression, stale-result blocking and exemplar visibility.

## Files to change or add

Paths below are relative to `apps/api/app/analytics/` unless stated otherwise.

| File | Planned change |
|---|---|
| `error_handoff.py` (new) | Agreed producer DTO/adapter, explicit completion semantics, version validation |
| `reviewed_excerpts.py` (new) | Versioned excerpt export, revision/ownership validation, audit digests |
| `cluster_review.py` (new) | Candidate content keys, review template and decision validation |
| `evidence_repository.py` | Read the agreed minimal producer fields and error joins; no arbitrary payload mining |
| `text_preparation.py` | Reuse core preparation; expose accurate exclusions and provenance as needed |
| `service.py` | ML readiness, reviewed optional path, frozen review provenance, score-only compatibility |
| `cli.py` | ML preflight, versioned exports, review-template output and `--cluster-review` |
| `arr_generation.py` | Publish approved, cohort-eligible groups only; retain accurate lineage |
| `repository.py` / publication validation | Enforce new live ML review requirements without changing old run identities |
| `dashboard.py`, `routers/analytics.py` | Sanitized approved exemplars and staff-only evidence drill-down |
| Web types/page/tests | Group display, exemplar/evidence view, correct empty/unavailable/review states |
| Analytics tests/docs | Producer contract, review, compatibility, evaluation and end-to-end fixtures |

Changes to B's writer are a coordinated producer deliverable; there is no
confirmed extraction producer implementation in this checkout. Do not hide
that dependency inside an analytics reader or expand this task into a new OCR/LLM
extraction system without explicitly changing scope.

## Verification and acceptance

1. Contract tests: unknown/completed/no-error states, wrong versions, ownership,
   bad IDs, missing evidence/outcome associations, rejected tags, superseded LERs.
2. Review tests: unreviewed/mismatched/oversized text, linked evidence, reviewer
   attribution, revision mismatch, changed export/model/config/group approvals,
   pending/rejected groups, and no automatic privacy attestations.
3. Clustering tests: deduplication, assistance partitions, distinct LER/student
   thresholds, noise, ordering stability and missing/invalid/overlong model input.
4. Integration: fictional evidence -> agreed adapter -> reviewed excerpts -> real
   cached MiniLM -> candidate review -> final cluster ARRs -> simulated storage
   and authorized API display. Statistics remain numerically unchanged.
5. Compatibility: old score bundles/complete-run hashes and retry behavior remain
   valid; source correction/revocation invalidates affected results; no secrets or
   unapproved raw text enter public responses, logs or committed fixtures.
6. Live controlled trial: readiness passes, source/exemplars reviewed, at least one
   valid accepted group where the data support it, exact result/link readback,
   no duplicate retry, and real JWT role tests. No forced clusters to satisfy a demo.

Run targeted tests during development, then the backend regression suite, cached
model evaluation, frontend tests and production build once the integration is
complete. Never rerun migrations or modify actual grades for testing.

Implementation order: repository reconciliation -> B/D contract and fixture ->
reviewed export/preflight -> candidate evaluation and cluster-review mechanism ->
publication guards -> authorized UI/evidence -> controlled live acceptance.
The blocking external dependencies are B's real classified LER output and the
auth/database owner's user enrollments. Both can be tested with offline fixtures
while awaiting the live handoffs.

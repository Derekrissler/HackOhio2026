# Analytics direction after the latest main pull

Implementation checkpoint: the authenticated tutor/ARR bridge, strict completion
adapter, fictional B-to-D fixture, reviewed excerpt export, ML preflight,
cluster-review binding/publication gates and staff evidence display are now
implemented. See [analytics-error-integration.md](analytics-error-integration.md)
for actual commands and remaining live-data/account prerequisites. The milestones
below retain the design context; the B extraction producer and live user/RLS
acceptance have not been supplied by these changes.

Planning baseline: remote `main` through `714ad76` (Carmen Study Tutor), merged
with the local Phase 7 analytics commit `b3bb285`. Local analytics notes and the
detailed clustering plan were preserved. This document proposes the next work;
it does not authorize database migrations, source reclassification or publication.

## Where this is going

```text
Canvas questions, responses and instructor feedback
  -> B: evidence-backed LERs, outcome mappings and classified errors
  -> D: deterministic statistics + optional reviewed semantic clusters
  -> versioned, evidence-linked ARRs
  -> E: separate student/instructor explanations and dashboards
  -> F: authorized course retrieval and guided tutoring
  -> later: practice LERs and refreshed analytics
```

The first complete slice should explain one real, grounded mistake and connect
it to an outcome, a correct statistic and an authorized course resource. ML adds
group discovery; it is not required to establish that evidence chain. Student
scores remain observed performance, never unvalidated predictive mastery.

## What the pull adds and what remains

| Area | Current implementation | Remaining integration |
|---|---|---|
| Carmen ingestion | More complete quiz item/response export, protected keys, local role tests | Coordinate new exports with source revisions; do not assume re-exported data are already analyzed |
| Statistics/ARRs | Live score run published: 163 results, 27,750 verified dependency links | Feed explicit classified errors and verify error statistics on course data |
| ML | MiniLM/ONNX, DBSCAN, eligibility and candidate ARRs already implemented | Real error inputs, reviewed snippets, course evaluation and cluster interpretation review |
| Analytics dashboard | Supabase JWT routes and instructor aggregate UI | Real enrollments/identity mappings and live user-session verification |
| Study Tutor | New Carmen UI, policy modes, retrieval, generation, verifier, session logs, local tests | ARR 1.1 reader compatibility, user-session retrieval, authenticated identity integration |
| Insights/practice | ARR source chain and separate practice statistics supported | Audience-specific IR integration and a complete practice-attempt-to-LER refresh loop |

The tutor's request-matching classifier identifies protected assessment requests;
it does not classify mistakes in graded responses. This pull does not deliver a
Workstream B academic error-extraction producer. The latest recorded ML preflight
found 555 current LERs but zero error rows/evidence links and no completion
metadata recognized by our adapter. Recheck before implementation rather than
assuming that snapshot is permanent.

## Step 1: make the existing components consume the same contracts

Priority: integration prerequisite for real user delivery. Owners: D/F with G
and the auth/database owner.

1. Fix `carmen-study-guide/mock-canvas/tutor/repo.py::weak_outcomes`. It currently
   expects `metrics.observed_score_ratio`, while our schema 1.1 rows store it at
   `metrics.document.metrics.observed_score_ratio`. Prefer a version-aware adapter
   backed by the existing guarded ARR service: validate rows, select a completed
   current run, preserve learner scope, check source freshness, ignore null or
   insufficient estimates, and deduplicate outcome IDs. Do not blindly average
   historical runs or merely move one JSON lookup.
2. Split tutor data access into a user-session read/retrieval client and a
   server-only write/control client. The newly pulled host constructs one
   service-role repository, and `search_resource_chunks` currently runs on it.
   The project rule requires the **logged-in student's JWT** for retrieval;
   `p_student_safe=true` does not replace RLS. Keep session/log writes server-side.
3. Connect authenticated Supabase identity to enrollments and learner mappings.
   Carmen's single mock student/pseudonym and the React demo selector are demo
   fixtures, not authority for shared student records. Coordinate actual account
   setup with its owner rather than invent mappings from display names.
4. Add contract and role-isolation tests: known schema 1.1 scores yield correct
   weak-outcome IDs, stale/incomplete/insufficient results do not; student A cannot
   read B's context or staff-only data; the RPC receives the user's credentials.

Completion: a verified user can consume a current authorized score ARR in both
the dashboard and tutor, and an old/private row cannot bypass the shared reader.

## Step 2: finish the B-to-D error handoff

Priority: first new data capability. Owners: B produces, D adapts, G tests.

- Agree the actual producer schema, completion semantics and error taxonomy.
  `payload.analytics_v1` is our proposed namespace, not a specification mandate.
  Adapt equivalent existing producer output when available.
- Each classified mistake needs an error code/review status, original evidence
  references and explicit outcome attribution where supported. Completed with
  no detected errors must be distinguishable from not processed/unknown.
- Begin with 10–20 reviewed fictional examples, including a known error,
  completed-with-no-errors, unknown/insufficient evidence and multiple outcomes.
  Include at least five distinct learners in a prospective publishable group;
  repeated snippets from one learner cannot substitute for cohort size.
- Ground labels in question/response/feedback. A low score alone does not identify
  an error. Technical failures remain job failures, not academic diagnoses.
- B writes new append-only LER revisions and existing error/evidence child rows
  through server code. Never edit existing LERs in place, fabricate tags for the
  existing 555 records, or rerun schema migrations.

Completion: one agreed fixture passes the producer/consumer validators, and live
readiness reports genuine completed classifications and eligible error events.
If B is external or not ready, implement the adapter against an offline fixture;
do not quietly turn D into a new OCR/LLM extraction workstream.

## Step 3: deliver error-pattern insights with deterministic analytics

Owner: D, then E for presentation. Use the statistics already implemented.

- Verify recurring error counts, distinct attempts/questions, unique-student
  prevalence, explicit eligibility denominators and missing-classification
  coverage against a hand-calculated fixture.
- Keep assisted practice separate, reject ambiguous attribution, and apply cohort
  suppression consistently. No rate may use unclassified responses as evidence
  of no errors.
- Produce a new reviewed run; preserve the prior score run as history. Confirm
  course writers are paused before a controlled publication and verify readback,
  lineage, retry behavior and source freshness afterwards.
- Hand E typed evidence-bearing error summaries and interpretation limits. This
  enables grounded "what went wrong" insights before semantic clustering ships.

Completion: a student/instructor explanation cites an actual tagged error and
its supporting evidence, with statistics that reconcile to eligible LERs.

## Step 4: integrate the optional ML path

Owner: D with B's input and a designated reviewer. Detailed contracts, file
changes and tests are in
[analytics-clustering-integration-plan.md](analytics-clustering-integration-plan.md).

1. Export short descriptions/feedback excerpts after grounding/privacy review,
   with source LER/error revisions, evidence IDs and review provenance.
2. Add ML preflight for eligible text, distinct LER/student support and pinned
   local model availability. Explicitly report insufficient/unavailable/no-group
   outcomes while leaving ordinary statistics usable.
3. Reuse local MiniLM + cosine DBSCAN. Evaluate course-specific examples and
   opposite/unrelated mistakes; tune on development examples and keep acceptance
   examples separate. Retain noise rather than force a cluster.
4. Review candidate groups' meaning and medoid exemplars separately from input
   privacy review. Only approved groups meeting cohort thresholds enter a new
   `misconception_cluster` ARR publication.
5. Show authorized instructor group summaries, approved exemplars and evidence
   drill-down. Similarity/cohesion are not a confidence probability or proof of
   a shared misconception. Cluster counts are not prevalence without a declared
   assessed denominator.

Completion: at least one defensible group where the data support it, reviewed
and saved with model/config/input provenance and exact lineage, displayed only
to authorized staff. An all-noise run can be a valid result but cannot demonstrate
the usefulness of the grouping feature by itself.

## Step 5: close the demonstration loop

Owners: E/F/G with D's outputs.

- Student view: own observed outcome performance, one supported mistake, evidence
  citation and a released resource. Instructor view: reconciled class rates and
  approved mistake groups, with audience-specific interpretation.
- Tutor: boost retrieval from the student's eligible current ARR, enforce policy
  and use the student session for resource search; keep server-only logs private.
- Add a practice-attempt producer only after its scoring, assistance and LER
  contract is agreed. A tutor conversation or hint log is not automatically a
  graded practice result. The new tutor commit does not itself close this loop.
- Demonstrate correction/invalidation/recomputation with isolated fictional
  evidence, not edits to real grades. Current retrieval blocks stale results;
  automatic recomputation still needs orchestration.

## Deferred work

Validated predictive mastery, new embedding models, training/fine-tuning,
institution-wide ingestion, broad review UI, calibrated educational efficacy,
and production scheduling are separate scope decisions. Longitudinal trend
calculations need explicit timing/coverage policies before implementation.

## Verification and next concrete deliverable

For this pull, run the new tutor unit tests and local Carmen export/API tests
with the shared-database live tests excluded. Those tests establish local
behavior, not student-JWT/RLS compliance or correctness of the ARR bridge.
Post-merge verification: **65 tests passed** across the non-live tutor suite
and `tests/test_part_g.py`; neither shared-database live test module was collected.
Run analytics/frontend regressions when integration changes actually touch them.
Do not execute `tutor.demo_setup --apply`, live tutor tests, exports that invoke
the optional database writer, or new/existing migrations as a planning step.

Next implementation deliverable: a tested schema 1.1 ARR-to-tutor adapter and
agreed B-to-D error fixture, alongside the authenticated retrieval boundary.
After that, enable error statistics, then the reviewed clustering workflow.
Live error production, account provisioning and publication remain explicit
coordinated steps; no shared database writes are part of this plan update.

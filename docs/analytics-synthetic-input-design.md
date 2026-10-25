# VIBE 101 synthetic error-classification overlay: Phase 2 design

Phase 2 design recorded on 2026-10-25. This document preserves the approved
design and phase gates. The subsequently implemented Phase 3 subset and actual
commands are documented in [analytics-synthetic-inputs.md](analytics-synthetic-inputs.md).
Later-phase operations below remain proposals, not available commands.

## Purpose and scope

Simulate the upstream error-classification component for the existing VIBE 101
course, then use the actual analytics engine to discover patterns. Preserve
course `94c2f9d7-6940-463f-aa55-f09f66a35835` (mock Canvas `1001`); do not create a
new course. Operate on a private local copy. Do not write classifications,
evidence, taxonomy entries, completion flags, or ARRs to shared Supabase.

The dataset combines original recorded performance with hypothetical error
classifications. It is not a new measurement of student mistakes. A missing
answer or lower grade does not substantiate a specific misconception. Original
scores, questions, assessments, responses, feedback, outcome mappings, mapping
review flags, assistance, LER IDs/revisions, and semantic analysis statuses must
remain intact. Do not introduce real names or authentication identity mappings.

The generator supplies classifications and descriptions, never embeddings,
similarity scores, group membership, medoids, final cluster IDs, or cluster ARRs.
AWS, Bedrock, and another language-model provider are not needed for this
deterministic input generator.

## Inspection findings and limits

The local saved run `51828a2e-4ba4-418c-bcc3-32cce5f1f36f` and its source-review
context contain 555 current LERs, 15 learners, 553 analyzed and two insufficient
LERs, 551 selected independent score observations, seven outcomes, and no error
events. There are 165 LERs with earned points below possible points before
primary-observation selection. All 555 records are graded and independent.

The saved taxonomy is empty. Of 96 question/outcome mappings, 80 need review.
No generator action changes those review flags or verifies course outcomes.
These findings describe saved snapshots, not a new live database audit.

Some individual quiz questions have only three learners with lost points. The
assignment-level tasks offer broader context: the saved data has 15 such
responses with lost points for Assignment 1, 14 for Assignment 2, and 15 for
Assignment 3. These counts precede feature eligibility and do not guarantee an
eligible or coherent cluster. Exam whole-assessment records must still follow
the existing parts-preferred selection rule.

The actual questions are about prompting, code review, testing, debugging,
security, privacy, licensing, documentation, and appropriate AI use. Existing
inequality/unit-conversion test fixtures are software examples, not a curriculum
source for this demonstration.

## Existing contracts to preserve

| Boundary | Existing implementation and required behavior |
|---|---|
| Normalized input | `contracts.AnalyticalInput`: strict DTO, graded-response relationships, scores, mappings, errors, evidence, revision/currentness, assistance, semantic status. |
| Completion | `error_handoff.ErrorHandoffMetadata`: strict boolean/null `errors_analyzed` in `payload.analytics_v1`, schema `1.0`, outcome weights, explicit error UUID/outcome UUID associations. |
| Join and ownership | `evidence_repository.SupabaseEvidenceRepository.load_course`: course, learner, related rows, evidence ownership, mapping ownership and error support checks. |
| Feature policy | `features.build_features`: supersession, conflicting duplicates, latest valid attempts, primary independent error selection, and whole/part overlap rules. |
| Text preparation | `text_preparation.prepare_error_texts`: eligible error events, explicit privacy review, linked evidence, one excerpt per LER/code, NFC/whitespace normalization. |
| Text review | `reviewed_excerpts.ReviewedExcerptExport`: exact course, LER/revision/error identity, source evidence, reviewer, timestamp and digest. |
| ML | Pinned local MiniLM ONNX, 384-dimensional normalized vectors, existing cosine DBSCAN. |
| Group review | `cluster_review.ClusterReview`: source/text/model/config/membership binding; pending, approved or rejected decisions. |
| Results | `arr_generation.ARRDocument`, schema `1.1`; `service.AnalysisBundle` for frozen inputs, lineage, provenance and typed results. |

Keep defaults: six distinct LERs per partition, DBSCAN `min_samples=3`, at least
three distinct LERs in a retained candidate group, five distinct students for an
aggregate cluster ARR, cosine-distance epsilon `0.25`, maximum 2,000 texts per
partition, and small-cohort suppression. A partition is course/origin/assistance.
The default permits unreviewed error classifications; that permission does not
replace description privacy/context review or group interpretation review.

## Architecture

```text
Read-only source snapshot and question context
  + versioned rules + seed
  -> synthetic overlay + manual scenario evidence + pending text candidates
  -> ownership, preservation and contract validation
  -> human text decisions -> existing ReviewedExcerptExport
  -> existing features -> MiniLM -> existing DBSCAN
  -> pending group decisions -> existing ClusterReview
  -> existing ARR generator with explicit demo provenance
  -> local labeled fixture presentation (later phase)
```

Use one source copy per run. Overlay classifications on copied rows; do not feed
both original and modified rows with the same LER identity into feature building.
Preserving LER IDs/revisions in this offline counterfactual does not represent a
database correction. No append-only database revision is inserted or superseded.

### Snapshot capture

A proposed operator-only snapshot command will compose the existing analytics
reader with the read-only context reader in `source_repairs.read_source`.
The latter lacks learners, attempts, and assessments, so it is not sufficient by
itself. The analytical batch supplies those relationships and the baseline used
for score comparison; context supplies question text, outcome text, existing
feedback and the taxonomy. Exclude authentication tables and real identity maps.

Capture fingerprints before and after the context read and verify cross-object
IDs/hashes and projected context consistency. Reject a capture if relevant source
data changed. Multiple reads are not a transaction and cannot establish an atomic
database snapshot; record that limit. Analysis thereafter uses only the frozen
local snapshot. A stable snapshot is required; do not silently mix old LER IDs
with a current review packet. No database write or writer pause is required for
this local workflow; report unstable capture instead of claiming consistency.

### Shared validation boundary

Extract the existing manifest-to-envelope assembly from `load_course` into a
pure `assemble_evidence_batch(course_id, manifest)` helper. Keep query/pagination
in the live repository. Both the live reader and proposed offline demo source
call the helper. The demo source additionally validates all manifest identities,
foreign-key targets, taxonomy codes and overlay invariants before assembly.

The existing `FileEvidenceSource` accepts already joined arrays and constructs
only a minimal source manifest. Leave its legacy behavior unchanged; do not use
it as the complete validation boundary for the new demo.

`ReviewedExcerptExport.approved_inputs` currently checks exact error row IDs and
error/evidence links only for `live=True`. Refactor that check into a reusable
row-validation helper and require it for the full-manifest demo path too, while
preserving legacy fixture behavior. The offline source must not pretend to be a
Supabase source to obtain stronger validation. No test-only fake SDK is imported
by application code.

## Proposed artifact contracts

All new models inherit the strict project `Contract`; unknown fields are errors.
UUID relationships, hashes and aware timestamps are typed and validated. The
types below are design names, not changes to `AnalyticalInput` or SQL tables.

| Proposed type | Required contents |
|---|---|
| `DemoSourceSnapshot` | Schema `1.0`, course ID, base `EvidenceBatch`, private curriculum/source context, capture time, base batch fingerprint and stable context/snapshot digests. |
| `SyntheticGenerationConfig` | Generator/rules version, seed (default `2026`), requested target range, exact question/theme bindings and bounded per-LER/per-theme selection policy. |
| `SyntheticClassification` | Existing LER ID/revision, state, selection basis, synthetic error objects, legitimate context IDs and explicit hypothetical origin. |
| `SyntheticError` | Deterministic error UUID, LER ID, local taxonomy code, one description, explicit allowed outcome IDs, generated manual evidence IDs, `instructor_status=unreviewed`. |
| `SyntheticEvidenceOrigin` | Generated evidence UUID, `synthetic=true`, scenario ID, original LER/question/response context IDs, source snapshot digest and generator version. |
| `ExcerptCandidate` | Error/LER/revision/code/text/evidence identity, decision `pending/approved/rejected`, privacy attestation initially false, context/label attestation initially false, reviewer/time initially null. |
| `SyntheticDemoManifest` | Dataset kind, dataset ID, source snapshot digest, overlay digest, seed, generator/rules versions and config digest, counts, theme bindings, per-record source relationships, generated time and limitations. |

`dataset_kind` is the exact constant `synthetic_error_classification_overlay`.
Record that original performance is retained and error classifications are
synthetic. Every error and generated reference must have a corresponding origin
entry. A scenario's theme is input provenance, never a final ML cluster label.

Review candidates are not `ApprovedErrorText`: that existing type requires
`privacy_reviewed=True`. Only explicit, attributed human approval can produce a
`ReviewedExcerptExport` entry. Reviewer attribution remains an operator
attestation, not a new authenticated instructor endorsement.

### Classification state rules

| Synthetic state | Overlay completion | Error list | Meaning |
|---|---|---|---|
| `completed_with_errors` | `true` | At least one valid synthetic error | A simulated completed classification with hypothetical mistakes. |
| `completed_no_errors` | `true` | Empty | A simulated classification without detected errors; not inferred from a perfect grade. |
| `not_completed` | `false` | Empty | A deliberately unperformed synthetic classification. |
| `ambiguous` | `null` | Empty | The scenario has no accepted error determination; any speculation stays outside the accepted error list. |
| Untouched source record | Preserve source value | Preserve source list | No classification is invented for every remaining LER. |

`analysis_status`, `insufficiency_reason`, scores and assistance never change.
The original two insufficient LERs stay insufficient and are excluded by current
eligibility policy. Unknown completion remains distinct from completed/no-error.
State labels always live inside the demo artifact, never shared LER metadata.

### Evidence rules

Create deterministic, local `evidence_refs`-shaped objects with
`source_type=manual`, the legitimate course/learner IDs and a content hash. Use a
clearly synthetic `canvas_ref` locator such as `synthetic-demo://<dataset>/<id>`;
it is not a claim that a Canvas API object exists. Excerpt wording identifies a
generated hypothetical classification, not an observed student quote.

Set `document_id`, page and bounding box to null. Do not create a feedback row,
fake annotation, original instructor quotation or fake PDF. Preserve existing
references. Link each synthetic error only to its generated scenario evidence;
store original academic context relationships separately in the origin map.
Include the new refs in the copied LER's evidence union and error-evidence links.
They document the simulated input's origin, not proof that the mistake occurred.

Use `source_kind=error_description` for approved text. Keep synthetic labeling in
provenance and presentation rather than adding identical banner text to every
embedded description, which could bias semantic similarity.

## Curriculum and allocation rules

Resolve exact question UUIDs from the frozen snapshot. Bind each rule to its
assessment/question identity and question-content digest, not a repeated label
such as `Q5` or a broad keyword match. Use a vetted, versioned rule catalog with
the actual task context. Reject ambiguous bindings or changed question content.

| Proposed theme/code | Appropriate source context | Permitted outcome intent |
|---|---|---|
| `missing_prompt_constraints` | Assignment 1 requirements; strongest-prompt and prompt-component questions; prompt-spec rubric parts with full parent context. | LO-02, where already mapped. |
| `missing_edge_case_tests` | Assignment 2 required empty/singleton/identical-input cases; Assignment 3 average-of-empty-list task; maximum-of-empty-list quiz question. | LO-04; LO-03 only when the existing mapping and scenario support it. |
| `sql_injection_risk` | Assignment 3 string-built SQL, the SQL-injection quiz, or supported security-review rubric context. | LO-05, where already mapped. |
| `unsafe_secret_handling` | Assignment 3 hard-coded-key task, secret-storage and key-exposure questions, or relevant project requirements. | LO-05, where already mapped. |
| `debugging_by_regeneration` | The repeated-prompt question or a task explicitly contrasting diagnosis with regeneration. | Only existing mapped outcomes; do not inject LO-04 if the question currently maps to LO-02/LO-06. |
| Rare/negative scenarios | Licensing, privacy disclosure, mutable defaults, prompt-log purpose, or other supported curriculum contexts. | Explicit subset of the source LER mappings; no automatic all-outcome attribution. |

These are local demo taxonomy entries if absent from the snapshot. Do not insert
them into shared `error_taxonomy`. Preserve existing taxonomy definitions and
reject a conflicting local code definition. Preserve mapping `needs_review` and
`instructor_verified` flags, and report unresolved mapping quality in the demo.

Use a seed-shuffled, stable sorted candidate list and allocate across existing
learners and applicable questions. Start from eligible analyzed observations
with lost points; preserve the latest-attempt and parts-preferred policies.
Unscored or missing-answer contexts do not become observed misconceptions.
When only question/grade context exists, label the scenario
`hypothetical_from_question_context`, including missing-answer limitations.

Aim for 40-80 error-bearing LERs if the snapshot supports that many appropriate
cases, with 1-2 different codes at most per LER and a default maximum of one.
Use assignment context to increase participation only where its actual task and
mapped outcomes support the theme. Never expand into unrelated questions or
alter grades to meet a quota. Report actual counts and shortfalls, including
distinct eligible students/LERs per theme and partition. No final cluster quota
is promised. Include no-error and unknown cases, plus unrelated mistakes that
may become noise; DBSCAN determines whether they actually do.

Description variants come from a curated template bank and describe the same
underlying error without identical copies. Examples for the edge-case theme:
"Tests omit the empty-input case before accepting the generated function" and
"The test set covers ordinary lists but never checks an empty list." These are
design examples, not generated classifications for any learner. Do not conflate
all testing mistakes into one target group or remove difficult examples after
seeing clustering output. Keep theme IDs out of the embedded text.

## Reproducibility and preservation

Derive a stable UUID namespace from `hackohio2026:synthetic-error-overlay:v1`
using UUIDv5. The dataset ID derives from source snapshot digest, generator/rules
versions, seed and config digest. Derive scenario, error and manual evidence IDs
from the dataset ID and stable source/code/variant identities. Reject any
collision with original IDs. Sort inputs explicitly; do not use Python's
process-randomized `hash()` or depend on database return order. Use a local RNG,
never mutate global random state.

The dataset-content digest excludes execution timestamps and later review
decisions. Given the same frozen source, versions, configuration and seed,
classifications, text variants, IDs, associations and substantive counts match.
The manifest still records an aware generation time. New reviews and ML runs
have their own digests, IDs and times; they are not claimed byte-for-byte equal.

Retain a pristine source copy. Compare protected rows/fields canonically before
and after overlay. Only the explicit demo completion namespace, generated
errors, synthetic evidence and local taxonomy additions may differ in the
materialized input. Preserve unrelated payload keys and preexisting completion
weights/attribution. Do not overwrite an existing completed classification;
skip/report it unless a later approved design explicitly handles it.

Compare baseline and demo score metrics using the same config, period and source
selection: selected score LERs, normalized weights, earned/possible totals,
observed ratios and cohort denominators must match. Full ARRs will have changed
error metrics, dependencies and provenance, so do not require complete JSON
equality. Missing values remain null.

## Review, provenance and publication boundaries

1. Generation produces pending descriptions, not review approvals.
2. Explicit text decisions verify privacy, curricular fit, synthetic labeling,
   current LER revision and generated evidence ownership. Bind the decision
   packet to the immutable dataset and exact candidate digests; changed text,
   rules or source requires renewed approval.
3. Approved descriptions are exported through the existing reviewed format.
   Synthetic errors remain instructor-unreviewed even when their demo text has
   been approved for use.
4. Actual ML analysis emits candidate partitions, assignments, noise and an
   existing cluster-review template with every decision pending.
5. A reviewer inspects groups and approves/rejects meaning; rerun finalization
   with the bound review. Never automatically approve generated-input groups.
6. Treat any ARRs produced during the initial analysis as candidate-only. Only
   finalized, approved groups meeting suppression policy enter demo presentation.

Add a `synthetic_demo_v1` block to the offline batch source manifest and propagate
its validated provenance into the frozen analysis manifest *before* hashing.
Pass the same block into every ARR's existing provenance dictionary during
generation. Include dataset kind/ID/digest, seed/versions, original source
fingerprint and an explicit mixed-data interpretation limit. Do not append the
label after hashing. `AnalysisBundle` validation must reject missing/inconsistent
demo provenance or a demo bundle claiming `source_kind=supabase`.

No new fields are needed on individual `AnalyticalInput` objects or in shared SQL.
Only the demo path adds the new provenance block; legacy snapshots, hashes and
completed-run retry behavior must remain compatible. The model report still
contains real computed results; all display/export entry points for this demo
must retain the enclosing dataset provenance. Internal stripped group DTOs are
not standalone approved demo exports.

`SyntheticDemoSource.source_kind` stays `offline_fixture`. Keep the existing
publication rejection of offline bundles, and add a defense-in-depth rejection
of the synthetic provenance marker before constructing a privileged publication
client. No demo command exposes an insertion/publish flag. A future shared-data
proposal would need explicit approval and an isolation/reversal design; it is
outside this implementation plan.

## Proposed files and commands for subsequent phases

| File | Proposed change |
|---|---|
| `app/analytics/synthetic_inputs.py` | Typed artifact contracts, rules, deterministic generator, preservation checks and pending review candidates. |
| `app/analytics/synthetic_source.py` | Full-manifest offline source and read-only snapshot composition; private artifact loading, path and digest validation. |
| `app/analytics/evidence_repository.py` | Extract/reuse pure evidence assembly, retaining live query projections and behavior. |
| `app/analytics/reviewed_excerpts.py` | Reuse exact source-row validation for full-manifest demo reviews. |
| `app/analytics/service.py` | Freeze/validate demo provenance and retain offline-only publication restrictions. |
| `app/analytics/arr_generation.py` | Optional validated input provenance, propagated at document creation; no ML changes. |
| `app/analytics/cli.py` | Explicit local demo workflow, truthful pending/validated/candidate/final states and no publish option. |
| `tests/analytics/test_synthetic_inputs.py` | Generator contracts, reproducibility, preservation, ownership, review and publication rejection. |
| Existing repository/integration tests | Live assembly parity, legacy hashes/readback, correct strict demo reviews, genuine cached-model execution later. |

Commands are a proposed interface, not runnable instructions yet:

- `demo snapshot`: read-only capture for the existing course into the private directory.
- `demo generate`: frozen snapshot + rules + seed -> overlay, manifest, pending candidates and summary.
- `demo validate`: validate relationships/contracts/preservation and emit a report, with no inference.
- `demo review-text`: consume attributed human decisions and emit a bound reviewed export; no automatic approval.
- `demo analyze`: invoke existing `analyze_course` with the offline source and reviewed texts; emit pending group review.
- `demo finalize`: consume completed group review and regenerate typed, labeled ARRs through the existing engine.

Gate each operation on prerequisites. Validate/finalize must not regenerate data
implicitly. Generation has no credentials/network dependency after snapshot
capture. Missing model cache is an explicit readiness condition; normal runs do
not download a model. Put all private artifacts under the already ignored path
`data/analytics-runs/synthetic/vibe101/<dataset-id>/`; reject output outside that
root and overwriting a different artifact. Keep source snapshots, manifests,
overlays, evidence, candidates, decisions, reports and result bundles separate.
Commit only source code, public rules/tests and documentation after approval.

## Acceptance gates and phase boundaries

Phase 2 completion is this reviewable design. No application code, source export,
synthetic dataset, approval packet or model output is produced in this phase.

Phase 3, after approval, implements generation and the minimum offline contract
plumbing, then produces a private preview and pending candidates. It stops before
ML inference or any review is approved. Phase 4 adds/completes automated
validation and reports failures as well as counts. Required checks include:

- Original LER/learner/course/question/assessment/outcome relationships exist;
  error outcomes are an explicit valid subset and taxonomy codes resolve.
- Original grades, feedback, response content, source references, mapping
  approvals, statuses, assistance and unrelated payload values are unchanged.
- Every generated error/reference is unmistakably synthetic and belongs to its
  declared source context. No feedback row or fake annotation is created.
- State/error consistency, duplicate LER/code handling, deterministic IDs, stable
  regeneration, unchanged score statistics and retained insufficient cases pass.
- Pending/rejected/changed text cannot become an approved input; changed source,
  text, model/config or membership invalidates the relevant review.
- Removing or changing demo provenance fails at the demo loading/finalization
  boundary; no tagged bundle can enter the production publisher.
- Existing genuine fixtures, legacy bundles and live-reader behavior still work.

Phase 5 requires actual text review and runs unchanged MiniLM/DBSCAN, reporting
groups, noise, members, students, outcome links, medoids, similarities and limits.
If quality is poor, document false mergers, splits and sensitivity; do not
silently alter thresholds, labels or negative examples. Phase 6 requires human
group review before finalized ARRs. Phase 7 separately designs a locally enabled,
clearly labeled fixture view in the existing VIBE 101 interface. Do not inject
demo data into the normal live dashboard/tutor or use a service key to bypass
student access rules. Personalized insight generation remains separate work.

Stop for approval after each phase. No commits, pushes, merges, shared database
writes, migrations, course creation or automated review approvals are included
in the current authorization.

# VIBE 101 local synthetic analytics and review

Phase 3 implements deterministic upstream error inputs for the existing course.
Phases 4-6 add validation, explicit text review, the real local ML path and reviewed
ARR finalization. No command creates a course or writes shared academic evidence.
An explicitly authorized archive operation stores synthetic ML outputs in the
existing Supabase `analytics_runs` table. The Phase 2 design is in
[analytics-synthetic-input-design.md](analytics-synthetic-input-design.md).

## Implemented behavior

- `synthetic_inputs.py` defines strict snapshot, generation configuration,
  classification, generated evidence, pending excerpt, dataset and provenance
  contracts. It binds curriculum rules to actual question UUIDs/content digests
  and valid mapped outcomes. Default seed: `2026`.
- `synthetic_source.py` captures a read-only source snapshot and supplies the
  complete offline source. Capture compares two analytical reads and two context
  reads. It is change detection across REST calls, not an atomic transaction.
- `assemble_evidence_batch` reuses the live reader's joins. The offline path also
  checks table identities, relationships, taxonomy membership, deterministic
  regeneration and source preservation. Its source kind is `offline_fixture`.
- Generated errors use separate `manual` scenario evidence, a
  `synthetic-demo://` locator, null document/page/box, explicit synthetic origin,
  and `instructor_status=unreviewed`. No generated instructor feedback is created.
- Excerpt candidates are always pending with privacy/context review false and
  no reviewer. They cannot be used as an approved text export.
- Provenance enters the frozen analysis manifest before hashing and every ARR
  at construction. Bundle validation rejects missing/inconsistent labels, and
  the publisher rejects tagged synthetic results before repository writes.
  Candidate statistical ARRs are exercised only in fictional integration tests
  during this phase; the actual preview is input data and preservation reports.

No embedding, DBSCAN, SQL schema or RLS policy changes are needed. Existing live
and legacy fixture behavior remains unchanged when no synthetic marker exists.

## Commands

From `apps/api`, use the project's analytics/persistence Python environment
(`requirements-persistence.txt`). Snapshot capture reads the already configured
server-only Supabase settings in `apps/api/.env`; generation is offline and does
not need credentials. No AWS settings are used.

```powershell
python -m app.analytics.cli demo snapshot --output ../../data/analytics-runs/synthetic/vibe101/captures/source-phase3-2026-10-25.json
python -m app.analytics.cli demo generate --snapshot ../../data/analytics-runs/synthetic/vibe101/captures/source-phase3-2026-10-25.json --seed 2026 --target 60
```

The course defaults to the existing VIBE 101 UUID. Another course is rejected.
The generator prints a sanitized count/eligibility summary and a private output
directory. It never prints answers, feedback or excerpt text. Output paths must
resolve under the ignored `data/analytics-runs/synthetic/vibe101/` directory.
Different existing files are never overwritten. A generation retry from the same
snapshot/configuration reuses the original dataset timestamp and content.

Each `<dataset-id>/` directory contains:

| File | Contents |
|---|---|
| `source-snapshot.json` | Pristine analytical batch and private source context; original grades/feedback/IDs are retained. |
| `dataset.json` | Typed overlay, local taxonomy, question bindings, explicit error/outcome associations, synthetic evidence, pending excerpts and content digest. |
| `manifest.json` | Mixed-data provenance, seed/version/configuration, generation time, source digests, theme participation and source relationships. |
| `excerpt-candidates.json` | Pending descriptions for later human review; not an approved export. |
| `preview-report.json` | Source/state/theme counts, requested/actual size and shortfall, score preservation, original-field preservation and limitations. |

These files contain private source data and pseudonymous learner relationships.
Keep them ignored and local. Do not commit them or expose source snapshots as a
browser download. Only the explicitly authorized ML-run archive described below
is copied to shared Supabase; original source snapshots are not uploaded.

## Reading the preview correctly

The intended input themes are prompt constraints, empty-input testing, SQL
injection, secret handling, plus rarer regeneration, mutable-default and licensing
cases. Participation counts are generator input counts, not ML clusters. Some
themes may fail the five-student aggregate minimum. Do not inflate them or label
them publishable discovered groups. The requested target is a cap/goal, not an
instruction to fabricate unrelated scenarios when eligible context runs out.

Completion states are simulated only within the offline overlay:

- `completed_with_errors`: true completion and at least one synthetic error.
- `completed_no_errors`: true completion and no errors, explicitly hypothetical.
- `not_completed`: false completion and no accepted errors.
- `ambiguous`: null completion and no accepted errors.
- Other source LERs remain untouched, including genuine insufficient cases.

The overlay preserves scores and response content. It does not claim that lost
points identify an actual misconception or that a perfect score proves absence
of errors. Scenario evidence documents the simulation, not an original
annotation. Original mapping review flags and outcome verification remain intact.

The fresh capture on 2026-10-25 contains 555 analyzed LERs and 553 selected
independent scores, with zero insufficient LERs. This differs from the earlier
saved Phase 2 inventory (553 analyzed, two insufficient, 551 selected scores).
The newer statuses/grades were already present before the read-only capture;
the generator did not repair or change them. Preservation comparisons use the
fresh snapshot as their baseline, not outdated inventory counts.

## Validation and explicit reviews (Phases 4-6)

Automated regression tests use fictional
source data, including an insufficient case, to check deterministic generation,
preserved scores/source fields, evidence ownership, pending reviews, tampering
rejection, strict error identity checks, ARR provenance and publication denial.
Review tests use controlled vectors to test the actual DBSCAN and ARR wiring
without approving any VIBE 101 description. Automated validation does not establish
semantic correctness or certify privacy. No review is inferred from generation.

From `apps/api`, using the private directory printed by generation:

```powershell
$demo = '../../data/analytics-runs/synthetic/vibe101/584a54ae-0e7c-5882-a45e-f8f53df6448d'
python -m app.analytics.cli demo validate --snapshot "$demo/source-snapshot.json" --dataset "$demo/dataset.json"
```

This writes `validation-report.json`, `text-review.packet.json`, a readable
`text-review.md`, and pending `text-review.decisions.json`. Validation checks
ownership, explicit outcome attribution, contracts, preserved scores/feedback,
original evidence, duplicate identities, completion states, provenance,
reproducibility and insufficient cases. It also reports repetitions and coverage
limits. Retrying does not overwrite a person's decision file.

The user chose to review these packets personally. Leave every actual decision
pending until the user provides it. Completed text decisions need reviewer kind
`human`, an attributed reviewer reference, aware review time, approved/rejected
status for each error ID and notes. Approvals additionally require explicit
privacy/context/synthetic-label attestations. Rejections require reasons. This
is approval of a hypothetical demonstration description, not instructor
confirmation that a real learner made that error. A separately authorized
delegated review must identify itself as `delegated_agent` and record its
authority; it must never be presented as human review.

After the user reviews, the following commands are available:

```powershell
python -m app.analytics.cli demo review-text --snapshot "$demo/source-snapshot.json" --dataset "$demo/dataset.json" --review "$demo/text-review.decisions.json"
python -m app.analytics.cli demo analyze --snapshot "$demo/source-snapshot.json" --dataset "$demo/dataset.json" --review "$demo/text-review.decisions.json" --model-cache ../../.cache/analytics-models
```

Pending, partial, stale, duplicate or insufficiently attributed reviews fail before
model construction. The export validates exact current error IDs and linked
synthetic evidence. Rejected descriptions do not enter the embedding model.
The original generated error classifications remain explicitly hypothetical;
rejecting a description does not edit the frozen dataset or invent a corrected
source observation.

`demo analyze` uses unchanged MiniLM ONNX and DBSCAN with the default config. It
saves a private candidate bundle, `cluster-review-<run>.packet.json` with full
group members and similarity measurements, and a pending decision template.
It does not automatically approve groups or remove noise. The decision template
wraps the existing `ClusterReview` inside demo provenance and a candidate bundle
hash; the reviewer supplies attribution, decisions and an assessment of every
group. Human review of group meaning is separate from input text approval.

After group review, finalize using the paths from the candidate run:

```powershell
python -m app.analytics.cli demo finalize --snapshot "$demo/source-snapshot.json" --dataset "$demo/dataset.json" --review "$demo/text-review.decisions.json" --model-cache ../../.cache/analytics-models --candidate "$demo/candidate-<run>.json" --group-review "$demo/cluster-review-<run>.decisions.json"
```

Finalization recomputes the real pipeline, verifies the exact source/text/model/
configuration/membership review binding, and writes a new local final bundle,
summary and review audit. Rejected groups are excluded. Approved groups below
five students remain suppressed from aggregate cluster ARRs. Changed model files,
config, text or source requires renewed review. Every ARR retains synthetic
provenance, and the existing production publisher rejects these bundles.

Phase 7 (interface integration) was removed at the user's request. These phases
produce local data, reviews and ARRs, plus the separately authorized candidate
archive below. They do not implement a personalized
insight generator or inject synthetic results into the live dashboard/tutor.

## User-authorized MVP storage in Supabase

On 2026-10-25 the user explicitly requested storing the existing MVP ML output in
Supabase. This supersedes the earlier local-only storage preference. It does not
approve false instructor annotations, remove review requirements, or lower
aggregate cohort thresholds. `synthetic_storage.py` implements the bounded write.

`demo archive` inserts exactly one row into `analytics_runs`, using the existing
course and candidate run ID. It uses method `synthetic_demo_minilm_dbscan_v1`,
`params.status=demo_candidate`, synthetic provenance, and
`params.publication_status=not_published`. Its JSON params contain the actual
clustering report, 53 approved prepared descriptions/assignments, model/config
metadata, text review audit, counts and pending group-review template. The
original source fingerprint identifies a historical snapshot; this is not a
claim that a newly published live analysis was computed from current evidence.

Example, after explicit authorization and a successful local ML run:

```powershell
python -m app.analytics.cli demo archive --snapshot "$demo/source-snapshot.json" --dataset "$demo/dataset.json" --review "$demo/text-review.user-approved-53.json" --candidate "$demo/candidate-0049b9af-31b9-4de9-8889-3b7fb06bb676.json" --authorize-synthetic-storage --authorization-note 'User explicitly approved storing this labeled MVP ML run in the shared Supabase project.'
```

Only the server-side Supabase client writes this row. Existing RLS restricts
`analytics_runs` reads to course staff. No service key reaches a browser. Before
insertion, the archive validates the exact source, approved text digest, model,
assignment set, provenance, computed snapshot and existing course. Exact
readback follows insertion. An identical retry is read-only; conflicting content
under the same run UUID is rejected rather than overwritten. The normal
production ARR publisher continues to reject synthetic bundles.

There are no writes to `lers`, `ler_errors`, `evidence_refs`, `feedback`,
`error_taxonomy`, `analytics_results`, identities or lineage links. No migration,
new course or ingestion pause is needed for this insert-only archive. Existing
dashboard/tutor selection starts from published ARR rows, so this archive cannot
replace the live score dashboard. No synthetic cluster ARR is created for the
current run: every candidate has only three students and the minimum remains
five. Storing raw candidates in staff-only run metadata is not publication of
approved aggregate results.

Isolation/reversal: the archive is a single run UUID with this dedicated method
and an `archive_content_digest`. To reverse it, an authorized operator verifies
that UUID, method and digest, verifies it has no result/link rows, then deletes
only that archive row. Original evidence, genuine analytics and local artifacts
are retained. No automated cleanup or delete is performed by the archive command.

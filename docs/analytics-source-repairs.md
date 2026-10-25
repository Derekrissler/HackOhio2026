# Grounded source repairs and review workflow

Source repairs use the existing shared schema. They do not run migrations,
change grades, invent missing response text, mark outcomes instructor-verified,
or infer misconceptions from scores. Initial evidence repairs are separate from
subsequent human classification/mapping review.

## What the implementation does

`apps/api/app/analytics/source_repairs.py` reads an operator-only source snapshot
and builds a deterministic `RepairPlan`. It creates references from existing
question text, response text and Canvas locators. When a response has no text,
the excerpt explicitly identifies the stored grade/rubric/locator facts. That
excerpt is not a reconstruction of the student's answer. Existing PDF/image
references and instructor feedback are preserved.

Each affected LER gets a new revision. Its original identity links, status,
assistance, scores and existing associations are preserved; child outcome/error/
evidence rows are copied to the new revision. Existing error-to-outcome IDs are
translated to the copied error IDs. The shared supersession triggers retain the
original LERs and invalidate affected ARRs/IRs. No in-place LER edit is issued.

Plan-derived UUIDs and exact existing-row checks allow retry after partial writes.
Preflight binds the complete source snapshot and checks that only the plan's own
supersession/metadata operations occurred during a resume. Tampered plans,
unrelated evidence, wrong ownership, obsolete review revisions and concurrent
source changes stop the operation. Written rows and trigger-assigned revisions
are read back. Audit events use the database-generated bigint ID and the plan
UUID as `entity_id`, providing stable retry identity without a schema change.

This is a series of REST requests, not a transaction or an acquired lock. Pause
or serialize course ingestion, extraction and metadata writers before applying
repairs and refreshing analytics. Reading the course may continue, but analytics
will report stale until a verified replacement run is published. Resume writers
after verification.

## Preview only

From `apps/api`, using an environment with `requirements-persistence.txt`:

```powershell
python -m app.analytics.cli repair-plan --course 94c2f9d7-6940-463f-aa55-f09f66a35835 --output ../../data/analytics-runs/course-repair.json
```

The command prints counts only. It saves the exact private plan and a pending
review packet beside it. Output must be inside ignored `data/analytics-runs/`;
these files contain student response/feedback context and must not be committed
or sent to an AI chat. `repair-plan` performs no database writes. The summary's
`actual_insufficient_lers` counts records, unlike legacy readiness diagnostics,
which can report the same insufficient LER at two validation stages.

Inspect the plan. For an evidence-only repair, expect zero accepted errors,
completed classifications, verified mappings and reviewed ML descriptions.
Under serialized course access, apply that exact plan:

```powershell
python -m app.analytics.cli repair-apply --plan ../../data/analytics-runs/course-repair.json --exclusive-course-access
```

If a write fails, retain the original plan and resume it; do not generate a new
plan against a partially copied revision. Readers must remain behind freshness
checks while the partial operation is resolved. Verify completion and generate
a new analytical bundle from the repaired source using the existing analysis/
publication procedure. Score-only evidence repairs should leave numerical
measurements unchanged even though their LER IDs and provenance change.

## Completing the actual missing classifications and mapping reviews

After repairs, generate a **fresh** packet bound to the current revisions:

```powershell
python -m app.analytics.cli repair-plan --course 94c2f9d7-6940-463f-aa55-f09f66a35835 --output ../../data/analytics-runs/current-review-base.json
```

Edit the packet's `decisions` object locally; its `context` contains the source
questions, responses, feedback, outcomes, resources and reference IDs. Set an
opaque `reviewer_ref` and timezone-aware `reviewed_at` for completed decisions.
These are trusted operator attestations, not authenticated instructor identity.
Only an authorized reviewer should assert verification.

- `classifications`: leave `pending` unless the whole question observation has
  been checked. Set `decision: "complete"` with `errors: []` only after genuinely
  checking and finding no errors. Completed error items name `code`, `label`,
  grounded `description`, supporting `evidence_ref_ids` and explicit `outcome_ids`.
  A grade alone does not establish a diagnostic category. Unreviewed observations
  stay unknown and outside classification denominators.
- Errors require same-observation references and mapped course outcomes. New
  taxonomy labels are inserted only from explicit completed reviews; existing
  taxonomy entries are not overwritten. The resulting new LER has
  `analytics_v1.errors_analyzed=true` and error-specific outcome attribution.
- `privacy_reviewed: true` is a separate strict boolean on an error description.
  Apply it only after checking grounding and unnecessary personal/protected
  material. Only these descriptions enter a versioned `ReviewedExcerptExport`;
  classification does not automatically authorize embedding text.
- `outcomes`: change `pending` to `verified` only after checking the official
  syllabus wording. Nothing auto-approves the existing seven outcomes.
- `mappings`: change `pending` to `approved` only for reviewed existing question/
  outcome pairs. An optional explicit `weight` corrects the source weight. The
  repair also carries approval into the new LER's inherited outcome association,
  so the reader's LER-first mapping precedence does not retain an obsolete flag.
- `resources`: add only reviewed `{ "chunk_id": "UUID", "outcome_id": "UUID" }`
  pairs. This writes `chunk_outcomes` with instructor provenance. Released-resource
  permissions are unchanged; no resource embeddings are generated by this tool.

The initial workflow supports approving existing question mappings, not deleting
or inventing alternative official mappings. Leave a wrong pair pending and
coordinate its explicit correction with the source owner rather than approving
it to eliminate a warning.

Build a new exact plan with the completed decisions:

```powershell
python -m app.analytics.cli repair-plan --course 94c2f9d7-6940-463f-aa55-f09f66a35835 --review ../../data/analytics-runs/current-review-base.review.json --output ../../data/analytics-runs/reviewed-repair.json
```

If the source changed, regenerate and review rather than editing binding hashes.
Apply under serialized access, verify the output and recompute/review/publish the
analytics. `repair-apply` emits a private `.reviewed-excerpts.json` when explicitly
privacy-reviewed descriptions exist. Feed that versioned export to the existing
clustering readiness/candidate/group-review workflow. Group meaning approval is
still separate; this tool does not automatically publish ML groups.

## Configuration repair

Carmen's ingestion preflight now calls `pipeline_configuration_error()` from
its shared Supabase helper. It uses the same URL, alias, placeholder and
project-safe API-file fallback rules as `service_client()`, without constructing
a client or making a network request. Both `REPLACE_ME` and `YOUR-SECRET-KEY`
are rejected consistently. Actual secret values remain in local server settings.

## Verification

Regression coverage includes deterministic dry runs, private CLI exports,
unchanged source facts/scores, append-only revisions, exact retry after partial
writes, existing error attribution, source-change/tamper/ownership rejection,
explicit completed/no-error review, strict privacy approval, inherited mapping
approval and generated audit IDs. Fake SDK tests are not deployed RLS proof.

The VIBE 101 evidence repair on 25 October 2026 applied 606 source references and
555 new revisions. Original LERs were retained. Current LER evidence coverage
increased from 105/555 to **555/555**, with 771 unique course evidence references
and 1,275 links on current LERs. Two insufficient analyses retained their missing
grades and reasons. Classifications and instructor reviews remain pending.

Refreshed run `51828a2e-4ba4-418c-bcc3-32cce5f1f36f` was published after comparing
all 163 result measurements/limits against the original baseline. Selected score
observations remained 551. Exact typed readback passed, result flags were nonstale,
the source fingerprint matched, and a fresh repair plan proposed zero further
revisions. Course writers were released after verification. The ignored operator
result report records the check; source contents/bundles remain outside Git.

The current private review packet is
`data/analytics-runs/vibe101-current-source-review-2026-10-25.json`. It targets the
new LER revisions, unlike the historical pre-repair packet. Regenerate it if source
data changes before review/application.

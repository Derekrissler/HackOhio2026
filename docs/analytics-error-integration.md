# Error analytics and reviewed ML integration

This implementation connects authenticated tutoring to schema 1.1 analytics and
adds a concrete, testable error-input/review handoff. It does not create an OCR/LLM
extractor, alter shared grades/LERs, provision identities, run migrations or publish
new live results automatically. B's producer still needs to supply genuine
classified errors; the last live inventory contained no `ler_errors` rows.

## B-to-D contract

`app.analytics.error_handoff.ErrorHandoffMetadata` defines the proposed
`lers.payload.analytics_v1` namespace:

```json
{
  "schema_version": "1.0",
  "errors_analyzed": true,
  "outcome_weights": {},
  "error_outcomes": {"ERROR-UUID": ["OUTCOME-UUID"]}
}
```

UUID strings above are placeholders. `errors_analyzed` is a strict JSON boolean
or null, not a string/number. True plus no errors means classification completed
without detected errors; false/null never establishes error absence. Classification
completion is distinct from technical job status and the binary LER semantic
status. Invalid metadata stays unknown; malformed error attribution is separately
flagged and never inferred from the question mapping.

The producer writes actual error codes/statuses into `ler_errors` and evidence
links into `ler_error_evidence`. Missing support for an accepted error makes that
LER's error classification unusable; its valid score can remain usable. Error
outcome attribution must be explicit. Corrections use new LER revisions, preserving
the original question/feedback and source locations. Do not set flags from grades
alone. If B emits another schema, agree and add an explicit versioned adapter;
the analytics package does not scrape arbitrary payloads to guess meaning.

The committed `tests/analytics/fixtures/error_handoff.json` contains **20 fictional
LERs** for ten fictional learners: tagged mistakes, completed-with-no-errors,
unknown classifications and an insufficient analysis. It has 15 grounded error
observations in two families. `reviewed_errors.json` is its fictional text-review
export. Neither file is VIBE 101's actual source data or publishable live input.

## Reviewed descriptions and cluster review

`ReviewedExcerptExport` wraps the existing approved text contract with course,
extraction/review version, opaque reviewer attribution and an aware timestamp.
Each entry includes the actual `ler_error_id`, LER UUID/revision, taxonomy code,
short text, source kind, original evidence references and explicit privacy-review
attestation. Live inputs validate the exact current error row and its evidence;
rejected errors, unrelated references and superseded revisions are rejected.
Reviewer references are trusted-operator attribution, not authenticated identity
proof, and the flag is not automatic PII detection.

Review text for grounding and unnecessary personal/protected information before
export. No raw answers, whole submissions or arbitrary database prose are
automatically embedded. The export digest and audit data enter the restricted
snapshot. Multiple descriptions/tags cannot inflate one LER/error observation.

Input privacy review and cluster meaning review are separate. Candidate analysis
emits a private `.cluster-review.json` template. Inspect group members and medoid
exemplars in the private bundle, set reviewer attribution/time and explicitly
approve or reject each group. Do not approve a group just because its cohesion
is high. A second analysis takes that review and generates a new finalized run.

Approvals bind exact source, excerpt export, model/runtime/config and membership
digests. Changed inputs or pending decisions require renewed review. Group keys
are independent of the run UUID; published cluster IDs remain run-local. Only
approved groups satisfying the existing five-distinct-student suppression policy
can appear in finalized cluster ARRs. Internal density candidates require at
least three distinct LERs; a partition requires at least six. Noise remains noise.

New live clustering publication requires both review stages. Old completed score
bundles retain their model fields/hashes and idempotent retry behavior. Publication
also revalidates the frozen clustering snapshot and matching group documents;
do not hand-edit bundle JSON. Source/review corrections after publication must
go through B's new LER revisions so freshness checks can detect them. A local
export edit alone does not invalidate a published database result.

## Run from apps/api

Install both `requirements-persistence.txt` and `requirements-clustering.txt`
into the same API environment. The model must already be in the approved local
cache; these commands do not download a model or write to the database.

The fictional course UUID is `00000000-0000-4000-8000-000000000002`:

```powershell
python -m app.analytics.cli readiness --course 00000000-0000-4000-8000-000000000002 --input tests/analytics/fixtures/error_handoff.json --cluster --excerpts tests/analytics/fixtures/reviewed_errors.json --model-cache ../../.cache/analytics-models
python -m app.analytics.cli analyze --course 00000000-0000-4000-8000-000000000002 --input tests/analytics/fixtures/error_handoff.json --cluster --excerpts tests/analytics/fixtures/reviewed_errors.json --model-cache ../../.cache/analytics-models --save-bundle
```

Review the emitted private bundle/template locally, then rerun the analyze
command with `--cluster-review PATH-TO-COMPLETED-REVIEW.json`. A new run UUID is
expected. Candidate groups, completed groups and unavailable/no-group outcomes
are distinguished in the CLI summary. Readiness checks cached model availability
but performs no embedding inference. The fixed synthetic fixture demonstrates
the wiring, not generalization or course-data quality.

For live analysis, substitute the actual course UUID and versioned review export
and omit `--input`. First rerun readiness; zero classified errors/texts remains
not ready even when the model is installed. The producer's live records and real
account enrollments remain external dependencies. Legacy excerpt arrays remain
usable for local dry runs but cannot satisfy new live ML publication review.

Only after inspecting a finalized **live-source** bundle and reconfirming paused
course writers should an operator use the existing separate `publish` command.
Fictional/offline bundles remain unpublishable. All private exports, candidate
bundles, templates and decision files belong under gitignored `data/analytics-runs/`.

## Tutor integration

`tutor/analytics_bridge.py` reuses the API analytics library, including typed schema
1.1 parsing, newest visible run selection, completed-state/source checks and own
learner scope. It selects distinct outcomes below the declared observed-score
threshold; null, insufficient, stale or incomplete context supplies no boosts.
Unavailable analytics does not disable ordinary authorized tutoring.

`SupabaseTutorRepo` binds one authenticated learner per request. A fresh user
client handles retrieval, assessments and session/turn reads; a separate server
client writes logs and privately checks answer leakage/freshness. Resource search
always uses the user client with `p_student_safe=true`. Demo IDs and pseudonyms
cannot authorize shared data. Session ownership is checked before log writes.

The Carmen page now offers course-account sign-in. It uses the public-key Auth
client on the server and stores only the access token in an HttpOnly, SameSite
Strict cookie (Secure on HTTPS). Tokens/passwords are never returned in JSON.
Cookie-authenticated POST requests require the same-origin custom header and
origin check. Bearer-token API requests are also supported. Login verifies course
access on subsequent context requests using actual enrollment/learner mappings;
no account/mapping is invented. The initial page makes no privileged data query.

For this MVP, the cookie expires within one hour and there is no refresh-token
storage: sign in again when expired. Sign-out deletes the local cookie; it is not
global token revocation. Provider clients may be cached, user clients/repositories
are request-scoped. Configure Carmen's own `.env` as documented; never copy keys
into browser files. Missing Supabase settings fall back server-side to the canonical
`apps/api/.env` when the project URLs agree; usable Carmen settings take precedence.
A different Carmen project URL prevents borrowing a key from that fallback.
Its requirements now include the shared analytics reader.

## Dashboard and evidence

Instructor performance DTOs/UI now expose classified error prevalence with its
eligible denominator, rather than treating absent summaries as no mistakes.
Published groups display only approved representative text and distinct counts.
`GET /api/analytics/courses/{uuid}/clusters/{arr_uuid}/evidence` requires verified
course staff, current reviewed results and user-JWT reads of supporting evidence.
Private manifests, reviewer attribution and learner IDs stay out of summary DTOs.
Student-specific scores/errors stay on the existing own-results endpoint.

## Verification scope

Tests cover explicit completion, reviewed source ownership/revisions, rejection
of unreviewed/changed inputs, stable approvals across new run IDs, suppressed
groups, exact storage/retry behavior, role-gated evidence, typed tutor context,
cookie/origin protections and client separation. An opt-in cached-model test
executes the fictional handoff through MiniLM, review and simulated publication.
Real course semantic quality and real user-session/RLS acceptance still require
the actual upstream data and provisioned users. Tests do not modify the shared
database or call live model services.

Tutor live tests now require an explicit private `TUTOR_TEST_ACCESS_TOKEN` as well
as server credentials; they may write/delete test sessions and must be invoked
deliberately. Normal verification excludes both shared-database live test modules.

Implementation verification on 2026-10-24: **277 API tests**, **75 non-live
tutor/Carmen tests**, **24 frontend tests**, production build and tutor JavaScript
syntax check passed. Both cached MiniLM tests ran. A documented offline CLI smoke
run processed 20 fictional LERs, accepted 15 error descriptions, found two candidate
groups and saved a private review template without publication. A read-only live
check confirmed the previous published score bundle remains complete, hash
compatible and source-current; live ML inputs still contain zero error records.

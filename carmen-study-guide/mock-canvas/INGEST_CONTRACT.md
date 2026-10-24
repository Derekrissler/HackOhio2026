# Ingestion bundle contract (`ingest-1.1`)

The Carmen mock exports source records for the analytics pipeline. The bundle is the handoff from Canvas and document ingestion to question extraction and course knowledge indexing.

Create an export from the course page with **Export for analytics**, or run `python ingest.py 1001` from `mock-canvas/` while the server is running.

Each export is written to `mock-canvas/exports/<export_id>/`:

- `bundle.json` contains the normalized source records below.
- `files/` contains downloaded source PDFs. Their hashes are in `documents[].sha256`.

The adapter can target real Canvas through `CANVAS_BASE_URL` and `CANVAS_TOKEN`. The current item-level quiz response support is provided by the Carmen mock API; real Canvas quiz item responses require the applicable quiz submission endpoints and permissions.

## Contract and access rules

- **Evidence only.** The bundle records submitted work, grades, rubric data and source material. It does not infer error categories or outcome mastery.
- **Pseudonymous learner IDs.** `S-...` learner IDs and `G-...` grader IDs are HMAC-SHA256 pseudonyms using `ANON_SALT`. Names, emails and Canvas user IDs are not exported. Feedback text stays verbatim and may contain identifying text; scrub it before sending it to a model.
- **Missing data stays null.** Gaps appear in `quality.warnings` instead of being filled in.
- **Evidence is traceable.** Feedback, rubric notes and quiz item responses have an `evidence_ref_id` that points to `evidence_refs`. Each reference has an API path, Canvas identifiers, excerpt and content hash. Resource chunks have a locator and deep link.
- **Answer keys are instructor-only.** An instructor-scope export may include `correct_answer` on quiz question responses with `access_roles: ["instructor"]`. Student-only exports omit that field. Answer keys are never put in `documents` or `resource_chunks`; the optional database writer stores them in the protected `question_answer_keys` table.
- **Local demo authentication only.** Every `/api/v1/` request uses a bearer token. `dev` and `mock` are instructor demo tokens. `student-5001` through `student-5015` are synthetic student tokens. Students can read their own `/submissions/self` result, but cannot list the roster or all submissions. This models the handoff for the demo and is not production authentication.

The instructor handoff uses `GET /api/v1/courses/{course_id}/users` and `GET /api/v1/courses/{course_id}/assignments/{assignment_id}/submissions`. A student uses the corresponding `/submissions/self` endpoint. Every returned student record is scoped to that student's token.

## Top-level keys

| Key | What it holds |
|---|---|
| `schema_version` | `ingest-1.1` |
| `export` | Export ID, timestamp, adapter, source URL, course ID, content hash and API call count. The content hash covers the bundle except `export`, so identical source data produces the same hash. |
| `course` | Course ID, Canvas ID, name, course code, term and syllabus document ID. |
| `outcomes[]` | `outcome_id`, exact text, source, source reference and whether an instructor verified it. Syllabus objectives are marked as parsed, not verified. |
| `modules[]` | Course week/module structure and its assignment, page and file references. |
| `assessments[]` | Assessment ID, type, group, module, points, due date, description, rubric, stated outcomes, publication status and source reference. |
| `assessments[].rubric[]` | Rubric criterion and kind. `question_part` is a real problem part; `rubric_dimension` is an assignment-level criterion and must not be treated as a question. |
| `students[]` | Pseudonymous student ID and enrollment state. In a student-only export, this contains only the token owner's pseudonym. |
| `submissions[]` | One record per available student/assessment attempt, with workflow, score, response, item responses, rubric assessment, feedback and source reference. |
| `submissions[].question_responses[]` | Quiz question ID and number, question text, selected response, correctness, points, and evidence/source references. Instructor-scope records may also have `correct_answer` with `access_roles: ["instructor"]`. |
| `submissions[].response` | Submission type, body text and attachments. Attachments carry owner/instructor access roles. |
| `submissions[].rubric_assessment[]` | Criterion, awarded/possible points, comments and evidence reference. |
| `submissions[].feedback[]` | Comment ID, author role, pseudonymous author, verbatim text, timestamp and evidence reference. |
| `evidence_refs[]` | Stable-in-export evidence IDs, source type, API path, Canvas identifiers, excerpt and content hash. Quiz item responses use `source_type: canvas_quiz_response`. |
| `documents[]` | Source file/page/syllabus registry, source URL, type, hash, stored path, publication status and access roles. |
| `resource_chunks[]` | Retrieval units for the course knowledge index. PDF files are split by page; HTML pages by heading. Each includes content hash, locator, extraction method/version, outcome IDs and deep link. Answer keys are excluded. |
| `quality` | Scope (`instructor` or `self_only`), warnings and counts, including `question_responses`. |

Quiz item IDs are stable, for example `Q-2101-01` for the first item on assignment 2101. A response contains `choice_index` and/or response `text`, `correct` (nullable when Canvas provides a score but no per-item correctness), `points_earned`, `points_possible`, and an evidence reference. Instructor responses may include `correct_answer.choice_index` and `correct_answer.text`.

## Carmen demo data

The VIBE 101 course is synthetic and contains 15 student profiles and three completed quizzes. Each quiz has 10 graded items, for 450 question-level quiz responses in an instructor export. This supports repeatable roster, pagination, score and item-review demonstrations.

Written assignment feedback and rubric examples are concentrated on the Test Student profile. Other students' grade summaries and activity are seeded demo values. None of these records represent real student performance.

## Known limits

- A real Canvas course may restrict roster, submission or quiz detail APIs. The exporter reports unavailable optional data and marks a student-token bundle as `self_only`.
- The local demo tokens are fixed fixture tokens, not Canvas credentials or an authentication system.
- Pseudonymization does not anonymize free-text comments. Review comments before using them outside the local demo.

# Ingestion bundle contract (`ingest-1.5`)

The Carmen mock exports source records for the analytics pipeline. The bundle is the handoff from Canvas and document ingestion to question extraction and course knowledge indexing.

**Produce one:** open an assignment, quiz or exam and click **Export <name> for analytics** (top right). That exports
the assessment, its grades and feedback, and only the course material related to it. From the command line,
`.venv/bin/python ingest.py <course_id> <assignment_id>` does the same, and `.venv/bin/python ingest.py <course_id>`
exports the whole course.
Output goes to `mock-canvas/exports/<export_id>/`:
- `bundle.json`: this contract.
- `files/`: unmodified copies of the course files, hashed in `documents[].sha256`.

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
| `schema_version` | `"ingest-1.5"` (adds to 1.1: `scope` and `documents[].relevance`, chapter scope, `submission_files` and `extractions` (OCR), and per-question quiz comments) |
| `scope` | `level`: `assessment` or `course`. For an assessment: `assessment_id`, `assessment_name`, `assessment_type`, `home_module` (where it's assigned), `chapters_referenced`, `rules` |
| `export` | `export_id`, `generated_at`, `adapter`, `source.base_url`, `course_id`, `content_hash` (sha256 of everything except `export`, so an identical re-export has an identical hash), `api_calls` |
| `course` | `course_id`, `canvas_id`, `name`, `course_code`, `term`, `syllabus_document_id` |
| `outcomes[]` | `outcome_id` (`LO-01`…), `text` (**exact** syllabus wording), `source` (`canvas_outcomes` or `syllabus`), `source_ref`, `instructor_verified`. Parsed from the syllabus's "Learning Objectives" when the course has no formal Canvas outcomes. |
| `modules[]` | Week structure. `items[]` have `type`, `title`, `ref {kind, canvas_id}`, `url` |
| `assessments[]` | `assessment_id` (`A-<canvas id>`), `type` (`assignment`, `quiz`, `exam`, `project`), `assignment_group {name, weight_percent}`, `module`, `points_possible`, `due_at`, `submission_types`, `description_html/text`, `rubric[]`, `stated_outcome_ids[]`, `publication_status`, `source_ref` |
| `assessments[].rubric[]` | `criterion_id`, `description`, `points`, `kind`: `question_part` (e.g. "FRQ 2 (a)", a real question-level unit) or `rubric_dimension` (assignment-level criterion; **don't** treat it as a question) |
| `assessments[].stated_outcome_ids[]` | Outcomes the instructor listed in the assignment text ("Objectives: 1, 2, 6"), with `provenance: instructor_stated_in_assignment` and the `excerpt` |
| `assessments[].questions[]` | Quizzes: `question_id` (`Q-2101-01`…), `question_number`, `question_text`, `choices[]` (text). **No correct answers here.** |
| `assessments[].chapters_covered[]` | Chapter numbers the assessment covers, from its title, description or module headings ("Chapters 1–2") |
| `submission_files[]` | **Instructor + owner only.** Files students submitted, or instructors scanned for them: `document_id` (`SUBDOC-…`), `submission_id`, `assessment_id`, `student_id`, `filename`, `content_type`, `sha256`, `stored_path`, `upload_source` (`student_submission` or `instructor_scan`). Never indexed for retrieval. |
| `extractions[]` | Text read from each submission file (spec §4): `document_id`, `submission_id`, `engine` (e.g. `tesseract-5.5.3`), `extractor_version`, `methods`, `mean_confidence`, `flags` (`low_confidence`, `needs_review`, `no_text_found`), `text`, and `pages[] {page, method: native_text or ocr, text, mean_confidence, flags, lines[] {text, bbox_norm [x1,y1,x2,y2] 0–1, confidence 0–100, low_confidence?}}`. Native text is used when the PDF has a text layer; otherwise OCR at 300 dpi. |
| `students[]` | `student_id`, `enrollment_state` |
| `submissions[].response.extracted_text` | All text extracted from that submission's files (null when there are none). `response.attachments[]` points to `submission_files` by `document_id`. |
| `submissions[]` | One per student per assessment: `submission_id`, `assessment_id`, `student_id`, `attempt_id`, `workflow_state`, `submitted_at`, `graded_at`, `score` (null = ungraded), `points_possible`, `response {submission_type, body_text, attachments[]}`, `rubric_assessment[]`, `feedback[]` |
| `submissions[].question_responses[]` | Quiz items: `question_id` (`Q-2101-01`), `question_number`, `question_text`, `response {choice_index?, text}`, `correct` (nullable), `points_earned`, `points_possible`, `comments` (per-question grader note), `evidence_ref_id`, `comment_evidence_ref_id`, `source_ref`. Instructor-scope records may also have `correct_answer {choice_index, text, access_roles: ["instructor"]}`: never index it or show it to students; it is stored only in the RLS-protected `question_answer_keys` table. |
| `submissions[].rubric_assessment[]` | `criterion_id`, `criterion`, `kind`, `points`, `points_possible`, `comments`, `evidence_ref_id` |
| `submissions[].feedback[]` | `feedback_id`, `kind: submission_comment`, `author_role` (`grader` or `student`), `author_id`, `text` (verbatim), `created_at`, `evidence_ref_id` |
| `evidence_refs[]` | `id` (`EV-0001`…), `source_type` (`canvas_submission_comment`, `canvas_rubric_assessment`, `canvas_quiz_response` or `canvas_quiz_question_comment`), `api_path`, `canvas_ids`, `excerpt`, `content_hash` |
| `documents[].relevance[]` | Assessment exports only. Why the document is included, as `{rule, detail}`. Rules: `same_module` (in the module where the assessment is assigned), `chapter_reference` (a chapter named in the assessment's title, description or module headings, e.g. "Chapters 1–2"), `taught_with` (the slide deck taught alongside a referenced chapter) |
| `documents[]` | Source file registry: `document_id`, `source_type` (`canvas_file`, `canvas_page`, `canvas_syllabus`), `title`, `document_type` (`lecture_slides`, `textbook_section`, `course_page`, `syllabus`, `file`), `module`, `sha256`, `stored_path`, `page_count`, `source_url`, `publication_status`, `access_roles` |
| `resource_chunks[]` | Retrieval units for C. Slides get one chunk per PDF page (`locator.page`); pages get one chunk per heading section (`locator.section`). Each has `content`, `content_hash`, `outcome_ids: []` (for C to tag), `extraction {method, version}`, `deep_link`. Duplicate text is dropped. |
| `quality` | `outcome_source`, `scope` (`instructor` = all students; `self_only` = the token owner's work only), `warnings[]`, `counts` |

In an assessment export, `assessments`, `submissions` and `students` cover only that assessment. `outcomes` is
always the full course list, because mapping needs every candidate outcome. `modules` is the assessment's home module.
An assessment with no linked material, like the Final Project, exports with no documents and a warning.

## Known limits of the current data
- **OCR quality.** Tesseract reads typed and scanned print well (~90 confidence) and handwriting poorly. It can be confidently wrong on handwriting, so treat `needs_review` and `low_confidence` as "check the original". Extracted text is evidence of what OCR read, not of what the student wrote. Spec §4: never infer unreadable answers.
- **No student responses.** Canvas returned no submission bodies or attachments, so there is no question-level response text. B should create LERs from `question_part` rubric rows (exams) and keep assignment-level evidence separate, as spec §6 says.
- **Only one student has written feedback.** The course has 15 students, all with grades and quiz answers, but only the mock student has written comments and rubric notes.
- **Quiz items come from the mock's `quiz_responses`.** Question stems and choices are read from the quiz description. A real Canvas course would need the Classic Quizzes `submission_history` data or the New Quizzes API instead.
- A real Canvas course may restrict roster, submission or quiz detail APIs. The exporter reports unavailable optional data and marks a student-token bundle as `self_only`.
- The local demo tokens are fixed fixture tokens, not Canvas credentials or an authentication system.
- Pseudonymization does not anonymize free-text comments. Review comments before using them outside the local demo.

## Carmen demo data

The VIBE 101 course is synthetic and contains 15 student profiles and three completed quizzes. Each quiz has 10 graded items, for 450 question-level quiz responses in an instructor export. This supports repeatable roster, pagination, score and item-review demonstrations.

Written assignment feedback and rubric examples are concentrated on the Test Student profile. Other students' grade summaries and activity are seeded demo values. None of these records represent real student performance.


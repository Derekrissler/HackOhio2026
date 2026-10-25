# Ingestion bundle contract (`ingest-1.3`)

Output of Workstream A (Canvas + document ingestion). Input to B (extraction + LER) and C (course knowledge / RAG index).

**Produce one:** open an assignment, quiz or exam and click **Export <name> for analytics** (top right). That exports
the assessment, its grades and feedback, and only the course material related to it. From the command line,
`.venv/bin/python ingest.py <course_id> <assignment_id>` does the same, and `.venv/bin/python ingest.py <course_id>`
exports the whole course.
Output goes to `mock-canvas/exports/<export_id>/`:
- `bundle.json`: this contract.
- `files/`: unmodified copies of the course files, hashed in `documents[].sha256`.

The real-Canvas adapter is the same code with `CANVAS_BASE_URL` and `CANVAS_TOKEN` set. It calls only documented Canvas REST endpoints.

## Rules
- **Evidence only, no inference.** No error categories or AI outcome mappings. Those are produced by B and D.
- **Pseudonymous IDs.** Students are `S-…` and graders are `G-…`: HMAC-SHA256 of the Canvas user id with `ANON_SALT`, stable across exports. Names, emails and Canvas user ids are never written. Comment text is kept **verbatim**, so it can contain first names. Scrub it before any model sees it, if needed.
- **Missing means `null`.** Gaps are listed in `quality.warnings`, never filled in.
- **Every piece of evidence is traceable.** Every comment and rubric note has an `evidence_ref_id` that points into `evidence_refs`, which holds the API path, Canvas ids, verbatim excerpt and `content_hash`. Every chunk has a `locator` (page or section) and a `deep_link`.
- **No answer keys.** Instructor-only material is not in Canvas's student-visible content, so it isn't exported. Every exported chunk has `access_roles: ["student","instructor"]` and is safe for the student retrieval index.

## Top-level keys
| Key | What it holds |
|---|---|
| `schema_version` | `"ingest-1.2"` (1.1 added `scope` and `documents[].relevance`; 1.2 added quiz questions, per-question responses and `answer_keys`; 1.3 added `submission_files` and `extractions` (OCR)) |
| `scope` | `level`: `assessment` or `course`. For an assessment: `assessment_id`, `assessment_name`, `assessment_type`, `home_module` (where it's assigned), `chapters_referenced`, `rules` |
| `export` | `export_id`, `generated_at`, `adapter`, `source.base_url`, `course_id`, `content_hash` (sha256 of everything except `export`, so an identical re-export has an identical hash), `api_calls` |
| `course` | `course_id`, `canvas_id`, `name`, `course_code`, `term`, `syllabus_document_id` |
| `outcomes[]` | `outcome_id` (`LO-01`…), `text` (**exact** syllabus wording), `source` (`canvas_outcomes` or `syllabus`), `source_ref`, `instructor_verified`. Parsed from the syllabus's "Learning Objectives" when the course has no formal Canvas outcomes. |
| `modules[]` | Week structure. `items[]` have `type`, `title`, `ref {kind, canvas_id}`, `url` |
| `assessments[]` | `assessment_id` (`A-<canvas id>`), `type` (`assignment`, `quiz`, `exam`, `project`), `assignment_group {name, weight_percent}`, `module`, `points_possible`, `due_at`, `submission_types`, `description_html/text`, `rubric[]`, `stated_outcome_ids[]`, `publication_status`, `source_ref` |
| `assessments[].rubric[]` | `criterion_id`, `description`, `points`, `kind`: `question_part` (e.g. "FRQ 2 (a)", a real question-level unit) or `rubric_dimension` (assignment-level criterion; **don't** treat it as a question) |
| `assessments[].stated_outcome_ids[]` | Outcomes the instructor listed in the assignment text ("Objectives: 1, 2, 6"), with `provenance: instructor_stated_in_assignment` and the `excerpt` |
| `assessments[].questions[]` | Quizzes: `question_id` (`Q1`…), `canvas_id`, `position`, `text`, `type`, `points_possible`, `choices[] {choice_id, text}`. **No correct answers here.** |
| `answer_keys[]` | **Instructor-only.** `assessment_id`, `question_id`, `answer`, `access_roles: ["instructor"]`. Never index these or show them to students. Stored only in the RLS-protected `question_answer_keys` table. |
| `submission_files[]` | **Instructor + owner only.** Files students submitted, or instructors scanned for them: `document_id` (`SUBDOC-…`), `submission_id`, `assessment_id`, `student_id`, `filename`, `content_type`, `sha256`, `stored_path`, `upload_source` (`student_submission` or `instructor_scan`). Never indexed for retrieval. |
| `extractions[]` | Text read from each submission file (spec §4): `document_id`, `submission_id`, `engine` (e.g. `tesseract-5.5.3`), `extractor_version`, `methods`, `mean_confidence`, `flags` (`low_confidence`, `needs_review`, `no_text_found`), `text`, and `pages[] {page, method: native_text or ocr, text, mean_confidence, flags, lines[] {text, bbox_norm [x1,y1,x2,y2] 0–1, confidence 0–100, low_confidence?}}`. Native text is used when the PDF has a text layer; otherwise OCR at 300 dpi. |
| `students[]` | `student_id`, `enrollment_state` |
| `submissions[].response.extracted_text` | All text extracted from that submission's files (null when there are none). `response.attachments[]` points to `submission_files` by `document_id`. |
| `submissions[]` | One per student per assessment: `submission_id`, `assessment_id`, `student_id`, `attempt_id`, `workflow_state`, `submitted_at`, `graded_at`, `score` (null = ungraded), `points_possible`, `response {submission_type, body_text, attachments[]}`, `rubric_assessment[]`, `feedback[]` |
| `submissions[].question_responses[]` | Quiz attempts: `question_id`, `answer_choice_id`, `response_text` (the chosen option or the written answer), `points`, `points_possible`, `correct` (true, false or "partial"), `comments`, `evidence_ref_id` |
| `submissions[].rubric_assessment[]` | `criterion_id`, `criterion`, `kind`, `points`, `points_possible`, `comments`, `evidence_ref_id` |
| `submissions[].feedback[]` | `feedback_id`, `kind: submission_comment`, `author_role` (`grader` or `student`), `author_id`, `text` (verbatim), `created_at`, `evidence_ref_id` |
| `evidence_refs[]` | `id` (`EV-0001`…), `source_type` (`canvas_submission_comment` or `canvas_rubric_assessment`), `api_path`, `canvas_ids`, `excerpt`, `content_hash` |
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
- **Quiz data comes from the Classic Quizzes APIs.** Per-question answers come from `submission_history[].submission_data` and questions and keys from `/quizzes/:id/questions` (instructor token). New Quizzes would need its own API.

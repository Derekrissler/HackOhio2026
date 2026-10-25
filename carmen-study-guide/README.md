# Mock Canvas (Carmen)

A local Canvas-style course for the Carmen Study Guide. It serves VIBE 101 (course ID `1001`), mock Canvas REST endpoints, seeded student grades, and a normalized analytics export.

## Run locally

From this directory in PowerShell:

```powershell
cd mock-canvas
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server:app --reload --port 8001
```

Open [http://localhost:8001/courses/1001](http://localhost:8001/courses/1001). API documentation is at [http://localhost:8001/docs](http://localhost:8001/docs).
If port 8001 is already occupied, change the run command to `--port 8002` and open [http://localhost:8002/courses/1001](http://localhost:8002/courses/1001).

On macOS or Linux, use `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`, and `.venv/bin/uvicorn server:app --reload --port 8001`.

## Demo API access

The mock API requires a bearer token on `/api/v1/` routes:

- `Bearer dev` or `Bearer mock`: instructor view, including the synthetic roster and class submissions.
- `Bearer student-5001` through `Bearer student-5015`: student view. A student can only read their own `/submissions/self` response.

Student quiz review includes their score and whether each answer was correct. Correct-answer values are only present in instructor responses. These fixture tokens are for the local demo only.

## End-to-end checks

With the server running, open a second PowerShell terminal in this directory:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The integration checks launch a separate temporary local server, follow Canvas-style pagination, verify student/staff access, build instructor and student-only exports, and check the seeded quiz response data. They do not call the analytics export button or the optional Supabase storage writer.

## Export for analytics
Every assignment, quiz and exam page has a button at the top right labeled with that assessment, e.g.
**Export Quiz 1 for analytics**. It pulls that assessment through the Canvas API: its rubric, every submission's
grades, rubric notes and comments, and only the course material related to it. That means the pages and slides in
the module where it's assigned, textbook chapters it names ("Chapters 1–2"), and the lecture slides taught with
those chapters. Each document records why it was included. It writes one JSON bundle to
`mock-canvas/exports/<export_id>/bundle.json`, with the original files in `files/`, for the analytics pipeline. The format is in
[mock-canvas/INGEST_CONTRACT.md](mock-canvas/INGEST_CONTRACT.md).

**The database mirrors the course automatically.** Every course page and the dashboard start a background
sync of the whole course into the team's Supabase Postgres when they open or reload (`sync.py`). The header shows
"Syncing… / Database up to date". Nothing is written if nothing changed since the last sync. The sync covers every
student's grades, quiz answers per question, feedback, questions, the protected quiz answer keys, outcomes, and
materials. Rows for content deleted from the course aren't removed.

**Analytics-ready data (LERs).** After storing, every sync also does two things:
- `outcome_mapper.py` proposes outcome mappings for questions with none. It uses the chapter rule in
  `mappings/vibe101.json` and marks every mapping `needs_review`. Instructor-stated mappings are never touched.
- `ler_builder.py` writes one Learning Evidence Record per graded response, linked to its outcomes and
  evidence. LERs are append-only: changed data adds a revision, and the database supersedes the old one.

`analytics_bridge.py` loads the current LERs as the envelopes Richard's analytics expects
(`apps/api/app/analytics`). Run `.venv/bin/python analytics_bridge.py "VIBE 101"` to put the real data through
his adapter, features and statistics. Error metrics stay empty until there's an agreed error taxonomy and
classifier.

**Submitted work and OCR.** Assignment pages have a **Submit Assignment** upload (PDF, PNG or JPEG), and
**Scanned Work** in the course menu lets an instructor upload a scan for any student and review what OCR read.
Text comes from the PDF's own text layer when it has one, and otherwise from Tesseract (`brew install tesseract`).
Each line keeps its page, bounding box and confidence, and pages with shaky text are flagged for review. The sync
stores originals in the private `source-files` bucket, each line as an evidence reference, and the text as the
student's response. To make fictional test scans, run `.venv/bin/python make_sample_scans.py --upload`.

When `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_SECRET_KEY`) is set in `mock-canvas/.env`, the button also stores the export in the team's
Supabase Postgres (`db_store.py`), and re-clicking is safe. It writes the course, learners, outcomes, documents
(with the originals uploaded to the `course-materials` bucket), chunks, assessments, questions, attempts,
responses, evidence and feedback, and logs an `ingestion_jobs` row. To store an existing export by hand, run
`.venv/bin/python db_store.py exports/<export_id>/bundle.json`. To run the same export against real Canvas:
`CANVAS_BASE_URL=https://osu.instructure.com CANVAS_TOKEN=<token> .venv/bin/python ingest.py <course_id>`.

**Analyze goals (Hue).** Every quiz question (on the quiz review page), exam part (FRQ / Part rows of the rubric)
and assignment title has a small target icon. The answer appears in Hue, the chat box at the side of the page (the app
calls the assistant Hue; it runs on Claude). Clicking it sends Claude (`claude-opus-5-5`) the syllabus outcomes, all released course material
in Supabase and the question, and gets back which outcomes the question assesses with a share for each (adding to
100%), a reason and the material it relied on. The shares are saved as `question_outcomes` weights (provenance `ai`,
`needs_review` true) and the LERs are rebuilt, so the analytics use them right away. Instructor-stated or reviewed
mappings are never changed, and the automatic chapter rule never overwrites Claude's. Needs `ANTHROPIC_API_KEY` in
`mock-canvas/.env`; a click costs a few cents. From the terminal:
`.venv/bin/python claude_mapper.py "VIBE 101" 2201 "FRQ 1 (a)"`.


## Study Tutor (Hue)
Students meet the tutor as **Hue**. **Ask Hue** in the corner of every course page opens a chat box that expands into
the tutor window, and **Hue** in the course navigation (`/courses/1001/tutor`) opens that window directly
(`ui.hue_dock`, `static/hue.js`, `static/hue.css`). It is the integrity-aware tutor from the pipeline spec
(workstream F, §11). It answers from the course material stored in Supabase and cites the slides and pages it used.

Each message goes through `tutor/service.py`:
1. **Mode, decided in code** (`tutor/policy.py`). It comes from the assessment's `integrity_status` in Supabase:
   `active_protected` gives concept help only, `guided_homework` gives hints but no answers, and `released` gives
   independent study. A message that names or pastes text from an open assessment (`tutor/matcher.py`, plus a Haiku
   check for paraphrases) gets the strictest mode that applies.
2. **Retrieval**: `search_resource_chunks` with the authenticated student's JWT and `p_student_safe=true`.
   A validated, current schema 1.1 analytics result can boost the student's weaker outcomes.
3. **Reply**: Claude Opus 5.5 returns a fixed schema (message, move, hint level, cited chunk ids, next step).
4. **Verification** (`tutor/verifier.py`, plus a Haiku paraphrase check). It rejects moves the mode doesn't allow,
   hint jumps, citations to anything that wasn't retrieved, answer-key text, and other students' ids. A rejected draft
   gets one stricter retry, then a rule-based fallback. Answer keys are only ever compared on the server.
5. **Log**: `tutor_sessions` and `tutor_turns`, including the mode, the reason and any rejected drafts.

Setup: add the Supabase service key and either `ANTHROPIC_API_KEY` (Claude) or `TUTOR_LLM=ollama` (free, local:
install Ollama, then `ollama pull qwen2.5:7b` and `ollama pull qwen2.5:3b`) to `mock-canvas/.env`, install `requirements.txt`, and
export the course once (the **Export for analytics** button). To give every mode something to show, run
`.venv/bin/python -m tutor.demo_setup --apply` once. It makes Assignment 2 guided homework, releases Quiz 1, and adds a
fictional Quiz 2 answer key. Without the keys, the page loads and explains what's missing.

Sign in on the tutor page with an existing Supabase course account. Course enrollment and
`learner_identities` must already map that account to its learner; the demo picker does not
authorize shared records. The page stores an HttpOnly, SameSite cookie, expiring within an
hour; sign in again after expiry. The browser receives no service key or JWT JSON response.
Read/retrieval clients are per user request, while writes and private verification stay server-side.
Missing Supabase values can reuse `apps/api/.env` server-side when the project URLs agree;
Carmen's `.env` still supplies its model-provider settings and optional local overrides.
See [the integration guide](../docs/analytics-error-integration.md) for the complete boundaries.

Tests: `.venv/bin/pip install -r requirements-dev.txt`, then `.venv/bin/python -m pytest tutor` from `mock-canvas/`.
Shared-database tests additionally require an explicit private `TUTOR_TEST_ACCESS_TOKEN`
and service key; they write/delete sessions and should be invoked deliberately.
`tutor_host.py` is the only mock-canvas-specific part (who the student is, and the page); the `tutor/` package
doesn't import mock-canvas.

## Main files

| File | Purpose |
|---|---|
| `server.py` | Mock Canvas JSON API, demo token roles and course pages |
| `ui.py`, `static/` | Canvas-style dashboard, assignments, grades and people views |
| `fixtures/vibe101.json` | Generated synthetic course, roster, grades and quiz attempts |
| `build_course.py` | Rebuilds the course fixture from `CourseContent/` |
| `ingest.py` | Canvas API adapter and local analytics bundle exporter |
| `db_store.py` | Optional server-side Supabase storage for a completed export |
| `sync.py` | Background sync of the whole course into Supabase on every page load |
| `ocr.py`, `uploads.py`, `make_sample_scans.py` | Submitted files and scans, their OCR, and fictional test scans |
| `outcome_mapper.py`, `mappings/` | Automatic chapter-rule outcome mappings (marked for review) |
| `claude_mapper.py` | The **Analyze goals** button: Claude proposes outcome weights for one question |
| `ler_builder.py`, `analytics_bridge.py` | Learning Evidence Records, and loading them into the analytics pipeline |
| `INGEST_CONTRACT.md` | Bundle contract, access rules and known limits |
| `tutor/` | Study tutor: policy, retrieval, model calls, verification, API (see Study Tutor above) |
| `tutor_host.py`, `static/tutor.*` | Mounts the tutor in Mock Canvas: who the student is, and the chat page |

After editing `CourseContent/`, run `python build_course.py` from this directory.

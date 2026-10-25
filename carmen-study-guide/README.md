# Mock Canvas

A local copy of Canvas (Carmen) to build on. It serves Canvas-styled pages and the Canvas REST API, with the
same JSON shapes and Link-header pagination as osu.instructure.com. The course data is **VIBE 101** (course id
1001), built from the markdown in `CourseContent/`.

## Run it
```bash
cd mock-canvas
python3.13 -m venv .venv                 # first time only; needs Python 3.10+ (macOS's python3 is 3.9)
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn server:app --reload --port 8001
```
Open http://localhost:8001/courses/1001. The API is under http://localhost:8001/api/v1/, and you can try every
endpoint at http://localhost:8001/docs. Any bearer token works.

## What's in it
| Page | URL |
|---|---|
| Dashboard | `/` |
| Course home (modules) | `/courses/1001` |
| Assignments, grouped and weighted | `/courses/1001/assignments` |
| Assignment with rubric, grade and comments | `/courses/1001/assignments/2001` |
| Grades | `/courses/1001/grades` |
| Pages, Files, Syllabus | `/courses/1001/pages`, `/files`, `/assignments/syllabus` |

API endpoints include courses, modules (`include[]=items`), pages, files and downloads, assignments, and
`submissions/self` (`include[]=submission_comments`, `rubric_assessment`, `assignment`).

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

**Analyze goals (Claude).** Every quiz question, exam part (FRQ / Part rows of the rubric) and assignment has an
**Analyze goals** button. It sends Claude (`claude-opus-5-5`) the syllabus outcomes, all released course material
in Supabase and the question, and gets back which outcomes the question assesses with a share for each (adding to
100%), a reason and the material it relied on. The shares are saved as `question_outcomes` weights (provenance `ai`,
`needs_review` true) and the LERs are rebuilt, so the analytics use them right away. Instructor-stated or reviewed
mappings are never changed, and the automatic chapter rule never overwrites Claude's. Needs `ANTHROPIC_API_KEY` in
`mock-canvas/.env`; a click costs a few cents. From the terminal:
`.venv/bin/python claude_mapper.py "VIBE 101" 2201 "FRQ 1 (a)"`.

## Where things live
| File | Job |
|---|---|
| `mock-canvas/server.py` | JSON API |
| `mock-canvas/ui.py`, `static/` | Canvas-styled pages |
| `mock-canvas/fixtures/*.json` | Course data, one course per file. Edits show up on the next request |
| `mock-canvas/ingest.py` | Canvas → analytics bundle exporter (the button) |
| `mock-canvas/build_course.py` | Rebuilds `fixtures/vibe101.json` from `CourseContent/` |
| `mock-canvas/snapshot.py` | Copies a real Canvas course's materials into `fixtures/local/` (gitignored) |

After editing the markdown in `CourseContent/`, run `.venv/bin/python build_course.py` from `mock-canvas/`.
Answer keys and the TA comment bank are left out on purpose, because the course is the student's view.

To mock a real course, put `CANVAS_BASE_URL` and a real `CANVAS_TOKEN` in `mock-canvas/.env`, then run
`.venv/bin/python snapshot.py <COURSE_ID>`.

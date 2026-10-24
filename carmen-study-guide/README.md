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

The course pages have an **Export for analytics** button. It calls the mock Canvas API and writes `mock-canvas/exports/<export_id>/bundle.json` plus source PDFs. The format and data limits are documented in [mock-canvas/INGEST_CONTRACT.md](mock-canvas/INGEST_CONTRACT.md).

When the server has a Supabase secret configured in `mock-canvas/.env`, the export button also invokes the server-side writer in `db_store.py`. It stores source records and quiz item responses; answer keys are stored only in the protected `question_answer_keys` table. The browser never receives the secret key. To export a local bundle without storing it, run `python ingest.py 1001` from this directory while the local server is up.

## Study Tutor
**Study Tutor** in the course navigation (`/courses/1001/tutor`) is the integrity-aware tutor from the pipeline spec
(workstream F, §11). It answers from the course material stored in Supabase and cites the slides and pages it used.

Each message goes through `tutor/service.py`:
1. **Mode, decided in code** (`tutor/policy.py`). It comes from the assessment's `integrity_status` in Supabase:
   `active_protected` gives concept help only, `guided_homework` gives hints but no answers, and `released` gives
   independent study. A message that names or pastes text from an open assessment (`tutor/matcher.py`, plus a Haiku
   check for paraphrases) gets the strictest mode that applies.
2. **Retrieval**: `search_resource_chunks` with `p_student_safe=true`, filtered to the student's course.
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

Tests: `.venv/bin/pip install -r requirements-dev.txt`, then `.venv/bin/python -m pytest tutor` from `mock-canvas/`.
The tests that use Supabase run only when a service key is set, and they delete the sessions they create.
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
| `INGEST_CONTRACT.md` | Bundle contract, access rules and known limits |
| `tutor/` | Study tutor: policy, retrieval, model calls, verification, API (see Study Tutor above) |
| `tutor_host.py`, `static/tutor.*` | Mounts the tutor in Mock Canvas: who the student is, and the chat page |

After editing `CourseContent/`, run `python build_course.py` from this directory.

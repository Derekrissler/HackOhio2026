# Carmen Study Guide (hackathon MVP)

Chrome extension and small Python backend. On a graded Carmen assignment, a student clicks
**Analyze my feedback**. It reads the grader's comments and rubric deductions and shows each
mistake's underlying concept, with links to the specific course pages and lecture-slide pages
to review. It never shows answers.

## How it works
1. `extension/content.js` runs on `osu.instructure.com/courses/*/assignments/*`. It calls the Canvas API
   **as the logged-in student** (their session cookie, no token) to get their own submission
   comments and rubric assessment.
2. `extension/background.js` relays that feedback to the backend at `http://localhost:8000`.
3. `backend/main.py` indexes the course with the instructor's token: module items, wiki pages
   (body text), and every PDF **split per page**. It then asks Claude to map each mistake to
   catalog IDs. Only IDs that exist in the index are turned into links, so the output can't include made-up URLs.

## Setup (~5 min)
```bash
cd backend
python3.13 -m venv .venv && source .venv/bin/activate   # needs Python 3.10+; macOS's python3 is 3.9
pip install -r requirements.txt
cp .env.example .env        # fill in ANTHROPIC_API_KEY and CANVAS_TOKEN
uvicorn main:app --reload --port 8000
```
Check it: open http://localhost:8000/health, then pre-build the index (the first build is slow):
```bash
curl -X POST http://localhost:8000/reindex/<COURSE_ID>
```
The JSON lists the first 20 indexed items. Confirm the slides appear as "— page N".

Extension: go to `chrome://extensions`, turn on Developer mode, click **Load unpacked**, and select the `extension/` folder.
Open a graded assignment in the test course while logged in as a student. A red **Study Guide** panel
appears in the bottom-right.

## Developing without Carmen (mock Canvas)
`mock-canvas/` is a local copy of the Canvas endpoints this project calls, with the same JSON shapes and
Link-header pagination, plus Canvas-styled pages. It serves **VIBE 101** (course id 1001), built from the
markdown in `CourseContent/`. After editing that markdown, rebuild the course with
`../backend/.venv/bin/python build_course.py` from `mock-canvas/`. Answer keys and the TA comment bank are left
out on purpose, so the model never sees them.
```bash
cd mock-canvas
../backend/.venv/bin/uvicorn server:app --reload --port 8001
```
In `backend/.env`, set `CANVAS_BASE_URL=http://localhost:8001` and `CANVAS_TOKEN=dev`. Then start the backend
as usual and run `curl -X POST http://localhost:8000/reindex/1001`.

To work on the extension, open http://localhost:8001 and click an assignment. The page loads the real
`extension/content.js` with a stub `chrome.runtime` that posts to the backend, so you don't need to reload
the extension. Edit `fixtures/*.json` to change the course data. Changes apply on the next request.

To mock a real course: with a real `CANVAS_TOKEN` in `backend/.env`, run
`../backend/.venv/bin/python snapshot.py <COURSE_ID>` from `mock-canvas/`. It copies modules, pages, PDFs and
rubrics (no student data) into `fixtures/local/`, which is gitignored.

## Limitations of this MVP
- Reads **rubric comments + submission comments** only. Inline DocViewer annotations on PDFs aren't in the
  public API, so that's a stretch goal.
- Links to a PDF open the file. The page number is shown in the link title, not deep-linked.
- Index is in memory. Restarting the backend means a reindex. Hit `/reindex/<id>` again after adding material.
- Backend is localhost-only, so it's for demoing on one laptop. Deploy it (Render/Fly) and change
  `backendUrl` before anyone else uses it.

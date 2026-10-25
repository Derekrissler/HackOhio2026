# HackOhio2026: codebase map

Read this before scanning the tree. Setup, run, seed and test commands are in [README.md](README.md).

## Skip when searching

- `.claude/` and `.agents/`: agent skills (tooling, not app code). `.agents/skills/` mirrors
  `.claude/skills/supabase*` for `npx skills` (`skills-lock.json`). One exception: `npm run e2e` runs
  `.claude/skills/webapp-testing/scripts/with_server.py`, so keep that folder.
- `**/.venv/`, `node_modules/`, `__pycache__/`: installed packages and caches.
- `data/seed/`: generated seed data. Regenerate with `npm run seed:generate`; don't hand-edit.

## Three apps

| Folder | What | Port |
|---|---|---|
| `apps/web` | React + Vite Canvas-style LMS frontend (`src/pages`, `src/shell`, `src/api`) | 5173 |
| `apps/api` | FastAPI mock LMS on SQLite (`app/routers`, `app/ingest`), plus the Supabase analytics pipeline in `app/analytics/` | 8000 |
| `carmen-study-guide/mock-canvas` | Mock Canvas "Carmen" (FastAPI, server-rendered HTML) and the Study Tutor (`tutor/`), shown in the UI as "Hue" | 8001 |

Shared: `supabase/migrations/` (team Supabase schema), `docs/` (plans and analytics specs;
`docs/project-state-2026-10-24.md` is the latest state audit), `scripts/` (Python launchers behind the npm
scripts, e2e click-through).

## LLM calls (all in `carmen-study-guide/mock-canvas`)

- `claude_mapper.py`, `_ask_claude()`: the "Analyze goals" button (`server.py` → `claude_mapper.map_question`).
  Anthropic SDK, `claude-opus-5-5`, JSON-schema output; writes `question_outcomes` rows in Supabase.
- `tutor/llm.py`, `AnthropicTutorLLM`: tutor replies (`claude-opus-5-5`) plus leak and reference checks
  (`claude-haiku-5-5`).
- `tutor/llm_ollama.py`, `OllamaTutorLLM`: the same three methods against an Ollama server (`OLLAMA_URL`,
  `OLLAMA_TUTOR_MODEL`, `OLLAMA_CHECK_MODEL`).
- `tutor_host.py`, `_llm()`: picks the tutor backend from `TUTOR_LLM` and `ANTHROPIC_API_KEY`.
- Settings live in `mock-canvas/.env` (template: `.env.example`).
- User-facing text calls the assistant **Hue**, never Claude. Both features reach users through the Hue dock on every
  course page (`ui.hue_dock`, `static/hue.js`, `static/hue.css`).

`apps/api` makes no LLM calls; `app/analytics/embeddings.py` runs a local MiniLM ONNX embedding model offline.

## Carmen mock-canvas, main files

- `server.py` (FastAPI app and JSON API), `ui.py` (HTML pages), `static/` (JS and CSS)
- `sync.py` → `db_store.py`, `outcome_mapper.py`, `ler_builder.py`: mirror the course into Supabase
- `ingest.py` (Canvas → analytics bundle), `ocr.py`, `uploads.py`
- `tutor/service.py`: one tutor turn (scope → mode → retrieve → generate → verify → log); see also `policy.py`,
  `prompts.py`, `verifier.py`, `repo.py`, `router.py`

## Tests

`apps/api/tests` (pytest, `npm run test:api`), `apps/web/src/test` (Vitest), and
`carmen-study-guide/mock-canvas/tests` plus `tutor/tests` (pytest, run with the mock-canvas `.venv`).

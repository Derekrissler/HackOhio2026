# Phase 1 — Repository Analysis & Architecture Plan

Status: **proposal, awaiting approval**. No application code has been written or modified.

Reference repo analysed: `../canvas-lms` (clean clone of `instructure/canvas-lms`, branch `master`, HEAD `1c9f0bb8013`). It has not been modified.

---

## 1. Technical overview of `canvas-lms`

| Area | What the source shows |
|---|---|
| **Languages** | Ruby (backend), TypeScript/JavaScript (frontend), ERB templates, SCSS |
| **Backend** | Ruby on Rails **8.0** (`config/canvas_rails_switcher.rb`), Ruby **3.4** (`Dockerfile`: `ARG RUBY=3.4`). ~335 models in `app/models`, ~224 controllers, large business-logic layer in `lib/`, plugins in `gems/plugins/` |
| **Frontend** | React 18 + **InstUI 11.6** (`@instructure/ui-*`), TanStack Query, Apollo GraphQL client, *and* legacy Backbone 1.1 / jQuery / JST. 232 page bundles in `ui/features/*`, 230 shared packages in `ui/shared/*`, built with rspack (`rspack.config.js`) |
| **Page model** | A hybrid: Rails renders `app/views/layouts/application.html.erb` (global nav, course nav, `window.ENV` payload), then mounts one JS bundle from `ui/features/<page>` for that page. Many pages (e.g. `grade_summary`, `syllabus`) still mix Backbone, jQuery and React |
| **Database** | **PostgreSQL only** (`config/database.yml.example`, `Gemfile.d/postgres.rb`), with Switchman sharding and partitioned tables. The base schema is a squashed 5,400-line migration (`db/migrate/20101210192618_init_canvas_db.rb`) |
| **Other infrastructure** | Redis (cache/sessions), delayed_jobs worker, and optional Consul, Vault, DynamoDB, Kinesis, Kafka, S3/Inst-FS, Canvadocs/DocViewer, RCE API, mail, Sentry and StatsD (36 `config/*.yml.example` files) |
| **Auth & roles** | `Pseudonym` (login) → `User`; roles come from `Enrollment` types (Student, Teacher, TA, Designer, Observer) plus a large `Role`/`RoleOverride` permission system over `Account` hierarchies (multi-tenant) |
| **Courses** | `Course` (5,153 lines) ← `Enrollment`, `CourseSection`, `ContextModule`/`ContentTag` (modules), `WikiPage` (pages), `syllabus_body` on the course |
| **Assignments** | `Assignment` + `AssignmentGroup` (weighted categories), `AssignmentOverride`, `Rubric`/`RubricAssociation`/`RubricAssessment` |
| **Quizzes** | Classic Quizzes: `Quizzes::Quiz`, `QuizQuestion` (`question_data` is serialized YAML), `QuizSubmission` (`submission_data` is a serialized array of per-question results such as `{question_id, correct, points, text, more_comments}`). **New Quizzes** is a separate Instructure-hosted LTI service, so its item data is not in this DB |
| **Gradebook** | `ui/features/gradebook` (SlickGrid), `enhanced_individual_gradebook`, `grade_summary` (student "Grades" page), backed by `Submission` (3,944 lines) and `lib/grade_calculator.rb` |
| **Feedback storage** | `SubmissionComment` (text, attachments, media, `attempt`, `teacher_only_comment`, `draft`); `RubricAssessment.data` (per-criterion points and comments); quiz per-question comments (`more_comments`); **PDF annotations from SpeedGrader live in the external DocViewer/Canvadocs service.** Only `CanvadocsAnnotationContext` (a pointer) is stored locally |
| **Outcomes** | `LearningOutcome`, `LearningOutcomeGroup`, `OutcomeProficiency`; alignments are `ContentTag` rows with `tag_type='learning_outcome'`; results are `LearningOutcomeResult` (score, possible, mastery, per user and per alignment) |
| **Files** | `Attachment` (2,826 lines) + `Folder`, stored on local disk/S3/Inst-FS; previews through Canvadocs |
| **API** | REST `/api/v1/*` (`config/routes.rb`, `lib/api/v1/*.rb` serializers, YARD `@API`/`@model` docs in controllers), plus GraphQL (`schema.graphql`) |
| **Running locally** | Officially Docker Compose (`web`, `jobs`, `postgres`, `redis`) + `script/docker_dev_setup.sh`, then `yarn build`, `rails db:initial_setup`. Native Windows is not supported |

**How the pieces interact:** browser → Rails controller (checks permissions through `grants_right?` across Account/Course/Enrollment) → ActiveRecord models (Postgres) → ERB layout + `js_env` → per-page React/Backbone bundle → that bundle calls `/api/v1` or GraphQL for more data. Background work (grading recalculation, outcome rollups, notifications) runs on delayed_jobs.

**Local machine check:** Docker 29, Node 24 and Python 3.14 are installed. Ruby is **4.0** (Canvas pins 3.4), and there is no Yarn or Postgres. Native Canvas would not run as-is; Docker is the only option.

---

## 2. KEEP / SIMPLIFY / REMOVE

"Keep" here means **keep the concept and its UX in our app**, not necessarily Canvas's code (see §3).

### KEEP

| Feature | Why |
|---|---|
| Dashboard (course cards) → course home | The entry point of the demo flow; users expect it to look like Canvas |
| Left global nav + course nav (Home, Syllabus, Assignments, Quizzes, Grades, Files, **Learning Insights**) | Gives the "this lives inside Canvas" feel. Our analytics tab sits here, where an LTI tool would later appear |
| Syllabus page with explicit learning objectives | Source of truth for learning outcomes |
| Assignments list and detail, quizzes and exams | The assessed artefacts |
| Questions and per-question responses/scores | **Core AI input.** Canvas only stores these for Classic Quizzes; we model them for every assessment type |
| Submission comments, rubric scores and criterion comments, quiz question comments | **Core AI input** (instructor feedback) |
| Learning outcomes and alignments (question/criterion → outcome) | Core of the mapping; same concept as Canvas `ContentTag` alignments |
| Student Grades page | The baseline we improve on |
| Files / course materials (lectures, slides, readings, scanned PDFs) | Retrieval targets for recommendations; scanned exams are evidence |
| Enrollment-based roles (student / teacher) | Needed for permissions and class-wide aggregation |

### SIMPLIFY

| Feature | Canvas today | Our version |
|---|---|---|
| Authentication | Pseudonyms, SAML/LDAP/OAuth, MFA, sessions in Redis | Demo user switcher (picks a seeded user). One backend dependency resolves the "current user", so LTI 1.3 can replace it later |
| Permissions | Account hierarchy, `RoleOverride`, ~200 permissions | Two checks: *is enrolled as teacher in this course* / *is this student's own data* |
| Database | Postgres + sharding + partitions + Redis | One SQLite file |
| Gradebook | SlickGrid gradebook, weighting, late policies, moderation, post policies | Read-only grade summary; optional assignment-group weights; no editing in v1 |
| Quizzes | Classic + New Quizzes, regrades, question banks, logs | Static question list + stored responses; no quiz-taking engine |
| Modules | Prerequisites, mastery paths, requirements | Optional "week/module" label on materials and assessments |
| Files | Folders, Inst-FS, Canvadocs previews, usage rights | Flat list per course on local disk; in-browser PDF view |
| Outcomes | Account-level banks, proficiency scales, calculation methods | Course-level outcomes + one mastery threshold |
| Config | 36 YAML configs, Consul, Vault, feature flags | One `.env` file |

### REMOVE / DISABLE

| Feature | Why |
|---|---|
| Account/sub-account admin, terms, SIS import, authentication providers, branding/theme editor | Institutional administration, not needed for the demo |
| Conversations/Inbox, announcements, notifications, mail, Twilio | Messaging is out of scope |
| Discussions, collaborations, conferences, ePortfolios, groups, calendar, planner | Not assessment data (discussions could come back later as an extra evidence source) |
| Blueprint courses, course copy, content migrations/exports, Moodle/QTI importers | Content syndication |
| LTI tool hosting, developer keys, marketplace | We may become an LTI tool later; we don't host them |
| Built-in analytics (`analytics_hub`, `course_statistics`, page views, `learning_mastery_v2`) | Replaced by our analytics. `learning_mastery_v2`'s outcome × student grid is a useful **UX reference** for our heatmap |
| Canvas AI features (`ignite_agent`, `study_assist`, `learning_agent`) | Unrelated, and they depend on external services |
| K5, Canvas Career/Horizon, mobile login, accessibility checker, course pacing, moderated grading, peer review | Nonessential for the demo |
| Sharding, jobs infra, Kafka/Kinesis/DynamoDB, statsd, Sentry | Production infrastructure |

---

## 3. Approach A vs Approach B

### Approach A: simplify the existing repository

- **Setup cost:** Docker build of Ruby 3.4 + Passenger image, `bundle install` (hundreds of gems), `yarn install` (~1,000+ packages), full rspack build, `db:initial_setup`. Realistically **2–4 hours on a good machine, the first time**, with tens of GB of disk and 8–16 GB of RAM for Docker on Windows. Every teammate pays this cost.
- **Simplifying is the hard part.** Features are tightly coupled through `Course` (5k lines), `User` (4k), `Submission` (4k), callbacks, delayed jobs and permissions. Removing features means chasing breakage across ~560 models/controllers and specs. In 48 hours it is safer to leave Canvas whole, which means we are running a full LMS rather than a simplified one.
- **Adding our dashboard** means a Rails controller + route + permission check + ERB + `ui/features/<x>` bundle + rspack rebuild, written in Ruby by a team that would also need to learn Canvas internals.
- **AI pipeline** would sit in Ruby/Rails or need a sidecar service anyway.
- **Upside:** authentic UI and real Canvas data structures for free; its own REST API makes adapter testing trivial.
- **Licence:** AGPLv3. Fine if our repo is public and AGPL.

### Approach B: build a new lightweight app that reuses selected Canvas pieces

- **Reuse InstUI** (`@instructure/ui` 11.6, **MIT-licensed**, published on npm, the same version Canvas pins). This gives us Canvas's actual buttons, tables, tabs, typography and colours, which is most of the "looks like Canvas" effect, with no licence burden.
- **Reuse Canvas's information architecture and layout patterns** (dark global nav, course nav, breadcrumbs, Grades table, SpeedGrader-style comments). We re-implement these rather than copy code.
- **Reuse Canvas's REST response shapes as our ingestion contract.** The `@model` YARD docs in `app/controllers/*_api_controller.rb` and the serializers in `lib/api/v1/*.rb` define these shapes. Our seed data is written **in Canvas API JSON format** and goes through the same adapter as real API data (see §4.3).
- **Setup:** `npm install` + `pip install`, about 5 minutes; runs natively on Windows in VS Code.
- **Risk:** the UI is a lookalike, not real Canvas, so we have to build navigation and pages ourselves (but only ~8 pages).
- **Licence:** if we **don't copy Canvas source files**, our code carries no AGPL obligations. If we do copy a component (e.g. an SVG icon set or a SCSS variable file), we must license the repo AGPL-3.0. Decide this before Phase 2.

### Comparison

| | A: modify Canvas | B: new app + reuse |
|---|---|---|
| Time to first runnable page | 3–5 h (setup) | < 1 h |
| Ongoing complexity | Very high (Rails, Backbone, jQuery, rspack, Postgres, Redis) | Low (2 small services) |
| Fidelity to Canvas UI | 100% | ~85% (InstUI + layout) |
| Ease of adding analytics + AI | Low–medium | High |
| Windows/VS Code friendliness | Poor (Docker-only, heavy) | Good |
| Canvas API compatibility | Native | Through the adapter (designed for it) |
| Path to LTI 1.3 | Tool would be external anyway | App *is* the future LTI tool; the Canvas-lookalike shell gets dropped |
| 48-hour feasibility | Risky | **Good** |

### Recommendation: **Approach B**

The parts of Canvas we actually need (InstUI, the navigation layout, the data shapes) can be reused without running Canvas. The parts we'd inherit from Approach A (Postgres, Redis, sharding, permissions, Backbone) are cost with no demo value. Approach B also matches the long-term shape of the product: an analytics tool that **consumes** Canvas data and is eventually **launched from** Canvas through LTI. The Canvas-lookalike shell is demo scaffolding around that tool.

*Optional:* if someone has time in Phase 4, stock Canvas can run in Docker **unmodified** as a local "real Canvas API" to test the adapter. It is not on the critical path.

---

## 4. Recommended architecture

```
HackOhio2026/
├─ apps/
│  ├─ web/                 React 18 + TypeScript + Vite + InstUI 11 + React Router + TanStack Query
│  │  └─ src/
│  │     ├─ shell/         GlobalNav, CourseNav, Breadcrumbs, RoleSwitcher  (Canvas look)
│  │     ├─ pages/         Dashboard, CourseHome, Syllabus, Assignments, AssignmentDetail,
│  │     │                 Quizzes, Grades, Files, StudentInsights, InstructorAnalytics
│  │     └─ api/           typed client generated from the backend's OpenAPI schema
│  └─ api/                 Python FastAPI + SQLAlchemy 2 + SQLite
│     └─ app/
│        ├─ auth.py        current_user() + require_teacher()/require_self()   ← LTI swap point
│        ├─ models/        ORM tables (§5)
│        ├─ schemas/       Pydantic DTOs: the normalized "canonical" model
│        ├─ routers/       courses, assessments, submissions, outcomes, materials, analytics
│        ├─ ingest/        adapters → canonical model → loader (§4.3)
│        ├─ analytics/     deterministic metrics (mastery, denominators, aggregates)
│        └─ ai/            (Phase 5) diagnosis, mapping, retrieval, recommendations
├─ data/
│  ├─ seed/canvas_json/    fictional course written in Canvas REST API format
│  ├─ seed/files/          lecture PDFs, slides, scanned exam PDFs
│  └─ app.db               SQLite (gitignored, rebuilt from seed)
└─ docs/
```

### 4.1 Key decisions

1. **Frontend: React + InstUI**, the same stack Canvas's modern pages use. This keeps the "prefer the existing framework" requirement where it matters (the UI) and gets us the Canvas look.
2. **Backend: Python/FastAPI rather than Rails.** Rails only helps if we use Canvas's models, which we won't. Python is the strongest ecosystem for the AI phase (LLM SDKs, PDF tooling, embeddings), FastAPI emits OpenAPI for a typed frontend client, and SQLite needs zero setup. *Alternative:* Node/Express + TypeScript if the team strongly prefers one language. Everything else in this plan still holds.
3. **Strict separation:** the frontend never touches the DB or AI directly; everything goes through `/api`. Student and instructor dashboards call **the same analytics service** with different scopes, so their numbers can't disagree.
4. **One authorization choke point** (`auth.py`). Demo mode reads an `X-Demo-User` header set by the role switcher. LTI 1.3 later supplies the same `(user, course, role)` triple from the launch token.
5. **Recorded vs. inferred data live in separate tables** (§5). Every AI output row carries `analysis_run_id`, `confidence` and evidence links. This makes the integrity rules (§6 of the requirements) enforceable in the schema, not just the UI.
6. **Scanned PDFs:** stored as files. Text and handwriting extraction happens in Phase 5 by sending the PDF pages to a vision-capable LLM. No OCR engine install is needed.

### 4.2 Pages and the demo flow

- **Student:** Dashboard → Course → Syllabus (outcomes highlighted) → Assignments/Quizzes → Grades (with question-level breakdown + feedback) → **Learning Insights** (gaps, evidence, materials, practice).
- **Instructor:** Dashboard → Course → **Instructor Analytics**: outcome mastery bars → weakest outcomes → click an outcome → common misconceptions + questions + evidence → teaching recommendations; student × outcome heatmap; filterable student table.
- **Role switcher** in the global nav: "Viewing as: Prof. Rivera / Student: Alex Kim / …".

### 4.3 Interchangeable ingestion layer

```
          ┌──────────────────────┐
seed JSON │ CanvasJsonAdapter    │──┐
(Canvas   │ (reads files)        │  │      canonical Pydantic models      ┌────────┐
 format)  └──────────────────────┘  ├──►  Course, User, Outcome, Assessment, ──►│ Loader │──► SQLite
          ┌──────────────────────┐  │      Question, Submission, Response,     └────────┘
Canvas    │ CanvasApiAdapter     │──┤      Feedback, Material
REST API  │ (token, paginated)   │  │
          └──────────────────────┘  │
          ┌──────────────────────┐  │
manual    │ ManualAdapter        │──┘   for data Canvas can't provide (scanned exams,
upload    │ (CSV/PDF + form)     │      paper-exam question scores, PDF annotations)
          └──────────────────────┘
```

Both Canvas adapters share one `normalize_*()` layer. The API adapter just fetches the JSON; the JSON adapter reads the same JSON from disk. **Seed data therefore tests the real normalization code.** Each adapter declares a `capabilities` set (e.g. `{"question_responses", "rubrics"}`), so the UI can show "not available from this source" instead of empty charts.

**What real Canvas API access realistically provides** (affects Phase 4 scope):

| Data | Endpoint | Caveat |
|---|---|---|
| Courses, users, enrollments | `/courses`, `/courses/:id/users` | Student tokens see only themselves |
| Syllabus | `/courses/:id?include[]=syllabus_body` | HTML; objectives must be extracted |
| Assignments | `/courses/:id/assignments` | |
| Submissions + comments + rubric | `/…/submissions?include[]=submission_comments&include[]=rubric_assessment&include[]=submission_history` | Teacher token for class-wide data |
| Classic quiz questions | `/courses/:id/quizzes/:qid/questions` | Teacher only |
| Classic quiz per-question results | `submission_history[].submission_data` | Available for Classic Quizzes only |
| New Quizzes item responses | — | **Not in public REST API**, only via quiz reports (CSV) |
| Outcomes, alignments, results | `/outcome_groups`, `/outcome_alignments`, `/outcome_results`, `/outcome_rollups` | Many courses don't use outcomes |
| Files | `/courses/:id/files` | Downloads need auth |
| SpeedGrader PDF annotations | — | **Stored in DocViewer; not exposed.** Use ManualAdapter (annotated PDF export) |

---

## 5. Minimal data model (design only)

Legend: **[C]** = Canvas provides it directly · **[C*]** = Canvas provides it only sometimes (Classic Quizzes, courses that use outcomes/rubrics) · **[M]** = manual/seed · **[AI]** = inferred by our pipeline · **[D]** = derived deterministically from recorded data.

All tables have `id` (our PK) plus, where relevant, `source` (`canvas|seed|manual|ai`) and `external_id` (Canvas ID) for idempotent re-ingestion.

### 5.1 Recorded academic data

```
users            id, external_id[C], name[C], sortable_name[C], email[C], avatar_url[C]
courses          id, external_id[C], code[C], name[C], term[C], syllabus_html[C], syllabus_file_id[M]
enrollments      id, course_id, user_id, role{student,teacher,ta}[C], section[C]
                 UNIQUE(course_id,user_id,role)

learning_outcomes id, course_id, code ("LO3")[M/AI], title[C*/AI], description[C*/AI],
                 source{canvas,syllabus_ai,instructor}, external_id[C*],
                 mastery_threshold (default 0.70), position,
                 extraction_confidence[AI], instructor_approved bool

assessments      id, course_id, external_id[C], title[C], kind{homework,quiz,exam,project,lab}[C/M],
                 points_possible[C], due_at[C], assignment_group[C], group_weight[C],
                 submission_types[C], description_html[C], module_label[C/M], position

questions        id, assessment_id, external_id[C*], parent_question_id (sub-parts "3b"),
                 label ("Q3b")[M], position, prompt_text[C*/M/AI-from-scan],
                 question_type{multiple_choice,numeric,short_answer,essay,proof,file,…}[C*/M],
                 points_possible[C*/M], answer_key json[C*/M], source_file_id + page[M]

rubric_criteria  id, assessment_id, external_id[C*], description[C*], points[C*],
                 learning_outcome_id[C*]   -- Canvas's own outcome-aligned rubric rows

submissions      id, assessment_id, user_id, external_id[C], attempt[C],
                 submitted_at[C], graded_at[C], score[C], grade[C], excused/late/missing[C],
                 workflow_state[C], file_id[C/M]          UNIQUE(assessment_id,user_id,attempt)

question_responses id, submission_id, question_id, response json/text[C*/M/AI-from-scan],
                 points_awarded[C*/M], points_possible (snapshot), is_correct (nullable)[C*/D],
                 graded_by{canvas_auto,instructor,manual_entry}
                 UNIQUE(submission_id,question_id)

rubric_scores    id, submission_id, criterion_id, points[C*], comment[C*]

feedback         id, submission_id, question_response_id NULL, rubric_score_id NULL,
                 author_id[C], kind{submission_comment,question_comment,rubric_comment,
                 pdf_annotation,transcribed_handwriting}, text[C/M/AI],
                 file_id + page + bbox json (annotations)[M], attempt[C],
                 created_at[C], visible_to_student bool[C]

files            id, course_id, owner_user_id NULL, filename, mime, storage_path, sha256,
                 page_count, text_extraction_status{none,text,ocr_ai}, external_id[C]

course_materials id, course_id, file_id NULL, url NULL, title[C/M],
                 kind{lecture,slides,reading,notes,worked_example,video,other}[M],
                 module_label/week[C/M], position
material_segments id, material_id, locator ("slides 15–22" / "p. 4"), page_start, page_end,
                 text[D/AI], embedding blob NULL[AI]
```

### 5.2 Mappings (the heart of the system, provenance on every row)

```
question_outcomes  question_id, outcome_id, weight (0–1, default 1),
                   source{canvas_alignment,instructor,ai}, confidence, rationale, analysis_run_id NULL
                   PK(question_id,outcome_id)
material_outcomes  segment_id, outcome_id, source, confidence, analysis_run_id NULL
```
Question → material links are **derived through shared outcomes** (and later, embedding similarity), so there is no third table to keep in sync.

### 5.3 AI / analytics layer (Phase 5+, schema fixed now)

```
analysis_runs      id, course_id, scope{course,student}, model, prompt_version, input_hash,
                   started_at, finished_at, status
misconceptions     id, course_id, outcome_id, label, description, analysis_run_id
                   -- canonical, course-level clusters → enables "42% of students…"
diagnoses          id, analysis_run_id, question_response_id, user_id (denormalized),
                   outcome_id, misconception_id NULL,
                   error_type{conceptual,procedural,careless,incomplete,unknown},
                   explanation, confidence (0–1), evidence_sufficient bool
diagnosis_evidence diagnosis_id, evidence_type{response,feedback,rubric_score,question},
                   evidence_id, quote
mastery_estimates  user_id, outcome_id, analysis_run_id NULL, method{points_ratio,ai_adjusted},
                   points_earned, points_possible, n_questions, n_assessments,
                   estimate (0–1), level{proficient,developing,struggling,insufficient_evidence}
recommendations    id, analysis_run_id, audience{student,instructor}, user_id NULL, course_id,
                   outcome_id NULL, misconception_id NULL,
                   kind{review_material,practice,reteach_topic,worked_example,clarify_objective},
                   text, material_segment_ids json, evidence_diagnosis_ids json
practice_problems  id, outcome_id, misconception_id NULL, user_id NULL, prompt, solution,
                   analysis_run_id
```

### 5.4 Metric definitions (fixed denominators)

- **Outcome mastery (student, [D]):** Σ points_awarded ÷ Σ points_possible over graded `question_responses` whose question maps to the outcome (weighted by `question_outcomes.weight`). It is `insufficient_evidence` if fewer than 2 questions or 1 assessment contribute. It is labelled **"estimated"** whenever any contributing mapping has `source='ai'`.
- **% proficient (class):** numerator = students with level `proficient`; **denominator = enrolled students with ≥ 1 graded response aligned to that outcome**. The UI shows "n of N".
- **Struggling count:** students with level `struggling` (estimate < threshold − 0.15). Thresholds are configurable.
- **Misconception prevalence:** distinct students with ≥ 1 diagnosis linked to the misconception ÷ distinct students with a graded response to ≥ 1 question where that misconception was diagnosed for anyone. Listed with its question IDs.
- **Trend:** the same mastery formula computed per assessment, ordered by `due_at`.
- **Frequently missed question:** % of graded responses with points_awarded < 0.5 × possible; denominator = graded responses.

Recorded grades, derived mastery, AI-inferred misconceptions and AI recommendations each get a distinct visual badge.

---

## 6. Roadmap

| Phase | Deliverables | Likely files | Depends on | Acceptance criteria | Main risks |
|---|---|---|---|---|---|
| **1 Analysis** (done) | This document | `docs/PHASE1_PLAN.md` | — | Team approves the approach + model | — |
| **2 Minimal app** | Monorepo skeleton; FastAPI health + `/me` + `/courses`; React shell with Canvas-style global/course nav; role switcher; placeholder pages incl. both dashboards; tiny hard-coded seed (1 course, 1 teacher, 3 students) | `apps/web/*`, `apps/api/app/{main,auth,db}.py`, `README.md`, `.env.example` | Approval; licence decision | `npm run dev` + `uvicorn` run on Windows; all nav links route; switching to a student hides Instructor Analytics and the API returns 403 for it | InstUI 11 + Vite config quirks; Python 3.14 wheel availability (fallback 3.12) |
| **3 Academic data** | Full ORM schema (§5.1–5.2 + empty §5.3 tables); seed course in **Canvas JSON format** (~25 students, 6–8 assessments, 30–50 questions, comments, rubric, 5–7 outcomes, PDFs); CanvasJsonAdapter + loader; real pages for syllabus, assignments, quiz detail, grades with question breakdown, files/PDF viewer; deterministic mastery endpoint | `app/models/*`, `app/ingest/{canonical,canvas_normalize,canvas_json_adapter,loader}.py`, `data/seed/**`, `scripts/seed.py`, `apps/web/src/pages/*` | Phase 2 | `python scripts/seed.py` rebuilds DB from scratch; every page shows seeded data; mastery numbers match a hand-calculated spreadsheet for 2 students | Generating realistic seed data with *planted* misconceptions takes time (script + LLM-assisted authoring); PDF viewer dependency (pdf.js) to discuss |
| **4 Canvas integration** | CanvasApiAdapter (token, pagination, rate limits), capability flags, ManualAdapter (CSV question scores + PDF upload), CLI `ingest --source canvas --course 123` | `app/ingest/canvas_api_adapter.py`, `manual_adapter.py` | Phase 3; a token for some Canvas instance | Ingesting a real or sandbox course gives the same page behaviour; missing capabilities are shown, not faked | Limited token scope; New Quizzes/annotation gaps; no test instance (fallback: recorded API fixtures) |
| **5 AI pipeline** | Syllabus → outcomes extraction (instructor approves); question → outcome mapping; scanned-PDF transcription; per-response diagnosis with evidence + confidence; misconception clustering per course; material segmentation + retrieval; analysis_runs bookkeeping; cached results | `app/ai/{client,extract_outcomes,map_questions,diagnose,cluster,retrieve,prompts/}.py`, `routers/analysis.py` | Phase 3 data; LLM API key | Re-running on seed data reproduces planted misconceptions; every diagnosis has ≥ 1 evidence link; low-confidence items flagged | Cost/latency (batch + cache by `input_hash`); hallucinated mappings (instructor-approval step, confidence); handwriting quality |
| **6 Student dashboard** | Outcome mastery chart, gaps with evidence drill-down, linked material segments, AI practice problems, uncertainty badges | `pages/StudentInsights/*`, `components/charts/*`, `routers/analytics.py` | Phase 5 | Student sees only their own data; each gap links to questions + feedback + material | Chart library choice (to discuss: Recharts vs. hand-rolled SVG) |
| **7 Instructor dashboard** | Outcome mastery bars with n/N; weakest/strongest; outcome drill-down (misconceptions → questions → evidence); student × outcome heatmap; filterable student table; trends; assessment breakdown; teaching recommendations | `pages/InstructorAnalytics/*`, `analytics/aggregates.py` | Phases 5–6 (shared service) | Instructor workflow steps 1–7 work end-to-end; every number shows its denominator; numbers agree with the student view | Scope creep; heatmap readability with 25+ students |
| **8 Integration & demo** | Calculation tests, permission tests, one-command reset + seed + precomputed AI results (offline-safe demo), demo script | `tests/*`, `scripts/demo_reset.py`, `docs/DEMO.md` | All | Fresh clone → demo in < 10 min; demo works without network using cached AI output | Live API failures during judging (mitigated by cache) |

**Change from your draft roadmap:** the AI/analytics tables (§5.3) and metric definitions (§5.4) are created in **Phase 3**, not Phase 5, so that instructor aggregation never needs a migration later. Phase 3 also ships the deterministic mastery endpoint that both dashboards will use.

---

## 7. First concrete Phase 2 tasks

1. Create the monorepo layout in `HackOhio2026/` (`apps/web`, `apps/api`, `data/`, `docs/`) with a root `README.md` that has Windows-friendly run steps, plus `.gitignore` (`data/app.db`, `.venv`, `node_modules`, `.env`).
2. `apps/api`: FastAPI app, SQLAlchemy engine on `data/app.db`, `GET /api/health`, `GET /api/me`, `GET /api/courses`, `GET /api/courses/{id}`; `auth.py` with `current_user()` reading `X-Demo-User`, plus `require_enrolled()` and `require_teacher()`; a minimal `users/courses/enrollments` table set + a 5-row seed.
3. `apps/web`: Vite + React 18 + TS; install the InstUI packages we need (`@instructure/ui` meta-package or ~10 scoped packages at 11.6.x) and apply the `canvas` theme; React Router routes `/`, `/courses/:id`, `/courses/:id/{syllabus,assignments,quizzes,grades,files,insights,analytics}`.
4. Shell components: `GlobalNav` (dark left rail: Account, Dashboard, Courses), `CourseNav` (role-aware: *Learning Insights* for students, *Instructor Analytics* for teachers), `Breadcrumbs`, `RoleSwitcher` (stores the selected user, sets the header on every request).
5. Placeholder pages that fetch from the API and render "coming in Phase N" panels; Dashboard renders real course cards.
6. Vite dev proxy `/api → localhost:8000`; `npm run dev` script that starts both (e.g. `concurrently`, to be confirmed).
7. Smoke checks: a student calling `/api/courses/1/analytics/*` gets 403; nav hides the instructor tab.

### Decisions needed before Phase 2

1. Approve **Approach B**.
2. Backend language: **Python/FastAPI** (recommended) or Node/TypeScript.
3. Licence: avoid copying Canvas source (recommended; our code stays under any licence) **or** copy freely and license the repo AGPL-3.0.
4. Location: build in `HackOhio2026/` (assumed) and keep `canvas-lms/` as a read-only reference.
5. New dependencies for Phase 2: InstUI, React Router, TanStack Query, Vite (frontend); FastAPI, Uvicorn, SQLAlchemy, Pydantic (backend). All lightweight; listed here for sign-off.

-- Core schema for the learning-analytics pipeline (spec §7).
-- Raw source facts, LERs (evidence), ARRs (analytics) and IRs (insights) are distinct tables.
-- All pipeline writes go through the service role; browsers only read, scoped by RLS.

create schema if not exists private;

-- ---------------------------------------------------------------------------
-- People, courses, enrollment
-- ---------------------------------------------------------------------------

create table public.profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  is_admin     boolean not null default false,
  created_at   timestamptz not null default now()
);

create table public.courses (
  id         uuid primary key default gen_random_uuid(),
  code       text not null unique,                -- e.g. ISE3200
  title      text not null,
  canvas_id  text unique,
  created_at timestamptz not null default now()
);

create table public.enrollments (
  course_id  uuid not null references public.courses(id) on delete cascade,
  user_id    uuid not null references public.profiles(id) on delete cascade,
  role       text not null check (role in ('student','instructor','ta')),
  created_at timestamptz not null default now(),
  primary key (course_id, user_id)
);

-- Pseudonymous analytics identity, kept apart from the real user (spec §14).
create table public.learners (
  id         uuid primary key default gen_random_uuid(),
  course_id  uuid not null references public.courses(id) on delete cascade,
  pseudonym  text not null,                       -- e.g. S-014
  created_at timestamptz not null default now(),
  unique (course_id, pseudonym)
);

-- Identity mapping: readable by the learner themself and course instructors only.
create table public.learner_identities (
  learner_id uuid primary key references public.learners(id) on delete cascade,
  user_id    uuid not null references public.profiles(id) on delete cascade,
  course_id  uuid not null references public.courses(id) on delete cascade,
  unique (course_id, user_id)
);

-- ---------------------------------------------------------------------------
-- Outcomes, documents, resource index (spec §5)
-- ---------------------------------------------------------------------------

create table public.outcomes (
  id                   uuid primary key default gen_random_uuid(),
  course_id            uuid not null references public.courses(id) on delete cascade,
  code                 text not null,             -- e.g. LO-03
  syllabus_text        text not null,             -- exact syllabus wording
  parent_id            uuid references public.outcomes(id),
  source_document_id   uuid,                      -- FK added below
  instructor_verified  boolean not null default false,
  unique (course_id, code)
);

create table public.documents (
  id                  uuid primary key default gen_random_uuid(),
  course_id           uuid not null references public.courses(id) on delete cascade,
  title               text not null,
  doc_type            text not null check (doc_type in
                        ('syllabus','slides','textbook','reading','assessment','submission_scan','answer_key','other')),
  storage_bucket      text not null,
  storage_path        text not null,
  sha256              text not null,
  mime_type           text,
  page_count          int,
  canvas_id           text,
  -- Owner learner for student submissions; null for course material.
  learner_id          uuid references public.learners(id) on delete cascade,
  publication_status  text not null default 'draft'
                        check (publication_status in ('draft','released','restricted')),
  rights_cleared      boolean not null default false,
  uploaded_at         timestamptz not null default now(),
  unique (course_id, sha256)
);

alter table public.outcomes
  add constraint outcomes_source_document_fk
  foreign key (source_document_id) references public.documents(id);

create table public.resource_chunks (
  id                  uuid primary key default gen_random_uuid(),
  course_id           uuid not null references public.courses(id) on delete cascade,
  document_id         uuid not null references public.documents(id) on delete cascade,
  title               text,
  content             text not null,
  doc_type            text not null,
  page                int,
  slide               int,
  section             text,
  deep_link           text,
  -- Copied from the document at index time; must be released + student_visible to reach students.
  publication_status  text not null check (publication_status in ('draft','released','restricted')),
  student_visible     boolean not null default false,
  extraction_version  text not null,
  embedding           extensions.vector(1536),
  embedding_version   text,
  fts                 tsvector generated always as (to_tsvector('english', coalesce(title,'') || ' ' || content)) stored,
  created_at          timestamptz not null default now()
);

create table public.chunk_outcomes (
  chunk_id   uuid not null references public.resource_chunks(id) on delete cascade,
  outcome_id uuid not null references public.outcomes(id) on delete cascade,
  confidence real,
  provenance text not null default 'ai' check (provenance in ('ai','instructor','syllabus')),
  primary key (chunk_id, outcome_id)
);

-- ---------------------------------------------------------------------------
-- Assessments, questions, attempts, responses
-- ---------------------------------------------------------------------------

create table public.assessments (
  id               uuid primary key default gen_random_uuid(),
  course_id        uuid not null references public.courses(id) on delete cascade,
  code             text not null,                 -- e.g. HW2
  title            text not null,
  assessment_type  text not null check (assessment_type in ('homework','quiz','exam','project','practice')),
  -- Drives tutor assistance mode (spec §11.2); enforced server-side.
  integrity_status text not null default 'active_protected'
                     check (integrity_status in ('active_protected','guided_homework','closed','released')),
  answers_released boolean not null default false,
  due_at           timestamptz,
  canvas_id        text,
  unique (course_id, code)
);

create table public.questions (
  id               uuid primary key default gen_random_uuid(),
  course_id        uuid not null references public.courses(id) on delete cascade,
  assessment_id    uuid not null references public.assessments(id) on delete cascade,
  code             text not null,                 -- e.g. Q4
  position         int,
  text             text,
  locator          jsonb,                         -- {document_id, page, bbox_norm}
  question_type    text,
  points_possible  numeric,                       -- nullable by spec
  canvas_id        text,
  unique (assessment_id, code)
);

-- Protected: instructor/service only, never indexed for retrieval.
create table public.question_answer_keys (
  question_id  uuid primary key references public.questions(id) on delete cascade,
  course_id    uuid not null references public.courses(id) on delete cascade,
  answer       text not null,
  solution     text,
  updated_at   timestamptz not null default now()
);

create table public.question_outcomes (
  question_id   uuid not null references public.questions(id) on delete cascade,
  outcome_id    uuid not null references public.outcomes(id) on delete cascade,
  weight        real not null default 1.0,
  provenance    text not null default 'ai' check (provenance in ('ai','instructor')),
  confidence    real,
  rationale     text,
  needs_review  boolean not null default true,
  primary key (question_id, outcome_id)
);

create table public.attempts (
  id              uuid primary key default gen_random_uuid(),
  course_id       uuid not null references public.courses(id) on delete cascade,
  assessment_id   uuid not null references public.assessments(id) on delete cascade,
  learner_id      uuid not null references public.learners(id) on delete cascade,
  attempt_number  int not null default 1,
  submitted_at    timestamptz,
  canvas_id       text,
  unique (assessment_id, learner_id, attempt_number)
);

create table public.responses (
  id               uuid primary key default gen_random_uuid(),
  course_id        uuid not null references public.courses(id) on delete cascade,
  attempt_id       uuid not null references public.attempts(id) on delete cascade,
  question_id      uuid not null references public.questions(id) on delete cascade,
  learner_id       uuid not null references public.learners(id) on delete cascade,
  response_text    text,
  locator          jsonb,
  points_earned    numeric,                       -- nullable by spec
  rubric           jsonb,
  assistance       jsonb,                         -- independence/assistance metadata
  content_hash     text,
  updated_at       timestamptz not null default now(),
  unique (attempt_id, question_id)
);

-- ---------------------------------------------------------------------------
-- Evidence and feedback
-- ---------------------------------------------------------------------------

create table public.evidence_refs (
  id              uuid primary key default gen_random_uuid(),
  course_id       uuid not null references public.courses(id) on delete cascade,
  learner_id      uuid references public.learners(id) on delete cascade,
  source_type     text not null check (source_type in ('pdf','image','canvas_api','manual')),
  document_id     uuid references public.documents(id),
  canvas_ref      text,
  page            int,
  bbox_norm       real[] check (bbox_norm is null or array_length(bbox_norm,1) = 4),
  excerpt         text,
  content_hash    text,
  created_at      timestamptz not null default now()
);

create table public.feedback (
  id               uuid primary key default gen_random_uuid(),
  course_id        uuid not null references public.courses(id) on delete cascade,
  response_id      uuid not null references public.responses(id) on delete cascade,
  learner_id       uuid not null references public.learners(id) on delete cascade,
  kind             text not null check (kind in ('comment','handwritten','rubric_note','canvas_comment')),
  text             text not null,                 -- exact instructor wording
  evidence_ref_id  uuid references public.evidence_refs(id),
  created_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Learning Evidence Records (spec §6, §11.4). Append-only; corrections add a revision.
-- ---------------------------------------------------------------------------

create table public.error_taxonomy (
  code         text primary key,                  -- e.g. inequality_direction
  label        text not null,
  description  text,
  parent_code  text references public.error_taxonomy(code)
);

create table public.lers (
  id                       uuid primary key default gen_random_uuid(),
  schema_version           text not null default '1.0',
  course_id                uuid not null references public.courses(id) on delete cascade,
  learner_id               uuid not null references public.learners(id) on delete cascade,
  assessment_id            uuid references public.assessments(id) on delete cascade,
  question_id              uuid references public.questions(id) on delete cascade,
  attempt_id               uuid references public.attempts(id) on delete cascade,
  response_id              uuid references public.responses(id) on delete cascade,
  practice_attempt_id      uuid,                  -- FK added after practice_attempts
  revision                 int not null default 1,
  is_current               boolean not null default true,
  superseded_by            uuid references public.lers(id) deferrable initially deferred,
  assessment_origin        text not null default 'graded_canvas'
                             check (assessment_origin in ('graded_canvas','instructor_practice','generated_practice')),
  assistance_level         text,
  hints_used               int,
  independent_correctness  boolean,
  analysis_status          text not null check (analysis_status in ('analyzed','insufficient')),
  insufficiency_reason     text,
  extraction_version       text,
  model_version            text,
  payload                  jsonb not null default '{}'::jsonb,  -- full LER JSON as emitted by B
  created_at               timestamptz not null default now(),
  check (analysis_status = 'insufficient' or insufficiency_reason is null),
  check (response_id is not null or practice_attempt_id is not null or assessment_origin <> 'graded_canvas')
);

-- One current LER per graded response / practice attempt.
create unique index lers_current_response_uidx on public.lers(response_id) where is_current and response_id is not null;
create unique index lers_current_practice_uidx on public.lers(practice_attempt_id) where is_current and practice_attempt_id is not null;
create index lers_learner_idx on public.lers(course_id, learner_id) where is_current;

create table public.ler_outcomes (
  ler_id        uuid not null references public.lers(id) on delete cascade,
  outcome_id    uuid not null references public.outcomes(id) on delete cascade,
  confidence    real,
  provenance    text not null default 'ai' check (provenance in ('ai','instructor','question_mapping')),
  needs_review  boolean not null default true,
  primary key (ler_id, outcome_id)
);

create table public.ler_errors (
  id                 uuid primary key default gen_random_uuid(),
  ler_id             uuid not null references public.lers(id) on delete cascade,
  code               text not null references public.error_taxonomy(code),
  subcategory        text,
  misconception      text,
  confidence         real,                        -- model signal, not a calibrated probability
  instructor_status  text not null default 'unreviewed'
                       check (instructor_status in ('unreviewed','confirmed','rejected'))
);

create table public.ler_error_evidence (
  ler_error_id     uuid not null references public.ler_errors(id) on delete cascade,
  evidence_ref_id  uuid not null references public.evidence_refs(id) on delete cascade,
  primary key (ler_error_id, evidence_ref_id)
);

create table public.ler_evidence (
  ler_id           uuid not null references public.lers(id) on delete cascade,
  evidence_ref_id  uuid not null references public.evidence_refs(id) on delete cascade,
  role             text,                          -- question | response | feedback
  primary key (ler_id, evidence_ref_id)
);

-- ---------------------------------------------------------------------------
-- Analytics Result Records (spec §8–9)
-- ---------------------------------------------------------------------------

create table public.analytics_runs (
  id              uuid primary key default gen_random_uuid(),
  course_id       uuid not null references public.courses(id) on delete cascade,
  method          text not null,                  -- e.g. weighted_outcome_v1
  model_version   text not null,
  input_snapshot  text not null,                  -- hash of the eligible LER id set
  params          jsonb not null default '{}'::jsonb,
  started_at      timestamptz not null default now(),
  computed_at     timestamptz
);

create table public.analytics_results (
  id                     uuid primary key default gen_random_uuid(),
  schema_version         text not null default '1.0',
  run_id                 uuid not null references public.analytics_runs(id) on delete cascade,
  course_id              uuid not null references public.courses(id) on delete cascade,
  scope                  text not null check (scope in
                           ('student_outcome','class_outcome','assessment_question','misconception_cluster','longitudinal_trend')),
  subject_learner_id     uuid references public.learners(id) on delete cascade,
  outcome_id             uuid references public.outcomes(id) on delete cascade,
  assessment_id          uuid references public.assessments(id) on delete cascade,
  question_id            uuid references public.questions(id) on delete cascade,
  error_code             text references public.error_taxonomy(code),
  metrics                jsonb not null,
  numerator              numeric,
  denominator            numeric,
  inclusion_rule         text,
  period_start           timestamptz,
  period_end             timestamptz,
  interpretation_limits  jsonb not null default '{}'::jsonb,
  is_stale               boolean not null default false,
  created_at             timestamptz not null default now(),
  check ((scope = 'student_outcome') = (subject_learner_id is not null))
);

create index analytics_results_lookup_idx on public.analytics_results(course_id, scope, outcome_id) where not is_stale;
create index analytics_results_subject_idx on public.analytics_results(subject_learner_id) where subject_learner_id is not null;

create table public.arr_ler_links (
  arr_id  uuid not null references public.analytics_results(id) on delete cascade,
  ler_id  uuid not null references public.lers(id) on delete cascade,
  primary key (arr_id, ler_id)
);
create index arr_ler_links_ler_idx on public.arr_ler_links(ler_id);

-- ---------------------------------------------------------------------------
-- Insight Records (spec §10): persisted, invalidated when source ARRs go stale
-- ---------------------------------------------------------------------------

create table public.insight_records (
  id                  uuid primary key default gen_random_uuid(),
  course_id           uuid not null references public.courses(id) on delete cascade,
  audience            text not null check (audience in ('student','instructor')),
  subject_learner_id  uuid references public.learners(id) on delete cascade,
  outcome_id          uuid references public.outcomes(id) on delete cascade,
  headline            text not null,
  message             text not null,
  next_steps          jsonb not null default '[]'::jsonb,
  limits              jsonb not null default '{}'::jsonb,
  generation_method   text not null check (generation_method in ('template','llm','template+llm')),
  model_version       text,
  is_stale            boolean not null default false,
  generated_at        timestamptz not null default now(),
  expires_at          timestamptz,
  check ((audience = 'student') = (subject_learner_id is not null))
);

create table public.ir_arr_links (
  ir_id   uuid not null references public.insight_records(id) on delete cascade,
  arr_id  uuid not null references public.analytics_results(id) on delete cascade,
  primary key (ir_id, arr_id)
);
create index ir_arr_links_arr_idx on public.ir_arr_links(arr_id);

create table public.ir_chunk_links (
  ir_id     uuid not null references public.insight_records(id) on delete cascade,
  chunk_id  uuid not null references public.resource_chunks(id) on delete cascade,
  primary key (ir_id, chunk_id)
);

-- ---------------------------------------------------------------------------
-- Tutor and practice (spec §11)
-- ---------------------------------------------------------------------------

create table public.tutor_sessions (
  id              uuid primary key default gen_random_uuid(),
  course_id       uuid not null references public.courses(id) on delete cascade,
  learner_id      uuid not null references public.learners(id) on delete cascade,
  outcome_id      uuid references public.outcomes(id),
  assessment_id   uuid references public.assessments(id),
  question_id     uuid references public.questions(id),
  assistance_mode text not null check (assistance_mode in ('protected_assessment','guided_homework','independent_study')),
  started_at      timestamptz not null default now()
);

create table public.tutor_turns (
  id               uuid primary key default gen_random_uuid(),
  session_id       uuid not null references public.tutor_sessions(id) on delete cascade,
  speaker          text not null check (speaker in ('student','tutor')),
  content          text not null,
  pedagogical_move text check (pedagogical_move in ('ask','hint','analogous_example','feedback','explanation','decline')),
  hint_level       int,
  cited_chunk_ids  uuid[] not null default '{}',
  policy_decision  jsonb,                         -- mode, verifier verdict, blocked reasons
  created_at       timestamptz not null default now()
);

create table public.practice_attempts (
  id                       uuid primary key default gen_random_uuid(),
  course_id                uuid not null references public.courses(id) on delete cascade,
  learner_id               uuid not null references public.learners(id) on delete cascade,
  session_id               uuid references public.tutor_sessions(id) on delete set null,
  outcome_id               uuid references public.outcomes(id),
  origin                   text not null check (origin in ('instructor_practice','generated_practice')),
  prompt                   text not null,
  response                 text,
  hints_used               int not null default 0,
  assistance_level         text,
  independent_correctness  boolean,
  created_at               timestamptz not null default now()
);

alter table public.lers
  add constraint lers_practice_attempt_fk
  foreign key (practice_attempt_id) references public.practice_attempts(id) on delete cascade;

-- ---------------------------------------------------------------------------
-- Operations and lineage (technical status lives here, never on LERs)
-- ---------------------------------------------------------------------------

create table public.ingestion_jobs (
  id           uuid primary key default gen_random_uuid(),
  course_id    uuid not null references public.courses(id) on delete cascade,
  source       text not null check (source in ('canvas','mock','upload')),
  kind         text not null,                     -- ingest | extract | analytics | index | insight
  status       text not null default 'queued' check (status in ('queued','running','succeeded','failed','retrying')),
  attempts     int not null default 0,
  input        jsonb not null default '{}'::jsonb,
  output       jsonb,
  error        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create table public.extraction_revisions (
  id               uuid primary key default gen_random_uuid(),
  course_id        uuid not null references public.courses(id) on delete cascade,
  target_table     text not null,
  target_id        uuid not null,
  reviewer_id      uuid references public.profiles(id),
  before           jsonb,
  after            jsonb not null,
  reason           text,
  created_at       timestamptz not null default now()
);

create table public.audit_events (
  id          bigint generated always as identity primary key,
  course_id   uuid references public.courses(id) on delete cascade,
  actor_id    uuid,
  event       text not null,
  entity      text,
  entity_id   uuid,
  detail      jsonb,
  created_at  timestamptz not null default now()
);

-- Retrieval indexes
create index resource_chunks_embedding_idx on public.resource_chunks
  using hnsw (embedding extensions.vector_cosine_ops);
create index resource_chunks_fts_idx on public.resource_chunks using gin (fts);
create index resource_chunks_course_idx on public.resource_chunks(course_id, student_visible, publication_status);

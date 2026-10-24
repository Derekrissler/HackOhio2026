-- Row-level security (spec §2 boundaries, §14). Browsers are read-only; the pipeline and
-- tutor server write with the service role. Students see only their own learner rows and
-- released, student-visible material; staff (instructor/ta) see their course.

grant usage on schema private to authenticated;

create or replace function private.is_course_member(p_course uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.enrollments
                 where course_id = p_course and user_id = (select auth.uid()));
$$;

create or replace function private.is_course_staff(p_course uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.enrollments
                 where course_id = p_course and user_id = (select auth.uid())
                   and role in ('instructor','ta'));
$$;

create or replace function private.my_learner_ids()
returns setof uuid language sql stable security definer set search_path = '' as $$
  select learner_id from public.learner_identities where user_id = (select auth.uid());
$$;

grant execute on function private.is_course_member(uuid), private.is_course_staff(uuid),
  private.my_learner_ids() to authenticated;

-- Enable RLS everywhere in public.
do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

-- People / enrollment
create policy profiles_read on public.profiles for select to authenticated using (
  id = (select auth.uid())
  or exists (select 1 from public.enrollments e
             where e.user_id = profiles.id and private.is_course_staff(e.course_id)));

create policy courses_read on public.courses for select to authenticated
  using (private.is_course_member(id));

create policy enrollments_read on public.enrollments for select to authenticated
  using (user_id = (select auth.uid()) or private.is_course_staff(course_id));

create policy learners_read on public.learners for select to authenticated
  using (id in (select private.my_learner_ids()) or private.is_course_staff(course_id));

create policy learner_identities_read on public.learner_identities for select to authenticated
  using (user_id = (select auth.uid()) or private.is_course_staff(course_id));

-- Course structure visible to all members
create policy outcomes_read on public.outcomes for select to authenticated
  using (private.is_course_member(course_id));

create policy assessments_read on public.assessments for select to authenticated
  using (private.is_course_member(course_id));

create policy questions_read on public.questions for select to authenticated
  using (private.is_course_member(course_id));

create policy question_outcomes_read on public.question_outcomes for select to authenticated
  using (exists (select 1 from public.questions q where q.id = question_id));

create policy error_taxonomy_read on public.error_taxonomy for select to authenticated
  using (true);

-- Protected answer keys: staff only
create policy question_answer_keys_read on public.question_answer_keys for select to authenticated
  using (private.is_course_staff(course_id));

-- Documents and the retrieval index
create policy documents_read on public.documents for select to authenticated using (
  private.is_course_staff(course_id)
  or learner_id in (select private.my_learner_ids())
  or (learner_id is null and publication_status = 'released' and doc_type <> 'answer_key'
      and private.is_course_member(course_id)));

create policy resource_chunks_read on public.resource_chunks for select to authenticated using (
  private.is_course_staff(course_id)
  or (student_visible and publication_status = 'released' and private.is_course_member(course_id)));

create policy chunk_outcomes_read on public.chunk_outcomes for select to authenticated
  using (exists (select 1 from public.resource_chunks c where c.id = chunk_id));

-- Per-learner evidence: own rows or course staff
create policy attempts_read on public.attempts for select to authenticated
  using (learner_id in (select private.my_learner_ids()) or private.is_course_staff(course_id));

create policy responses_read on public.responses for select to authenticated
  using (learner_id in (select private.my_learner_ids()) or private.is_course_staff(course_id));

create policy feedback_read on public.feedback for select to authenticated
  using (learner_id in (select private.my_learner_ids()) or private.is_course_staff(course_id));

create policy evidence_refs_read on public.evidence_refs for select to authenticated using (
  private.is_course_staff(course_id)
  or learner_id in (select private.my_learner_ids())
  or (learner_id is null and private.is_course_member(course_id)));

create policy lers_read on public.lers for select to authenticated
  using (learner_id in (select private.my_learner_ids()) or private.is_course_staff(course_id));

create policy ler_outcomes_read on public.ler_outcomes for select to authenticated
  using (exists (select 1 from public.lers l where l.id = ler_id));

create policy ler_errors_read on public.ler_errors for select to authenticated
  using (exists (select 1 from public.lers l where l.id = ler_id));

create policy ler_error_evidence_read on public.ler_error_evidence for select to authenticated
  using (exists (select 1 from public.ler_errors e where e.id = ler_error_id));

create policy ler_evidence_read on public.ler_evidence for select to authenticated
  using (exists (select 1 from public.lers l where l.id = ler_id));

-- Analytics: students see only their own student_outcome ARRs; class scopes are staff-only
create policy analytics_runs_read on public.analytics_runs for select to authenticated
  using (private.is_course_staff(course_id));

create policy analytics_results_read on public.analytics_results for select to authenticated
  using (subject_learner_id in (select private.my_learner_ids()) or private.is_course_staff(course_id));

create policy arr_ler_links_read on public.arr_ler_links for select to authenticated
  using (exists (select 1 from public.analytics_results r where r.id = arr_id));

-- Insights: students get their own student-audience IRs; staff get the course's
create policy insight_records_read on public.insight_records for select to authenticated using (
  private.is_course_staff(course_id)
  or (audience = 'student' and subject_learner_id in (select private.my_learner_ids())));

create policy ir_arr_links_read on public.ir_arr_links for select to authenticated
  using (exists (select 1 from public.insight_records i where i.id = ir_id));

create policy ir_chunk_links_read on public.ir_chunk_links for select to authenticated
  using (exists (select 1 from public.insight_records i where i.id = ir_id));

-- Tutor / practice history
create policy tutor_sessions_read on public.tutor_sessions for select to authenticated
  using (learner_id in (select private.my_learner_ids()) or private.is_course_staff(course_id));

create policy tutor_turns_read on public.tutor_turns for select to authenticated
  using (exists (select 1 from public.tutor_sessions s where s.id = session_id));

create policy practice_attempts_read on public.practice_attempts for select to authenticated
  using (learner_id in (select private.my_learner_ids()) or private.is_course_staff(course_id));

-- Operations: staff only
create policy ingestion_jobs_read on public.ingestion_jobs for select to authenticated
  using (private.is_course_staff(course_id));

create policy extraction_revisions_read on public.extraction_revisions for select to authenticated
  using (private.is_course_staff(course_id));

create policy audit_events_read on public.audit_events for select to authenticated
  using (private.is_course_staff(course_id));

-- Private storage buckets; files are served via server-issued signed URLs after authz.
insert into storage.buckets (id, name, public)
values ('source-files', 'source-files', false),
       ('course-materials', 'course-materials', false)
on conflict (id) do nothing;

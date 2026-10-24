-- Advisor fixes: pin search_path on trigger functions; index FKs used by RLS and hot paths.

alter function private.lers_guard_update()           set search_path = '';
alter function private.lers_supersede_previous()     set search_path = '';
alter function private.lers_mark_dependents_stale()  set search_path = '';
alter function private.lers_mark_course_arrs_stale() set search_path = '';
alter function private.arrs_mark_irs_stale()         set search_path = '';
alter function private.responses_mark_stale()        set search_path = '';

create index enrollments_user_idx         on public.enrollments(user_id);
create index learner_identities_user_idx  on public.learner_identities(user_id);
create index attempts_learner_idx         on public.attempts(learner_id);
create index responses_learner_idx        on public.responses(learner_id);
create index responses_question_idx       on public.responses(question_id);
create index feedback_response_idx        on public.feedback(response_id);
create index feedback_learner_idx         on public.feedback(learner_id);
create index evidence_refs_learner_idx    on public.evidence_refs(learner_id);
create index ler_errors_ler_idx           on public.ler_errors(ler_id);
create index ler_errors_code_idx          on public.ler_errors(code);
create index ler_outcomes_outcome_idx     on public.ler_outcomes(outcome_id);
create index question_outcomes_outcome_idx on public.question_outcomes(outcome_id);
create index chunk_outcomes_outcome_idx   on public.chunk_outcomes(outcome_id);
create index analytics_results_run_idx    on public.analytics_results(run_id);
create index insight_records_subject_idx  on public.insight_records(subject_learner_id);
create index insight_records_course_idx   on public.insight_records(course_id, audience) where not is_stale;
create index tutor_sessions_learner_idx   on public.tutor_sessions(learner_id);
create index tutor_turns_session_idx      on public.tutor_turns(session_id);
create index practice_attempts_learner_idx on public.practice_attempts(learner_id);

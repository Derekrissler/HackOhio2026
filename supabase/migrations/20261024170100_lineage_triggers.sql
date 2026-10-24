-- Append-only LERs and stale propagation LER -> ARR -> IR (spec §7 refresh rules).

-- LERs are immutable: only the supersession bookkeeping may change, and rows are never deleted
-- (except via course/learner cascade).
create or replace function private.lers_guard_update()
returns trigger language plpgsql as $$
begin
  if (to_jsonb(new) - 'is_current' - 'superseded_by') is distinct from (to_jsonb(old) - 'is_current' - 'superseded_by') then
    raise exception 'LERs are append-only; insert a new revision instead (ler %)', old.id
      using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger lers_guard_update
  before update on public.lers
  for each row execute function private.lers_guard_update();

-- Inserting a new revision for the same response/practice attempt supersedes the previous one.
create or replace function private.lers_supersede_previous()
returns trigger language plpgsql as $$
declare
  prev_id uuid;
begin
  select id into prev_id
  from public.lers
  where is_current
    and id <> new.id
    and ((new.response_id is not null and response_id = new.response_id)
      or (new.practice_attempt_id is not null and practice_attempt_id = new.practice_attempt_id))
  for update;

  if prev_id is not null then
    update public.lers set is_current = false, superseded_by = new.id where id = prev_id;
    new.revision := (select revision + 1 from public.lers where id = prev_id);
  end if;
  return new;
end $$;

create trigger lers_supersede_previous
  before insert on public.lers
  for each row execute function private.lers_supersede_previous();

-- When a LER is superseded, every ARR built on it is stale.
create or replace function private.lers_mark_dependents_stale()
returns trigger language plpgsql as $$
begin
  if old.is_current and not new.is_current then
    update public.analytics_results r
       set is_stale = true
      from public.arr_ler_links l
     where l.ler_id = new.id and r.id = l.arr_id and not r.is_stale;
  end if;
  return new;
end $$;

create trigger lers_mark_dependents_stale
  after update of is_current on public.lers
  for each row execute function private.lers_mark_dependents_stale();

-- A brand-new current LER (e.g. new practice) also invalidates the learner's existing
-- student/class ARRs for the course so the analytics job knows to recompute.
create or replace function private.lers_mark_course_arrs_stale()
returns trigger language plpgsql as $$
begin
  update public.analytics_results
     set is_stale = true
   where course_id = new.course_id
     and not is_stale
     and (subject_learner_id = new.learner_id or subject_learner_id is null);
  return null;
end $$;

create trigger lers_mark_course_arrs_stale
  after insert on public.lers
  for each row execute function private.lers_mark_course_arrs_stale();

-- Stale ARR -> stale IRs that cite it.
create or replace function private.arrs_mark_irs_stale()
returns trigger language plpgsql as $$
begin
  if new.is_stale and not old.is_stale then
    update public.insight_records i
       set is_stale = true
      from public.ir_arr_links l
     where l.arr_id = new.id and i.id = l.ir_id and not i.is_stale;
  end if;
  return new;
end $$;

create trigger arrs_mark_irs_stale
  after update of is_stale on public.analytics_results
  for each row execute function private.arrs_mark_irs_stale();

-- A changed grade or response text invalidates ARRs built on that response's current LER;
-- the extraction job then writes a new LER revision.
create or replace function private.responses_mark_stale()
returns trigger language plpgsql as $$
begin
  if (new.points_earned, new.response_text, new.rubric)
       is distinct from (old.points_earned, old.response_text, old.rubric) then
    new.updated_at := now();
    update public.analytics_results r
       set is_stale = true
      from public.arr_ler_links l
      join public.lers e on e.id = l.ler_id
     where e.response_id = new.id and e.is_current and r.id = l.arr_id and not r.is_stale;
  end if;
  return new;
end $$;

create trigger responses_mark_stale
  before update on public.responses
  for each row execute function private.responses_mark_stale();

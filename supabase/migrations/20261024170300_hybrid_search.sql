-- Hybrid lexical + vector retrieval with outcome boost (spec §5 PROPOSED retrieval).
-- SECURITY INVOKER: called with a user's JWT, RLS filters chunks before ranking.
-- p_student_safe (default true) re-applies the student filter even under the service role.
-- p_embedding may be null: falls back to keyword + outcome filtering (spec §16 fallback).

create or replace function public.search_resource_chunks(
  p_course_id     uuid,
  p_query         text,
  p_embedding     extensions.vector(1536) default null,
  p_outcome_ids   uuid[] default '{}',
  p_k             int default 8,
  p_student_safe  boolean default true
)
returns table (
  chunk_id     uuid,
  document_id  uuid,
  title        text,
  content      text,
  doc_type     text,
  page         int,
  slide        int,
  section      text,
  deep_link    text,
  score        double precision,
  outcome_match boolean
)
language sql stable security invoker set search_path = public, extensions as $$
  with eligible as (
    select c.*
    from resource_chunks c
    where c.course_id = p_course_id
      and (not p_student_safe or (c.student_visible and c.publication_status = 'released'))
  ),
  sem as (
    select id, row_number() over (order by embedding <=> p_embedding) as r
    from eligible
    where p_embedding is not null and embedding is not null
    order by embedding <=> p_embedding
    limit p_k * 4
  ),
  lex as (
    select id, row_number() over (order by ts_rank_cd(fts, q) desc) as r
    from eligible, websearch_to_tsquery('english', coalesce(p_query, '')) q
    where fts @@ q
    order by ts_rank_cd(fts, q) desc
    limit p_k * 4
  ),
  fused as (
    select id, sum(1.0 / (60 + r)) as rrf
    from (select * from sem union all select * from lex) s
    group by id
  )
  select e.id, e.document_id, e.title, e.content, e.doc_type, e.page, e.slide, e.section, e.deep_link,
         f.rrf + case when m.matched then 0.02 else 0 end as score,
         coalesce(m.matched, false) as outcome_match
  from fused f
  join eligible e on e.id = f.id
  left join lateral (
    select true as matched from chunk_outcomes co
    where co.chunk_id = e.id and co.outcome_id = any(p_outcome_ids)
    limit 1
  ) m on true
  order by score desc
  limit p_k;
$$;

revoke execute on function public.search_resource_chunks from anon, public;
grant execute on function public.search_resource_chunks to authenticated, service_role;

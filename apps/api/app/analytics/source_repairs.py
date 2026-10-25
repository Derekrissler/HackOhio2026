"""Source-grounded repairs, dry-run first, with append-only LER revisions.

Private snapshots/review files contain source text. Never print them or commit them.
Writes require serialized course access; separate REST calls are not a transaction.
"""
from copy import deepcopy
import json
from typing import Literal
from urllib.parse import quote
from uuid import UUID, uuid5

from pydantic import AwareDatetime, Field, JsonValue, StrictBool, model_validator

from .contracts import Contract, Nonnegative
from .evidence_repository import RepositoryError, read_pages
from .provenance import content_hash

NAMESPACE = UUID('469edcd9-e36b-49be-944c-480f46a39736')
METHOD = 'grounded_source_repair_v1'
CHILD_KEYS = {'ler_outcomes': ('ler_id', 'outcome_id'), 'ler_errors': ('id',),
              'ler_evidence': ('ler_id', 'evidence_ref_id'),
              'ler_error_evidence': ('ler_error_id', 'evidence_ref_id')}


class ReviewedError(Contract):
    code: str = Field(pattern=r'^[a-z][a-z0-9_]{0,79}$')
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    evidence_ref_ids: list[UUID] = Field(min_length=1)
    outcome_ids: list[UUID] = Field(min_length=1)
    privacy_reviewed: StrictBool = False


class ClassificationReview(Contract):
    ler_id: UUID
    revision: int = Field(ge=1, strict=True)
    # Explicit review of the whole observation, including completed/no-error cases.
    decision: Literal['pending', 'complete'] = 'pending'
    errors: list[ReviewedError] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_codes(self):
        if len({e.code for e in self.errors}) != len(self.errors):
            raise ValueError('duplicate error category')
        if self.decision == 'pending' and self.errors:
            raise ValueError('uncompleted classification cannot contain accepted errors')
        return self


class OutcomeReview(Contract):
    outcome_id: UUID
    decision: Literal['pending', 'verified'] = 'pending'


class MappingReview(Contract):
    question_id: UUID
    outcome_id: UUID
    decision: Literal['pending', 'approved'] = 'pending'
    weight: Nonnegative | None = None


class ResourceReview(Contract):
    chunk_id: UUID
    outcome_id: UUID


class SourceReview(Contract):
    schema_version: Literal['1.0'] = '1.0'
    course_id: UUID
    input_snapshot: str
    reviewer_ref: str | None = Field(default=None, max_length=100)
    reviewed_at: AwareDatetime | None = None
    classifications: list[ClassificationReview] = Field(default_factory=list)
    outcomes: list[OutcomeReview] = Field(default_factory=list)
    mappings: list[MappingReview] = Field(default_factory=list)
    resources: list[ResourceReview] = Field(default_factory=list)

    @model_validator(mode='after')
    def attributed(self):
        for rows, key in ((self.classifications, lambda r:r.ler_id),
                          (self.outcomes, lambda r:r.outcome_id),
                          (self.mappings, lambda r:(r.question_id,r.outcome_id)),
                          (self.resources, lambda r:(r.chunk_id,r.outcome_id))):
            if len({key(row) for row in rows}) != len(rows):
                raise ValueError('duplicate review identity')
        active = self.resources or any(r.decision != 'pending' for r in [*self.classifications,*self.outcomes,*self.mappings])
        if active and (not self.reviewer_ref or self.reviewed_at is None):
            raise ValueError('completed review requires attribution')
        return self


class RepairPlan(Contract):
    schema_version: Literal['1.0'] = '1.0'
    method: Literal['grounded_source_repair_v1'] = METHOD
    id: UUID
    course_id: UUID
    input_snapshot: str
    source: dict[str, JsonValue]
    review: SourceReview | None = None
    evidence_refs: list[dict[str, JsonValue]]
    revisions: list[dict[str, JsonValue]]
    taxonomy: list[dict[str, JsonValue]]
    edits: list[dict[str, JsonValue]]
    chunk_links: list[dict[str, JsonValue]]
    reviewed_excerpts: list[dict[str, JsonValue]]

    def summary(self):
        return {'plan_id':str(self.id), 'course_id':str(self.course_id),
                'new_evidence_refs':len(self.evidence_refs), 'ler_revisions':len(self.revisions),
                'completed_classifications':sum(r['classified'] for r in self.revisions),
                'new_error_records':sum(len(r['ler_errors']) for r in self.revisions if r['classified']),
                'reviewed_mapping_or_outcome_edits':len(self.edits),
                'resource_outcome_links':len(self.chunk_links),
                'reviewed_ml_descriptions':len(self.reviewed_excerpts),
                'actual_insufficient_lers':sum(r['analysis_status']=='insufficient' for r in self.source['lers']),
                'unverified_course_outcomes':sum(not r['instructor_verified'] for r in self.source['outcomes']),
                'pending_question_mappings':sum(r['needs_review'] for r in self.source['question_outcomes']),
                'persisted':False}


def _by_ids(client, table, ids, *, field='id', columns='*', order=None):
    ids = sorted(set(map(str,ids)))
    return [row for start in range(0,len(ids),100) for row in read_pages(
        client,table,columns,in_filter=(field,ids[start:start+100]),order=order or (field,))]


def read_source(client, course_id, *, ler_ids=None):
    """Restricted operator-only source snapshot; no browser endpoint uses this reader."""
    cid = str(course_id)
    lers = (read_pages(client,'lers','*',filters={'course_id':cid,'is_current':True}) if ler_ids is None
            else _by_ids(client,'lers',ler_ids))
    if any(row['course_id'] != cid for row in lers):
        raise RepositoryError('repair_cross_course_ler')
    source = {'course_id':cid,'lers':lers}
    for table,field in [('responses','response_id'),('questions','question_id')]:
        source[table] = _by_ids(client,table,[r[field] for r in lers if r.get(field)])
    for table in ('ler_outcomes','ler_errors','ler_evidence'):
        source[table] = _by_ids(client,table,[r['id'] for r in lers],field='ler_id',order=CHILD_KEYS[table])
    source['ler_error_evidence'] = _by_ids(client,'ler_error_evidence',[r['id'] for r in source['ler_errors']],field='ler_error_id',order=CHILD_KEYS['ler_error_evidence'])
    response_ids = {r['id'] for r in source['responses']}
    source['feedback'] = [r for r in read_pages(client,'feedback','*',filters={'course_id':cid}) if r['response_id'] in response_ids]
    ref_ids = [r['evidence_ref_id'] for t in ('ler_evidence','ler_error_evidence','feedback') for r in source[t] if r.get('evidence_ref_id')]
    source['evidence_refs'] = _by_ids(client,'evidence_refs',ref_ids)
    source['question_outcomes'] = _by_ids(client,'question_outcomes',[r['id'] for r in source['questions']],field='question_id',order=('question_id','outcome_id'))
    source['outcomes'] = read_pages(client,'outcomes','*',filters={'course_id':cid})
    source['resource_chunks'] = read_pages(client,'resource_chunks','id,course_id,document_id,title,content,page,slide,section,deep_link,publication_status,student_visible,extraction_version',filters={'course_id':cid})
    source['chunk_outcomes'] = _by_ids(client,'chunk_outcomes',[r['id'] for r in source['resource_chunks']],field='chunk_id',order=('chunk_id','outcome_id'))
    source['error_taxonomy'] = read_pages(client,'error_taxonomy','*',order=('code',))
    return source


def _key(row,fields):
    return tuple(str(row[f]) for f in fields)


def _reference(source, ler, row, kind):
    locator = row.get('locator')
    if not isinstance(locator,dict):
        return None
    path = locator.get('canvas_api')
    if not isinstance(path,str) or not path.startswith(('/courses/','/api/v1/')) or any(c in path for c in '\r\n'):
        return None
    # Excerpts are verbatim text or explicit recorded facts, never inferred answers.
    if kind == 'question':
        excerpt = row.get('text')
        learner = None
    else:
        excerpt = row.get('response_text')
        if not isinstance(excerpt,str) or not excerpt.strip():
            excerpt = 'Recorded response facts: ' + json.dumps({'points_earned':row.get('points_earned'),
                'rubric':row.get('rubric'), 'locator':locator},sort_keys=True,ensure_ascii=False)
        learner = ler['learner_id']
    if not isinstance(excerpt,str) or not excerpt.strip():
        return None
    identity = {'course':source['course_id'],'kind':kind,'row_id':row['id'],'locator':locator,'excerpt':excerpt}
    digest = content_hash(identity)
    fragment = ('question_id='+quote(str(locator['quiz_question_id']),safe='') if locator.get('quiz_question_id') else
                'rubric_criterion_id='+quote(str(locator['rubric_criterion_id']),safe='') if locator.get('rubric_criterion_id') else '')
    return {'id':str(uuid5(NAMESPACE,digest)), 'course_id':source['course_id'],'learner_id':learner,
            'source_type':'canvas_api','canvas_ref':path+('#'+fragment if fragment else ''),
            'document_id':None,'page':None,'bbox_norm':None,'excerpt':excerpt,'content_hash':digest.split(':',1)[1]}


def build_plan(source, review=None):
    """Deterministic plan. Ordinary source repair never invents error classifications."""
    source = deepcopy(source)
    cid = UUID(source['course_id'])
    digest = content_hash(source)
    review = SourceReview.model_validate(review) if review is not None else None
    if review and (review.course_id != cid or review.input_snapshot != digest):
        raise ValueError('source review is obsolete or belongs to another course')
    plan_id = uuid5(NAMESPACE,content_hash({'method':METHOD,'source':digest,'review':review}))
    lers = {r['id']:r for r in source['lers']}
    responses = {r['id']:r for r in source['responses']}
    questions = {r['id']:r for r in source['questions']}
    outcomes = {r['id']:r for r in source['outcomes']}
    refs = {r['id']:r for r in source['evidence_refs']}
    taxonomy = {r['code']:r for r in source['error_taxonomy']}
    classifications = {str(r.ler_id):r for r in review.classifications if r.decision=='complete'} if review else {}
    if review and any(str(r.ler_id) not in lers or lers[str(r.ler_id)]['revision'] != r.revision for r in review.classifications if r.decision=='complete'):
        raise ValueError('classification review references obsolete evidence')
    edits, chunk_links, new_refs, revisions, new_taxonomy, excerpts = [], [], {}, [], {}, []
    if review:
        for decision in review.outcomes:
            if decision.decision=='verified':
                old = outcomes.get(str(decision.outcome_id))
                if not old: raise ValueError('review outcome is outside course')
                if not old['instructor_verified']:
                    edits.append({'table':'outcomes','keys':['id'],'before':old,'after':old|{'instructor_verified':True}})
        mappings = {_key(r,('question_id','outcome_id')):r for r in source['question_outcomes']}
        for decision in review.mappings:
            if decision.decision=='approved':
                old = mappings.get((str(decision.question_id),str(decision.outcome_id)))
                if not old: raise ValueError('review mapping is outside source')
                changes = {'needs_review':False,'provenance':'instructor'}
                if decision.weight is not None: changes['weight'] = float(decision.weight)
                new = old|changes
                if old != new: edits.append({'table':'question_outcomes','keys':['question_id','outcome_id'],'before':old,'after':new})
        chunks = {r['id']:r for r in source['resource_chunks']}
        existing_links = {_key(r,('chunk_id','outcome_id')) for r in source['chunk_outcomes']}
        for decision in review.resources:
            key = (str(decision.chunk_id),str(decision.outcome_id))
            if key[0] not in chunks or key[1] not in outcomes: raise ValueError('resource mapping is outside course')
            if key not in existing_links: chunk_links.append({'chunk_id':key[0],'outcome_id':key[1],'provenance':'instructor'})
    for old_id, old in sorted(lers.items()):
        if not old['is_current']: raise ValueError('repair source must contain current LERs')
        response, question = responses.get(old.get('response_id')), questions.get(old.get('question_id'))
        if not response or not question: raise ValueError('repair missing source relationships')
        if (response['course_id'] != str(cid) or question['course_id'] != str(cid)
                or response['learner_id'] != old['learner_id'] or response['question_id'] != old['question_id']
                or response['attempt_id'] != old['attempt_id'] or question['assessment_id'] != old['assessment_id']):
            raise ValueError('repair source ownership mismatch')
        links = {r['evidence_ref_id']:deepcopy(r) for r in source['ler_evidence'] if r['ler_id']==old_id}
        for link in links.values():
            ref = refs.get(link['evidence_ref_id'])
            if not ref or ref['course_id'] != str(cid) or ref.get('learner_id') not in (None,old['learner_id']):
                raise ValueError('repair evidence ownership mismatch')
        before = set(links)
        for row,kind in ((question,'question'),(response,'response')):
            ref = _reference(source,old,row,kind)
            if ref:
                links.setdefault(ref['id'],{'ler_id':old_id,'evidence_ref_id':ref['id'],'role':kind})
                if ref['id'] not in refs: new_refs[ref['id']] = ref
        classified = classifications.get(old_id)
        if classified and old['analysis_status'] != 'analyzed':
            raise ValueError('insufficient evidence cannot be marked classified')
        approved_mappings = {(str(r.question_id),str(r.outcome_id)) for r in review.mappings if r.decision=='approved'} if review else set()
        mapping_changed = any(r['ler_id']==old_id and (old['question_id'],r['outcome_id']) in approved_mappings
                              and (r['needs_review'] or r['provenance']!='instructor') for r in source['ler_outcomes'])
        if set(links)==before and classified is None and not mapping_changed:
            continue
        new_id = str(uuid5(plan_id,old_id))
        new = {k:deepcopy(v) for k,v in old.items() if k not in ('created_at','superseded_by')}
        new.update(id=new_id,revision=old['revision']+1,is_current=True,superseded_by=None)
        new['payload'] = deepcopy(old.get('payload') or {})
        new['payload']['source_repair_v1'] = {'method':METHOD,'plan_id':str(plan_id),'parent_ler_id':old_id,'source_snapshot':digest}
        children = {table:[] for table in CHILD_KEYS}
        children['ler_outcomes'] = [r|{'ler_id':new_id} for r in source['ler_outcomes'] if r['ler_id']==old_id]
        for mapping in children['ler_outcomes']:
            if (old['question_id'],mapping['outcome_id']) in approved_mappings:
                mapping.update(needs_review=False,provenance='instructor')
        children['ler_evidence'] = [r|{'ler_id':new_id} for r in links.values()]
        metadata = deepcopy(new['payload'].get('analytics_v1') or {})
        if classified:
            mapped = {r['outcome_id'] for r in source['ler_outcomes'] if r['ler_id']==old_id} or {r['outcome_id'] for r in source['question_outcomes'] if r['question_id']==old['question_id']}
            error_outcomes = {}
            for error in classified.errors:
                e_refs, e_outcomes = set(map(str,error.evidence_ref_ids)), set(map(str,error.outcome_ids))
                if not e_refs <= set(links) or not e_outcomes <= mapped:
                    raise ValueError('reviewed error references unrelated evidence or outcomes')
                error_id = str(uuid5(UUID(new_id),error.code))
                if error.code not in taxonomy:
                    row = {'code':error.code,'label':error.label,'description':None,'parent_code':None}
                    if error.code in new_taxonomy and new_taxonomy[error.code] != row:
                        raise ValueError('conflicting new taxonomy labels')
                    new_taxonomy[error.code] = row
                children['ler_errors'].append({'id':error_id,'ler_id':new_id,'code':error.code,'subcategory':None,
                    'misconception':error.description,'confidence':None,'instructor_status':'confirmed'})
                children['ler_error_evidence'].extend({'ler_error_id':error_id,'evidence_ref_id':ref} for ref in sorted(e_refs))
                error_outcomes[error_id] = sorted(e_outcomes)
                if error.privacy_reviewed:
                    excerpts.append({'ler_id':new_id,'ler_revision':new['revision'],'ler_error_id':error_id,
                        'error_code':error.code,'text':error.description,'source_kind':'error_description',
                        'evidence_ref_ids':sorted(e_refs),'privacy_reviewed':True})
            metadata.update(schema_version='1.0',errors_analyzed=True,error_outcomes=error_outcomes)
            new['payload']['analytics_v1'] = metadata
            new['payload']['source_repair_v1']['review'] = {'reviewer_ref':review.reviewer_ref,'reviewed_at':review.reviewed_at.isoformat()}
        else:
            translated = {}
            for error in source['ler_errors']:
                if error['ler_id'] != old_id: continue
                error_id = str(uuid5(UUID(new_id),error['id']))
                children['ler_errors'].append(error|{'id':error_id,'ler_id':new_id})
                children['ler_error_evidence'].extend(r|{'ler_error_id':error_id} for r in source['ler_error_evidence'] if r['ler_error_id']==error['id'])
                if error['id'] in metadata.get('error_outcomes',{}): translated[error_id] = metadata['error_outcomes'][error['id']]
            if 'error_outcomes' in metadata:
                metadata['error_outcomes'] = translated
                new['payload']['analytics_v1'] = metadata
        revisions.append({'previous_ler_id':old_id,'ler':new,'classified':classified is not None,**children})
    return RepairPlan(id=plan_id,course_id=cid,input_snapshot=digest,source=source,review=review,
                      evidence_refs=sorted(new_refs.values(),key=lambda r:r['id']),revisions=revisions,
                      taxonomy=sorted(new_taxonomy.values(),key=lambda r:r['code']),edits=edits,
                      chunk_links=chunk_links,reviewed_excerpts=excerpts)


def review_packet(plan):
    """Pending decisions plus original source context, for private human review."""
    source = plan.source
    classifications = [ClassificationReview(ler_id=r['id'],revision=r['revision']) for r in source['lers'] if r['analysis_status']=='analyzed']
    review = SourceReview(course_id=plan.course_id,input_snapshot=plan.input_snapshot,classifications=classifications,
        outcomes=[OutcomeReview(outcome_id=r['id']) for r in source['outcomes'] if not r['instructor_verified']],
        mappings=[MappingReview(question_id=r['question_id'],outcome_id=r['outcome_id']) for r in source['question_outcomes'] if r['needs_review']])
    return {'decisions':review.model_dump(mode='json'),
            'context':{key:source[key] for key in ('questions','responses','feedback','outcomes','question_outcomes','resource_chunks','error_taxonomy')}
                | {'evidence_refs':source['evidence_refs']+plan.evidence_refs,
                   'ler_sources':[{'ler_id':r['id'],'revision':r['revision'],'response_id':r['response_id'],'question_id':r['question_id']} for r in source['lers']]}}


def _same(actual,expected):
    return all(actual.get(k)==v for k,v in expected.items())


def _insert_missing(client,table,rows,keys):
    if not rows: return
    existing = _by_ids(client,table,[r[keys[0]] for r in rows],field=keys[0],order=keys)
    index = {_key(r,keys):r for r in existing}
    pending = []
    for row in rows:
        previous = index.get(_key(row,keys))
        if previous is not None:
            if not _same(previous,row): raise RepositoryError('repair_write_conflict')
        else: pending.append(row)
    for start in range(0,len(pending),100):
        client.table(table).insert(pending[start:start+100]).execute()


def _preflight(client,plan):
    current = read_source(client,plan.course_id,ler_ids=[r['id'] for r in plan.source['lers']])
    # Permit only this plan's already completed mutations when resuming.
    by_id = {r['id']:r for r in current['lers']}
    source_lers = {r['id']:r for r in plan.source['lers']}
    revision_ids = {r['previous_ler_id']:r['ler']['id'] for r in plan.revisions}
    for lid,row in by_id.items():
        if row.get('superseded_by') not in (None,revision_ids.get(lid)):
            raise RepositoryError('repair_source_changed')
        row['is_current'] = source_lers[lid]['is_current']
        row['superseded_by'] = source_lers[lid].get('superseded_by')
    expected_population = set(source_lers)
    population = {r['id'] for r in read_pages(client,'lers','id',filters={'course_id':str(plan.course_id),'is_current':True})}
    for old,new in revision_ids.items():
        if new in population: expected_population.remove(old); expected_population.add(new)
    if population != expected_population: raise RepositoryError('repair_source_changed')
    existing_codes = {r['code'] for r in plan.source['error_taxonomy']}
    current['error_taxonomy'] = [r for r in current['error_taxonomy'] if r['code'] in existing_codes]
    inserted_links = {_key(r,('chunk_id','outcome_id')) for r in plan.chunk_links}
    current['chunk_outcomes'] = [r for r in current['chunk_outcomes'] if _key(r,('chunk_id','outcome_id')) not in inserted_links]
    for edit in plan.edits:
        for i,row in enumerate(current[edit['table']]):
            if _key(row,edit['keys'])==_key(edit['before'],edit['keys']) and row==edit['after']:
                current[edit['table']][i] = edit['before']
    if content_hash(current) != plan.input_snapshot:
        raise RepositoryError('repair_source_changed')


def apply_plan(client,plan,*,exclusive_course_access=False):
    if not exclusive_course_access: raise ValueError('repair requires serialized course access')
    plan = RepairPlan.model_validate(plan)
    if build_plan(plan.source,plan.review).model_dump(mode='json') != plan.model_dump(mode='json'):
        raise ValueError('repair plan differs from validated source facts')
    _preflight(client,plan)
    try:
        _insert_missing(client,'evidence_refs',plan.evidence_refs,('id',))
        _insert_missing(client,'error_taxonomy',plan.taxonomy,('code',))
        _insert_missing(client,'lers',[r['ler'] for r in plan.revisions],('id',))
        for table,keys in CHILD_KEYS.items():
            _insert_missing(client,table,[row for revision in plan.revisions for row in revision[table]],keys)
        for edit in plan.edits:
            query = client.table(edit['table']).update({k:v for k,v in edit['after'].items() if edit['before'].get(k)!=v})
            for key in edit['keys']: query = query.eq(key,edit['before'][key])
            query.execute()
        _insert_missing(client,'chunk_outcomes',plan.chunk_links,('chunk_id','outcome_id'))
        _preflight(client,plan)
        # Verify every written row, including trigger-assigned LER revision numbers.
        for table,rows,keys in [('evidence_refs',plan.evidence_refs,('id',)),('error_taxonomy',plan.taxonomy,('code',)),
                                ('lers',[r['ler'] for r in plan.revisions],('id',)),('chunk_outcomes',plan.chunk_links,('chunk_id','outcome_id')),
                                *[(edit['table'],[edit['after']],tuple(edit['keys'])) for edit in plan.edits],
                                *[(t,[row for rev in plan.revisions for row in rev[t]],k) for t,k in CHILD_KEYS.items()]]:
            actual = {_key(row,keys):row for row in _by_ids(client,table,[r[keys[0]] for r in rows],field=keys[0],order=keys)} if rows else {}
            if any(_key(r,keys) not in actual or not _same(actual[_key(r,keys)],r) for r in rows):
                raise RepositoryError('repair_readback_failed')
        detail = plan.summary()|{'persisted':True}
        if plan.review:
            detail['review'] = {'reviewer_ref':plan.review.reviewer_ref,
                'reviewed_at':plan.review.reviewed_at.isoformat() if plan.review.reviewed_at else None,
                'digest':content_hash(plan.review)}
        event = {'course_id':str(plan.course_id),'event':'source.repaired',
                 'entity':'source_repair_plan','entity_id':str(plan.id),'detail':detail}
        # audit_events.id is a generated bigint, not a UUID. The plan UUID is
        # the stable entity identity; serialized writers make this retry-safe.
        audit_filters = {key:event[key] for key in ('course_id','event','entity','entity_id')}
        saved = read_pages(client,'audit_events','*',filters=audit_filters)
        if not saved:
            client.table('audit_events').insert(event).execute()
            saved = read_pages(client,'audit_events','*',filters=audit_filters)
        if len(saved)!=1 or not _same(saved[0],event):
            raise RepositoryError('repair_audit_readback_failed')
    except RepositoryError:
        raise
    except Exception:
        raise RepositoryError('repair_write_failed_retry_same_plan') from None
    return plan.summary()|{'persisted':True,'analytics_refresh_required':bool(plan.revisions or plan.edits)}

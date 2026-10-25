"""Reuse the analytics package's validated, freshness-checked ARR reader."""
from pathlib import Path
from datetime import datetime
import sys
import threading
import time
from uuid import UUID

API_ROOT = str(Path(__file__).resolve().parents[3] / "apps" / "api")
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

# Loading the dashboard takes seconds; a learner's weak outcomes only change when analytics are re-run.
TTL_SECONDS = 300
_cache: dict[tuple, tuple[float, list[str], tuple | None]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def weak_outcomes(writer, reader, learner, threshold=0.7, now=time.monotonic):
    key = (learner.course_id, learner.learner_id, threshold)
    token = _visible_run_token(reader, learner)
    with _lock:
        hit = _cache.get(key)
    if hit and now() - hit[0] < TTL_SECONDS and hit[2] == token:
        # TTL is a reuse limit, not permission to serve stale analytics context.
        # Check user visibility before privileged source/run control reads.
        if _source_current(writer, reader, learner, token):
            return list(hit[1])
    with _lock:
        _cache.pop(key, None)
    value = _load(writer, reader, learner, threshold)  # failures propagate and aren't cached
    after = _visible_run_token(reader, learner)
    if after == token:
        with _lock:
            _cache[key] = (now(), value, after)
    return list(value)


def _visible_run_token(reader, learner):
    # None clients are used only by isolated cache tests with an injected loader.
    if reader is None:
        return None
    from app.analytics.evidence_repository import RepositoryError, read_pages
    rows = read_pages(reader, 'analytics_results', 'id,run_id,is_stale,created_at', filters={
        'course_id': learner.course_id, 'subject_learner_id': learner.learner_id,
        'scope': 'student_outcome', 'schema_version': '1.1',
    })
    if not rows:
        return ('unavailable',)
    try:
        newest = max(rows, key=lambda r: (datetime.fromisoformat(r['created_at'].replace('Z', '+00:00')), r['run_id']))
        selected = [r for r in rows if r['run_id'] == newest['run_id']]
        if any(r['is_stale'] for r in selected):
            return ('unavailable',)
        return ('run', newest['run_id'], tuple(sorted(r['id'] for r in selected)))
    except (TypeError, ValueError, KeyError):
        raise RepositoryError('invalid_stored_arr') from None


def _source_current(writer, reader, learner, token):
    if writer is None and reader is None:
        return True  # injected-loader unit tests, never an authenticated repo request
    if not token or token[0] != 'run':
        return False
    from app.analytics.repository import SupabaseAnalysisRepository
    control = SupabaseAnalysisRepository(writer)
    run = control.get_run(UUID(token[1]))
    return bool(run and run['course_id'] == learner.course_id
                and run['params'].get('status') == 'complete'
                and control.load_course(UUID(learner.course_id)).fingerprint() == run['params'].get('source_fingerprint'))


def _load(writer, reader, learner, threshold):
    from app.analytics.dashboard import load_dashboard
    from app.analytics.repository import SupabaseAnalysisRepository
    result = load_dashboard(reader, lambda: SupabaseAnalysisRepository(writer),
                            UUID(learner.course_id), learner_id=UUID(learner.learner_id))
    if result.status != "ready":
        return []
    return sorted({str(row.outcome_id) for row in result.performance
                   if row.scope == "student_outcome" and row.outcome_id is not None
                   and not row.insufficient_evidence and not row.suppressed
                   and row.observed_score_ratio is not None and row.observed_score_ratio < threshold})

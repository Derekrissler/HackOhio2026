"""Reuse the analytics package's validated, freshness-checked ARR reader."""
from pathlib import Path
import sys
from uuid import UUID

API_ROOT = str(Path(__file__).resolve().parents[3] / "apps" / "api")
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)


def weak_outcomes(writer, reader, learner, threshold=0.7):
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

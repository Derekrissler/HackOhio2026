"""Read-only ML input checks; no embedding inference or model download."""
from collections import Counter, defaultdict

from .config import AnalyticsConfig
from .features import build_features
from .text_preparation import prepare_error_texts


def ml_readiness(records, excerpts, config=None, period=None, embedder=None):
    config = config or AnalyticsConfig()
    prepared = prepare_error_texts(records, excerpts, config, period)
    parts = defaultdict(list)
    for text in prepared.observations:
        parts[(str(text.course_id), text.assessment_origin, text.assistance)].append(text)
    model_ready, model_reason = False, "model_cache_not_configured"
    if embedder is not None and getattr(embedder, 'local_files_only', True) is False:
        model_reason = "offline_model_cache_required"
    elif embedder is not None:
        from .embeddings import EmbeddingUnavailable
        try:
            embedder.metadata  # Loads/validates cached artifacts; never encodes text.
            model_ready, model_reason = True, None
        except (EmbeddingUnavailable, ImportError):
            model_reason = "model_or_dependencies_unavailable"
    partitions = []
    for (course, origin, assistance), texts in sorted(parts.items()):
        lers, students = len({t.ler_id for t in texts}), len({t.learner_id for t in texts})
        reason = ("partition_size_limit" if len(texts) > config.clustering_max_observations else
                  "insufficient_distinct_lers" if lers < config.clustering_min_observations else
                  model_reason if not model_ready else None)
        partitions.append({"course_id": course, "origin": origin, "assistance": assistance,
                           "texts": len(texts), "distinct_lers": lers, "distinct_students": students,
                           "status": "ready" if reason is None else "not_ready", "reason": reason,
                           "has_publication_cohort": students >= config.class_min_students})
    return {"completed_classifications": sum(r.errors_analyzed is True for r in records),
            "eligible_error_events": len(build_features(records, config, period).errors),
            "accepted_texts": len(prepared.observations), "excluded_texts": len(prepared.exclusions),
            "exclusion_counts": dict(Counter(x.reason for x in prepared.exclusions)),
            "model_ready": model_ready, "model_reason": model_reason, "partitions": partitions,
            "status": "ready" if partitions and any(p["status"] == "ready" for p in partitions) else "not_ready"}

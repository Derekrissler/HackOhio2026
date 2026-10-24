"""Opt-in real-model evaluation; normal tests never download model artifacts."""

import importlib.util
import os
from pathlib import Path

import numpy as np
import pytest

from app.analytics.clustering import discover_misconceptions
from app.analytics.config import AnalyticsConfig
from app.analytics.embeddings import MODEL_REVISION, EmbeddingUnavailable, MiniLMOnnxEmbedder
from app.analytics.text_preparation import prepare_error_texts
from .test_clustering import NOW, RUN_ID, source


TEXTS = [
    "The inequality sign is reversed in this constraint.",
    "You reversed the direction of the inequality.",
    "This constraint uses the wrong inequality direction.",
    "The answer has an incorrect conversion from meters to centimeters.",
    "You converted meters to centimeters using the wrong factor.",
    "The meter-to-centimeter conversion factor is incorrect.",
    "The bibliography is missing the author's publication year.",
]


@pytest.mark.skipif(not os.environ.get("ANALYTICS_MODEL_CACHE"), reason="real-model cache not configured")
def test_real_minilm_semantic_relationships_and_threshold_sensitivity():
    encoder = MiniLMOnnxEmbedder(Path(os.environ["ANALYTICS_MODEL_CACHE"]))
    vectors = encoder.encode(TEXTS)
    assert vectors.shape == (7, 384)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)
    np.testing.assert_array_equal(vectors, encoder.encode(TEXTS))
    similarity = vectors @ vectors.T
    assert similarity[0, 1] > similarity[0, 3]
    assert similarity[3, 4] > similarity[3, 6]
    assert encoder.metadata.revision == MODEL_REVISION
    assert importlib.util.find_spec("torch") is None
    with pytest.raises(EmbeddingUnavailable, match="^text_token_limit_exceeded$"):
        encoder.encode(["inequality " * 300])
    records, excerpts = source(TEXTS)
    for index, (record, excerpt) in enumerate(zip(records, excerpts)):
        code = ("inequality_direction" if index < 3 else
                "unit_conversion_error" if index < 6 else "missing_citation")
        record.errors[0].code = excerpt.error_code = code
    data = prepare_error_texts(records, excerpts)
    evaluation = []
    for eps in (0.25, 0.35, 0.45):
        result = discover_misconceptions(data, run_id=RUN_ID, embedder=encoder,
                                        config=AnalyticsConfig(clustering_eps=eps), computed_at=NOW)
        part = result.partitions[0]
        assert part.status == "completed"
        evaluation.append({"eps": eps, "groups": [g.text_observation_count for g in part.groups],
                           "noise": part.noise_count, "silhouette": part.silhouette_cosine})
        if eps == 0.35:
            clusters = {assignment.ler_id: assignment.cluster_id for assignment in part.assignments}
            assert clusters[records[0].ler_id] == clusters[records[1].ler_id] == clusters[records[2].ler_id]
            assert clusters[records[3].ler_id] == clusters[records[4].ler_id] == clusters[records[5].ler_id]
            assert clusters[records[0].ler_id] is not None
            assert clusters[records[3].ler_id] is not None
            assert clusters[records[0].ler_id] != clusters[records[3].ler_id]
            assert clusters[records[6].ler_id] is None
            assert {group.representative_error_code for group in part.groups} == {
                "inequality_direction", "unit_conversion_error",
            }
    print("Synthetic semantic evaluation:", evaluation)

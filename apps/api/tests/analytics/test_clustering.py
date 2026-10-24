from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID

import numpy as np
import pytest
from pydantic import ValidationError

from app.analytics.clustering import ClusteringResult, discover_misconceptions
from app.analytics.config import AnalyticsConfig
from app.analytics.embeddings import EmbeddingMetadata, EmbeddingUnavailable, MiniLMOnnxEmbedder
from app.analytics.statistics import analyze_statistics
from app.analytics.text_preparation import ApprovedErrorText, PreparedTexts, normalize_error_text, prepare_error_texts
from .test_features import record, uid

pytest.importorskip("sklearn", reason="install requirements-clustering.txt for semantic clustering tests")


RUN_ID = uid(8000)
NOW = datetime(2026, 10, 24, 18, tzinfo=timezone.utc)


def source(texts=None):
    texts = texts or ["direction a", "direction b", "direction c", "conversion a", "conversion b", "conversion c", "unrelated"]
    records, excerpts = [], []
    for i, text in enumerate(texts):
        item = record(101 + i).model_copy(update={"question_id": UUID(uid(600 + i))})
        item.errors[0].outcome_ids = [item.outcome_mappings[0].outcome_id]
        records.append(item)
        excerpts.append(ApprovedErrorText(
            ler_id=item.ler_id, error_code=item.errors[0].code, text=text,
            source_kind="instructor_feedback", evidence_ref_ids=item.evidence_ref_ids,
            privacy_reviewed=True,
        ))
    return records, excerpts


def prepared():
    records, excerpts = source()
    return prepare_error_texts(records, excerpts)


class FixtureEmbedder:
    metadata = EmbeddingMetadata(
        model_id="fictional-unit-vectors", revision="fixture-v1", backend="test_only", dimensions=3,
        pooling="none", normalization="none", max_tokens=256, artifact_sha256={}, package_versions={},
    )

    def encode(self, texts):
        # Controlled geometry tests the algorithm, not a claim of language quality.
        return np.asarray([
            [1, 0, 0] if text.startswith("direction") else
            [0, 1, 0] if text.startswith("conversion") else [0, 0, 1]
            for text in texts
        ], dtype=float)


def discover(data=None, embedder=None, config=None):
    return discover_misconceptions(data or prepared(), run_id=RUN_ID,
                                  embedder=embedder, config=config, computed_at=NOW)


def test_related_vectors_form_two_groups_and_outlier_stays_noise():
    result = discover(embedder=FixtureEmbedder())
    partition = result.partitions[0]
    assert partition.status == "completed"
    assert sorted(g.text_observation_count for g in partition.groups) == [3, 3]
    assert partition.noise_count == partition.unassigned_count == 1
    assert partition.silhouette_cosine == 1
    assert all(g.evidence_observation_count == g.distinct_question_count == 3 for g in partition.groups)
    assert all(g.unique_student_count == 1 for g in partition.groups)
    assert all(g.mean_pairwise_cosine_similarity == 1 for g in partition.groups)
    assert len(partition.assignments) == 7
    assert result.model.model_id == "fictional-unit-vectors"
    assert result.package_versions["scikit-learn"]


def test_reproducible_memberships_and_snapshot_under_permutation():
    data = prepared()
    first = discover(data, FixtureEmbedder())
    data.observations.reverse()
    second = discover(data, FixtureEmbedder())
    assert first.model_dump_json() == second.model_dump_json()
    assert ClusteringResult.model_validate_json(first.model_dump_json()) == first


def test_cluster_ids_are_scoped_to_run():
    first = discover(embedder=FixtureEmbedder())
    second = discover_misconceptions(prepared(), run_id=uid(8001), embedder=FixtureEmbedder(), computed_at=NOW)
    assert first.input_snapshot == second.input_snapshot
    assert first.partitions[0].groups[0].cluster_id != second.partitions[0].groups[0].cluster_id


def test_missing_embedder_returns_unassigned_without_fake_clusters():
    partition = discover().partitions[0]
    assert partition.status == "unavailable" and partition.groups == []
    assert partition.unassigned_count == 7 and partition.noise_count == 0


def test_unavailable_model_does_not_affect_statistics():
    class Missing(FixtureEmbedder):
        def encode(self, texts):
            raise EmbeddingUnavailable("model_missing_or_unloadable")
    records, _ = source()
    before = analyze_statistics(records).model_dump_json()
    assert discover(embedder=Missing()).partitions[0].status == "unavailable"
    assert analyze_statistics(records).model_dump_json() == before


@pytest.mark.parametrize("size", [1, 2, 5])
def test_small_data_skips_model_loading(size):
    class NeverLoad(FixtureEmbedder):
        def encode(self, texts):
            raise AssertionError("must not load a model for insufficient evidence")
    data = prepared()
    data.observations = data.observations[:size]
    partition = discover(data, NeverLoad()).partitions[0]
    assert partition.status == "insufficient_data" and partition.unassigned_count == size


def test_empty_data_has_no_partitions():
    result = discover_misconceptions(PreparedTexts(observations=[], exclusions=[]), run_id=RUN_ID)
    assert result.partitions == [] and result.model is None


def test_no_cross_course_or_assistance_pooling():
    data = prepared()
    data.observations[0].course_id = data.observations[0].course_id.__class__(uid(900))
    data.observations[1].assessment_origin = "generated_practice"
    data.observations[1].assistance = "assisted"
    result = discover(data, FixtureEmbedder())
    assert len(result.partitions) == 3
    assert all(part.status == "insufficient_data" for part in result.partitions)


def test_representative_is_a_member_and_keeps_source_references():
    data = prepared()
    result = discover(data, FixtureEmbedder())
    by_id = {o.observation_id: o for o in data.observations}
    for group in result.partitions[0].groups:
        representative = by_id[group.representative_observation_id]
        assert group.representative_text == representative.text
        assert set(group.evidence_ref_ids) == set(representative.evidence_ref_ids)
        assert representative.ler_id in group.evidence_ler_ids
        assert "hypothesis" not in group.representative_error_code


def test_single_cluster_has_no_silhouette():
    class Same(FixtureEmbedder):
        def encode(self, texts):
            return np.asarray([[1, 0, 0]] * len(texts))
    partition = discover(embedder=Same()).partitions[0]
    assert len(partition.groups) == 1 and partition.silhouette_cosine is None


@pytest.mark.parametrize("bad", [np.zeros((7, 3)), np.full((7, 3), np.nan), np.ones((2, 3)), np.ones(7), [["bad"]] * 7])
def test_invalid_embeddings_produce_no_clusters(bad):
    class Bad(FixtureEmbedder):
        def encode(self, texts):
            return bad
    partition = discover(embedder=Bad()).partitions[0]
    assert partition.status == "invalid_embeddings" and partition.groups == []


def test_partition_size_guard_prevents_quadratic_allocation():
    partition = discover(embedder=FixtureEmbedder(), config=AnalyticsConfig(clustering_max_observations=6)).partitions[0]
    assert partition.status == "size_limit"


def test_duplicate_prepared_ids_rejected():
    data = prepared()
    data.observations.append(deepcopy(data.observations[0]))
    with pytest.raises(ValueError, match="duplicate"):
        discover(data, FixtureEmbedder())


def test_text_normalization_preserves_math_negation_and_units():
    assert normalize_error_text("  x ≥ 0\n is NOT x ≤ 0;  10 cm ≠ 10 m  ") == "x ≥ 0 is NOT x ≤ 0; 10 cm ≠ 10 m"


def test_multiple_excerpts_do_not_manufacture_density():
    records, excerpts = source()
    extra = excerpts[0].model_copy(update={"text": "a much longer phrasing of this exact same mistake"})
    data = prepare_error_texts(records, excerpts + [extra, excerpts[0]])
    assert len(data.observations) == 7
    assert data.model_dump_json() == prepare_error_texts(records[::-1], list(reversed(excerpts + [extra, excerpts[0]]))).model_dump_json()


def test_text_requires_explicit_privacy_attestation():
    _, excerpts = source()
    data = excerpts[0].model_dump()
    del data["privacy_reviewed"]
    with pytest.raises(ValidationError):
        ApprovedErrorText.model_validate(data)


def test_unlinked_excerpt_is_excluded():
    records, excerpts = source()
    excerpts[0].evidence_ref_ids = [excerpts[0].ler_id]
    data = prepare_error_texts(records, excerpts)
    assert len(data.observations) == 6
    assert data.exclusions[0].reason == "excerpt_not_linked_to_error_evidence"


def test_rejected_errors_and_unselected_history_are_not_embedded():
    records, excerpts = source()
    records[0].errors[0].instructor_status = "rejected"
    records[1].is_current = False
    assert len(prepare_error_texts(records, excerpts).observations) == 5


def test_model_initialization_and_empty_encode_do_not_load_or_download(monkeypatch):
    encoder = MiniLMOnnxEmbedder(Path("unused-model-cache"))
    def no_load():
        raise AssertionError("empty input should not load the model")
    monkeypatch.setattr(encoder, "_load", no_load)
    assert encoder._session is None
    assert encoder.encode([]).shape == (0, 384)


def test_optional_missing_runtime_is_reported_without_text_in_exception(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    encoder = MiniLMOnnxEmbedder(Path("unused-model-cache"))
    with pytest.raises(EmbeddingUnavailable, match="^embedding_dependencies_unavailable$"):
        encoder.encode(["private error text should not appear in errors"])


def test_multiple_error_codes_from_one_ler_cannot_form_a_cluster_alone():
    data = prepared()
    first = data.observations[0]
    for item in data.observations[:3]:
        item.ler_id = first.ler_id
        item.text = "direction same"
    for i in range(3):
        extra = deepcopy(data.observations[3 + i])
        extra.observation_id = "text:" + str(i + 1) * 64
        extra.ler_id = first.ler_id.__class__(uid(950 + i))
        extra.text = "conversion extra"
        data.observations.append(extra)
    result = discover(data, FixtureEmbedder()).partitions[0]
    assert result.status == "completed"
    assert not any(first.ler_id in group.evidence_ler_ids for group in result.groups)
    assert all(item.cluster_id is None for item in result.assignments if item.ler_id == first.ler_id)

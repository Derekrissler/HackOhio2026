"""Optional misconception hypotheses, partitioned by course/origin/assistance.

No statistical service imports this module. Missing models never block statistics.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from typing import Literal
from uuid import UUID

import numpy as np
from pydantic import AwareDatetime, Field

from .config import AnalyticsConfig
from .contracts import Contract, Count
from .embeddings import EmbeddingMetadata, EmbeddingProvider, EmbeddingUnavailable
from .text_preparation import PreparedTexts


class ClusterAssignment(Contract):
    observation_id: str
    ler_id: UUID
    cluster_id: str | None
    reason: str | None = None


class MisconceptionGroup(Contract):
    cluster_id: str
    representative_error_code: str
    representative_text: str
    representative_observation_id: str
    text_observation_count: Count
    evidence_observation_count: Count
    unique_student_count: Count
    distinct_question_count: Count
    outcome_ids: list[UUID]
    evidence_ler_ids: list[UUID]
    evidence_ref_ids: list[UUID]
    mean_pairwise_cosine_similarity: float = Field(ge=-1, le=1)
    interpretation_limit: str = "Semantic similarity suggests related mistakes; it does not establish a shared misconception."


class ClusterPartition(Contract):
    course_id: UUID
    assessment_origin: str
    assistance: str
    status: Literal["completed", "insufficient_data", "unavailable", "invalid_embeddings", "size_limit"]
    reason: str | None
    text_observation_count: Count
    evidence_observation_count: Count
    groups: list[MisconceptionGroup]
    assignments: list[ClusterAssignment]
    noise_count: Count
    unassigned_count: Count
    # Only computed for 2..n-1 non-noise clusters; never a confidence probability.
    silhouette_cosine: float | None = Field(default=None, ge=-1, le=1)


class ClusteringResult(Contract):
    run_id: UUID
    computed_at: AwareDatetime
    algorithm: Literal["dbscan_cosine"] = "dbscan_cosine"
    config: AnalyticsConfig
    model: EmbeddingMetadata | None
    package_versions: dict[str, str]
    input_snapshot: str
    normalization_version: str
    partitions: list[ClusterPartition]


def discover_misconceptions(
    prepared: PreparedTexts, *, run_id: UUID, embedder: EmbeddingProvider | None = None,
    config: AnalyticsConfig | None = None, computed_at: datetime | None = None,
) -> ClusteringResult:
    config = config or AnalyticsConfig()
    partitions = defaultdict(list)
    identities = [item.observation_id for item in prepared.observations]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate prepared observation IDs")
    for item in prepared.observations:
        partitions[(str(item.course_id), item.assessment_origin, item.assistance)].append(item)
    result = ClusteringResult(
        run_id=run_id, computed_at=computed_at or datetime.now(timezone.utc), config=config,
        model=None, package_versions={"numpy": version("numpy")}, input_snapshot="pending",
        normalization_version=prepared.normalization_version, partitions=[],
    )
    for key, observations in sorted(partitions.items()):
        observations.sort(key=lambda item: item.observation_id)
        n, evidence_count = len(observations), len({item.ler_id for item in observations})
        partition = ClusterPartition(
            course_id=key[0], assessment_origin=key[1], assistance=key[2],
            status="insufficient_data", reason="too_few_distinct_evidence_observations",
            text_observation_count=n, evidence_observation_count=evidence_count,
            groups=[], assignments=[], noise_count=0, unassigned_count=n,
        )
        labels = None
        if n > config.clustering_max_observations:
            partition.status, partition.reason = "size_limit", "partition_exceeds_configured_limit"
        elif evidence_count < max(config.clustering_min_observations, config.clustering_min_samples):
            pass
        elif embedder is None:
            partition.status, partition.reason = "unavailable", "embedder_not_configured"
        else:
            try:
                from sklearn.cluster import DBSCAN
                from sklearn.metrics import silhouette_score
            except ImportError:
                partition.status, partition.reason = "unavailable", "clustering_dependency_unavailable"
            else:
                try:
                    embeddings = np.asarray(embedder.encode([item.text for item in observations]), dtype=np.float64)
                    metadata = embedder.metadata
                except EmbeddingUnavailable as exc:
                    partition.status, partition.reason = "unavailable", str(exc)
                except (TypeError, ValueError, OverflowError):
                    partition.status, partition.reason = "invalid_embeddings", "invalid_embedding_values"
                else:
                    norms = np.linalg.norm(embeddings, axis=1) if embeddings.ndim == 2 else np.array([])
                    if (embeddings.shape != (n, metadata.dimensions) or not np.isfinite(embeddings).all()
                            or not np.isfinite(norms).all() or (norms <= 0).any()):
                        partition.status, partition.reason = "invalid_embeddings", "nonfinite_zero_or_wrong_shape"
                    else:
                        if result.model is not None and result.model != metadata:
                            raise ValueError("embedding metadata changed during the run")
                        result.model = metadata
                        result.package_versions["scikit-learn"] = version("scikit-learn")
                        normalized = embeddings / norms[:, None]
                        similarities = np.clip(normalized @ normalized.T, -1, 1)
                        distances = np.clip(1 - similarities, 0, 2)
                        np.fill_diagonal(distances, 0)
                        labels = DBSCAN(eps=config.clustering_eps, min_samples=config.clustering_min_samples,
                                        metric="precomputed", n_jobs=1).fit_predict(distances)
                        for label in set(labels) - {-1}:
                            members = np.flatnonzero(labels == label)
                            if len({observations[i].ler_id for i in members}) < config.clustering_min_samples:
                                labels[members] = -1
                        groups = sorted((np.flatnonzero(labels == label) for label in set(labels) - {-1}),
                                        key=lambda members: observations[int(members[0])].observation_id)
                        member_clusters = {}
                        partition_token = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]
                        for number, members in enumerate(groups):
                            cluster_id = f"{run_id}:{partition_token}:{number}"
                            items = [observations[int(i)] for i in members]
                            within = similarities[np.ix_(members, members)]
                            medoid = int(np.argmax(within.mean(axis=1)))
                            representative = items[medoid]
                            counts = Counter(item.error_code for item in items)
                            code = min(counts, key=lambda item: (-counts[item], item))
                            off_diagonal = within[~np.eye(len(items), dtype=bool)]
                            partition.groups.append(MisconceptionGroup(
                                cluster_id=cluster_id, representative_error_code=code,
                                representative_text=representative.text,
                                representative_observation_id=representative.observation_id,
                                text_observation_count=len(items),
                                evidence_observation_count=len({item.ler_id for item in items}),
                                unique_student_count=len({item.learner_id for item in items}),
                                distinct_question_count=len({item.question_id for item in items if item.question_id}),
                                outcome_ids=sorted({oid for item in items for oid in item.outcome_ids}, key=str),
                                evidence_ler_ids=sorted({item.ler_id for item in items}, key=str),
                                evidence_ref_ids=sorted({ref for item in items for ref in item.evidence_ref_ids}, key=str),
                                mean_pairwise_cosine_similarity=float(np.clip(off_diagonal.mean(), -1, 1)),
                            ))
                            for i in members:
                                member_clusters[int(i)] = cluster_id
                        partition.status, partition.reason = "completed", None
                        partition.noise_count = int((labels == -1).sum())
                        partition.unassigned_count = partition.noise_count
                        kept = np.flatnonzero(labels != -1)
                        if 2 <= len(groups) < len(kept):
                            partition.silhouette_cosine = float(silhouette_score(
                                distances[np.ix_(kept, kept)], labels[kept], metric="precomputed",
                            ))
                        partition.assignments = [ClusterAssignment(
                            observation_id=item.observation_id, ler_id=item.ler_id,
                            cluster_id=member_clusters.get(i), reason="noise" if labels[i] == -1 else None,
                        ) for i, item in enumerate(observations)]
        if labels is None:
            partition.assignments = [ClusterAssignment(
                observation_id=item.observation_id, ler_id=item.ler_id, cluster_id=None,
                reason=partition.reason,
            ) for item in observations]
        result.partitions.append(partition)
    snapshot = {
        "observations": [item.model_dump(mode="json") for item in sorted(prepared.observations, key=lambda item: item.observation_id)],
        "normalization_version": prepared.normalization_version, "config": config.model_dump(mode="json"),
        "model": result.model.model_dump(mode="json") if result.model else None,
        "package_versions": result.package_versions,
    }
    result.input_snapshot = "sha256:" + hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return result

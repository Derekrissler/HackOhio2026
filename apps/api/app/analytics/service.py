"""One-course analysis, dry-run by default; publication requires exclusive access.

Multiple REST calls are NOT a transaction. The caller must serialize ingestion,
metadata edits and analysis for the course. This is a precondition, not a lock.
"""

from collections import Counter
from datetime import datetime, timezone
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import AwareDatetime, JsonValue, TypeAdapter, model_validator

from .arr_generation import ARRDocument, generate_arrs
from .config import AnalyticsConfig
from .contracts import AnalysisPeriod, AnalyticalInput, Contract
from .evidence_repository import EvidenceBatch, RepositoryError
from .features import build_features
from .ler_adapter import adapt_ler
from .provenance import METHOD, canonical, content_hash, runtime_versions
from .statistics import analyze_statistics


class EvidenceSource(Protocol):
    def load_course(self, course_id: UUID) -> EvidenceBatch: ...


class ReadinessReport(Contract):
    current_ler_count: int
    joined_ler_count: int
    validated_ler_count: int
    selected_independent_scores: int
    selected_mapped_scores: int
    eligible_error_events: int
    practice_attempt_count: int
    issue_counts: dict[str, int]


class AnalysisBundle(Contract):
    run_id: UUID
    course_id: UUID
    source_kind: Literal["offline_fixture", "supabase"]
    started_at: AwareDatetime
    computed_at: AwareDatetime
    source_fingerprint: str
    input_snapshot: str
    manifest: dict[str, JsonValue]
    readiness: ReadinessReport
    documents: list[ARRDocument]
    clustering_report: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def time_order(self):
        if self.computed_at < self.started_at:
            raise ValueError("computation precedes run start")
        if content_hash(self.manifest) != self.input_snapshot:
            raise ValueError("snapshot manifest changed")
        if self.manifest.get("source_fingerprint") != self.source_fingerprint:
            raise ValueError("source fingerprint mismatch")
        records = [AnalyticalInput.model_validate(row) for row in self.manifest.get("records", [])]
        owners = {record.ler_id: (record.course_id, record.learner_id) for record in records}
        if len({doc.id for doc in self.documents}) != len(self.documents):
            raise ValueError("duplicate document ID")
        for doc in self.documents:
            if doc.run_id != self.run_id or doc.course_id != self.course_id or doc.created_at != self.computed_at:
                raise ValueError("document belongs to a different run")
            if doc.provenance.get("input_snapshot") != self.input_snapshot:
                raise ValueError("document snapshot mismatch")
            if doc.provenance.get("configuration") != self.manifest.get("configuration"):
                raise ValueError("document configuration mismatch")
            for lid in doc.dependency_ler_ids:
                owner = owners.get(lid)
                if owner is None or owner[0] != self.course_id or (
                    doc.subject_learner_id is not None and owner[1] != doc.subject_learner_id
                ):
                    raise ValueError("cross-course or cross-learner lineage")
        return self

    def bundle_hash(self):
        return content_hash(self)


def _adapt(batch, config, period):
    records, issues = [], Counter(issue.code for issue in batch.issues)
    for envelope in batch.envelopes:
        result = adapt_ler(envelope)
        issues.update(issue.code for issue in result.issues)
        if result.record is not None:
            if result.record.course_id != batch.course_id:
                issues["cross_course_record"] += 1
            else:
                records.append(result.record)
    features = build_features(records, config, period)
    issues.update(features.exclusions.reason)
    source_lers = batch.source_manifest.get("lers", [envelope.get("ler", {}) for envelope in batch.envelopes])
    report = ReadinessReport(
        current_ler_count=sum(row.get("is_current") is True for row in source_lers),
        joined_ler_count=len(batch.envelopes), validated_ler_count=len(records),
        selected_independent_scores=int(features.observations.primary_score.sum()),
        selected_mapped_scores=len(set(features.outcomes.loc[features.outcomes.primary_score, "ler_id"])),
        eligible_error_events=len(features.errors), practice_attempt_count=len(features.practice),
        issue_counts=dict(sorted(issues.items())),
    )
    return records, features, report


def check_readiness(source: EvidenceSource, course_id, config=None, period=None):
    batch = source.load_course(UUID(str(course_id)))
    return _adapt(batch, config or AnalyticsConfig(), period)[2]


def analyze_course(
    source: EvidenceSource, course_id, *, config=None, period=None, run_id=None,
    started_at=None, computed_at=None, cluster=False, approved_excerpts=(), embedder=None,
    reviewed_export=None, cluster_review=None,
) -> AnalysisBundle:
    config = config or AnalyticsConfig()
    course_id, run_id = UUID(str(course_id)), UUID(str(run_id)) if run_id else uuid4()
    started_at = TypeAdapter(AwareDatetime).validate_python(started_at or datetime.now(timezone.utc))
    computed_at = TypeAdapter(AwareDatetime).validate_python(computed_at) if computed_at is not None else None
    batch = source.load_course(course_id)
    if batch.course_id != course_id:
        raise ValueError("source returned a different course")
    records, features, report = _adapt(batch, config, period)
    if (reviewed_export is not None or cluster_review is not None) and not cluster:
        raise ValueError("text/group review requires clustering")
    if reviewed_export is not None:
        if approved_excerpts:
            raise ValueError("provide one excerpt input")
        from .reviewed_excerpts import ReviewedExcerptExport
        reviewed_export = ReviewedExcerptExport.model_validate(reviewed_export)
        approved_excerpts = reviewed_export.approved_inputs(records, batch, live=getattr(source, "source_kind", "offline_fixture") == "supabase")
    statistics = analyze_statistics(records, config, period)
    timestamp = computed_at or datetime.now(timezone.utc)
    clustering, prepared = None, None
    if cluster:
        from .clustering import discover_misconceptions
        from .text_preparation import prepare_error_texts
        prepared = prepare_error_texts(records, list(approved_excerpts), config, period)
        clustering = discover_misconceptions(prepared, run_id=run_id, embedder=embedder,
                                             config=config, computed_at=timestamp)
    computed_at = computed_at or datetime.now(timezone.utc)
    if clustering:
        clustering.computed_at = computed_at
    # Freeze normalized analytical facts, not arbitrary LER payload or unapproved prose.
    frozen_records = [record.model_dump(mode="json", exclude={"errors": {"__all__": {"misconception"}}})
                      for record in records]
    manifest = canonical({
        "method": METHOD, "configuration": config, "period": period,
        "source_fingerprint": batch.fingerprint(),
        "records": frozen_records, "readiness": report,
        "feature_exclusions": features.exclusions.to_dict(orient="records"),
        "runtime_versions": runtime_versions(), "cluster_requested": cluster,
        "prepared_texts": prepared,
        "clustering_model": clustering.model if clustering else None,
        "clustering_runtime": clustering.package_versions if clustering else {},
        "clustering_status": [{"course_id": str(part.course_id), "origin": part.assessment_origin,
                               "assistance": part.assistance, "status": part.status, "reason": part.reason}
                              for part in clustering.partitions] if clustering else [],
    })
    snapshot = content_hash(manifest)
    approved_clusters = None
    if cluster:
        from .cluster_review import ClusterReview, approved_ids, template
        manifest["cluster_review_template"] = template(clustering, batch.fingerprint(), reviewed_export.digest() if reviewed_export else None).model_dump(mode="json")
        if reviewed_export is not None:
            manifest["excerpt_review"] = reviewed_export.audit()
        if cluster_review is not None:
            if reviewed_export is None:
                raise ValueError("group review requires a reviewed excerpt export")
            cluster_review = ClusterReview.model_validate(cluster_review)
            approved_clusters = approved_ids(cluster_review, clustering, batch.fingerprint(), reviewed_export.digest())
            manifest["cluster_review"] = cluster_review.model_dump(mode="json")
        snapshot = content_hash(manifest)
    documents = generate_arrs(statistics, records=records, run_id=run_id, input_snapshot=snapshot,
                              computed_at=computed_at, clustering=clustering, approved_clusters=approved_clusters)
    if cluster_review is not None:
        for doc in documents:
            if doc.scope == "misconception_cluster":
                doc.provenance["cluster_review"] = {"approved": True, "binding": cluster_review.binding}
    return AnalysisBundle(
        run_id=run_id, course_id=course_id, started_at=started_at, computed_at=computed_at,
        source_kind=getattr(source, "source_kind", "offline_fixture"),
        source_fingerprint=batch.fingerprint(), input_snapshot=snapshot,
        manifest=manifest, readiness=report, documents=documents,
        clustering_report=clustering.model_dump(mode="json") if clustering else None,
    )


def persist_analysis(repository, bundle: AnalysisBundle, *, exclusive_course_access=False):
    """Stage, verify, and publish. Caller guarantees no concurrent course writers.

    Stable run/document IDs permit retries of the SAME bundle. A new intentional
    analysis uses a new run ID. Completed history is never upserted or republished.
    """
    if not exclusive_course_access:
        raise ValueError("publication requires exclusive course access, including ingestion and metadata edits")
    # Revalidate mutable DTOs before using privileged storage methods.
    bundle = AnalysisBundle.model_validate_json(bundle.model_dump_json())
    if bundle.source_kind != "supabase":
        raise ValueError("offline fixture bundles cannot be published to the shared database")
    if not bundle.documents:
        raise ValueError("no analytical results to persist")
    if content_hash(bundle.manifest) != bundle.input_snapshot:
        raise ValueError("snapshot manifest changed")
    if any(doc.run_id != bundle.run_id or doc.course_id != bundle.course_id for doc in bundle.documents):
        raise ValueError("cross-run or cross-course document")
    previous = repository.get_run(bundle.run_id)
    if previous:
        if previous["params"].get("bundle_hash") != bundle.bundle_hash():
            raise ValueError("run ID already belongs to different analytical content")
        if previous["params"].get("status") == "complete":
            return "already_completed"
    if bundle.manifest.get("cluster_requested"):
        from .cluster_review import ClusterReview, approved_ids
        from .clustering import ClusteringResult, clustering_snapshot
        from .text_preparation import PreparedTexts
        audit, review = bundle.manifest.get("excerpt_review"), bundle.manifest.get("cluster_review")
        if not audit or not review or not bundle.clustering_report:
            raise ValueError("live clustering publication requires excerpt and group review")
        result = ClusteringResult.model_validate(bundle.clustering_report)
        prepared = PreparedTexts.model_validate(bundle.manifest["prepared_texts"])
        if (result.run_id != bundle.run_id or result.config.model_dump(mode='json') != bundle.manifest['configuration']
                or (result.model.model_dump(mode='json') if result.model else None) != bundle.manifest['clustering_model']
                or result.package_versions != bundle.manifest['clustering_runtime']
                or result.input_snapshot != clustering_snapshot(prepared, result.config, result.model, result.package_versions)):
            raise ValueError("cluster report differs from frozen inputs")
        accepted = approved_ids(ClusterReview.model_validate(review), result, bundle.source_fingerprint, audit["digest"])
        groups = {g.cluster_id: g for part in result.partitions for g in part.groups}
        for doc in bundle.documents:
            if doc.scope == "misconception_cluster":
                group = doc.metrics.group
                if group.cluster_id not in accepted or group != groups[group.cluster_id]:
                    raise ValueError("unapproved cluster document")
                if doc.provenance.get("cluster_review") != {"approved": True, "binding": review["binding"]}:
                    raise ValueError("cluster review provenance mismatch")
    if repository.load_course(bundle.course_id).fingerprint() != bundle.source_fingerprint:
        raise RepositoryError("source_changed_before_publication")
    params = {
        "status": "writing", "bundle_hash": bundle.bundle_hash(), "source_fingerprint": bundle.source_fingerprint,
        "manifest": bundle.manifest, "clustering_report": bundle.clustering_report,
        "attempts": (previous["params"].get("attempts", 0) if previous else 0) + 1,
        "previous_failures": list(previous["params"].get("previous_failures", [])) if previous else [],
        "document_ids": [str(doc.id) for doc in bundle.documents],
    }
    row = {
        "id": str(bundle.run_id), "course_id": str(bundle.course_id), "method": METHOD,
        "model_version": bundle.manifest["configuration"]["method_version"],
        "input_snapshot": bundle.input_snapshot, "params": params,
        "started_at": bundle.started_at.isoformat(), "computed_at": None,
    }
    repository.write_run(row)
    try:
        repository.stage_documents(bundle.documents)
        repository.write_links(bundle.documents)
        repository.verify_staged(bundle.run_id, bundle.documents)
        if repository.load_course(bundle.course_id).fingerprint() != bundle.source_fingerprint:
            raise RepositoryError("source_changed_during_publication")
        # Mark verified payload complete first; all result rows are still staged/stale.
        # Publishing the run's rows is then ONE SQL update, not one update per ARR.
        params["status"] = "publishing"
        row["computed_at"] = bundle.computed_at.isoformat()
        repository.write_run(row)
        repository.set_stale(bundle.run_id, False)
        if repository.load_course(bundle.course_id).fingerprint() != bundle.source_fingerprint:
            raise RepositoryError("source_changed_during_publication")
        params["status"] = "complete"
        repository.write_run(row)
    except Exception as exc:
        code = str(exc) if isinstance(exc, RepositoryError) else "publication_failed"
        params["status"] = "failed"
        params["previous_failures"].append(code)
        # Best effort; never replace the original failure with a cleanup exception.
        try:
            repository.set_stale(bundle.run_id, True)
            repository.write_run(row)
        except Exception:
            pass
        raise RepositoryError(code) from None
    return "completed"


def retrieve_current_results(control_repository, user_reader, course_id, run_id, *, scope=None, learner_id=None):
    """RLS reads first; private control metadata is never returned to the caller.

    Source revalidation catches score/mapping edits not covered by SQL triggers.
    This is still not a transactional read against concurrent course writers.
    """
    documents = user_reader.read_published(course_id, run_id, scope=scope, learner_id=learner_id)
    if not documents:
        return []
    run = control_repository.get_run(run_id)
    if not run or run["course_id"] != str(course_id) or run["params"].get("status") != "complete":
        return []
    if control_repository.load_course(UUID(str(course_id))).fingerprint() != run["params"].get("source_fingerprint"):
        raise RepositoryError("analysis_run_is_stale")
    return documents

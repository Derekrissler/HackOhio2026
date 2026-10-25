"""Validated local demo reviews, real clustering and reviewed ARR finalization.

No approval is inferred from data generation, cohesion or an empty decision file.
Review attribution distinguishes human review from explicitly delegated agent
review. Neither certifies that a hypothetical error occurred in original work.
"""
from collections import Counter
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from .cluster_review import ClusterReview, approved_ids, group_keys
from .clustering import ClusteringResult, clustering_snapshot
from .config import AnalyticsConfig
from .contracts import Contract
from .provenance import content_hash
from .reviewed_excerpts import ReviewedExcerpt, ReviewedExcerptExport
from .service import AnalysisBundle, _adapt, analyze_course
from .synthetic_inputs import KIND, MARKER, SyntheticDemoProvenance, generate_dataset
from .synthetic_source import SyntheticDemoSource, preview_report
from .text_preparation import PreparedTexts


class TextDecision(Contract):
    ler_error_id: UUID
    decision: Literal["pending", "approved", "rejected"] = "pending"
    privacy_reviewed: StrictBool = False
    context_reviewed: StrictBool = False
    synthetic_label_verified: StrictBool = False
    notes: str = Field(default="", max_length=2000)


class DemoTextReview(Contract):
    schema_version: Literal["1.0"] = "1.0"
    provenance: SyntheticDemoProvenance
    binding: str
    reviewer_kind: Literal["human", "delegated_agent"] | None = None
    reviewer_ref: str | None = None
    reviewed_at: AwareDatetime | None = None
    review_authority: str | None = None
    decisions: list[TextDecision]

    @model_validator(mode="after")
    def consistent(self):
        if len({d.ler_error_id for d in self.decisions}) != len(self.decisions):
            raise ValueError("duplicate text decision")
        if any(d.decision != "pending" for d in self.decisions):
            if not self.reviewer_ref or not self.reviewer_kind or not self.reviewed_at:
                raise ValueError("completed demo text review requires attribution")
            if self.reviewer_kind == "delegated_agent" and not self.review_authority:
                raise ValueError("delegated review requires explicit authority attribution")
        for decision in self.decisions:
            if decision.decision == "approved" and not (decision.privacy_reviewed and decision.context_reviewed
                    and decision.synthetic_label_verified and decision.notes.strip()):
                raise ValueError("approved demo text requires explicit review attestations and notes")
            if decision.decision == "rejected" and not decision.notes.strip():
                raise ValueError("rejected demo text requires a reason")
        return self


class GroupAssessment(Contract):
    group_key: str
    notes: str = Field(min_length=1, max_length=4000)


class DemoGroupReview(Contract):
    schema_version: Literal["1.0"] = "1.0"
    provenance: SyntheticDemoProvenance
    candidate_bundle_hash: str
    reviewer_kind: Literal["human", "delegated_agent"]
    review_authority: str | None = None
    review: ClusterReview
    assessments: list[GroupAssessment]

    @model_validator(mode="after")
    def consistent(self):
        if self.reviewer_kind == "delegated_agent" and not self.review_authority:
            raise ValueError("delegated group review requires authority attribution")
        keys = [a.group_key for a in self.assessments]
        if len(keys) != len(set(keys)) or set(keys) != {d.group_key for d in self.review.decisions}:
            raise ValueError("every group needs one documented assessment")
        if any(d.decision == "pending" for d in self.review.decisions):
            raise ValueError("group decisions remain pending")
        return self


def validation_report(source):
    snapshot, dataset = source.snapshot, source.dataset
    report = preview_report(snapshot, dataset)
    regenerated = generate_dataset(snapshot, dataset.config, generated_at=dataset.generated_at)
    if regenerated != dataset:
        raise ValueError("seed/source reproducibility failure")
    batch = source.load_course(dataset.course_id)
    records, features, readiness = _adapt(batch, AnalyticsConfig(), None)
    by_id = {r.ler_id: r for r in records}
    candidate_ids = {c.ler_error_id for c in dataset.excerpt_candidates}
    errors = {e.id: (case, e) for case in dataset.classifications for e in case.errors}
    refs = {e.id: e for e in dataset.evidence}
    if candidate_ids != set(errors) or len(candidate_ids) != len(dataset.excerpt_candidates):
        raise ValueError("review candidate/error identities differ")
    for case in dataset.classifications:
        record = by_id[case.ler_id]
        if (record.revision, record.learner_id, record.question_id) != (
                case.ler_revision, case.learner_id, case.question_id):
            raise ValueError("synthetic source ownership differs")
        for error in case.errors:
            if not set(error.outcome_ids) <= {m.outcome_id for m in record.outcome_mappings}:
                raise ValueError("synthetic outcome attribution differs")
            for rid in error.evidence_ref_ids:
                ref = refs[rid]
                if (ref.course_id, ref.learner_id, ref.source_ler_id, ref.source_question_id,
                        ref.source_response_id) != (record.course_id, record.learner_id, record.ler_id,
                        record.question_id, record.response_id):
                    raise ValueError("synthetic evidence ownership differs")
                if ref.content_hash != content_hash(ref.excerpt):
                    raise ValueError("synthetic evidence hash differs")
    for candidate in dataset.excerpt_candidates:
        case, error = errors[candidate.ler_error_id]
        if (candidate.ler_id, candidate.ler_revision, candidate.error_code, candidate.text,
                candidate.evidence_ref_ids) != (case.ler_id, case.ler_revision, error.code,
                error.description, error.evidence_ref_ids):
            raise ValueError("candidate differs from generated scenario")
    checks = ["existing_course_and_ler_relationships", "learner_and_evidence_ownership",
        "valid_explicit_error_outcomes", "taxonomy_and_analytical_contracts", "source_scores_preserved",
        "original_feedback_and_academic_fields_preserved", "no_fake_original_annotations",
        "unique_ler_code_and_error_identities", "explicit_completion_states", "synthetic_provenance",
        "seed_and_source_reproducibility", "insufficient_cases_preserved", "pending_review_attestations"]
    repetitions = Counter(c.text for c in dataset.excerpt_candidates)
    report.update(status="validated_pending_text_review", validation_schema="1.0",
        checks={name: "passed" for name in checks},
        unique_description_count=len(repetitions), max_description_repetitions=max(repetitions.values(), default=0),
        eligible_error_events=readiness.eligible_error_events,
        unknown_completion_lers=sum(r.errors_analyzed is None for r in records),
        preserved_mapping_review_count=sum(m.needs_review for r in records for m in r.outcome_mappings),
        human_or_delegated_context_and_privacy_review="pending; not established by automated validation")
    return report


def text_review_packet(source):
    dataset, snapshot = source.dataset, source.snapshot
    questions = {UUID(r["id"]): r for r in snapshot.context["questions"]}
    outcomes = {UUID(r["id"]): r for r in snapshot.context["outcomes"]}
    errors = {e.id: (c, e) for c in dataset.classifications for e in c.errors}
    contexts = []
    for candidate in dataset.excerpt_candidates:
        case, error = errors[candidate.ler_error_id]
        contexts.append({"candidate": candidate.model_dump(mode="json"),
            "question_id": str(case.question_id), "question_code": questions[case.question_id].get("code"),
            "question_text": questions[case.question_id]["text"],
            "outcomes": [{"id": str(oid), "code": outcomes[oid]["code"],
                           "text": outcomes[oid].get("syllabus_text")} for oid in error.outcome_ids],
            "selection_basis": case.selection_basis, "response_text_available": case.response_text_available,
            "interpretation_limit": "Hypothetical demo scenario; question context is not evidence of a genuine learner mistake."})
    binding = content_hash({"provenance": dataset.provenance(), "contexts": contexts})
    review = DemoTextReview(provenance=dataset.provenance(), binding=binding,
        decisions=[TextDecision(ler_error_id=c.ler_error_id) for c in dataset.excerpt_candidates])
    return {"review": review.model_dump(mode="json"), "contexts": contexts}


def compile_text_review(source, review):
    review = DemoTextReview.model_validate_json(review.model_dump_json())
    expected = DemoTextReview.model_validate(text_review_packet(source)["review"])
    if (review.binding != expected.binding or review.provenance != expected.provenance
            or {d.ler_error_id for d in review.decisions} != {d.ler_error_id for d in expected.decisions}):
        raise ValueError("text review source/candidates changed")
    if any(d.decision == "pending" for d in review.decisions) or not review.reviewer_ref or not review.reviewed_at:
        raise ValueError("text review is incomplete")
    decisions = {d.ler_error_id: d for d in review.decisions}
    entries = []
    for candidate in source.dataset.excerpt_candidates:
        if decisions[candidate.ler_error_id].decision == "approved":
            fields = candidate.model_dump(exclude={"decision", "privacy_reviewed", "context_reviewed", "reviewer_ref", "reviewed_at"})
            entries.append(ReviewedExcerpt(**fields, privacy_reviewed=True))
    export = ReviewedExcerptExport(schema_version="1.0", course_id=source.dataset.course_id,
        extraction_version=source.dataset.config.generator_version,
        reviewer_ref=f"{review.reviewer_kind}:{review.reviewer_ref}", reviewed_at=review.reviewed_at,
        review_revision=content_hash(review), entries=entries)
    batch = source.load_course(source.dataset.course_id)
    records, _, _ = _adapt(batch, AnalyticsConfig(), None)
    export.approved_inputs(records, batch, verify_source_rows=True)
    return export


def analyze_demo(source, review, embedder, *, config=None):
    """Only explicit bound text decisions reach the existing embedding engine."""
    export = compile_text_review(source, review)
    if not export.entries:
        raise ValueError("no approved demo descriptions")
    return analyze_course(source, source.dataset.course_id, cluster=True, reviewed_export=export,
                          embedder=embedder, config=config), export


def cluster_review_packet(bundle):
    bundle = AnalysisBundle.model_validate_json(bundle.model_dump_json())
    if bundle.source_kind != "offline_fixture" or MARKER not in bundle.manifest or not bundle.clustering_report:
        raise ValueError("candidate is not a synthetic clustering bundle")
    result = ClusteringResult.model_validate(bundle.clustering_report)
    prepared = PreparedTexts.model_validate(bundle.manifest["prepared_texts"])
    if (result.run_id != bundle.run_id or result.config.model_dump(mode="json") != bundle.manifest["configuration"]
            or result.input_snapshot != clustering_snapshot(prepared, result.config, result.model, result.package_versions)):
        raise ValueError("candidate clustering differs from frozen inputs")
    keys = group_keys(result)
    observations = {o["observation_id"]: o for o in bundle.manifest["prepared_texts"]["observations"]}
    groups = []
    for part in result.partitions:
        for group in part.groups:
            members = [observations[a.observation_id] for a in part.assignments if a.cluster_id == group.cluster_id]
            groups.append({"group_key": keys[group.cluster_id], "group": group.model_dump(mode="json"),
                "members": members, "distinct_error_codes": sorted({m["error_code"] for m in members}),
                "meets_aggregate_student_minimum": group.unique_student_count >= result.config.class_min_students})
    return {"provenance": bundle.manifest[MARKER], "candidate_bundle_hash": bundle.bundle_hash(),
            "review": bundle.manifest["cluster_review_template"], "groups": groups,
            "partitions": [{"status": p.status, "reason": p.reason, "noise_count": p.noise_count,
                            "silhouette_cosine": p.silhouette_cosine} for p in result.partitions]}


def finalize_demo(source, text_review, candidate, group_review, embedder):
    group_review = DemoGroupReview.model_validate_json(group_review.model_dump_json())
    packet = cluster_review_packet(candidate)
    if (group_review.candidate_bundle_hash != packet["candidate_bundle_hash"]
            or group_review.provenance.model_dump(mode="json") != source.dataset.provenance()):
        raise ValueError("group review belongs to different demo results")
    export = compile_text_review(source, text_review)
    result = ClusteringResult.model_validate(candidate.clustering_report)
    accepted = approved_ids(group_review.review, result, candidate.source_fingerprint, export.digest())
    final = analyze_course(source, source.dataset.course_id, config=result.config, cluster=True,
        reviewed_export=export, cluster_review=group_review.review, embedder=embedder)
    # Recomputed groups must bind to exactly the original candidate's source/model/inputs.
    if final.manifest["cluster_review_template"]["binding"] != group_review.review.binding:
        raise ValueError("final clustering differs from reviewed candidate")
    cluster_docs = [d for d in final.documents if d.scope == "misconception_cluster"]
    allowed_keys = {group_keys(result)[cid] for cid in accepted}
    final_result = ClusteringResult.model_validate(final.clustering_report)
    final_keys = group_keys(final_result)
    if any(final_keys[d.metrics.group.cluster_id] not in allowed_keys for d in cluster_docs):
        raise ValueError("final ARR contains an unreviewed group")
    summary = {"provenance": source.dataset.provenance(), "status": "finalized_local_demo",
        "candidate_run_id": str(candidate.run_id), "final_run_id": str(final.run_id),
        "total_arrs": len(final.documents), "cluster_arrs": len(cluster_docs),
        "approved_groups": len(accepted), "rejected_groups": sum(d.decision == "rejected" for d in group_review.review.decisions),
        "suppressed_approved_groups": len(accepted) - len(cluster_docs),
        "scope_counts": dict(Counter(d.scope for d in final.documents)),
        "reviewer_kind": group_review.reviewer_kind, "database_writes": False,
        "cluster_summaries": [{"representative": d.metrics.group.representative_text,
            "error_code": d.metrics.group.representative_error_code,
            "unique_students": d.metrics.group.unique_student_count,
            "evidence_lers": d.metrics.group.evidence_observation_count,
            "cohesion": d.metrics.group.mean_pairwise_cosine_similarity} for d in cluster_docs]}
    return final, summary


def text_review_markdown(packet):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# VIBE 101: synthetic description review", "",
        "These are hypothetical demonstration inputs, not observed learner mistakes or instructor feedback.",
        "All decisions are pending. Review privacy, fit to the question and outcome, and the synthetic label.",
        "Approve or reject each error ID; explain rejections or requested edits. Do not edit dataset.json.",
        "", f"Dataset: `{packet['review']['provenance']['dataset_id']}`",
        f"Binding: `{packet['review']['binding']}`", "",
        "| # | Error ID | Code | Question | Outcome | Proposed description |",
        "|---|---|---|---|---|---|"]
    questions = {}
    for number, row in enumerate(packet["contexts"], 1):
        candidate = row["candidate"]
        qid = row.get("question_id", "")
        questions[qid] = row["question_text"]
        values = [number, candidate["ler_error_id"], candidate["error_code"], qid,
                  ", ".join(o["code"] for o in row["outcomes"]), candidate["text"]]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += ["", "## Question contexts", ""]
    for qid, text in questions.items():
        lines += [f"### {qid}", "", text, ""]
    return "\n".join(lines) + "\n"


def review_attention(packet):
    """Advisories for the reviewer, never automatic approval or rejection."""
    flags = []
    for number, row in enumerate(packet["contexts"], 1):
        candidate = row["candidate"]
        question = row["question_text"].casefold()
        if candidate["error_code"] == "missing_edge_case_tests" and not any(
                anchor in question for anchor in ("empty", "edge case", "boundary", "average", "normalize")):
            flags.append({"row": number, "ler_error_id": candidate["ler_error_id"],
                "question_text": row["question_text"], "proposed_description": candidate["text"],
                "reason": "The description names an empty-input omission but this question stem does not establish that specific testing context. Consider rejecting or revising it.",
                "decision": "pending"})
    return {"provenance": packet["review"]["provenance"], "text_review_binding": packet["review"]["binding"],
            "advisory_count": len(flags), "flags": flags, "automated_decisions": False}


def run_review_cli(args):
    from pathlib import Path
    from .synthetic_source import PRIVATE_ROOT, private_path, write_private, write_private_text
    source = SyntheticDemoSource.from_files(args.snapshot, args.dataset)
    folder = PRIVATE_ROOT / str(source.dataset.dataset_id)
    report = validation_report(source)
    if args.demo_command == "validate":
        packet = text_review_packet(source)
        attention = review_attention(packet)
        write_private(folder / "validation-report.json", report)
        write_private(folder / "text-review.packet.json", packet)
        # Never overwrite a person's in-progress decisions on a validation retry.
        decision_path = folder / "text-review.decisions.json"
        if not decision_path.exists():
            write_private(decision_path, packet["review"])
        markdown = write_private_text(folder / "text-review.md", text_review_markdown(packet))
        write_private(folder / "review-attention.json", attention)
        attention_lines = ["# Description review: items needing special attention", "",
            "These are advisories, not review decisions. Every item remains pending.", ""]
        for flag in attention["flags"]:
            attention_lines += [f"## Packet row {flag['row']}: {flag['ler_error_id']}", "",
                f"Question: {flag['question_text']}", "", f"Description: {flag['proposed_description']}", "",
                flag["reason"], ""]
        write_private_text(folder / "review-attention.md", "\n".join(attention_lines) + "\n")
        return {"status": report["status"], "checks_passed": len(report["checks"]),
                "descriptions": report["pending_text_reviews"], "private_report": str(folder / "validation-report.json"),
                "review_packet": str(markdown), "decisions": str(decision_path),
                "review_advisories": attention["advisory_count"],
                "attention_packet": str(folder / "review-attention.md"), "database_writes": False}
    review = DemoTextReview.model_validate_json(private_path(args.review).read_text(encoding="utf-8"))
    export = compile_text_review(source, review)  # Reject pending text before loading a model.
    token = content_hash(review).removeprefix("sha256:")
    export_path = write_private(folder / f"reviewed-excerpts-{token}.json", export)
    write_private(folder / f"text-review-audit-{token}.json", review)
    if args.demo_command == "review-text":
        return {"status": "text_review_complete", "approved_descriptions": len(export.entries),
                "rejected_descriptions": len(review.decisions) - len(export.entries),
                "reviewer_kind": review.reviewer_kind, "reviewed_export": str(export_path), "database_writes": False}
    if args.demo_command == "archive":
        from .synthetic_storage import archive_row, store_demo_run
        from .supabase_clients import create_pipeline_client
        candidate = AnalysisBundle.model_validate_json(private_path(args.candidate).read_text(encoding="utf-8"))
        if not args.authorize_synthetic_storage:
            raise ValueError("explicit shared synthetic-storage authorization required")
        archive_row(source, review, candidate, authorization_note=args.authorization_note)
        result = store_demo_run(create_pipeline_client(), source, review, candidate,
            authorize_synthetic_storage=True, authorization_note=args.authorization_note)
        write_private(folder / f"supabase-archive-{candidate.run_id}.json",
            {k: v for k, v in result.items() if k != "status"})
        return result
    from .embeddings import MiniLMOnnxEmbedder
    embedder = MiniLMOnnxEmbedder(Path(args.model_cache))
    if args.demo_command == "analyze":
        bundle, _ = analyze_demo(source, review, embedder)
        packet = cluster_review_packet(bundle)
        path = write_private(folder / f"candidate-{bundle.run_id}.json", bundle)
        write_private(folder / f"cluster-review-{bundle.run_id}.packet.json", packet)
        write_private(folder / f"cluster-review-{bundle.run_id}.decisions.json", {
            "schema_version": "1.0", "provenance": packet["provenance"],
            "candidate_bundle_hash": packet["candidate_bundle_hash"],
            "reviewer_kind": None, "review_authority": None, "review": packet["review"],
            "assessments": [{"group_key": row["group_key"], "notes": ""} for row in packet["review"]["decisions"]]})
        return {"status": "candidate_groups_pending_review", "candidate": str(path),
                "groups": len(packet["groups"]), "partitions": packet["partitions"],
                "review_packet": str(folder / f"cluster-review-{bundle.run_id}.packet.json"),
                "approved_descriptions": len(export.entries), "database_writes": False}
    if args.demo_command == "finalize":
        candidate = AnalysisBundle.model_validate_json(private_path(args.candidate).read_text(encoding="utf-8"))
        group_review = DemoGroupReview.model_validate_json(private_path(args.group_review).read_text(encoding="utf-8"))
        final, summary = finalize_demo(source, review, candidate, group_review, embedder)
        path = write_private(folder / f"final-{final.run_id}.json", final)
        write_private(folder / f"final-{final.run_id}.summary.json", summary)
        write_private(folder / f"group-review-audit-{final.run_id}.json", group_review)
        return {**summary, "final_bundle": str(path)}
    raise ValueError("unsupported demo review operation")

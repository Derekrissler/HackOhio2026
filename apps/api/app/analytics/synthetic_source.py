"""Private offline demonstration source; the only network operation is read-only capture."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID

from .config import AnalyticsConfig
from .evidence_repository import SupabaseEvidenceRepository
from .provenance import content_hash
from .service import _adapt
from .synthetic_inputs import (DemoSourceSnapshot, SyntheticDataset, SyntheticGenerationConfig,
                               VIBE_COURSE, generate_dataset, materialize)

PRIVATE_ROOT = Path(__file__).resolve().parents[4] / "data" / "analytics-runs" / "synthetic" / "vibe101"
CONTEXT_TABLES = ("lers", "responses", "questions", "feedback", "evidence_refs", "outcomes",
                  "question_outcomes", "error_taxonomy")


def private_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(PRIVATE_ROOT.resolve()) or path == PRIVATE_ROOT.resolve():
        raise ValueError("synthetic artifacts belong in the private VIBE 101 directory")
    return path


def write_private(path, data):
    """Identical retries are harmless; never overwrite a different private artifact."""
    path = private_path(path)
    encoded = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
    if path.exists():
        if content_hash(json.loads(path.read_text(encoding="utf-8"))) != content_hash(encoded):
            raise ValueError("private artifact already has different content")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(encoded, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return path


def write_private_text(path, text):
    path = private_path(path)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError("private text artifact already has different content")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def capture_snapshot(client, course_id=VIBE_COURSE):
    """SELECT only; repeated reads detect changes, not a database transaction."""
    from .source_repairs import read_source
    course_id = UUID(str(course_id))
    if course_id != VIBE_COURSE:
        raise ValueError("synthetic workflow is scoped to existing VIBE 101")
    reader = SupabaseEvidenceRepository(client)
    before = reader.load_course(course_id)
    context = {k: v for k, v in read_source(client, course_id).items() if k in CONTEXT_TABLES}
    confirmation = {k: v for k, v in read_source(client, course_id).items() if k in CONTEXT_TABLES}
    after = reader.load_course(course_id)
    if before.fingerprint() != after.fingerprint() or content_hash(context) != content_hash(confirmation):
        raise ValueError("source changed during read-only capture; retry after it stabilizes")
    values = {"captured_at": datetime.now(timezone.utc), "base_batch": before, "context": context}
    values["snapshot_digest"] = content_hash({"base_batch": before, "context": context})
    return DemoSourceSnapshot(**values)


class SyntheticDemoSource:
    source_kind = "offline_fixture"
    requires_source_row_review = True

    def __init__(self, snapshot, dataset):
        self.snapshot = DemoSourceSnapshot.model_validate_json(snapshot.model_dump_json())
        self.dataset = SyntheticDataset.model_validate_json(dataset.model_dump_json())

    @classmethod
    def from_files(cls, snapshot_path, dataset_path):
        return cls(DemoSourceSnapshot.model_validate_json(private_path(snapshot_path).read_text(encoding="utf-8")),
                   SyntheticDataset.model_validate_json(private_path(dataset_path).read_text(encoding="utf-8")))

    def load_course(self, course_id):
        if UUID(str(course_id)) != self.dataset.course_id:
            raise ValueError("demo source belongs to another course")
        return materialize(self.snapshot, self.dataset)


def _score_signature(features):
    # Source evidence unions change; only genuine score facts must be identical.
    observations = features.observations
    selected = observations.loc[observations.primary_score]
    outcomes = features.outcomes.loc[features.outcomes.primary_score]
    return content_hash({"selected": selected[["ler_id", "source_points_earned", "source_points_possible"]].to_dict("records"),
                         "outcomes": outcomes[["ler_id", "outcome_id", "raw_weight", "normalized_weight",
                                               "weighted_earned", "weighted_possible"]].to_dict("records")})


def preview_report(snapshot, dataset):
    source = SyntheticDemoSource(snapshot, dataset)
    batch = source.load_course(dataset.course_id)
    records, features, ready = _adapt(batch, AnalyticsConfig(), None)
    baseline_records, baseline, baseline_ready = _adapt(snapshot.base_batch, AnalyticsConfig(), None)
    if _score_signature(features) != _score_signature(baseline):
        raise ValueError("synthetic overlay changed score selection or metrics")
    # Round-trip all original tables/fields, excluding only the agreed completion overlay.
    restored = deepcopy(batch.source_manifest)
    changed = {str(c.ler_id) for c in dataset.classifications}
    original_lers = {r["id"]: r for r in snapshot.base_batch.source_manifest["lers"]}
    for row in restored["lers"]:
        if row["id"] in changed:
            row["analytics_metadata"] = deepcopy(original_lers[row["id"]].get("analytics_metadata"))
    for table in ("ler_errors", "ler_error_evidence", "ler_evidence", "evidence_refs"):
        # Original rows must be retained unchanged; deterministic regeneration checks all additions.
        if not all(row in restored[table] for row in snapshot.base_batch.source_manifest[table]):
            raise ValueError("original evidence was changed")
        restored[table] = deepcopy(snapshot.base_batch.source_manifest[table])
    restored.pop("synthetic_demo_v1")
    if content_hash(restored) != content_hash(snapshot.base_batch.source_manifest):
        raise ValueError("original academic source fields were changed")
    states, themes = {}, {}
    primary_errors = set(features.observations.loc[features.observations.primary_error, "ler_id"])
    for case in dataset.classifications:
        states[case.state] = states.get(case.state, 0) + 1
    for code in sorted({e.code for c in dataset.classifications for e in c.errors}):
        cases = [c for c in dataset.classifications if any(e.code == code for e in c.errors)]
        eligible = [c for c in cases if str(c.ler_id) in primary_errors]
        themes[code] = {"generated_lers": len(cases), "eligible_lers": len(eligible),
                       "eligible_students": len({c.learner_id for c in eligible}),
                       "eligible_questions": len({c.question_id for c in eligible}),
                       "meets_five_student_arr_minimum": len({c.learner_id for c in eligible}) >= 5}
    insufficient = lambda rows: sorted(str(r.ler_id) for r in rows if r.analysis_status == "insufficient")
    if insufficient(records) != insufficient(baseline_records):
        raise ValueError("insufficient source cases changed")
    return {"dataset_id": str(dataset.dataset_id), "dataset_kind": dataset.dataset_kind,
            "seed": dataset.config.seed, "source_snapshot_digest": snapshot.snapshot_digest,
            "content_digest": dataset.content_digest, "source_lers": len(records),
            "distinct_learners": len({r.learner_id for r in records}),
            "states": states, "untouched_lers": len(records) - len(dataset.classifications),
            "requested_error_lers": dataset.config.target_error_lers,
            "generated_error_lers": states.get("completed_with_errors", 0),
            "shortfall": max(0, dataset.config.target_error_lers - states.get("completed_with_errors", 0)),
            "pending_text_reviews": len(dataset.excerpt_candidates), "approved_text_reviews": 0,
            "synthetic_manual_evidence": len(dataset.evidence), "themes": themes,
            "insufficient_lers_preserved": len(insufficient(records)),
            "selected_independent_scores": ready.selected_independent_scores,
            "baseline_selected_independent_scores": baseline_ready.selected_independent_scores,
            "score_signature_unchanged": True, "original_source_fields_unchanged": True,
            "source_context_digest": content_hash(snapshot.context),
            "source_kind": source.source_kind, "ml_executed": False, "database_writes": False,
            "status": "preview_pending_human_text_review",
            "limitations": ["Hypothetical classifications are not observed learner behavior.",
                            "Theme participation is not discovered cluster membership.",
                            "Mappings/outcomes retain their original review status.",
                            "Source capture uses repeated reads, not a database transaction."]}


def run_demo_cli(args):
    """Local phase gates; no implicit approvals and no publication command."""
    if args.demo_command == "snapshot":
        from .supabase_clients import create_pipeline_client
        private_path(args.output)  # Reject an unsafe destination before accessing credentials.
        snapshot = capture_snapshot(create_pipeline_client(), args.course)
        write_private(args.output, snapshot)
        return {"snapshot": str(private_path(args.output)), "snapshot_digest": snapshot.snapshot_digest,
                "source_lers": len(snapshot.base_batch.envelopes), "database_writes": False}
    snapshot = DemoSourceSnapshot.model_validate_json(private_path(args.snapshot).read_text(encoding="utf-8"))
    if args.demo_command == "generate":
        config = SyntheticGenerationConfig(seed=args.seed, target_error_lers=args.target)
        dataset = generate_dataset(snapshot, config)
        folder = PRIVATE_ROOT / str(dataset.dataset_id)
        # Stable content retries reuse the original execution timestamp/artifact.
        previous = folder / "dataset.json"
        if previous.exists():
            saved = SyntheticDataset.model_validate_json(previous.read_text(encoding="utf-8"))
            if saved.content_digest != dataset.content_digest:
                raise ValueError("dataset identity conflict")
            dataset = saved
        report = preview_report(snapshot, dataset)
        write_private(folder / "source-snapshot.json", snapshot)
        write_private(folder / "dataset.json", dataset)
        write_private(folder / "manifest.json", {**dataset.provenance(),
            "generated_at": dataset.generated_at.isoformat(), "configuration": dataset.config.model_dump(mode="json"),
            "classification_count": len(dataset.classifications), "theme_counts": report["themes"],
            "source_relationships": [{"ler_id": str(c.ler_id), "ler_revision": c.ler_revision,
                "question_id": str(c.question_id), "learner_id": str(c.learner_id),
                "state": c.state, "error_ids": [str(e.id) for e in c.errors]} for c in dataset.classifications]})
        write_private(folder / "excerpt-candidates.json", [c.model_dump(mode="json") for c in dataset.excerpt_candidates])
        write_private(folder / "preview-report.json", report)
        return {**report, "private_directory": str(folder)}
    from .synthetic_workflow import run_review_cli
    return run_review_cli(args)

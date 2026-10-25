"""Explicitly authorized synthetic ML storage, isolated from published ARRs.

Writes one append-only analytics_runs row. Never changes academic evidence,
analytics_results, lineage links, existing runs, schema, or review decisions.
"""
from pydantic import AwareDatetime, TypeAdapter

from .evidence_repository import RepositoryError, read_pages
from .provenance import content_hash
from .service import AnalysisBundle
from .synthetic_inputs import MARKER
from .synthetic_workflow import cluster_review_packet, compile_text_review

METHOD = "synthetic_demo_minilm_dbscan_v1"
STATUS = "demo_candidate"


def archive_row(source, text_review, bundle, *, authorization_note):
    """Pure validation/row construction; keeps pending groups pending."""
    if not isinstance(authorization_note, str) or not authorization_note.strip():
        raise ValueError("synthetic storage requires explicit authorization attribution")
    bundle = AnalysisBundle.model_validate_json(bundle.model_dump_json())
    packet = cluster_review_packet(bundle)
    batch = source.load_course(bundle.course_id)
    export = compile_text_review(source, text_review)
    if (bundle.course_id != source.dataset.course_id or batch.fingerprint() != bundle.source_fingerprint
            or bundle.manifest[MARKER] != source.dataset.provenance()
            or bundle.manifest.get("excerpt_review", {}).get("digest") != export.digest()):
        raise ValueError("stored demo must match the approved source and text review")
    result = bundle.clustering_report
    if not result["model"] or not result["partitions"] or any(p["status"] != "completed" for p in result["partitions"]):
        raise ValueError("only successfully computed ML runs can be archived")
    if (result["model"] != bundle.manifest["clustering_model"]
            or result["package_versions"] != bundle.manifest["clustering_runtime"]):
        raise ValueError("stored model metadata differs from the computed snapshot")
    observations = bundle.manifest["prepared_texts"]["observations"]
    assignments = [a for p in result["partitions"] for a in p["assignments"]]
    if {o["observation_id"] for o in observations} != {a["observation_id"] for a in assignments}:
        raise ValueError("incomplete ML assignments")
    params = {
        "status": STATUS, "storage_kind": "synthetic_ml_candidate_archive_v1",
        "publication_status": "not_published", "source_kind": "offline_fixture",
        MARKER: source.dataset.provenance(), "authorization_note": authorization_note.strip(),
        "candidate_bundle_hash": bundle.bundle_hash(),
        "source_fingerprint": bundle.source_fingerprint,
        "source_freshness": "frozen_historical_snapshot; not revalidated for live publication",
        "configuration": bundle.manifest["configuration"],
        "clustering_report": result, "prepared_texts": bundle.manifest["prepared_texts"],
        "excerpt_review": bundle.manifest["excerpt_review"],
        "text_decisions": text_review.model_dump(mode="json"),
        "cluster_review_template": packet["review"],
        "counts": {"processed_descriptions": len(observations),
            "excluded_descriptions": len(text_review.decisions) - len(export.entries),
            "candidate_groups": len(packet["groups"]),
            "noise_descriptions": sum(p["noise_count"] for p in result["partitions"]),
            "groups_meeting_student_minimum": sum(g["meets_aggregate_student_minimum"] for g in packet["groups"]),
            "published_cluster_arrs": 0},
        "interpretation_limits": ["Synthetic hypothetical classifications, not observed learner mistakes.",
            "Groups remain pending interpretation review; no live ARR publication.",
            "Small groups and noise are retained in staff-only run metadata.",
            "This row does not replace published score analytics or original academic evidence."],
    }
    params["archive_content_digest"] = content_hash(params)
    return {"id": str(bundle.run_id), "course_id": str(bundle.course_id), "method": METHOD,
        "model_version": result["model"]["model_id"] + "@" + result["model"]["revision"],
        "input_snapshot": bundle.input_snapshot, "params": params,
        "started_at": bundle.started_at.isoformat(), "computed_at": bundle.computed_at.isoformat()}


def _matches(actual, expected):
    for key, value in expected.items():
        if key in ("started_at", "computed_at"):
            if TypeAdapter(AwareDatetime).validate_python(actual.get(key)) != TypeAdapter(AwareDatetime).validate_python(value):
                return False
        elif content_hash(actual.get(key)) != content_hash(value):
            return False
    return True


def store_demo_run(client, source, text_review, bundle, *, authorize_synthetic_storage=False, authorization_note=""):
    """Insert/read back one run. Explicit retries never overwrite any row."""
    if authorize_synthetic_storage is not True:
        raise ValueError("explicit shared synthetic-storage authorization is required")
    row = archive_row(source, text_review, bundle, authorization_note=authorization_note)
    courses = read_pages(client, "courses", "id", filters={"id": row["course_id"]})
    if len(courses) != 1:
        raise ValueError("existing course not found; no new course will be created")
    existing = read_pages(client, "analytics_runs", "*", filters={"id": row["id"]})
    if existing:
        if len(existing) != 1 or not _matches(existing[0], row):
            raise ValueError("run ID already belongs to different content; refusing overwrite")
        status = "already_stored"
    else:
        try:
            client.table("analytics_runs").insert(row).execute()
        except Exception:
            # An uncertain response can be retried with the exact same immutable row.
            raise RepositoryError("synthetic_run_insert_failed; verify the run ID before retry") from None
        status = "stored"
    stored = read_pages(client, "analytics_runs", "*", filters={"id": row["id"]})
    if len(stored) != 1 or not _matches(stored[0], row):
        raise RepositoryError("synthetic_run_readback_mismatch")
    return {"status": status, "table": "analytics_runs", "run_id": row["id"],
        "course_id": row["course_id"], "method": METHOD, "synthetic": True,
        "counts": row["params"]["counts"], "readback_verified": True,
        "published_arrs": 0, "academic_evidence_changed": False,
        "archive_content_digest": row["params"]["archive_content_digest"]}

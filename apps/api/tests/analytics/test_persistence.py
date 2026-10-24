"""No live Supabase calls: SDK simulation plus service failure/lineage tests."""

from copy import deepcopy
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.analytics.arr_generation import document_from_row
from app.analytics.config import AnalyticsConfig
from app.analytics.contracts import AnalyticalInput
from app.analytics.evidence_repository import RepositoryError, SupabaseEvidenceRepository
from app.analytics.provenance import content_hash
from app.analytics.repository import SupabaseAnalysisRepository, SupabaseARRReader
from app.analytics.service import AnalysisBundle, analyze_course, check_readiness, persist_analysis, retrieve_current_results
from app.analytics.statistics import analyze_statistics
from .test_contracts import fixture
from .test_features import uid


NOW = "2026-10-24T18:00:00Z"
COURSE = fixture()["ler"]["course_id"]
CONFIG = AnalyticsConfig(class_min_students=2)


class Query:
    def __init__(self, client, table):
        self.client, self.table = client, table
        self.mode, self.filters, self.ordering = "select", [], []
        self.columns, self.bounds, self.values = "*", None, None

    def select(self, columns):
        self.columns = columns
        return self

    def eq(self, key, value):
        self.filters.append((key, lambda item, v=value: item == v))
        return self

    def in_(self, key, values):
        self.filters.append((key, lambda item: item in values))
        return self

    def order(self, key):
        self.ordering.append(key)
        return self

    def range(self, first, last):
        self.bounds = (first, last)
        return self

    def upsert(self, values, on_conflict):
        self.mode, self.values, self.conflict = "upsert", values, on_conflict.split(",")
        return self

    def update(self, values):
        self.mode, self.values = "update", values
        return self

    def execute(self):
        self.client.calls.append((self.table, self.mode, self.columns, self.bounds))
        if self.client.fail_table == self.table and self.mode != "select":
            self.client.fail_table = None
            raise RuntimeError("fictional-private-upstream-error")
        rows = self.client.tables.setdefault(self.table, [])
        if self.mode == "upsert":
            values = self.values if isinstance(self.values, list) else [self.values]
            for value in values:
                previous = next((row for row in rows if all(row[k] == value[k] for k in self.conflict)), None)
                if previous is None:
                    rows.append(deepcopy(value))
                else:
                    previous.update(deepcopy(value))
            selected = values
        else:
            selected = [row for row in rows if all(predicate(row.get(key)) for key, predicate in self.filters)]
            # Deliberately simple RLS simulation, not a live policy verification.
            if self.client.learner_id is not None:
                if self.table == "analytics_runs":
                    selected = []
                elif self.table == "analytics_results":
                    selected = [r for r in selected if r.get("subject_learner_id") == self.client.learner_id]
            if self.mode == "update":
                for row in selected:
                    row.update(deepcopy(self.values))
            else:
                for key in reversed(self.ordering):
                    selected = sorted(selected, key=lambda row: str(row.get(key)))
                if self.bounds:
                    first, last = self.bounds
                    selected = selected[first:last + 1]
                if self.columns != "*":
                    output = []
                    for row in selected:
                        projected = {}
                        for expression in self.columns.split(","):
                            if ":" in expression:
                                alias, path = expression.split(":", 1)
                                column, prop = path.split("->", 1)
                                projected[alias] = row.get(column, {}).get(prop)
                            else:
                                projected[expression] = row.get(expression)
                        output.append(projected)
                    selected = output
        if self.client.after_query:
            self.client.after_query(self)
        return SimpleNamespace(data=deepcopy(selected))


class Client:
    def __init__(self, tables, learner_id=None):
        self.tables, self.learner_id = tables, learner_id
        self.calls, self.fail_table, self.after_query = [], None, None

    def table(self, name):
        return Query(self, name)


def database():
    data = {name: [] for name in (
        "lers", "learners", "responses", "questions", "attempts", "assessments", "practice_attempts",
        "ler_outcomes", "ler_errors", "ler_evidence", "ler_error_evidence", "question_outcomes",
        "evidence_refs", "outcomes", "analytics_runs", "analytics_results", "arr_ler_links",
    )}
    original = fixture()
    aid = original["ler"]["assessment_id"]
    oid = original["outcome_mappings"][0]["outcome_id"]
    data["assessments"] = [{"id": aid, "course_id": COURSE, "assessment_type": "exam"}]
    data["outcomes"] = [{"id": oid, "course_id": COURSE}]
    for student in range(2):
        lid, att = uid(300 + student), uid(400 + student)
        data["learners"].append({"id": lid, "course_id": COURSE})
        data["attempts"].append({"id": att, "course_id": COURSE, "learner_id": lid,
                                 "assessment_id": aid, "attempt_number": 1, "submitted_at": NOW})
        for question in range(2):
            number = 100 + student * 2 + question
            qid, rid, eid, error_id = uid(500 + question), uid(600 + number), uid(700 + number), uid(800 + number)
            ler = deepcopy(original["ler"])
            ler.update(id=uid(number), learner_id=lid, question_id=qid, response_id=rid, attempt_id=att)
            ler["payload"] = {"unapproved_text": "fictional private answer", "analytics_v1": {
                "schema_version": "1.0", "errors_analyzed": True, "error_outcomes": {error_id: [oid]},
            }}
            data["lers"].append(ler)
            data["responses"].append({"id": rid, "course_id": COURSE, "learner_id": lid,
                                       "attempt_id": att, "question_id": qid,
                                       "points_earned": 6 + question * 2 if student == 0 else 2 + question * 2,
                                       "response_text": "fictional private answer", "content_hash": f"grade-{number}", "updated_at": NOW})
            data["evidence_refs"].append({"id": eid, "course_id": COURSE, "learner_id": lid, "content_hash": f"ref-{number}"})
            data["ler_evidence"].append({"ler_id": ler["id"], "evidence_ref_id": eid, "role": "feedback"})
            if student == 0:
                data["ler_errors"].append({"id": error_id, "ler_id": ler["id"], "code": "inequality_direction", "instructor_status": "confirmed"})
                data["ler_error_evidence"].append({"ler_error_id": error_id, "evidence_ref_id": eid})
            if student == 0:
                data["questions"].append({"id": qid, "course_id": COURSE, "assessment_id": aid,
                                          "question_type": "rubric_question_part", "points_possible": 10})
                data["question_outcomes"].append({"question_id": qid, "outcome_id": oid, "weight": 1,
                                                   "provenance": "instructor", "needs_review": False})
    return data


def setup(config=CONFIG):
    client = Client(database())
    repo = SupabaseAnalysisRepository(client, page_size=1)
    bundle = analyze_course(repo, COURSE, config=config, run_id=uid(900), started_at=NOW, computed_at=NOW)
    return client, repo, bundle


def test_paginated_reader_assembles_join_and_avoids_private_text():
    client = Client(database())
    batch = SupabaseEvidenceRepository(client, page_size=1).load_course(UUID(COURSE))
    assert len(batch.envelopes) == 4
    assert "fictional private answer" not in batch.model_dump_json()
    assert batch.envelopes[0]["outcome_mappings"][0]["weight"] == 1
    assert batch.envelopes[0]["errors"][0]["outcome_ids"] == [database()["outcomes"][0]["id"]]
    assert any(table == "lers" and bounds == (4, 4) for table, _, _, bounds in client.calls)


def test_readiness_reports_real_eligibility_not_just_row_counts():
    client, repo, _ = setup()
    result = check_readiness(repo, COURSE)
    assert result.current_ler_count == result.validated_ler_count == 4
    assert result.selected_independent_scores == result.selected_mapped_scores == 4
    assert result.eligible_error_events == 2
    client.tables["lers"][0]["assistance_level"] = None
    assert check_readiness(repo, COURSE).selected_independent_scores == 3


def test_no_lers_is_a_valid_readiness_result_and_cannot_publish():
    client = Client(database())
    client.tables["lers"] = []
    repo = SupabaseAnalysisRepository(client)
    bundle = analyze_course(repo, COURSE)
    assert bundle.documents == []
    assert bundle.readiness.current_ler_count == 0
    with pytest.raises(ValueError, match="no analytical"):
        persist_analysis(repo, bundle, exclusive_course_access=True)


def test_missing_metadata_does_not_fabricate_error_free_denominator():
    client = Client(database())
    client.tables["lers"][0]["payload"] = {}
    batch = SupabaseEvidenceRepository(client).load_course(UUID(COURSE))
    assert batch.envelopes[0]["errors_analyzed"] is None
    assert "missing_analytics_metadata" in {issue.code for issue in batch.issues}


def test_missing_weight_is_flagged_not_replaced_by_confidence():
    client = Client(database())
    client.tables["question_outcomes"] = []
    for ler in client.tables["lers"]:
        client.tables["ler_outcomes"].append({"ler_id": ler["id"], "outcome_id": client.tables["outcomes"][0]["id"],
                                               "provenance": "ai", "needs_review": True, "confidence": 0.99})
    result = check_readiness(SupabaseEvidenceRepository(client), COURSE)
    assert result.selected_mapped_scores == 0
    assert result.issue_counts["missing_outcome_weight"] == 4


def test_wrong_evidence_owner_quarantines_join():
    client = Client(database())
    client.tables["evidence_refs"][0]["learner_id"] = uid(9999)
    result = check_readiness(SupabaseEvidenceRepository(client), COURSE)
    assert result.validated_ler_count == 3
    assert result.issue_counts["invalid_evidence_ownership"] == 1


def test_dry_run_generates_typed_evidence_linked_arrs_without_writes():
    client, _, bundle = setup()
    assert all(mode == "select" for _, mode, _, _ in client.calls)
    assert len(bundle.documents) == 5  # 2 students + 1 class outcome + 2 questions
    student = next(d for d in bundle.documents if d.scope == "student_outcome" and str(d.subject_learner_id) == uid(300))
    assert student.metrics.observed_score_ratio == 0.7
    assert student.numerator == 14 and student.denominator == 20
    aggregate = next(d for d in bundle.documents if d.scope == "class_outcome")
    assert aggregate.metrics.mean_student_ratio == 0.5
    assert aggregate.numerator == 1 and aggregate.denominator == 2
    assert bundle.input_snapshot == content_hash(bundle.manifest)
    assert "fictional private answer" not in bundle.model_dump_json()


def test_snapshot_can_replay_frozen_statistical_inputs():
    _, _, bundle = setup()
    records = [AnalyticalInput.model_validate(row) for row in bundle.manifest["records"]]
    result = analyze_statistics(records, CONFIG)
    assert result.student_outcomes == [d.metrics for d in sorted(
        (d for d in bundle.documents if d.scope == "student_outcome"), key=lambda d: str(d.subject_learner_id)
    )]


def test_all_arrs_roundtrip_and_column_mismatch_rejected():
    _, _, bundle = setup()
    for doc in bundle.documents:
        row = doc.database_row()
        assert document_from_row(row) == doc
        row["course_id"] = uid(12345)
        with pytest.raises(ValueError):
            document_from_row(row)


def test_suppressed_arr_has_no_counts_or_lineage():
    _, _, bundle = setup(AnalyticsConfig())
    aggregates = [d for d in bundle.documents if d.scope != "student_outcome"]
    assert all(d.interpretation_limits.suppressed for d in aggregates)
    assert all(not d.dependency_ler_ids and not d.evidence_ler_ids for d in aggregates)
    bad = aggregates[0].model_dump()
    bad["metrics"]["assessed_student_count"] = 2
    with pytest.raises(ValidationError):
        type(aggregates[0]).model_validate(bad)


def test_source_score_mapping_and_config_changes_change_snapshot():
    client, repo, original = setup()
    client.tables["responses"][0]["points_earned"] = 5
    changed = analyze_course(repo, COURSE, config=CONFIG, run_id=uid(900), started_at=NOW, computed_at=NOW)
    assert changed.input_snapshot != original.input_snapshot
    client.tables["question_outcomes"][0]["weight"] = 2
    changed_weight = analyze_course(repo, COURSE, config=CONFIG, run_id=uid(900), started_at=NOW, computed_at=NOW)
    assert changed_weight.input_snapshot != changed.input_snapshot


def test_completed_run_is_idempotent_and_new_run_preserves_history():
    client, repo, bundle = setup()
    assert persist_analysis(repo, bundle, exclusive_course_access=True) == "completed"
    assert persist_analysis(repo, bundle, exclusive_course_access=True) == "already_completed"
    assert len(client.tables["analytics_runs"]) == 1 and len(client.tables["analytics_results"]) == 5
    new_run = analyze_course(repo, COURSE, config=CONFIG, run_id=uid(901), started_at=NOW, computed_at=NOW)
    assert new_run.input_snapshot == bundle.input_snapshot
    persist_analysis(repo, new_run, exclusive_course_access=True)
    assert len(client.tables["analytics_runs"]) == 2 and len(client.tables["analytics_results"]) == 10


def test_run_id_cannot_overwrite_completed_different_content():
    client, repo, bundle = setup()
    persist_analysis(repo, bundle, exclusive_course_access=True)
    client.tables["responses"][0]["points_earned"] = 3
    changed = analyze_course(repo, COURSE, config=CONFIG, run_id=bundle.run_id, started_at=NOW, computed_at=NOW)
    with pytest.raises(ValueError, match="different analytical"):
        persist_analysis(repo, changed, exclusive_course_access=True)


def test_partial_failure_keeps_arrs_stale_and_retry_repairs_without_duplicates():
    client, repo, bundle = setup()
    client.fail_table = "arr_ler_links"
    with pytest.raises(RepositoryError, match="^lineage_write_failed$"):
        persist_analysis(repo, bundle, exclusive_course_access=True)
    assert all(row["is_stale"] for row in client.tables["analytics_results"])
    assert client.tables["analytics_runs"][0]["params"]["status"] == "failed"
    assert "fictional-private" not in json.dumps(client.tables["analytics_runs"])
    assert persist_analysis(repo, bundle, exclusive_course_access=True) == "completed"
    assert len(client.tables["analytics_results"]) == 5
    assert client.tables["analytics_runs"][0]["params"]["attempts"] == 2


def test_source_change_before_publication_writes_nothing():
    client, repo, bundle = setup()
    client.tables["questions"][0]["points_possible"] = 20
    with pytest.raises(RepositoryError, match="source_changed_before"):
        persist_analysis(repo, bundle, exclusive_course_access=True)
    assert client.tables["analytics_runs"] == client.tables["analytics_results"] == []


def test_source_change_after_publish_is_detected_and_restaled():
    client, repo, bundle = setup()
    def mutate(query):
        if query.table == "analytics_results" and query.mode == "update" and query.values["is_stale"] is False:
            client.tables["responses"][0]["points_earned"] = 0
            client.after_query = None
    client.after_query = mutate
    with pytest.raises(RepositoryError, match="source_changed_during"):
        persist_analysis(repo, bundle, exclusive_course_access=True)
    assert all(row["is_stale"] for row in client.tables["analytics_results"])


def test_retrieval_applies_user_read_scope_and_checks_source_freshness():
    client, repo, bundle = setup()
    persist_analysis(repo, bundle, exclusive_course_access=True)
    user = SupabaseARRReader(Client(client.tables, learner_id=uid(300)))
    documents = retrieve_current_results(repo, user, COURSE, bundle.run_id)
    assert len(documents) == 1 and str(documents[0].subject_learner_id) == uid(300)
    client.tables["question_outcomes"][0]["weight"] = 3  # not covered by existing grade triggers
    with pytest.raises(RepositoryError, match="analysis_run_is_stale"):
        retrieve_current_results(repo, user, COURSE, bundle.run_id)


def test_stale_rows_and_unfinished_runs_not_retrieved():
    client, repo, bundle = setup()
    persist_analysis(repo, bundle, exclusive_course_access=True)
    reader = SupabaseARRReader(client)
    repo.set_stale(bundle.run_id, True)
    assert retrieve_current_results(repo, reader, COURSE, bundle.run_id) == []
    repo.set_stale(bundle.run_id, False)
    client.tables["analytics_runs"][0]["params"]["status"] = "failed"
    assert retrieve_current_results(repo, reader, COURSE, bundle.run_id) == []


def test_serialization_attestation_is_required():
    _, repo, bundle = setup()
    with pytest.raises(ValueError, match="exclusive course"):
        persist_analysis(repo, bundle)


def test_cross_learner_lineage_cannot_be_published():
    _, repo, bundle = setup()
    student = next(d for d in bundle.documents if d.scope == "student_outcome")
    other = next(d for d in bundle.documents if d.scope == "student_outcome" and d.subject_learner_id != student.subject_learner_id)
    student.dependency_ler_ids.append(other.dependency_ler_ids[0])
    with pytest.raises(ValidationError, match="cross-course or cross-learner"):
        persist_analysis(repo, bundle, exclusive_course_access=True)


def test_manifest_is_immutable_for_publication():
    _, repo, bundle = setup()
    bundle.manifest["configuration"]["observed_performance_threshold"] = 0.99
    with pytest.raises(ValidationError, match="snapshot manifest changed"):
        persist_analysis(repo, bundle, exclusive_course_access=True)


def test_metadata_namespace_does_not_copy_unknown_text():
    client = Client(database())
    client.tables["lers"][0]["payload"]["analytics_v1"]["unapproved_notes"] = "fictional private note"
    batch = SupabaseEvidenceRepository(client).load_course(UUID(COURSE))
    assert "fictional private note" not in batch.model_dump_json()


def test_missing_join_is_reported_and_quarantined():
    client = Client(database())
    client.tables["responses"].pop(0)
    report = check_readiness(SupabaseEvidenceRepository(client), COURSE)
    assert report.validated_ler_count == 3
    assert report.issue_counts["missing_referenced_response"] == 1


def test_invalid_error_association_is_not_inferred():
    client = Client(database())
    first = client.tables["lers"][0]
    first["payload"]["analytics_v1"]["error_outcomes"] = {uid(900): {"invalid": "shape"}}
    # Use the actual error ID to exercise malformed JSON, not a missing key.
    error_id = client.tables["ler_errors"][0]["id"]
    first["payload"]["analytics_v1"]["error_outcomes"][error_id] = [{"bad": "value"}]
    batch = SupabaseEvidenceRepository(client).load_course(UUID(COURSE))
    assert batch.envelopes[0]["errors"][0]["outcome_ids"] == []
    assert "invalid_error_outcome_attribution" in {issue.code for issue in batch.issues}


def test_practice_source_hints_cannot_be_labeled_independent():
    client = Client(database())
    first = client.tables["lers"][0]
    first.update(assessment_origin="generated_practice", practice_attempt_id=uid(7777),
                 assessment_id=None, question_id=None, response_id=None, attempt_id=None)
    client.tables["practice_attempts"].append({
        "id": uid(7777), "course_id": COURSE, "learner_id": first["learner_id"],
        "created_at": NOW, "hints_used": 3, "assistance_level": "assisted", "independent_correctness": None,
    })
    report = check_readiness(SupabaseEvidenceRepository(client), COURSE)
    assert report.validated_ler_count == 3
    assert report.issue_counts["conflicting_practice_assistance"] == 1


def test_excluded_candidate_dependencies_preserved_for_stale_propagation():
    client, repo, _ = setup()
    client.tables["responses"][0]["points_earned"] = None
    bundle = analyze_course(repo, COURSE, config=CONFIG, run_id=uid(900), started_at=NOW, computed_at=NOW)
    student = next(d for d in bundle.documents if str(d.subject_learner_id) == uid(300))
    excluded = UUID(client.tables["lers"][0]["id"])
    assert excluded not in student.evidence_sets.score_ler_ids
    assert excluded in student.dependency_ler_ids


def test_cluster_outputs_and_noise_are_preserved_when_requested():
    from app.analytics.text_preparation import ApprovedErrorText
    client, repo, _ = setup()
    excerpt = ApprovedErrorText(
        ler_id=client.tables["lers"][0]["id"], error_code="inequality_direction",
        text="A fictional inequality direction mistake.", source_kind="error_description",
        evidence_ref_ids=[client.tables["evidence_refs"][0]["id"]], privacy_reviewed=True,
    )
    bundle = analyze_course(repo, COURSE, config=CONFIG, run_id=uid(900), started_at=NOW,
                            computed_at=NOW, cluster=True, approved_excerpts=[excerpt])
    assert bundle.clustering_report["partitions"][0]["status"] == "insufficient_data"
    assert bundle.clustering_report["partitions"][0]["unassigned_count"] == 1
    assert len(bundle.documents) == 5  # no fabricated cluster ARR


def test_cli_offline_dry_run_never_initializes_supabase(monkeypatch, capsys):
    from pathlib import Path
    from app.analytics.cli import main
    from app.analytics import supabase_clients
    contents = json.dumps([fixture()])
    original_read = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda path, *args, **kwargs:
                        contents if path.name == "fictional.json" else original_read(path, *args, **kwargs))
    def forbidden():
        raise AssertionError("offline CLI must not initialize a Supabase client")
    monkeypatch.setattr(supabase_clients, "create_pipeline_client", forbidden)
    assert main(["analyze", "--course", COURSE, "--input", "fictional.json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["persisted"] is False
    assert output["readiness"]["validated_ler_count"] == 1
    assert "arr_count" in output


def test_cli_rejects_offline_bundle_publication_before_client_init(monkeypatch, capsys):
    from pathlib import Path
    from app.analytics.cli import main
    from app.analytics import supabase_clients
    _, _, bundle = setup()
    bundle.source_kind = "offline_fixture"
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: bundle.model_dump_json())
    def forbidden():
        raise AssertionError("must reject offline publication before initializing a client")
    monkeypatch.setattr(supabase_clients, "create_pipeline_client", forbidden)
    assert main(["publish", "--bundle", "fictional.json", "--exclusive-course-access"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_input_or_unavailable_configuration"


def test_real_sdk_clients_construct_without_network_and_use_separate_credentials(monkeypatch):
    pytest.importorskip("supabase")
    import dotenv
    from app.analytics.supabase_clients import create_pipeline_client, create_user_client
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("SUPABASE_URL", "https://unit-test.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_fictional")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_fictional")
    pipeline = create_pipeline_client()
    user_a, user_b = create_user_client("fictional-session-a"), create_user_client("fictional-session-b")
    assert pipeline.supabase_key == "sb_secret_fictional"
    assert user_a.supabase_key == "sb_publishable_fictional"
    assert user_a.postgrest.headers["Authorization"] == "Bearer fictional-session-a"
    assert user_b.postgrest.headers["Authorization"] == "Bearer fictional-session-b"
    assert pipeline.options.persist_session is False and pipeline.options.auto_refresh_token is False


@pytest.mark.parametrize("placeholder", ["", "YOUR-SECRET-KEY", "REPLACE_ME"])
def test_secret_placeholder_rejected_without_echo(monkeypatch, placeholder):
    from app.analytics.supabase_clients import _required
    monkeypatch.setenv("SUPABASE_SECRET_KEY", placeholder)
    with pytest.raises(RuntimeError, match="Configure SUPABASE_SECRET_KEY"):
        _required("SUPABASE_SECRET_KEY")


def test_user_session_required_before_loading_env():
    from app.analytics.supabase_clients import create_user_client
    with pytest.raises(ValueError, match="logged-in"):
        create_user_client("")


def test_generated_student_ratio_must_match_frozen_points():
    _, _, bundle = setup()
    student = next(doc for doc in bundle.documents if doc.scope == "student_outcome")
    student.metrics.observed_score_ratio = 0.99
    with pytest.raises(ValidationError, match="ratio differs"):
        AnalysisBundle.model_validate_json(bundle.model_dump_json())


def test_cluster_arr_generation_and_privacy_policy():
    from app.analytics.evidence_repository import EvidenceBatch
    from .test_clustering import FixtureEmbedder, source
    records, excerpts = source()
    envelopes = []
    for record in records:
        envelope = fixture()
        values = record.model_dump(mode="json")
        for key in list(envelope["ler"]):
            if key in values:
                envelope["ler"][key] = values[key]
        envelope["ler"]["id"] = str(record.ler_id)
        envelope["response"].update(id=str(record.response_id), points_earned=str(record.points_earned))
        envelope["question"].update(id=str(record.question_id), points_possible=str(record.points_possible))
        envelope["attempt"].update(id=str(record.attempt_id), attempt_number=record.attempt_number)
        envelope["errors"] = [error.model_dump(mode="json") for error in record.errors]
        envelopes.append(envelope)
    batch = EvidenceBatch(course_id=COURSE, envelopes=envelopes)
    class Source:
        def load_course(self, course_id):
            return batch.model_copy(deep=True)
    bundle = analyze_course(Source(), COURSE, config=AnalyticsConfig(suppress_small_cohorts=False),
                            cluster=True, approved_excerpts=excerpts, embedder=FixtureEmbedder(),
                            run_id=uid(900), started_at=NOW, computed_at=NOW)
    groups = [doc for doc in bundle.documents if doc.scope == "misconception_cluster"]
    assert len(groups) == 2
    assert all(len(doc.evidence_ler_ids) == doc.metrics.group.evidence_observation_count == 3 for doc in groups)
    assert bundle.clustering_report["partitions"][0]["noise_count"] == 1
    for doc in groups:
        assert document_from_row(doc.database_row()) == doc
    suppressed = analyze_course(Source(), COURSE, cluster=True, approved_excerpts=excerpts,
                                 embedder=FixtureEmbedder(), run_id=uid(901), started_at=NOW, computed_at=NOW)
    assert not any(doc.scope == "misconception_cluster" for doc in suppressed.documents)
    assert len(suppressed.clustering_report["partitions"][0]["groups"]) == 2


def test_actual_sdk_user_reader_sends_jwt_and_only_read_requests():
    pytest.importorskip("supabase")
    import httpx
    from supabase import create_client
    from supabase.lib.client_options import SyncClientOptions
    _, _, bundle = setup()
    document = next(doc for doc in bundle.documents if str(doc.subject_learner_id) == uid(300))
    requests = []
    def respond(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer fictional-user-jwt"
        assert request.headers["apikey"] == "sb_publishable_fictional"
        assert request.url.params["is_stale"] == "eq.false"
        assert request.url.params["schema_version"] == "eq.1.1"
        return httpx.Response(200, json=[document.database_row(is_stale=False)])
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = create_client("https://unit-test.supabase.co", "sb_publishable_fictional",
                               options=SyncClientOptions(httpx_client=transport, auto_refresh_token=False, persist_session=False))
        client.postgrest.auth("fictional-user-jwt")
        output = SupabaseARRReader(client).read_published(COURSE, bundle.run_id)
        assert output == [document]
    assert len(requests) == 1

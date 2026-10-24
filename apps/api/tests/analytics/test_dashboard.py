"""HTTP and display integration against fictional evidence; not a live RLS test."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.analytics.config import AnalyticsConfig
from app.analytics.dashboard import load_dashboard
from app.analytics.service import analyze_course, persist_analysis
from app.analytics.repository import SupabaseAnalysisRepository
from app.analytics import supabase_clients
from app.routers import analytics
from .test_persistence import COURSE, CONFIG, Client as FakeClient, database as source_tables
from .test_features import uid

USER = uid(900)
LEARNER = uid(300)
PATH = f"/api/analytics/courses/{COURSE}"
AUTH = {"Authorization": "Bearer fictional-user-token"}


@pytest.fixture
def published(monkeypatch):
    sdk = FakeClient(source_tables())
    sdk.tables["courses"] = [{"id": COURSE, "code": "TEST101", "title": "Fictional course", "canvas_id": "1"}]
    sdk.tables["enrollments"] = [{"course_id": COURSE, "user_id": USER, "role": "instructor"}]
    sdk.tables["learner_identities"] = [{"course_id": COURSE, "user_id": USER, "learner_id": LEARNER}]
    sdk.tables["outcomes"][0]["code"] = "LO-1"
    for index, row in enumerate(sdk.tables["questions"]):
        row["code"] = f"Q{index + 1}"
    sdk.auth = SimpleNamespace(get_user=lambda token: SimpleNamespace(user=SimpleNamespace(id=USER)))
    repo = SupabaseAnalysisRepository(sdk)
    bundle = analyze_course(repo, UUID(COURSE), config=CONFIG)
    persist_analysis(repo, bundle, exclusive_course_access=True)
    monkeypatch.setattr(supabase_clients, "create_user_client", lambda token: sdk)
    monkeypatch.setattr(analytics, "control_repository", lambda: repo)
    return sdk, repo, bundle


@pytest.mark.parametrize("path", ["/api/analytics/courses", PATH + "/summary", PATH + "/my-results"])
def test_demo_header_does_not_authorize_supabase(client, path):
    response = client.get(path, headers={"X-Demo-User": "1"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_never_reaches_privileged_repository(client, published, monkeypatch):
    sdk, _, _ = published
    def reject(token):
        raise ValueError("fictional-secret-diagnostic")
    sdk.auth.get_user = reject
    monkeypatch.setattr(analytics, "control_repository", lambda: pytest.fail("privileged access"))
    response = client.get(PATH + "/summary", headers=AUTH)
    assert response.status_code == 401
    assert "fictional-secret" not in response.text


@pytest.mark.parametrize("role", ["student", "unrecognized"])
def test_staff_endpoint_requires_actual_supabase_staff(client, published, monkeypatch, role):
    sdk, _, _ = published
    sdk.tables["enrollments"][0]["role"] = role
    monkeypatch.setattr(analytics, "control_repository", lambda: pytest.fail("privileged access"))
    assert client.get(PATH + "/summary", headers=AUTH | {"X-Demo-User": "1"}).status_code == 403


def test_unenrolled_user_denied_before_control_access(client, published, monkeypatch):
    sdk, _, _ = published
    sdk.tables["enrollments"] = []
    monkeypatch.setattr(analytics, "control_repository", lambda: pytest.fail("privileged access"))
    assert client.get(PATH + "/summary", headers=AUTH).status_code == 403
    assert client.get("/api/analytics/courses", headers=AUTH).json() == []


def test_course_discovery_uses_verified_identity(client, published):
    sdk, _, _ = published
    sdk.tables["enrollments"].append({"course_id": uid(999), "user_id": uid(998), "role": "instructor"})
    response = client.get("/api/analytics/courses", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == [{"id": COURSE, "code": "TEST101", "title": "Fictional course", "canvas_id": "1", "role": "instructor"}]


@pytest.mark.parametrize("role", ["instructor", "ta"])
def test_staff_gets_display_fields_without_private_lineage(client, published, role):
    sdk, _, bundle = published
    sdk.tables["enrollments"][0]["role"] = role
    response = client.get(PATH + "/summary", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready" and body["run_id"] == str(bundle.run_id)
    assert response.headers["cache-control"] == "no-store"
    assert len(body["performance"]) == 3
    assert {row["scope"] for row in body["performance"]} == {"class_outcome", "assessment_question"}
    outcome = next(row for row in body["performance"] if row["scope"] == "class_outcome")
    assert outcome["label"] == "LO-1" and outcome["mean_student_ratio"] == pytest.approx(.5)
    assert outcome["eligible_students"] == 2
    assert outcome["evidence_count"] == 4
    for private in ("manifest", "dependency_ler_ids", "evidence_ler_ids", "learner_id", "fictional private answer", "source_fingerprint"):
        assert private not in response.text


def test_student_identity_cannot_be_overridden_by_query(client, published, monkeypatch):
    sdk, _, bundle = published
    sdk.tables["enrollments"][0]["role"] = "student"
    user_sdk = FakeClient(sdk.tables, learner_id=LEARNER)
    user_sdk.auth = sdk.auth
    monkeypatch.setattr(supabase_clients, "create_user_client", lambda token: user_sdk)
    response = client.get(PATH + "/my-results?learner_id=" + uid(301), headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert len(body["performance"]) == 1
    row = body["performance"][0]
    assert row["scope"] == "student_outcome" and row["observed_score_ratio"] == pytest.approx(.7)
    assert row["score_observations"] == 2 and row["mean_student_ratio"] is None
    assert not body["clusters"] and uid(301) not in response.text


def test_missing_student_identity_is_not_guessed(client, published):
    sdk, _, _ = published
    sdk.tables["learner_identities"] = []
    assert client.get(PATH + "/my-results", headers=AUTH).status_code == 404


def test_no_visible_results_never_load_private_metadata(client, published, monkeypatch):
    sdk, _, _ = published
    sdk.tables["analytics_results"] = []
    monkeypatch.setattr(analytics, "control_repository", lambda: pytest.fail("privileged access"))
    response = client.get(PATH + "/summary", headers=AUTH)
    assert response.json()["status"] == "no_results"
    assert response.json()["run_id"] is None


@pytest.mark.parametrize("change,expected", [("grade", "stale"), ("flag", "stale"), ("incomplete", "incomplete")])
def test_unavailable_runs_never_return_metrics(client, published, change, expected):
    sdk, _, _ = published
    if change == "grade":
        sdk.tables["responses"][0]["points_earned"] = 0
    elif change == "flag":
        sdk.tables["analytics_results"][0]["is_stale"] = True
    else:
        sdk.tables["analytics_runs"][0]["params"]["status"] = "publishing"
    body = client.get(PATH + "/summary", headers=AUTH).json()
    assert body["status"] == expected
    assert body["performance"] == [] and body["clusters"] == []


def test_newest_stale_run_does_not_fall_back_to_old(client, published):
    sdk, repo, old = published
    newer = analyze_course(repo, UUID(COURSE), config=CONFIG)
    persist_analysis(repo, newer, exclusive_course_access=True)
    repo.set_stale(newer.run_id, True)
    body = client.get(PATH + "/summary", headers=AUTH).json()
    assert body["run_id"] == str(newer.run_id) and body["status"] == "stale"
    history = client.get(PATH + "/summary?run_id=" + str(old.run_id), headers=AUTH).json()
    assert history["run_id"] == str(old.run_id) and history["status"] == "ready"


def test_small_cohort_dto_preserves_suppression(client, published):
    sdk, repo, _ = published
    bundle = analyze_course(repo, UUID(COURSE))  # Default minimum is 5; dataset has 2 students.
    persist_analysis(repo, bundle, exclusive_course_access=True)
    body = client.get(PATH + "/summary", headers=AUTH).json()
    assert body["status"] == "insufficient_evidence"
    for row in body["performance"]:
        assert row["suppressed"]
        assert all(row[key] is None for key in (
            "evidence_count", "eligible_students", "assessed_students", "mean_student_ratio", "pooled_score_ratio",
        ))


def test_distinct_average_and_pooled_values_are_not_recomputed(client, published):
    sdk, repo, _ = published
    sdk.tables["responses"][-1]["points_earned"] = None
    bundle = analyze_course(repo, UUID(COURSE), config=AnalyticsConfig(class_min_students=2, student_min_questions=1))
    persist_analysis(repo, bundle, exclusive_course_access=True)
    body = client.get(PATH + "/summary", headers=AUTH).json()
    outcome = next(row for row in body["performance"] if row["scope"] == "class_outcome")
    assert outcome["mean_student_ratio"] == pytest.approx(.45)
    assert outcome["pooled_score_ratio"] == pytest.approx(16 / 30)


def test_repository_error_is_sanitized(client, published, monkeypatch):
    from app.analytics.evidence_repository import RepositoryError
    monkeypatch.setattr(analytics, "load_dashboard", lambda *args, **kwargs: (_ for _ in ()).throw(RepositoryError("private-diagnostic")))
    response = client.get(PATH + "/summary", headers=AUTH)
    assert response.status_code == 503 and "private-diagnostic" not in response.text


def test_mid_read_stale_flag_blocks_output(published):
    sdk, repo, bundle = published
    original = repo.load_course
    def invalidate(course):
        data = original(course)
        repo.set_stale(bundle.run_id, True)
        return data
    repo.load_course = invalidate
    result = load_dashboard(sdk, lambda: repo, UUID(COURSE))
    assert result.status == "stale" and result.performance == []

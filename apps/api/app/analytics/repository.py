"""Staged, retryable storage using existing Supabase tables; no schema changes."""

from uuid import UUID

from .arr_generation import document_from_row
from .evidence_repository import RepositoryError, SupabaseEvidenceRepository, read_pages


class SupabaseAnalysisRepository(SupabaseEvidenceRepository):
    def get_run(self, run_id):
        rows = read_pages(self.client, "analytics_runs", "*", filters={"id": str(UUID(str(run_id)))})
        return rows[0] if rows else None

    def write_run(self, row):
        try:
            self.client.table("analytics_runs").upsert(row, on_conflict="id").execute()
        except Exception:
            raise RepositoryError("run_write_failed") from None

    def stage_documents(self, documents):
        rows = [document.database_row(is_stale=True) for document in documents]
        try:
            for start in range(0, len(rows), 100):
                self.client.table("analytics_results").upsert(rows[start:start + 100], on_conflict="id").execute()
        except Exception:
            raise RepositoryError("arr_write_failed") from None

    def write_links(self, documents):
        links = [{"arr_id": str(document.id), "ler_id": str(ler_id)}
                 for document in documents for ler_id in document.dependency_ler_ids]
        try:
            for start in range(0, len(links), 100):
                self.client.table("arr_ler_links").upsert(
                    links[start:start + 100], on_conflict="arr_id,ler_id",
                ).execute()
        except Exception:
            raise RepositoryError("lineage_write_failed") from None

    def verify_staged(self, run_id, documents):
        rows = read_pages(self.client, "analytics_results", "*", filters={"run_id": str(run_id)})
        expected = {str(document.id): document for document in documents}
        if {row["id"] for row in rows} != set(expected):
            raise RepositoryError("incomplete_arr_set")
        for row in rows:
            if row.get("is_stale") is not True:
                raise RepositoryError("arr_not_staged")
            if document_from_row(row) != expected[row["id"]]:
                raise RepositoryError("stored_arr_mismatch")
        links = []
        ids = sorted(expected)
        for start in range(0, len(ids), 100):
            links.extend(read_pages(self.client, "arr_ler_links", "arr_id,ler_id",
                                    in_filter=("arr_id", ids[start:start + 100]), order=("arr_id", "ler_id")))
        actual = {(row["arr_id"], row["ler_id"]) for row in links}
        required = {(str(document.id), str(lid)) for document in documents for lid in document.dependency_ler_ids}
        if actual != required:
            raise RepositoryError("incomplete_lineage")

    def set_stale(self, run_id, stale):
        try:
            self.client.table("analytics_results").update({"is_stale": stale}).eq("run_id", str(run_id)).execute()
        except Exception:
            raise RepositoryError("publication_update_failed") from None


class SupabaseARRReader:
    """Read-only methods. Construct with create_user_client(jwt), never service credentials."""

    def __init__(self, user_client):
        self.client = user_client

    def read_published(self, course_id, run_id, *, scope=None, learner_id=None):
        filters = {"course_id": str(UUID(str(course_id))), "run_id": str(UUID(str(run_id))),
                   "is_stale": False, "schema_version": "1.1"}
        if scope is not None:
            if scope not in ("student_outcome", "class_outcome", "assessment_question", "misconception_cluster"):
                raise ValueError("unsupported ARR scope")
            filters["scope"] = scope
        if learner_id is not None:
            filters["subject_learner_id"] = str(UUID(str(learner_id)))
        rows = read_pages(self.client, "analytics_results", "*", filters=filters)
        try:
            return [document_from_row(row) for row in rows]
        except (KeyError, TypeError, ValueError):
            raise RepositoryError("invalid_stored_arr") from None

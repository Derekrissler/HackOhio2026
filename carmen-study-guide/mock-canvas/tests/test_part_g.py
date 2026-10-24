from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

MOCK_CANVAS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOCK_CANVAS))
import db_store
import ingest


class ApiAndExportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(MOCK_CANVAS) + os.pathsep + env.get("PYTHONPATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "error"],
            cwd=MOCK_CANVAS, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if cls.proc.poll() is not None:
                raise RuntimeError("Temporary Carmen integration server exited before becoming ready")
            try:
                if requests.get(f"{cls.base}/docs", timeout=0.5).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.1)
        else:
            cls.proc.terminate()
            raise RuntimeError("Temporary Carmen integration server did not start")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "proc", None) and cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)

    @staticmethod
    def headers(token):
        return {"Authorization": f"Bearer {token}"}

    def paged(self, path, token, per_page=4):
        url, params = f"{self.base}{path}", {"per_page": per_page}
        result, sizes = [], []
        while url:
            response = requests.get(url, params=params, headers=self.headers(token), timeout=5)
            self.assertEqual(response.status_code, 200, response.text)
            page = response.json()
            self.assertIsInstance(page, list)
            result.extend(page)
            sizes.append(len(page))
            url, params = response.links.get("next", {}).get("url"), None
        return result, sizes

    def test_bearer_auth_and_student_scope(self):
        path = "/api/v1/courses/1001/assignments/2101/submissions"
        self.assertEqual(requests.get(self.base + path, timeout=5).status_code, 401)
        self.assertEqual(requests.get(self.base + path,
                                      headers={"Authorization": "student-5001"}, timeout=5).status_code, 401)
        self.assertEqual(requests.get(self.base + path,
                                      headers=self.headers("unknown"), timeout=5).status_code, 401)

        roster, sizes = self.paged("/api/v1/courses/1001/users?enrollment_type%5B%5D=student", "dev")
        self.assertEqual(len(roster), 15)
        self.assertTrue(all(size <= 4 for size in sizes))
        self.assertEqual(requests.get(self.base + "/api/v1/courses/1001/users",
                                      headers=self.headers("student-5001"), timeout=5).status_code, 403)
        self.assertEqual(requests.get(self.base + path,
                                      headers=self.headers("student-5001"), timeout=5).status_code, 403)

        own = requests.get(self.base + path + "/self", headers=self.headers("student-5001"), timeout=5)
        self.assertEqual(own.status_code, 200, own.text)
        self.assertEqual(own.json()["user_id"], 5001)
        self.assertNotIn("correct_answer_index", own.json()["quiz_responses"][0])
        another_student = requests.get(self.base + path + "/self", headers=self.headers("student-5002"), timeout=5)
        self.assertEqual(another_student.json()["user_id"], 5002)
        self.assertEqual(requests.get(self.base + "/api/v1/courses", headers=self.headers("dev"),
                                      timeout=5).status_code, 200)
        student_courses = requests.get(self.base + "/api/v1/courses", headers=self.headers("student-5001"),
                                       timeout=5)
        self.assertEqual([course["id"] for course in student_courses.json()], [1001])

    def test_teacher_pagination_and_quiz_reviews(self):
        item_count = 0
        for assignment_id in (2101, 2102, 2103):
            submissions, _ = self.paged(
                f"/api/v1/courses/1001/assignments/{assignment_id}/submissions", "dev")
            self.assertEqual(len(submissions), 15)
            for submission in submissions:
                items = submission["quiz_responses"]
                self.assertEqual(len(items), 10)
                self.assertTrue(all("correct_answer_index" in item for item in items
                                    if item["answer_index"] is not None))
                self.assertAlmostEqual(sum(item["points_earned"] or 0 for item in items), submission["score"])
                item_count += len(items)
        self.assertEqual(item_count, 450)

    def test_export_contract_evidence_reproducibility_and_student_scope(self):
        with tempfile.TemporaryDirectory(prefix="carmen-export-") as export_root:
            old_exports = ingest.EXPORTS
            ingest.EXPORTS = Path(export_root)
            try:
                bundle, path = ingest.export_course(self.base, "dev", "1001")
                repeated, _ = ingest.export_course(self.base, "dev", "1001")
                self.assertTrue(path.is_file())
                self.assertEqual(bundle["schema_version"], "ingest-1.1")
                self.assertEqual(bundle["quality"]["scope"], "instructor")
                self.assertEqual(bundle["quality"]["counts"]["students"], 15)
                self.assertEqual(bundle["quality"]["counts"]["question_responses"], 450)
                self.assertEqual(bundle["export"]["content_hash"], repeated["export"]["content_hash"])
                self.assertNotEqual(bundle["export"]["export_id"], repeated["export"]["export_id"])
                evidence_ids = {e["id"] for e in bundle["evidence_refs"]}
                items = [item for sub in bundle["submissions"] for item in sub["question_responses"]]
                self.assertTrue(all(item["evidence_ref_id"] in evidence_ids for item in items))
                self.assertTrue(all(item["correct_answer"]["access_roles"] == ["instructor"]
                                    for item in items if "correct_answer" in item))
                self.assertTrue(all("correct_answer" not in chunk for chunk in bundle["resource_chunks"]))

                student, _ = ingest.export_course(self.base, "student-5001", "1001")
                self.assertEqual(student["quality"]["scope"], "self_only")
                self.assertEqual(len(student["students"]), 1)
                self.assertTrue(all("correct_answer" not in item for sub in student["submissions"]
                                    for item in sub["question_responses"]))
            finally:
                ingest.EXPORTS = old_exports


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.name, self.rows = db, table, []
        self.mode, self.filters = "upsert", []

    def select(self, _columns):
        self.mode = "select"
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def upsert(self, rows, on_conflict):
        self.mode = "upsert"
        self.rows = [dict(row) for row in rows]
        return self

    def insert(self, rows):
        self.mode = "insert"
        self.rows = [dict(row) for row in rows]
        return self

    def execute(self):
        if self.mode == "select":
            rows = self.db.tables.get(self.name, [])
            for column, value in self.filters:
                rows = [row for row in rows if row.get(column) == value]
            return type("Result", (), {"data": rows})()
        saved = []
        for row in self.rows:
            row.setdefault("id", f"{self.name}-{len(self.db.tables.get(self.name, [])) + 1}")
            self.db.tables.setdefault(self.name, []).append(row)
            saved.append(row)
        return type("Result", (), {"data": saved})()


class FakeDatabase:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return FakeQuery(self, name)


class StoreMappingTests(unittest.TestCase):
    @staticmethod
    def sample_bundle(scope):
        return {
            "quality": {"scope": scope},
            "export": {"source": {"base_url": "http://localhost:8001"}},
            "evidence_refs": [{"id": "EV-0001", "source_type": "canvas_quiz_response",
                               "api_path": "/quiz/2101/submissions",
                               "canvas_ids": {"submission_id": 98765, "question_id": "Q-2101-01",
                                              "attempt_id": "1"},
                               "excerpt": "Question response excerpt", "content_hash": "sha256:abc123"}],
            "assessments": [{"assessment_id": "A-2101", "canvas_id": 2101, "name": "Quiz 1",
                             "type": "quiz", "points_possible": 2, "description_text": "Question 1",
                             "source_ref": {"api_path": "/quiz/2101"}, "rubric": [],
                             "stated_outcome_ids": []}],
            "students": [{"student_id": "S-5001"}],
            "submissions": [{"assessment_id": "A-2101", "student_id": "S-5001", "attempt_id": "1",
                              "canvas_id": 98765, "submitted_at": "2026-01-01T00:00:00Z", "score": 2,
                              "response": {"body_text": None, "attachments": []}, "rubric_assessment": [],
                              "feedback": [], "source_ref": {"api_path": "/quiz/2101/submissions"},
                              "question_responses": [{"question_id": "Q-2101-01", "question_number": 1,
                                                       "question_text": "What is a test?",
                                                       "response": {"choice_index": 1, "text": "A check"},
                                                       "correct": True, "points_earned": 2,
                                                       "points_possible": 2,
                                                       "correct_answer": {"choice_index": 1, "text": "A check"},
                                                       "evidence_ref_id": "EV-0001"}]}],
        }

    def store_fake(self, scope):
        db = FakeDatabase()
        with patch.object(db_store, "service_client", return_value=db):
            store = db_store.Store(self.sample_bundle(scope), Path(tempfile.gettempdir()))
            store.cid = "course-1"
            store.learners()
            store.assessment = {"A-2101": "assessment-1"}
            store.questions()
            store.submissions()
            store.feedback()
        return db

    def test_instructor_items_and_protected_answer_keys(self):
        db = self.store_fake("instructor")
        self.assertEqual(len(db.tables["questions"]), 1)
        self.assertEqual(db.tables["questions"][0]["question_type"], "quiz_item")
        self.assertEqual(len(db.tables["question_answer_keys"]), 1)
        self.assertEqual(json.loads(db.tables["question_answer_keys"][0]["answer"])["text"], "A check")
        self.assertEqual(len(db.tables["responses"]), 1)
        self.assertNotIn("correct_answer", db.tables["responses"][0]["rubric"])
        self.assertEqual(db.tables["responses"][0]["locator"]["evidence_content_hash"], "abc123")
        self.assertEqual(len(db.tables["evidence_refs"]), 1)
        self.assertEqual(db.tables["evidence_refs"][0]["source_type"], "canvas_api")

    def test_student_scope_does_not_store_answer_keys(self):
        db = self.store_fake("self_only")
        self.assertEqual(db.tables.get("question_answer_keys", []), [])


if __name__ == "__main__":
    unittest.main()

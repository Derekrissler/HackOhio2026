from app.ingest.canvas_normalize import normalize_assignment_groups, normalize_submission

QUIZ_SUBMISSION = {
    "id": 1, "assignment_id": 10, "user_id": 9002, "attempt": 1, "grader_id": 9001,
    "submitted_at": "2026-09-18T20:00:00Z", "graded_at": "2026-09-18T20:00:00Z",
    "score": 2.0, "workflow_state": "graded",
    "submission_history": [{
        "attempt": 1,
        "submission_data": [
            {"question_id": 77001, "correct": True, "points": 2.0, "answer_id": 5001, "text": "", "more_comments": ""},
            {"question_id": 77002, "correct": False, "points": 0.0, "text": "11",
             "more_comments": "Check every corner point."},
        ],
    }],
    "submission_comments": [
        {"id": 900, "author_id": 9001, "comment": "Nice work", "created_at": "2026-09-19T10:00:00Z", "draft": False},
        {"id": 901, "author_id": 9001, "comment": "Private note", "created_at": "2026-09-19T10:05:00Z", "draft": True},
    ],
}


def test_quiz_submission_data_becomes_responses():
    sub, files = normalize_submission(QUIZ_SUBMISSION, quiz_answers={"5001": "a corner point"})
    assert files == []
    first, second = sub.responses
    assert (first.question, first.response, first.points_awarded, first.is_correct, first.graded_by) == (
        "77001", "a corner point", 2.0, True, "canvas_auto"
    )
    assert (second.response, second.is_correct) == ("11", False)


def test_quiz_more_comments_become_question_feedback():
    sub, _ = normalize_submission(QUIZ_SUBMISSION, quiz_answers={})
    q_comments = [f for f in sub.feedback if f.kind == "question_comment"]
    assert [(f.question, f.text) for f in q_comments] == [("77002", "Check every corner point.")]


def test_draft_comment_is_hidden_from_students():
    sub, _ = normalize_submission(QUIZ_SUBMISSION, quiz_answers={})
    visibility = {f.text: f.visible_to_student for f in sub.feedback if f.kind == "submission_comment"}
    assert visibility == {"Nice work": True, "Private note": False}


def test_rubric_assessment_becomes_rubric_scores():
    raw = {
        "id": 2, "assignment_id": 11, "user_id": 9003, "workflow_state": "graded", "score": 40,
        "rubric_assessment": {"_8201": {"points": 8.0, "comments": ""}, "_8202": {"points": 20, "comments": "Recheck pivot 2"}},
        "attachments": [{"id": 550100, "display_name": "hw2.pdf", "filename": "hw2.pdf",
                         "content-type": "application/pdf", "size": 10, "url": "files/x/hw2.pdf"}],
    }
    sub, files = normalize_submission(raw, quiz_answers={}, seed_prefix="seed/")
    assert [(r.criterion, r.points, r.comment) for r in sub.rubric_scores] == [
        ("_8201", 8.0, None), ("_8202", 20, "Recheck pivot 2"),
    ]
    assert sub.file == "550100"
    assert (files[0].owner, files[0].storage_path) == ("9003", "seed/files/x/hw2.pdf")


def test_exam_is_recognised_by_name_and_quiz_by_flag():
    groups = [{"id": 1, "name": "All", "assignments": [
        {"id": 10, "name": "Midterm Exam", "points_possible": 100},
        {"id": 11, "name": "Quiz 1", "quiz_id": 5, "is_quiz_assignment": True, "points_possible": 10},
        {"id": 12, "name": "HW1", "points_possible": 40},
    ]}]
    _, assessments = normalize_assignment_groups(groups, quiz_questions={}, module_labels={})
    assert [a.kind for a in assessments] == ["exam", "quiz", "homework"]

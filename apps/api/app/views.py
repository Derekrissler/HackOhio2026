"""Model → DTO builders shared by the routers. Every student-facing field passes through the
visibility helpers in app/auth.py here, so routers can't forget a rule."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import is_teacher, results_visible, visible_feedback
from app.models import (
    Assessment,
    Enrollment,
    Feedback,
    File,
    LearningOutcome,
    Question,
    RubricCriterion,
    Submission,
    User,
)
from app.schemas import (
    AssessmentSummaryOut,
    FeedbackOut,
    FileRefOut,
    MySubmissionOut,
    OutcomeRefOut,
    ResponseOut,
    RubricScoreOut,
    SubmissionCountsOut,
)


def feedback_out(db: Session, f: Feedback) -> FeedbackOut:
    return FeedbackOut(id=f.id, kind=f.kind, author_name=db.get(User, f.author_id).name, text=f.text,
                       created_at=f.created_at, visible_to_student=f.visible_to_student)


def own_submission(db: Session, assessment_id: int, user_id: int) -> Submission | None:
    return db.scalar(select(Submission).where(Submission.assessment_id == assessment_id,
                                              Submission.user_id == user_id).order_by(Submission.attempt.desc()))


def my_submission_out(enrollment: Enrollment, sub: Submission | None) -> MySubmissionOut | None:
    if sub is None:
        return None
    return MySubmissionOut(id=sub.id, workflow_state=sub.workflow_state,
                           score=sub.score if results_visible(enrollment, sub) else None,
                           submitted_at=sub.submitted_at, late=sub.late, missing=sub.missing, excused=sub.excused)


def submission_counts(db: Session, assessment_id: int) -> SubmissionCountsOut:
    rows = dict(db.execute(select(Submission.workflow_state, func.count())
                           .where(Submission.assessment_id == assessment_id)
                           .group_by(Submission.workflow_state)).all())
    total = sum(rows.values())
    return SubmissionCountsOut(submitted=rows.get("submitted", 0) + rows.get("graded", 0),
                               graded=rows.get("graded", 0), total=total)


def assessment_summary(db: Session, enrollment: Enrollment, a: Assessment) -> AssessmentSummaryOut:
    teacher = is_teacher(enrollment)
    return AssessmentSummaryOut(
        id=a.id, title=a.title, kind=a.kind, group_id=a.assignment_group_id, points_possible=a.points_possible,
        due_at=a.due_at, module_label=a.module_label,
        my_submission=None if teacher else my_submission_out(enrollment, own_submission(db, a.id, enrollment.user_id)),
        submission_counts=submission_counts(db, a.id) if teacher else None,
    )


def outcome_ref(o: LearningOutcome | None) -> OutcomeRefOut | None:
    return OutcomeRefOut(id=o.id, code=o.code, title=o.title) if o else None


def file_ref(f: File | None) -> FileRefOut | None:
    if f is None:
        return None
    return FileRefOut(id=f.id, display_name=f.display_name, mime=f.mime, page_count=f.page_count,
                      has_text_layer=f.has_text_layer, url=f"/api/files/{f.id}/content")


def rubric_scores_out(db: Session, enrollment: Enrollment, sub: Submission) -> list[RubricScoreOut]:
    if not results_visible(enrollment, sub):
        return []
    out = []
    for rs in sorted(sub.rubric_scores, key=lambda r: db.get(RubricCriterion, r.criterion_id).position):
        crit = db.get(RubricCriterion, rs.criterion_id)
        out.append(RubricScoreOut(criterion_id=crit.id, description=crit.description, points=rs.points,
                                  points_possible=crit.points, comment=rs.comment))
    return out


def submission_comments(db: Session, enrollment: Enrollment, sub: Submission) -> list[FeedbackOut]:
    rows = [f for f in sub.feedback if f.kind == "submission_comment"]
    return [feedback_out(db, f) for f in visible_feedback(enrollment, sub, rows)]


def responses_out(db: Session, enrollment: Enrollment, sub: Submission) -> list[ResponseOut]:
    show = results_visible(enrollment, sub)
    by_response: dict[int, list[Feedback]] = {}
    for f in visible_feedback(enrollment, sub, [f for f in sub.feedback if f.question_response_id]):
        by_response.setdefault(f.question_response_id, []).append(f)
    out = []
    for r in sorted(sub.responses, key=lambda r: db.get(Question, r.question_id).position):
        q = db.get(Question, r.question_id)
        parent = db.get(Question, q.parent_question_id) if q.parent_question_id else None
        out.append(ResponseOut(
            question_id=q.id, label=q.label, parent_label=parent.label if parent else None,
            prompt_html=q.prompt_html, question_type=q.question_type, choices=q.choices, response=r.response,
            points_awarded=r.points_awarded if show else None, points_possible=r.points_possible,
            is_correct=r.is_correct if show else None, answer_key=q.answer_key if show else None,
            graded_by=r.graded_by, source_page=q.source_page,
            comments=[feedback_out(db, f) for f in by_response.get(r.id, [])],
        ))
    return out

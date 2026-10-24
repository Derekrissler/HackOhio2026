from fastapi import APIRouter
from sqlalchemy import select

from app.auth import DbSession, Enrolled, Teacher, get_assessment, is_teacher, questions_visible, results_visible
from app.models import Assessment, AssignmentGroup, LearningOutcome, QuestionOutcome, Submission, User
from app.schemas import (
    AssessmentDetailOut,
    AssignmentGroupOut,
    QuestionOut,
    RubricCriterionOut,
    SubmissionRowOut,
)
from app.views import assessment_summary, my_submission_out, outcome_ref, own_submission

router = APIRouter(prefix="/api/courses/{course_id}", tags=["assessments"])


@router.get("/assignment_groups", response_model=list[AssignmentGroupOut])
def list_assignment_groups(enrollment: Enrolled, db: DbSession) -> list[AssignmentGroupOut]:
    groups = db.scalars(select(AssignmentGroup).where(AssignmentGroup.course_id == enrollment.course_id)
                        .order_by(AssignmentGroup.position)).all()
    return [
        AssignmentGroupOut(id=g.id, name=g.name, weight=g.group_weight,
                           assessments=[assessment_summary(db, enrollment, a) for a in g.assessments])
        for g in groups
    ]


@router.get("/assessments/{assessment_id}", response_model=AssessmentDetailOut)
def get_assessment_detail(assessment_id: int, enrollment: Enrolled, db: DbSession) -> AssessmentDetailOut:
    a = get_assessment(db, enrollment, assessment_id)
    teacher = is_teacher(enrollment)
    sub = None if teacher else own_submission(db, a.id, enrollment.user_id)
    show_questions = questions_visible(enrollment, a, sub)
    show_keys = results_visible(enrollment, sub)

    questions = None
    if show_questions:
        questions = []
        for q in a.questions:
            outcomes = []
            if teacher:
                outcomes = [outcome_ref(db.get(LearningOutcome, qo.outcome_id)) for qo in
                            db.scalars(select(QuestionOutcome).where(QuestionOutcome.question_id == q.id))]
            questions.append(QuestionOut(
                id=q.id, label=q.label, parent_id=q.parent_question_id, position=q.position,
                prompt_html=q.prompt_html, question_type=q.question_type, points_possible=q.points_possible,
                choices=q.choices, answer_key=q.answer_key if show_keys else None, outcomes=outcomes,
                source_page=q.source_page,
            ))

    reason = None
    if not show_questions:
        reason = ("Questions are shown after you take this quiz." if a.kind == "quiz"
                  else "Questions are shown after the exam.")
    return AssessmentDetailOut(
        id=a.id, title=a.title, kind=a.kind, group_name=a.group.name, group_weight=a.group.group_weight,
        points_possible=a.points_possible, due_at=a.due_at, module_label=a.module_label,
        description_html=a.description_html, submission_types=a.submission_types,
        questions=questions, questions_hidden_reason=reason,
        rubric=[
            RubricCriterionOut(id=c.id, description=c.description, long_description=c.long_description,
                               points=c.points,
                               outcome=outcome_ref(db.get(LearningOutcome, c.learning_outcome_id))
                               if c.learning_outcome_id else None)
            for c in a.rubric_criteria
        ],
        my_submission=my_submission_out(enrollment, sub),
    )


@router.get("/assessments/{assessment_id}/submissions", response_model=list[SubmissionRowOut])
def list_submissions(assessment_id: int, enrollment: Teacher, db: DbSession) -> list[SubmissionRowOut]:
    a: Assessment = get_assessment(db, enrollment, assessment_id)
    rows = db.execute(select(Submission, User).join(User, User.id == Submission.user_id)
                      .where(Submission.assessment_id == a.id).order_by(User.sortable_name)).all()
    return [
        SubmissionRowOut(id=s.id, user_id=u.id, user_name=u.name, sortable_name=u.sortable_name,
                         workflow_state=s.workflow_state, score=s.score, submitted_at=s.submitted_at,
                         late=s.late, missing=s.missing, excused=s.excused)
        for s, u in rows
    ]

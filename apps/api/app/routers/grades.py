from fastapi import APIRouter
from sqlalchemy import select

from app.auth import DbSession, Enrolled, Teacher, require_student_access, results_visible
from app.grading import student_grade
from app.models import Assessment, AssignmentGroup, Course, Enrollment, Submission, User
from app.schemas import (
    GradebookCellOut,
    GradebookOut,
    GradebookStudentOut,
    GradeRowOut,
    GradesOut,
    GroupGradeOut,
)
from app.views import assessment_summary, rubric_scores_out, submission_comments

router = APIRouter(prefix="/api/courses/{course_id}", tags=["grades"])


def _assessments(db: DbSession, course_id: int) -> list[Assessment]:
    return list(db.scalars(
        select(Assessment).join(AssignmentGroup).where(Assessment.course_id == course_id)
        .order_by(Assessment.due_at.is_(None), Assessment.due_at, AssignmentGroup.position, Assessment.position)
    ))


def _students(db: DbSession, course_id: int) -> list[User]:
    return list(db.scalars(select(User).join(Enrollment).where(Enrollment.course_id == course_id,
                                                               Enrollment.role == "student")
                           .order_by(User.sortable_name)))


@router.get("/users/{user_id}/grades", response_model=GradesOut)
def get_grades(user_id: int, enrollment: Enrolled, db: DbSession) -> GradesOut:
    require_student_access(enrollment, user_id)
    if user_id not in {u.id for u in _students(db, enrollment.course_id)}:
        require_student_access(enrollment, -1)  # teachers asking about a non-student: 404 too
    summary = student_grade(db, enrollment.course_id, user_id)
    subs = {s.assessment_id: s for s in db.scalars(select(Submission).where(Submission.user_id == user_id))}
    rows = []
    for a in _assessments(db, enrollment.course_id):
        s = subs.get(a.id)
        show = results_visible(enrollment, s)
        rows.append(GradeRowOut(
            assessment_id=a.id, title=a.title, kind=a.kind, group_id=a.assignment_group_id, due_at=a.due_at,
            points_possible=a.points_possible, submission_id=s.id if s else None,
            workflow_state=s.workflow_state if s else "unsubmitted",
            score=s.score if s and show else None,
            late=bool(s and s.late), missing=bool(s and s.missing), excused=bool(s and s.excused),
            comments=submission_comments(db, enrollment, s) if s else [],
            rubric=rubric_scores_out(db, enrollment, s) if s else [],
        ))
    return GradesOut(
        user_id=user_id, user_name=db.get(User, user_id).name,
        weighted=db.get(Course, enrollment.course_id).apply_group_weights,
        current_percent=summary.current_percent,
        groups=[GroupGradeOut(id=g.group_id, name=g.name, weight=g.weight, earned=g.earned, possible=g.possible,
                              percent=g.percent) for g in summary.groups.values()],
        rows=rows,
    )


@router.get("/gradebook", response_model=GradebookOut)
def get_gradebook(enrollment: Teacher, db: DbSession) -> GradebookOut:
    assessments = _assessments(db, enrollment.course_id)
    subs = {(s.assessment_id, s.user_id): s for s in db.scalars(
        select(Submission).join(Assessment).where(Assessment.course_id == enrollment.course_id))}
    students = []
    for u in _students(db, enrollment.course_id):
        cells = []
        for a in assessments:
            s = subs.get((a.id, u.id))
            cells.append(GradebookCellOut(
                submission_id=s.id if s else None, workflow_state=s.workflow_state if s else "unsubmitted",
                score=s.score if s else None, late=bool(s and s.late), missing=bool(s and s.missing),
                excused=bool(s and s.excused)))
        students.append(GradebookStudentOut(
            id=u.id, name=u.name, sortable_name=u.sortable_name,
            current_percent=student_grade(db, enrollment.course_id, u.id).current_percent, cells=cells))
    return GradebookOut(assessments=[assessment_summary(db, enrollment, a) for a in assessments], students=students)

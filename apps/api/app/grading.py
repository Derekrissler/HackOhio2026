"""Canvas-style "current grade": computed over graded work only.

- A submission counts when it is graded, not excused and has a score. Missing work that was
  graded 0 counts; submitted-but-ungraded and unsubmitted work does not.
- Group % = Σ score / Σ points possible over counted submissions.
- Weighted courses: Σ(weight × group %) / Σ weight, over groups with at least one counted
  submission (so an empty Final Exam group is ignored rather than counted as 0).
- Unweighted courses: Σ score / Σ points possible across all counted submissions.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assessment, AssignmentGroup, Course, Submission


@dataclass(frozen=True)
class GradeRow:
    group_id: int
    points_possible: float
    score: float | None
    workflow_state: str
    excused: bool = False
    missing: bool = False

    @property
    def counts(self) -> bool:
        return self.workflow_state == "graded" and not self.excused and self.score is not None


@dataclass
class GroupGrade:
    group_id: int
    name: str
    weight: float
    earned: float = 0.0
    possible: float = 0.0

    @property
    def percent(self) -> float | None:
        return 100 * self.earned / self.possible if self.possible else None


@dataclass
class GradeSummary:
    groups: dict[int, GroupGrade] = field(default_factory=dict)
    current_percent: float | None = None


def compute_grade(
    weights: dict[int, float], rows: list[GradeRow], weighted: bool, names: dict[int, str] | None = None
) -> GradeSummary:
    names = names or {}
    groups = {gid: GroupGrade(gid, names.get(gid, ""), w) for gid, w in weights.items()}
    for row in rows:
        if row.counts:
            group = groups[row.group_id]
            group.earned += row.score or 0
            group.possible += row.points_possible

    active = [g for g in groups.values() if g.possible > 0]
    if not active:
        return GradeSummary(groups)
    if weighted:
        total_weight = sum(g.weight for g in active)
        if total_weight > 0:
            percent = sum(g.weight * (g.percent or 0) for g in active) / total_weight
            return GradeSummary(groups, percent)
    earned = sum(g.earned for g in active)
    possible = sum(g.possible for g in active)
    return GradeSummary(groups, 100 * earned / possible)


def student_grade(db: Session, course_id: int, user_id: int) -> GradeSummary:
    course = db.get(Course, course_id)
    groups = db.scalars(
        select(AssignmentGroup).where(AssignmentGroup.course_id == course_id).order_by(AssignmentGroup.position)
    ).all()
    rows = db.execute(
        select(Assessment.assignment_group_id, Assessment.points_possible, Submission)
        .join(Submission, Submission.assessment_id == Assessment.id)
        .where(Assessment.course_id == course_id, Submission.user_id == user_id)
    ).all()
    return compute_grade(
        {g.id: g.group_weight for g in groups},
        [
            GradeRow(group_id=gid, points_possible=possible, score=s.score, workflow_state=s.workflow_state,
                     excused=s.excused, missing=s.missing)
            for gid, possible, s in rows
        ],
        weighted=bool(course and course.apply_group_weights),
        names={g.id: g.name for g in groups},
    )

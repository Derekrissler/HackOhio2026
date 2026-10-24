"""ORM tables (docs/PHASE1_PLAN.md §5.1–5.2, minus AI columns).

Importing this package registers every table on Base.metadata.
"""

from app.models.assessments import (
    Assessment,
    AssignmentGroup,
    Question,
    QuestionOutcome,
    RubricCriterion,
)
from app.models.files import CourseMaterial, File
from app.models.outcomes import LearningOutcome
from app.models.people import ROLES, Course, Enrollment, User
from app.models.submissions import Feedback, QuestionResponse, RubricScore, Submission

__all__ = [
    "ROLES",
    "Assessment",
    "AssignmentGroup",
    "Course",
    "CourseMaterial",
    "Enrollment",
    "Feedback",
    "File",
    "LearningOutcome",
    "Question",
    "QuestionOutcome",
    "QuestionResponse",
    "RubricCriterion",
    "RubricScore",
    "Submission",
    "User",
]

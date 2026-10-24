"""Deterministic student performance. All randomness comes from the single `rng` passed in,
consumed in a fixed order, so the same seed always yields the same course."""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from seedgen.content import AssessmentSpec, CourseSpec, Err, Q
from seedgen.people import (
    ABILITY,
    EARLY_HW3,
    EXCUSED,
    MISSING,
    PRIVATE_NOTES,
    Person,
)


@dataclass
class QResult:
    question: Q
    response: str
    points: float | None  # None until graded
    error: Err | None
    comment: str | None  # visible question-level comment


@dataclass
class Comment:
    text: str
    created_at: datetime
    visible: bool = True


@dataclass
class SubResult:
    assessment: AssessmentSpec
    student: Person
    state: str  # unsubmitted | submitted | graded
    submitted_at: datetime | None = None
    graded_at: datetime | None = None
    late: bool = False
    missing: bool = False
    excused: bool = False
    questions: list[QResult] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    rubric: dict[str, tuple[float, str | None]] = field(default_factory=dict)

    @property
    def score(self) -> float | None:
        if self.state != "graded" or self.excused:
            return None
        return sum(q.points or 0 for q in self.questions)


PRAISE = (
    "Excellent work — clear and complete.",
    "Very well done; your setup and notation are easy to follow.",
    "Great job. Nice, careful work throughout.",
)
SOLID = (
    "Solid work overall; see the question comments for where points were lost.",
    "Good effort — review the marked parts before the next quiz.",
    "Mostly correct. Watch the details flagged on each question.",
)
CONCERN = (
    "Please come to office hours this week so we can go over the marked questions together.",
    "Several setup errors here; rework the flagged parts using the lecture slides for this week.",
    "Review the comment on each question and redo those parts before the exam.",
)


def _half(x: float) -> float:
    return round(x * 2) / 2


def answer_question(q: Q, student: Person, rng: random.Random) -> tuple[str, float, Err | None]:
    """Return (response, credit fraction, error) for one question."""
    habit_errors = [e for e in q.errors if e.tag in student.habits]
    p_correct = ABILITY[student.profile] - q.difficulty - (0.3 if habit_errors else 0.0)
    p_correct = min(0.98, max(0.05, p_correct + rng.gauss(0, 0.07)))
    blank = student.profile == "struggling" and q.qtype == "essay" and rng.random() < 0.06
    if blank:
        return "", 0.0, Err("blank", 0.0, "", "No answer given.")
    if not q.errors or rng.random() < p_correct:
        return q.answer, 1.0, None
    weights = [6 if e.tag in student.habits else 1 for e in q.errors]
    err = rng.choices(q.errors, weights)[0]
    return err.response, err.credit, err


def simulate_submission(
    course: CourseSpec, spec: AssessmentSpec, student: Person, rng: random.Random
) -> SubResult:
    sub = SubResult(spec, student, "unsubmitted")
    key = (spec.key, student.id)

    if spec.state == "upcoming" or (spec.state == "early" and student.id not in EARLY_HW3):
        return sub
    if key in EXCUSED:
        sub.state, sub.excused = "graded", True
        sub.graded_at = spec.due + timedelta(days=2)
        sub.comments.append(Comment("Excused — documentation received by the advising office.", sub.graded_at))
        return sub
    if key in MISSING:
        sub.state, sub.missing = "graded", True
        sub.graded_at = spec.due + timedelta(days=1)
        sub.questions = [QResult(q, "", 0.0, None, None) for q in spec.questions]
        return sub

    # Submission time
    if spec.kind == "exam":
        sub.submitted_at = spec.due
    elif spec.state == "early":
        sub.submitted_at = spec.due - timedelta(days=rng.randint(7, 10), hours=rng.randint(0, 12))
    elif spec.kind == "homework" and rng.random() < 0.08:
        sub.submitted_at, sub.late = spec.due + timedelta(hours=rng.randint(1, 20)), True
    else:
        sub.submitted_at = spec.due - timedelta(hours=rng.randint(2, 70))

    graded = spec.state == "graded"
    sub.state = "graded" if graded else "submitted"
    if graded:
        sub.graded_at = spec.due + timedelta(days=rng.randint(2, 5), hours=rng.randint(0, 6))

    comment_rate = 0.6 if spec.kind == "quiz" else 0.85
    for q in spec.questions:
        response, credit, err = answer_question(q, student, rng)
        points = _half(q.points * credit) if graded else None
        comment = err.comment if graded and err and rng.random() < comment_rate else None
        sub.questions.append(QResult(q, response, points, err, comment))

    if not graded:
        return sub

    pct = (sub.score or 0) / spec.points
    if rng.random() < (0.25 if spec.kind == "quiz" else 0.55):
        pool = PRAISE if pct >= 0.9 else SOLID if pct >= 0.75 else CONCERN
        sub.comments.append(Comment(rng.choice(pool), sub.graded_at))
    for note_key, note_student, text in PRIVATE_NOTES:
        if (note_key, note_student) == key:
            sub.comments.append(Comment(text, sub.graded_at + timedelta(minutes=5), visible=False))

    by_key = {r.question.key: r for r in sub.questions}
    for crit in spec.rubric:
        rows = [by_key[k] for k in crit.question_keys]
        earned = sum(r.points or 0 for r in rows)
        possible = sum(r.question.points for r in rows)
        comment = "Review this section — see the comments on each part." if earned < 0.6 * possible else None
        sub.rubric[crit.key] = (earned, comment)
    return sub

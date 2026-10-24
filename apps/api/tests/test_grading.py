import pytest

from app.grading import GradeRow, compute_grade, student_grade
from tests.conftest import ALEX_ID, ISE_COURSE, MARCUS_ID, STAT_COURSE

HW, QUIZ, EXAM, FINAL = 1, 2, 3, 4
WEIGHTS = {HW: 30.0, QUIZ: 20.0, EXAM: 25.0, FINAL: 25.0}


def graded(group: int, score: float, possible: float, **kw) -> GradeRow:
    return GradeRow(group_id=group, points_possible=possible, score=score, workflow_state="graded", **kw)


def test_weighted_grade_renormalises_over_groups_with_graded_work():
    rows = [graded(HW, 45, 50), graded(QUIZ, 8, 10)]  # no exam or final graded yet
    summary = compute_grade(WEIGHTS, rows, weighted=True)
    # (30 × 0.9 + 20 × 0.8) / (30 + 20) = 43 / 50
    assert summary.current_percent == pytest.approx(86.0)
    assert summary.groups[EXAM].percent is None


def test_ungraded_and_unsubmitted_work_is_ignored():
    rows = [
        graded(HW, 40, 50),
        GradeRow(group_id=HW, points_possible=50, score=None, workflow_state="submitted"),
        GradeRow(group_id=HW, points_possible=50, score=None, workflow_state="unsubmitted"),
    ]
    assert compute_grade(WEIGHTS, rows, weighted=True).current_percent == pytest.approx(80.0)


def test_excused_work_is_left_out_but_missing_work_counts_as_zero():
    rows = [
        graded(HW, 40, 50),
        GradeRow(group_id=HW, points_possible=50, score=None, workflow_state="graded", excused=True),
        graded(HW, 0, 50, missing=True),
    ]
    summary = compute_grade(WEIGHTS, rows, weighted=True)
    assert (summary.groups[HW].earned, summary.groups[HW].possible) == (40, 100)
    assert summary.current_percent == pytest.approx(40.0)


def test_unweighted_grade_is_total_points():
    rows = [graded(HW, 45, 50), graded(QUIZ, 5, 10)]
    # 50 / 60, regardless of group weights
    assert compute_grade(WEIGHTS, rows, weighted=False).current_percent == pytest.approx(83.333, abs=1e-3)


def test_no_graded_work_gives_no_grade():
    rows = [GradeRow(group_id=HW, points_possible=50, score=None, workflow_state="submitted")]
    assert compute_grade(WEIGHTS, rows, weighted=True).current_percent is None


def test_alex_kim_current_grade_matches_hand_calculation(db):
    """ISE 3200, weights Homework 30 / Quizzes 20 / Midterm 25 / Final Exam 25.

    Homework: HW1 32/40 + HW2 50/50 (HW3 submitted, not graded → ignored) = 82/90  = 91.111%
    Quizzes:  Quiz 1 8/10 + Quiz 2 4/10 (Quiz 3 not taken → ignored)       = 12/20  = 60.000%
    Midterm:  89/100                                                         =          89.000%
    Final:    nothing graded → group dropped, weights renormalised over 75

    (30 × 0.91111 + 20 × 0.60 + 25 × 0.89) / 75 = (27.333 + 12 + 22.25) / 75 = 61.583 / 75 = 82.111%
    """
    summary = student_grade(db, ISE_COURSE, ALEX_ID)
    by_name = {g.name: g for g in summary.groups.values()}
    assert by_name["Homework"].percent == pytest.approx(91.111, abs=1e-3)
    assert by_name["Quizzes"].percent == pytest.approx(60.0)
    assert by_name["Midterm"].percent == pytest.approx(89.0)
    assert by_name["Final Exam"].percent is None
    assert summary.current_percent == pytest.approx(82.111, abs=1e-3)


def test_marcus_bell_current_grade_matches_hand_calculation(db):
    """Same weights. Marcus never took Quiz 2: it is graded 0 and marked missing, so it counts.

    Homework: HW1 29/40 + HW2 32.5/50 = 61.5/90 = 68.333%
    Quizzes:  Quiz 1 4/10 + Quiz 2 0/10 (missing) = 4/20 = 20.000%
    Midterm:  72.5/100 = 72.500%

    (30 × 0.68333 + 20 × 0.20 + 25 × 0.725) / 75 = (20.5 + 4 + 18.125) / 75 = 42.625 / 75 = 56.833%
    """
    summary = student_grade(db, ISE_COURSE, MARCUS_ID)
    assert summary.current_percent == pytest.approx(56.833, abs=1e-3)


def test_unweighted_course_uses_total_points(db):
    # STAT 1450 is unweighted; only Homework 1 is graded so far.
    summary = student_grade(db, STAT_COURSE, ALEX_ID)
    group = next(iter(summary.groups.values()))
    assert summary.current_percent == pytest.approx(100 * group.earned / group.possible)

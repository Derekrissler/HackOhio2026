"""Fictional roster. Ids 1–4 match the Phase 2 demo users and must stay stable."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Person:
    id: int  # our stable demo id; the Canvas id is 9000 + id
    name: str
    sortable_name: str
    profile: str = "teacher"  # teacher | strong | average | struggling
    habits: tuple[str, ...] = ()  # error tags this student makes repeatedly

    @property
    def canvas_id(self) -> int:
        return 9000 + self.id

    @property
    def email(self) -> str:
        first, last = self.sortable_name.split(", ")[::-1]
        return f"{first[0].lower()}{last.lower().replace(' ', '').replace(chr(39), '')}@example.edu"


def _p(id_: int, name: str, profile: str, habits: tuple[str, ...] = ()) -> Person:
    first, last = name.rsplit(" ", 1)
    return Person(id_, name, f"{last}, {first}", profile, habits)


TEACHER = Person(1, "Prof. Dana Rivera", "Rivera, Dana")

STUDENTS = (
    _p(2, "Alex Kim", "average", ("slack_sign",)),
    _p(3, "Priya Natarajan", "strong"),
    _p(4, "Marcus Bell", "struggling", ("missing_nonneg", "ratio_test", "entering_rule")),
    _p(5, "Jordan Alvarez", "average", ("coeff_swap",)),
    _p(6, "Samira Haddad", "strong"),
    _p(7, "Ethan Brooks", "average", ("missed_corner",)),
    _p(8, "Mei Lin Chen", "strong", ("arith",)),
    _p(9, "Daniel Okafor", "average", ("ratio_constraint", "free_variable")),
    _p(10, "Hannah Schultz", "average", ("optimality_check",)),
    _p(11, "Luis Romero", "struggling", ("vague_variables", "ineq_direction")),
    _p(12, "Grace Park", "strong"),
    _p(13, "Owen Fitzgerald", "struggling", ("slack_sign", "read_solution")),
    _p(14, "Aisha Rahman", "average", ("objective_negation",)),
    _p(15, "Tyler Nguyen", "struggling", ("missed_corner", "pivot_arith", "missing_nonneg")),
    _p(16, "Sofia Marchetti", "average", ("pivot_arith",)),
    _p(17, "Caleb Johnson", "struggling", ("entering_rule", "ratio_constraint")),
    _p(18, "Nadia Petrova", "strong"),
    _p(19, "Ryan O'Connell", "average", ("degeneracy_confusion", "multiple_optima")),
    _p(20, "Emily Watanabe", "average", ("missing_nonneg",)),
    _p(21, "Kwame Mensah", "average", ("wrong_sense", "slack_sign")),
)

ABILITY = {"strong": 0.93, "average": 0.78, "struggling": 0.58}

# Students also enrolled in the lightly populated STAT 1450.
STAT_STUDENT_IDS = (2, 3, 4)

# Deterministic special cases the grade tests rely on.
EXCUSED = {("hw1", 17)}  # Caleb Johnson: excused from HW1
MISSING = {("quiz2", 4)}  # Marcus Bell: never took Quiz 2 → graded 0, missing
EARLY_HW3 = (3, 6, 8, 12, 2, 10)  # submitted HW3 before the deadline (not graded yet)

# Teacher-only notes (never visible to students): (assessment key, student id, text)
PRIVATE_NOTES = (
    ("midterm", 4, "Spoke with Marcus after class; recommended the tutoring center for simplex practice."),
    ("hw2", 9, "Q3 wording is nearly identical to another submission. Follow up before grading HW3."),
    ("midterm", 12, "Regrade request for Q3b reviewed; the original score stands."),
)

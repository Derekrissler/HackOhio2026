"""Hand-written course content for the seed: outcomes, assessments, questions, error catalogue.

Everything here is fictional. Each wrong answer a student can give is an `Err`: what they
wrote, the share of points it keeps, and the comment an instructor would leave. Students with a
matching habit (see people.py) make that error far more often, so recurring misconceptions are
visible in the data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta


def et(month: int, day: int, hour: int = 23, minute: int = 59) -> datetime:
    """A US Eastern wall-clock time in autumn 2026, as naive UTC (EDT until Nov 1, then EST)."""
    local = datetime(2026, month, day, hour, minute)
    return local + timedelta(hours=4 if local < datetime(2026, 11, 1, 2) else 5)


@dataclass(frozen=True)
class Err:
    tag: str
    credit: float
    response: str
    comment: str


@dataclass(frozen=True)
class Q:
    key: str
    prompt: str
    points: float
    outcomes: tuple[str, ...]
    answer: str
    errors: tuple[Err, ...] = ()
    difficulty: float = 0.0
    qtype: str = "essay"
    parent: str | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Criterion:
    key: str
    description: str
    long_description: str
    question_keys: tuple[str, ...]
    outcome: str


@dataclass(frozen=True)
class AssessmentSpec:
    key: str
    title: str
    kind: str  # homework | quiz | exam
    group: str
    due: datetime
    description: str
    module: str
    state: str  # graded | early (a few submitted, none graded) | upcoming
    questions: tuple[Q, ...]
    stems: dict[str, str] = field(default_factory=dict)
    rubric: tuple[Criterion, ...] = ()
    pages: dict[str, int] = field(default_factory=dict)  # scanned exam: question → page

    @property
    def points(self) -> float:
        return sum(q.points for q in self.questions)


@dataclass(frozen=True)
class Outcome:
    code: str
    title: str
    description: str


@dataclass(frozen=True)
class Material:
    key: str
    title: str
    kind: str  # slides | reading
    week: int
    slides: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class CourseSpec:
    canvas_id: int
    code: str
    name: str
    term: str
    start: datetime
    end: datetime
    weighted: bool
    groups: tuple[tuple[str, float], ...]
    outcomes: tuple[Outcome, ...]
    weeks: dict[int, str]
    assessments: tuple[AssessmentSpec, ...]
    materials: tuple[Material, ...]
    syllabus_intro: str


# --------------------------------------------------------------------------------------------
# Shared error catalogue (tags are reused across assessments so habits carry over)
# --------------------------------------------------------------------------------------------

NONNEG = "Forgot the non-negativity constraints x₁, x₂ ≥ 0."
SLACK_SIGN = (
    "Sign of the slack variable is reversed: a ≥ constraint needs a surplus variable "
    "subtracted (−s), not a slack added (+s)."
)

# --------------------------------------------------------------------------------------------
# ISE 3200 – Linear Optimization
# --------------------------------------------------------------------------------------------

ISE_OUTCOMES = (
    Outcome("LO1", "Formulate linear programs",
            "Formulate linear programs from word problems by defining decision variables, an objective and constraints."),
    Outcome("LO2", "Convert to standard form",
            "Convert any LP to standard form using slack and surplus variables, non-negativity and free-variable substitution."),
    Outcome("LO3", "Solve graphically",
            "Solve two-variable LPs graphically and interpret corner points, unboundedness and multiple optima."),
    Outcome("LO4", "Apply the simplex method",
            "Carry out the simplex method: choose entering and leaving variables, perform pivots and recognise optimality, degeneracy and unboundedness."),
    Outcome("LO5", "Use duality",
            "Formulate the dual of an LP and apply weak duality, strong duality and complementary slackness."),
    Outcome("LO6", "Interpret sensitivity analysis",
            "Interpret shadow prices, reduced costs and the ranges over which the optimal basis stays optimal."),
)

ISE_WEEKS = {
    1: "Week 1: Introduction & LP Modeling",
    2: "Week 2: The Graphical Method",
    3: "Week 3: Standard Form",
    4: "Week 4: The Simplex Method I",
    5: "Week 5: The Simplex Method II",
    6: "Week 6: Duality",
    7: "Week 7: Complementary Slackness",
    8: "Week 8: Sensitivity Analysis",
}

FURNITURE = (
    "Buckeye Furniture makes tables and chairs. A table needs 4 hours of carpentry and 2 hours of "
    "finishing; a chair needs 3 hours of carpentry and 1 hour of finishing. Each week 240 carpentry "
    "hours and 100 finishing hours are available. Each table earns $70 profit and each chair $50."
)

HW1 = AssessmentSpec(
    key="hw1",
    title="HW1: Modeling & the Graphical Method",
    kind="homework",
    group="Homework",
    due=et(9, 11),
    module=ISE_WEEKS[2],
    state="graded",
    description=(
        "<p>Formulate and solve a two-variable product-mix LP. Upload a single PDF with your "
        "work. Show every corner point you evaluate.</p>"
    ),
    stems={
        "Q1": FURNITURE + " Formulate an LP that maximizes weekly profit.",
        "Q2": "Solve the LP from Q1 graphically.",
    },
    questions=(
        Q("Q1a", "Define the decision variables (with units).", 5, ("LO1",),
          "x₁ = tables built per week, x₂ = chairs built per week",
          (Err("vague_variables", 0.4, "x = furniture, y = profit",
               "Decision variables must be quantities you control, with units — 'x = furniture' doesn't say what is counted or over what period."),),
          difficulty=-0.1, parent="Q1"),
        Q("Q1b", "Write the objective function.", 5, ("LO1",),
          "max z = 70x₁ + 50x₂",
          (Err("wrong_sense", 0.4, "min z = 70x₁ + 50x₂",
               "This is a profit — the objective should be maximized, not minimized."),
           Err("coeff_swap", 0.6, "max z = 50x₁ + 70x₂",
               "Coefficients are swapped: tables earn $70 and chairs $50.")),
          parent="Q1"),
        Q("Q1c", "Write all constraints.", 10, ("LO1",),
          "4x₁ + 3x₂ ≤ 240 (carpentry); 2x₁ + x₂ ≤ 100 (finishing); x₁, x₂ ≥ 0",
          (Err("missing_nonneg", 0.7, "4x₁ + 3x₂ ≤ 240; 2x₁ + x₂ ≤ 100", NONNEG),
           Err("ineq_direction", 0.5, "4x₁ + 3x₂ ≥ 240; 2x₁ + x₂ ≥ 100; x₁, x₂ ≥ 0",
               "Resource limits are ≤ constraints: you can't use more than 240 carpentry hours."),
           Err("coeff_swap", 0.5, "4x₁ + 2x₂ ≤ 240; 3x₁ + x₂ ≤ 100; x₁, x₂ ≥ 0",
               "The carpentry row should use the carpentry hours of both products (4 and 3), not one product's two resources.")),
          difficulty=0.05, parent="Q1"),
        Q("Q2a", "List every corner point of the feasible region.", 8, ("LO3",),
          "(0, 0), (50, 0), (30, 40), (0, 80)",
          (Err("missed_corner", 0.5, "(0, 0), (50, 0), (0, 80)",
               "Only the axis intercepts were checked; the intersection (30, 40) of the two resource lines is also a corner point."),
           Err("arith", 0.6, "(0, 0), (50, 0), (30, 40), (0, 60)",
               "Arithmetic slip: the carpentry line meets the x₂-axis at 240/3 = 80, not 60.")),
          difficulty=0.05, parent="Q2"),
        Q("Q2b", "Give the optimal solution and its profit.", 6, ("LO3",),
          "x₁ = 30, x₂ = 40, z = $4,100",
          (Err("missed_corner", 0.3, "x₁ = 0, x₂ = 80, z = $4,000",
               "z = 4,100 at (30, 40) beats 4,000 at (0, 80); compare the objective at every corner point."),
           Err("arith", 0.6, "x₁ = 30, x₂ = 40, z = $4,300",
               "Right corner, but 70·30 + 50·40 = 4,100, not 4,300.")),
          parent="Q2"),
        Q("Q3", "Suppose the finishing constraint is removed. Is the LP still bounded? Give the new optimum.", 6, ("LO3",),
          "Still bounded: carpentry limits both products. New optimum x₁ = 60, x₂ = 0, z = $4,200.",
          (Err("unbounded_confusion", 0.3, "Unbounded — without finishing there is no limit on production.",
               "Removing one constraint doesn't make the LP unbounded: carpentry hours (4x₁ + 3x₂ ≤ 240) still bound both variables."),
           Err("missed_corner", 0.5, "Bounded; optimum stays at (30, 40).",
               "Without the finishing row, (30, 40) is no longer a corner point; the optimum moves to (60, 0) with z = 4,200.")),
          difficulty=0.15),
    ),
)

QUIZ1 = AssessmentSpec(
    key="quiz1",
    title="Quiz 1: Formulation",
    kind="quiz",
    group="Quizzes",
    due=et(9, 18),
    module=ISE_WEEKS[2],
    state="graded",
    description="<p>Five questions on LP formulation and graphical solutions. One attempt, 20 minutes.</p>",
    questions=(
        Q("1", "Which is a valid decision variable for a diet problem?", 2, ("LO1",),
          "xⱼ = ounces of food j in the daily diet",
          (Err("vague_variables", 0, "x = healthy food",
               "A decision variable needs a quantity and units, e.g. ounces of food j per day."),
           Err("var_is_parameter", 0, "xⱼ = cost of food j",
               "The cost of a food is given data (a parameter), not something you decide.")),
          qtype="multiple_choice",
          choices=("xⱼ = ounces of food j in the daily diet", "x = healthy food", "xⱼ = cost of food j", "x = total calories")),
        Q("2", "True or false: every LP with a nonempty feasible region has an optimal solution.", 2, ("LO3",),
          "False",
          (Err("unbounded_confusion", 0, "True",
               "A feasible LP can still be unbounded — e.g. max x₁ with only x₁ ≥ 0."),),
          qtype="true_false", choices=("True", "False")),
        Q("3", "For max z = 3x₁ + 2x₂ subject to x₁ + x₂ ≤ 4, x₁ + 3x₂ ≤ 6, x₁, x₂ ≥ 0, what is the optimal value of z?", 2, ("LO3",),
          "12",
          (Err("missed_corner", 0, "11",
               "(3, 1) gives 11, but the corner (4, 0) gives 12 — check every corner point."),
           Err("arith", 0, "14", "No feasible corner reaches 14; recheck the intercepts.")),
          difficulty=0.1, qtype="numerical"),
        Q("4", "If an LP has an optimal solution, at least one optimal solution occurs at:", 2, ("LO3",),
          "a corner point of the feasible region",
          (Err("missed_corner", 0, "the center of the feasible region",
               "LP optima are attained at extreme (corner) points, never only in the interior."),
           Err("arith", 0, "where the objective line crosses an axis",
               "The objective line's intercepts depend on z; the optimum is at a corner of the feasible region.")),
          difficulty=-0.1, qtype="multiple_choice",
          choices=("a corner point of the feasible region", "the center of the feasible region",
                   "where the objective line crosses an axis", "any point on the boundary")),
        Q("5", "Which constraint models “at least 30% of production must be chairs (x₂)”?", 2, ("LO1",),
          "−0.3x₁ + 0.7x₂ ≥ 0",
          (Err("ratio_constraint", 0, "x₂ ≥ 0.3",
               "A percentage requirement compares x₂ to total production: x₂ ≥ 0.3(x₁ + x₂)."),
           Err("ineq_direction", 0, "x₂ ≤ 0.3(x₁ + x₂)",
               "“At least” means ≥, not ≤.")),
          difficulty=0.15, qtype="multiple_choice",
          choices=("−0.3x₁ + 0.7x₂ ≥ 0", "x₂ ≥ 0.3", "x₂ ≤ 0.3(x₁ + x₂)", "0.3x₂ ≥ x₁ + x₂")),
    ),
)

HW2 = AssessmentSpec(
    key="hw2",
    title="HW2: Standard Form & Simplex",
    kind="homework",
    group="Homework",
    due=et(9, 25),
    module=ISE_WEEKS[4],
    state="graded",
    description=(
        "<p>Convert an LP to standard form, run the simplex method by hand and formulate a "
        "blending model. Graded with the rubric below.</p>"
    ),
    stems={
        "Q1": "Convert to standard form: min z = 2x₁ − 3x₂ subject to x₁ + x₂ ≤ 8, 2x₁ − x₂ ≥ 2, x₁ ≥ 0, x₂ free.",
        "Q2": "Solve with the simplex method: max z = 5x₁ + 4x₂ subject to 6x₁ + 4x₂ ≤ 24, x₁ + 2x₂ ≤ 6, x₁, x₂ ≥ 0.",
    },
    questions=(
        Q("Q1a", "Rewrite both constraints as equalities.", 5, ("LO2",),
          "x₁ + x₂ + s₁ = 8; 2x₁ − x₂ − s₂ = 2; s₁, s₂ ≥ 0",
          (Err("slack_sign", 0.4, "x₁ + x₂ + s₁ = 8; 2x₁ − x₂ + s₂ = 2", SLACK_SIGN),
           Err("missing_nonneg", 0.6, "x₁ + x₂ + s₁ = 8; 2x₁ − x₂ − s₂ = 2",
               "Slack and surplus variables must be non-negative too — add s₁, s₂ ≥ 0.")),
          parent="Q1"),
        Q("Q1b", "Handle the free variable and write the objective in max form.", 5, ("LO2",),
          "x₂ = x₂⁺ − x₂⁻ with x₂⁺, x₂⁻ ≥ 0; max −z = −2x₁ + 3x₂⁺ − 3x₂⁻",
          (Err("free_variable", 0.2, "add x₂ ≥ 0; max −z = −2x₁ + 3x₂",
               "x₂ is free: replace it by x₂⁺ − x₂⁻ with both parts ≥ 0; you cannot just add x₂ ≥ 0."),
           Err("objective_negation", 0.5, "x₂ = x₂⁺ − x₂⁻; max −z = −2x₁ − 3x₂⁺ + 3x₂⁻",
               "Converting min to max negates every coefficient: −(2x₁ − 3x₂) = −2x₁ + 3x₂⁺ − 3x₂⁻.")),
          difficulty=0.1, parent="Q1"),
        Q("Q2a", "Set up the initial tableau and choose the entering and leaving variables.", 8, ("LO4",),
          "Entering x₁ (most negative z-row coefficient, −5); ratios 24/6 = 4 and 6/1 = 6, so s₁ leaves.",
          (Err("entering_rule", 0.5, "Entering x₂; s₂ leaves.",
               "In the z-row form (z − 5x₁ − 4x₂ = 0), pick the most negative coefficient: x₁ enters, not x₂."),
           Err("ratio_test", 0.5, "Entering x₁; s₂ leaves.",
               "The ratio test picks the smallest ratio: 24/6 = 4 < 6/1 = 6, so s₁ leaves, not s₂.")),
          parent="Q2"),
        Q("Q2b", "Perform pivots until the tableau is optimal. Show each tableau.", 9, ("LO4",),
          "Pivot 1 on row s₁; pivot 2: x₂ enters, s₂ leaves (ratio 2 / (4/3) = 1.5). Final: x₁ = 3, x₂ = 1.5.",
          (Err("pivot_arith", 0.6, "Final: x₁ = 3, x₂ = 2.",
               "Row-operation error in the second pivot: the updated s₂ row should be (0, 4/3, −1/6, 1 | 2)."),
           Err("ratio_test", 0.5, "Pivot 2: x₂ enters, x₁ leaves (ratio 6).",
               "Minimum ratio in the second pivot is 2 / (4/3) = 1.5 on the s₂ row, not 4 / (2/3) = 6.")),
          difficulty=0.15, parent="Q2"),
        Q("Q2c", "State the optimal solution, the optimal value and which constraints are binding.", 8, ("LO4",),
          "x₁ = 3, x₂ = 1.5, z = 21; both constraints binding (s₁ = s₂ = 0).",
          (Err("optimality_check", 0.4, "x₁ = 4, x₂ = 0, z = 20 (stopped after one pivot).",
               "That tableau isn't optimal yet: the z-row still has a negative coefficient (−2/3 under x₂)."),
           Err("read_solution", 0.6, "x₁ = 1.5, x₂ = 3, z = 19.5.",
               "Basic variable values come from the RHS of their own rows: x₁ = 3 and x₂ = 1.5, not swapped.")),
          parent="Q2"),
        Q("Q3", "A refinery blends light (L) and heavy (H) crude into 1,000 barrels of fuel. At least 40% must be light crude, light costs $60/bbl and heavy $45/bbl, and at most 700 bbl of light crude is available. Formulate a minimum-cost LP.", 15, ("LO1",),
          "min 60L + 45H s.t. L + H = 1000; L ≥ 0.4(L + H); L ≤ 700; L, H ≥ 0",
          (Err("ratio_constraint", 0.6, "min 60L + 45H s.t. L + H = 1000; L ≥ 0.4; L ≤ 700; L, H ≥ 0",
               "A blending requirement like “at least 40% light crude” must be written as L ≥ 0.4(L + H), not L ≥ 0.4."),
           Err("missing_nonneg", 0.8, "min 60L + 45H s.t. L + H = 1000; L ≥ 0.4(L + H); L ≤ 700", NONNEG.replace("x₁, x₂", "L, H")),
           Err("ineq_direction", 0.6, "min 60L + 45H s.t. L + H ≥ 1000; L ≤ 0.4(L + H); L ≤ 700; L, H ≥ 0",
               "“At least 40% light” is a ≥ constraint on L; as written the model allows almost no light crude.")),
          difficulty=0.1),
    ),
    rubric=(
        Criterion("c1", "Standard form (Q1)", "Equalities with correctly signed slack/surplus variables, free-variable substitution and max-form objective.", ("Q1a", "Q1b"), "LO2"),
        Criterion("c2", "Simplex iterations (Q2)", "Correct entering/leaving choices, accurate pivots and a correctly read optimal tableau.", ("Q2a", "Q2b", "Q2c"), "LO4"),
        Criterion("c3", "Blending model (Q3)", "Complete, correctly directed constraints including the percentage requirement and non-negativity.", ("Q3",), "LO1"),
    ),
)

QUIZ2 = AssessmentSpec(
    key="quiz2",
    title="Quiz 2: Simplex Mechanics",
    kind="quiz",
    group="Quizzes",
    due=et(10, 2),
    module=ISE_WEEKS[5],
    state="graded",
    description="<p>Standard form and simplex mechanics. One attempt, 20 minutes.</p>",
    questions=(
        Q("1", "To convert 3x₁ + 2x₂ ≥ 12 to an equality in standard form, you:", 2, ("LO2",),
          "subtract a surplus variable s ≥ 0",
          (Err("slack_sign", 0, "add a slack variable s ≥ 0", SLACK_SIGN),
           Err("rhs_sign", 0, "multiply by −1 and add a slack variable",
               "That gives a negative right-hand side (−12); standard form needs b ≥ 0.")),
          qtype="multiple_choice",
          choices=("subtract a surplus variable s ≥ 0", "add a slack variable s ≥ 0",
                   "multiply by −1 and add a slack variable", "drop the constraint")),
        Q("2", "True or false: in standard form every variable, including slack and surplus variables, is non-negative.", 2, ("LO2",),
          "True",
          (Err("missing_nonneg", 0, "False", "All variables in standard form — slacks included — are ≥ 0."),),
          difficulty=-0.1, qtype="true_false", choices=("True", "False")),
        Q("3", "The z-row of a max problem is z − 3x₁ − 5x₂ + 0s₁ = 0. Which variable enters?", 2, ("LO4",),
          "x₂",
          (Err("entering_rule", 0, "x₁",
               "Pick the most negative coefficient in the z-row: −5 (x₂), not the first one listed."),
           Err("optimality_check", 0, "None — the tableau is optimal",
               "Negative z-row coefficients mean the tableau is not yet optimal.")),
          qtype="multiple_choice", choices=("x₂", "x₁", "s₁", "None — the tableau is optimal")),
        Q("4", "The entering column has entries (2, −1, 4) and the right-hand side is (10, 6, 12). What is the minimum ratio?", 2, ("LO4",),
          "3",
          (Err("ratio_test_negative", 0, "-6",
               "Ratios are only taken over positive column entries; −1 is skipped."),
           Err("ratio_test", 0, "5", "12/4 = 3 is smaller than 10/2 = 5.")),
          difficulty=0.1, qtype="numerical"),
        Q("5", "If the entering column has no positive entries, the LP is:", 2, ("LO4",),
          "unbounded",
          (Err("degeneracy_confusion", 0, "degenerate",
               "Degeneracy is a zero RHS in the ratio test; no positive entries means the LP is unbounded."),
           Err("unbounded_confusion", 0, "infeasible",
               "Infeasibility can't appear mid-simplex from a feasible basis; no positive entries means unbounded.")),
          difficulty=0.05, qtype="multiple_choice",
          choices=("unbounded", "infeasible", "degenerate", "has multiple optima")),
    ),
)

BAKERY = (
    "Scarlet Bakery bakes bagels and muffins. A dozen bagels uses 2 kg of flour and 1 hour of oven "
    "time; a dozen muffins uses 1 kg of flour and 1 hour of oven time. Each day 40 kg of flour and "
    "30 oven hours are available, and at least 5 dozen muffins must be baked. Profit is $9 per "
    "dozen bagels and $7 per dozen muffins."
)

MIDTERM = AssessmentSpec(
    key="midterm",
    title="Midterm Exam",
    kind="exam",
    group="Midterm",
    due=et(10, 14, 11, 20),
    module=ISE_WEEKS[5],
    state="graded",
    description=(
        "<p>In-class written exam, 80 minutes, covering Weeks 1–5. Graded papers were scanned; "
        "per-question scores and comments are shown with your scan.</p>"
    ),
    stems={
        "Q1": BAKERY + " Formulate an LP that maximizes daily profit.",
        "Q2": "Convert to standard form: max z = x₁ + 4x₂ subject to −x₁ + x₂ ≤ 3, 3x₁ + x₂ ≥ 6, x₁ ≥ 0, x₂ free.",
        "Q3": "Simplex: max z = 2x₁ + 3x₂ subject to x₁ + 2x₂ ≤ 8, 3x₁ + 2x₂ ≤ 12, x₁, x₂ ≥ 0.",
        "Q4": "Graphical method: max z = 5x₁ + 5x₂ subject to x₁ + x₂ ≤ 8, x₁ ≤ 5, x₂ ≤ 6, x₁, x₂ ≥ 0.",
    },
    pages={"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4},
    questions=(
        Q("Q1a", "Define the decision variables.", 8, ("LO1",),
          "x₁ = dozens of bagels per day, x₂ = dozens of muffins per day",
          (Err("vague_variables", 0.5, "x₁ = bagels, x₂ = muffins",
               "Give units and a period: dozens per day."),),
          difficulty=-0.1, parent="Q1"),
        Q("Q1b", "Write the objective function.", 8, ("LO1",),
          "max z = 9x₁ + 7x₂",
          (Err("wrong_sense", 0.4, "min z = 9x₁ + 7x₂", "Profit is maximized, not minimized."),
           Err("coeff_swap", 0.6, "max z = 7x₁ + 9x₂", "Coefficients are swapped: bagels earn $9 per dozen.")),
          parent="Q1"),
        Q("Q1c", "Write all constraints.", 14, ("LO1",),
          "2x₁ + x₂ ≤ 40; x₁ + x₂ ≤ 30; x₂ ≥ 5; x₁, x₂ ≥ 0",
          (Err("missing_nonneg", 0.75, "2x₁ + x₂ ≤ 40; x₁ + x₂ ≤ 30; x₂ ≥ 5", NONNEG),
           Err("ineq_direction", 0.55, "2x₁ + x₂ ≤ 40; x₁ + x₂ ≤ 30; x₂ ≤ 5; x₁, x₂ ≥ 0",
               "“At least 5 dozen muffins” is x₂ ≥ 5, not ≤."),
           Err("coeff_swap", 0.6, "x₁ + 2x₂ ≤ 40; x₁ + x₂ ≤ 30; x₂ ≥ 5; x₁, x₂ ≥ 0",
               "Flour use is 2 kg per dozen bagels and 1 kg per dozen muffins: 2x₁ + x₂ ≤ 40.")),
          difficulty=0.05, parent="Q1"),
        Q("Q2a", "Write the constraints as equalities with slack/surplus variables.", 10, ("LO2",),
          "−x₁ + x₂ + s₁ = 3; 3x₁ + x₂ − s₂ = 6; s₁, s₂ ≥ 0",
          (Err("slack_sign", 0.4, "−x₁ + x₂ + s₁ = 3; 3x₁ + x₂ + s₂ = 6", SLACK_SIGN),
           Err("missing_nonneg", 0.7, "−x₁ + x₂ + s₁ = 3; 3x₁ + x₂ − s₂ = 6",
               "Slack and surplus variables must be non-negative too — add s₁, s₂ ≥ 0.")),
          difficulty=0.05, parent="Q2"),
        Q("Q2b", "Handle the free variable x₂ and rewrite the objective.", 10, ("LO2",),
          "x₂ = x₂⁺ − x₂⁻, x₂⁺, x₂⁻ ≥ 0; max z = x₁ + 4x₂⁺ − 4x₂⁻",
          (Err("free_variable", 0.2, "x₂ ≥ 0; max z = x₁ + 4x₂",
               "x₂ is free: substitute x₂⁺ − x₂⁻ instead of assuming x₂ ≥ 0."),
           Err("objective_negation", 0.6, "x₂ = x₂⁺ − x₂⁻; max z = x₁ + 4x₂⁺ + 4x₂⁻",
               "Substituting x₂ = x₂⁺ − x₂⁻ gives 4x₂⁺ − 4x₂⁻; the second term is negative.")),
          difficulty=0.15, parent="Q2"),
        Q("Q3a", "Choose the entering and leaving variables for the first pivot.", 10, ("LO4",),
          "x₂ enters (−3); ratios 8/2 = 4, 12/2 = 6, so s₁ leaves.",
          (Err("entering_rule", 0.5, "x₁ enters; s₂ leaves.",
               "The most negative z-row coefficient is −3 (x₂), so x₂ enters."),
           Err("ratio_test", 0.5, "x₂ enters; s₂ leaves.", "Minimum ratio is 8/2 = 4 (row s₁), not 12/2 = 6.")),
          parent="Q3"),
        Q("Q3b", "Carry out pivots to optimality.", 10, ("LO4",),
          "Pivot 2: x₁ enters, s₂ leaves. Optimal x₁ = 2, x₂ = 3.",
          (Err("pivot_arith", 0.5, "Optimal x₁ = 2, x₂ = 4.",
               "Check the second pivot: after updating, the x₂ row is (0, 1, 3/4, −1/4 | 3)."),
           Err("ratio_test", 0.5, "Pivot 2: x₁ enters, x₂ leaves (ratio 8).",
               "Minimum ratio in the second pivot is 4 / 2 = 2 on the s₂ row, not 4 / (1/2) = 8.")),
          difficulty=0.2, parent="Q3"),
        Q("Q3c", "State the optimal solution and value; explain how you know it is optimal.", 10, ("LO4",),
          "x₁ = 2, x₂ = 3, z = 13; optimal because all z-row coefficients are ≥ 0.",
          (Err("optimality_check", 0.4, "x₁ = 0, x₂ = 4, z = 12 — optimal after one pivot.",
               "After the first pivot the z-row still has −1/2 under x₁, so it isn't optimal."),
           Err("read_solution", 0.6, "x₁ = 3, x₂ = 2, z = 12.",
               "Read basic values from each variable's own row: x₁ = 2, x₂ = 3.")),
          difficulty=0.1, parent="Q3"),
        Q("Q4a", "List the corner points of the feasible region.", 10, ("LO3",),
          "(0, 0), (5, 0), (5, 3), (2, 6), (0, 6)",
          (Err("missed_corner", 0.5, "(0, 0), (5, 0), (0, 6)",
               "The lines x₁ + x₂ = 8 with x₁ = 5 and with x₂ = 6 create corners (5, 3) and (2, 6)."),
           Err("arith", 0.7, "(0, 0), (5, 0), (5, 4), (2, 6), (0, 6)",
               "x₁ = 5 meets x₁ + x₂ = 8 at x₂ = 3, not 4.")),
          parent="Q4"),
        Q("Q4b", "Find all optimal solutions and explain.", 10, ("LO3", "LO4"),
          "Every point on the segment between (2, 6) and (5, 3) is optimal with z = 40: the objective is parallel to x₁ + x₂ ≤ 8.",
          (Err("multiple_optima", 0.4, "Unique optimum (5, 3), z = 40.",
               "The objective 5x₁ + 5x₂ is parallel to the binding constraint x₁ + x₂ = 8, so the whole edge from (2, 6) to (5, 3) is optimal."),
           Err("degeneracy_confusion", 0.5, "The LP is degenerate, so there is no unique answer.",
               "Multiple optima come from a parallel objective, not degeneracy (a zero basic variable).")),
          difficulty=0.25, parent="Q4"),
    ),
)

HW3 = AssessmentSpec(
    key="hw3",
    title="HW3: Duality & Sensitivity",
    kind="homework",
    group="Homework",
    due=et(10, 30),
    module=ISE_WEEKS[7],
    state="early",
    description="<p>Form a dual, apply complementary slackness and interpret sensitivity results. Graded with the rubric below.</p>",
    stems={
        "Q1": "Primal: max z = 4x₁ + 3x₂ subject to 2x₁ + x₂ ≤ 10, x₁ + 3x₂ ≤ 15, x₁, x₂ ≥ 0.",
        "Q3": "Use the primal from Q1 and its optimal basis.",
    },
    questions=(
        Q("Q1a", "Write the dual LP.", 10, ("LO5",),
          "min w = 10y₁ + 15y₂ s.t. 2y₁ + y₂ ≥ 4, y₁ + 3y₂ ≥ 3, y₁, y₂ ≥ 0", parent="Q1"),
        Q("Q1b", "Use strong duality to give the dual optimal value.", 8, ("LO5",),
          "w* = z* = 24 (primal optimum x = (3, 4))", parent="Q1"),
        Q("Q2", "Given x* = (3, 4), use complementary slackness to find y*.", 12, ("LO5",),
          "Both x > 0, so both dual constraints are tight: y* = (9/5, 2/5)."),
        Q("Q3a", "What is the shadow price of the first resource? Interpret it.", 10, ("LO6",),
          "y₁* = 1.8: one more unit of resource 1 raises z by about 1.8.", parent="Q3"),
        Q("Q3b", "Over what range of c₁ does the current basis stay optimal?", 10, ("LO6",),
          "1 ≤ c₁ ≤ 6", parent="Q3"),
    ),
    rubric=(
        Criterion("c1", "Dual formulation (Q1)", "Correct dual objective, transposed constraints with the right directions, and the strong-duality value.", ("Q1a", "Q1b"), "LO5"),
        Criterion("c2", "Complementary slackness (Q2)", "Uses tight dual constraints for positive primal variables and solves for y*.", ("Q2",), "LO5"),
        Criterion("c3", "Sensitivity (Q3)", "Correct shadow price with interpretation and a correct optimality range.", ("Q3a", "Q3b"), "LO6"),
    ),
)

QUIZ3 = AssessmentSpec(
    key="quiz3",
    title="Quiz 3: Duality",
    kind="quiz",
    group="Quizzes",
    due=et(11, 6),
    module=ISE_WEEKS[8],
    state="upcoming",
    description="<p>Duality and sensitivity. Opens after the HW3 deadline.</p>",
    questions=(
        Q("1", "The dual of a minimization LP with ≥ constraints and non-negative variables is:", 2, ("LO5",),
          "a maximization LP with ≤ constraints", qtype="multiple_choice",
          choices=("a maximization LP with ≤ constraints", "a minimization LP with ≥ constraints",
                   "a maximization LP with ≥ constraints", "the same LP")),
        Q("2", "True or false: any feasible dual solution gives an upper bound on a max primal's optimal value.", 2, ("LO5",),
          "True", qtype="true_false", choices=("True", "False")),
        Q("3", "A resource has shadow price 2.5. If 4 more units are added (within range), by how much does z change?", 2, ("LO6",),
          "10", qtype="numerical"),
        Q("4", "The reduced cost of a non-basic variable measures:", 2, ("LO6",),
          "how much its objective coefficient must improve before it enters the basis", qtype="multiple_choice",
          choices=("how much its objective coefficient must improve before it enters the basis",
                   "the value of one more unit of a resource", "the variable's current value", "the slack in its constraint")),
        Q("5", "True or false: if a primal constraint has positive slack at the optimum, its dual variable is zero.", 2, ("LO5",),
          "True", qtype="true_false", choices=("True", "False")),
    ),
)


def _deck(key: str, week: int, title: str, *slides: tuple[str, tuple[str, ...]]) -> Material:
    return Material(key, f"Lecture {week}: {title}", "slides", week, slides)


ISE_MATERIALS = (
    _deck("w01_intro", 1, "Introduction & LP Modeling",
          ("What is linear optimization?", ("Decisions, objective, constraints", "Linearity and divisibility assumptions", "Examples: product mix, diet, blending")),
          ("Building a model", ("1. Define decision variables with units", "2. Write the objective", "3. Write every constraint, including x >= 0")),
          ("Common pitfalls", ("Vague variables (\"x = furniture\")", "Percentages: x2 >= 0.3(x1 + x2), not x2 >= 0.3", "Forgetting non-negativity"))),
    _deck("w02_graphical", 2, "The Graphical Method",
          ("Feasible regions", ("Plot each constraint as a half-plane", "The feasible region is their intersection")),
          ("Corner-point theorem", ("If an optimum exists, one is at a corner point", "Evaluate z at every corner, including line intersections")),
          ("Special cases", ("Unbounded: the region extends in an improving direction", "Multiple optima: objective parallel to a binding edge", "Infeasible: empty region"))),
    _deck("w03_standard_form", 3, "Standard Form",
          ("Why standard form?", ("Simplex needs equalities and x >= 0", "Right-hand sides b >= 0")),
          ("Slack and surplus", ("<= constraint: add slack s >= 0", ">= constraint: subtract surplus s >= 0")),
          ("Free variables and min problems", ("x free: x = x+ - x-, both >= 0", "min z = max (-z): negate every coefficient"))),
    _deck("w04_simplex1", 4, "The Simplex Method I",
          ("The tableau", ("Basic and non-basic variables", "z-row: z - c x = 0")),
          ("Pivot rules", ("Entering: most negative z-row coefficient (max problem)", "Leaving: minimum ratio over positive column entries")),
          ("Pivoting", ("Scale the pivot row", "Eliminate the column from every other row, including z"))),
    _deck("w05_simplex2", 5, "The Simplex Method II",
          ("Optimality", ("Stop when every z-row coefficient is >= 0", "Read basic values from the RHS column")),
          ("Degeneracy", ("A basic variable equal to 0", "Ties in the ratio test; possible cycling")),
          ("Two-phase method", ("Phase I: minimise artificial variables", "Phase II: original objective from a feasible basis"))),
    _deck("w06_duality", 6, "Duality",
          ("Constructing the dual", ("One dual variable per primal constraint", "Transpose the constraint matrix", "Max with <= gives min with >=")),
          ("Weak and strong duality", ("Any feasible dual bounds the primal", "At optimality z* = w*"))),
    _deck("w07_complementary", 7, "Complementary Slackness",
          ("The conditions", ("Primal slack > 0 implies dual variable = 0", "Primal variable > 0 implies dual constraint is tight")),
          ("Using it", ("Recover y* from x* by solving the tight constraints", "Check feasibility of the result"))),
    _deck("w08_sensitivity", 8, "Sensitivity Analysis",
          ("Shadow prices", ("Dual value = change in z per unit of resource", "Valid only within the RHS range")),
          ("Reduced costs", ("How much c_j must improve before x_j enters", "Not the same as a shadow price")),
          ("Ranging", ("Objective coefficient ranges keep the basis optimal", "Compare objective slope with binding constraint slopes"))),
    Material("r_formulation", "Reading: A Guide to LP Formulation", "reading", 1,
             (("Reading", ("Worked examples of product-mix, diet and blending models.", "Checklist: units, objective sense, constraint direction, non-negativity.")),)),
    Material("r_simplex_example", "Reading: Simplex Worked Example", "reading", 4,
             (("Reading", ("A full three-tableau example with every row operation shown.", "Margin notes on the ratio test and on reading the final tableau.")),)),
    Material("r_duality_notes", "Reading: Duality Notes", "reading", 6,
             (("Reading", ("Primal-dual table for converting any LP.", "Proof sketch of weak duality and an economic interpretation of y.")),)),
)

ISE = CourseSpec(
    canvas_id=48213,
    code="ISE 3200",
    name="Linear Optimization",
    term="Autumn 2026",
    start=et(8, 24, 8, 0),
    end=et(12, 11),
    weighted=True,
    groups=(("Homework", 30), ("Quizzes", 20), ("Midterm", 25), ("Final Exam", 25)),
    outcomes=ISE_OUTCOMES,
    weeks=ISE_WEEKS,
    assessments=(HW1, QUIZ1, HW2, QUIZ2, MIDTERM, HW3, QUIZ3),
    materials=ISE_MATERIALS,
    syllabus_intro=(
        "<p>ISE 3200 introduces linear optimization: how to model decisions as linear programs, "
        "solve them graphically and with the simplex method, and interpret the answers through "
        "duality and sensitivity analysis.</p>"
        "<p><strong>Meetings:</strong> Mon/Wed 10:20–11:40, Hitchcock Hall 031. "
        "<strong>Office hours:</strong> Tue 2–4 pm, Baker Systems 280.</p>"
    ),
)

# --------------------------------------------------------------------------------------------
# STAT 1450 – lightly populated second course
# --------------------------------------------------------------------------------------------

STAT_HW = AssessmentSpec(
    key="stat_hw1",
    title="Homework 1: Describing Data",
    kind="homework",
    group="Assignments",
    due=et(9, 18),
    module="Week 2: Describing Data",
    state="graded",
    description="<p>Summaries and plots for a small data set.</p>",
    questions=(
        Q("Q1", "Find the mean and median of 4, 7, 7, 9, 23.", 10, ("S1",),
          "Mean 10, median 7",
          (Err("mean_median", 0.5, "Mean 7, median 10", "Mean and median are swapped: the mean is 50/5 = 10."),)),
        Q("Q2", "Which summary is more appropriate for these data, and why?", 10, ("S1",),
          "The median: 23 is an outlier that pulls the mean up.",
          (Err("outlier", 0.5, "The mean, because it uses every value.",
               "The outlier 23 inflates the mean; the median better reflects a typical value."),)),
    ),
)

STAT_QUIZ = AssessmentSpec(
    key="stat_quiz1",
    title="Quiz 1: Probability Basics",
    kind="quiz",
    group="Assignments",
    due=et(11, 4),
    module="Week 3: Probability",
    state="upcoming",
    description="<p>Three short probability questions.</p>",
    questions=(
        Q("1", "A fair die is rolled. What is P(even)?", 2, ("S2",), "0.5", qtype="numerical"),
        Q("2", "True or false: P(A or B) = P(A) + P(B) for any events A and B.", 2, ("S2",), "False",
          qtype="true_false", choices=("True", "False")),
        Q("3", "Two fair coins are tossed. What is P(two heads)?", 2, ("S2",), "0.25", qtype="numerical"),
    ),
)

STAT = CourseSpec(
    canvas_id=48190,
    code="STAT 1450",
    name="Introduction to Statistical Reasoning",
    term="Autumn 2026",
    start=et(8, 24, 8, 0),
    end=et(12, 11),
    weighted=False,
    groups=(("Assignments", 0),),
    outcomes=(
        Outcome("S1", "Describe data", "Summarise data with appropriate measures of centre and spread."),
        Outcome("S2", "Reason about probability", "Compute and interpret basic probabilities."),
    ),
    weeks={2: "Week 2: Describing Data", 3: "Week 3: Probability"},
    assessments=(STAT_HW, STAT_QUIZ),
    materials=(
        Material("stat_r1", "Reading: Measures of Centre", "reading", 2,
                 (("Reading", ("Mean, median and mode, and when each is appropriate.", "Effect of outliers on the mean.")),)),
    ),
    syllabus_intro="<p>An introduction to describing data and reasoning with probability.</p>",
)

COURSES = (ISE, STAT)

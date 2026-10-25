from tutor.models import Assessment, Mode
from tutor.policy import MODE_RULES, decide_mode


def a(status: str, released: bool = False, code: str = "Quiz 2") -> Assessment:
    return Assessment(id=f"id-{code}", code=code, title=code, integrity_status=status, answers_released=released)


def test_no_assessment_is_independent_study():
    assert decide_mode("student", None, []).mode is Mode.STUDY


def test_assessment_status_maps_to_mode():
    assert decide_mode("student", a("active_protected"), []).mode is Mode.PROTECTED
    assert decide_mode("student", a("guided_homework"), []).mode is Mode.GUIDED
    assert decide_mode("student", a("released"), []).mode is Mode.STUDY


def test_closed_without_released_answers_stays_guided():
    assert decide_mode("student", a("closed", released=False), []).mode is Mode.GUIDED
    assert decide_mode("student", a("closed", released=True), []).mode is Mode.STUDY


def test_message_matching_a_protected_item_overrides_a_looser_target():
    decision = decide_mode("student", a("released", code="Quiz 1"), [a("active_protected", code="Quiz 2")])
    assert decision.mode is Mode.PROTECTED
    assert decision.assessment_id == "id-Quiz 2"


def test_unknown_status_or_role_fails_closed():
    assert decide_mode("student", a("something_new"), []).mode is Mode.PROTECTED
    assert decide_mode("guest", None, []).mode is Mode.PROTECTED


def test_staff_preview_is_independent_study():
    assert decide_mode("instructor", a("active_protected"), []).mode is Mode.STUDY


def test_mode_rules_restrict_moves_and_hints():
    assert "explanation" in MODE_RULES[Mode.PROTECTED].moves
    assert "hint" not in MODE_RULES[Mode.PROTECTED].moves
    assert MODE_RULES[Mode.PROTECTED].max_hint == 0
    assert "explanation" not in MODE_RULES[Mode.GUIDED].moves
    assert MODE_RULES[Mode.GUIDED].max_hint == 3

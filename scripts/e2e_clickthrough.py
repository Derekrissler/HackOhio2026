"""Click through every Canvas tab as the teacher and as a student, in a real browser.

Run with the webapp-testing helper, which starts and stops both servers:

    apps/api/.venv/Scripts/python .claude/skills/webapp-testing/scripts/with_server.py \
      --server "cd apps/api && .venv/Scripts/python -m uvicorn app.main:app --port 8010" --port 8010 \
      --server "cd apps/web && API_PROXY_TARGET=http://127.0.0.1:8010 npx vite --port 5180 --strictPort" --port 5180 \
      -- apps/api/.venv/Scripts/python scripts/e2e_clickthrough.py

Uses the installed Microsoft Edge (no browser download). Screenshots go to $E2E_OUT
(default: a temp folder). Exits non-zero if any page has console errors, an error alert or
missing content.
"""

import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("E2E_BASE", "http://localhost:5180")
OUT = Path(os.environ.get("E2E_OUT", tempfile.mkdtemp(prefix="e2e-")))
ISE, STAT = 2, 1
TEACHER, ALEX = 1, 2


@dataclass
class Check:
    path: str
    expect: list[str] = field(default_factory=list)  # text that must appear in <main>
    selector: str | None = None  # an element that must exist
    allow_403: bool = False


failures: list[str] = []


def api(page: Page, user: int, path: str):
    res = page.request.get(f"{BASE}/api{path}", headers={"X-Demo-User": str(user)})
    assert res.ok, f"{path} → {res.status}"
    return res.json()


def visit(page: Page, user: int, name: str, check: Check, errors: list[str]) -> None:
    errors.clear()
    page.goto(f"{BASE}{check.path}")
    page.wait_for_load_state("networkidle")
    main = page.locator("main")
    text = main.inner_text()
    problems = []
    if not page.locator("main h1").count():
        problems.append("no <h1>")
    for phrase in check.expect:
        if phrase not in text:
            problems.append(f"missing text {phrase!r}")
    if check.selector and not page.locator(check.selector).count():
        problems.append(f"missing element {check.selector}")
    if re.search(r"Something went wrong|Not found\.", text) or ("Access denied" in text and not check.allow_403):
        problems.append("error alert shown")
    real_errors = [e for e in errors if not (check.allow_403 and "403" in e)]
    if real_errors:
        problems.append(f"console: {real_errors}")
    page.screenshot(path=OUT / f"{name}.png", full_page=True)
    status = "ok " if not problems else "FAIL"
    print(f"  {status} {check.path}{'  ' + '; '.join(problems) if problems else ''}")
    failures.extend(f"{name} {check.path}: {p}" for p in problems)


def run_as(page: Page, user: int, label: str, checks: dict[str, Check]) -> None:
    print(f"\n== {label} ==")
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.context.add_cookies([{"name": "demo_user", "value": str(user), "url": BASE}])
    page.add_init_script(f"localStorage.setItem('demoUserId', '{user}')")
    for name, check in checks.items():
        visit(page, user, f"{label}-{name}", check, errors)


def switch_user_via_tray(page: Page, course_path: str) -> None:
    """Search the role switcher for 'kim', pick Alex Kim, and check the nav becomes the student's."""
    print("\n== role switcher ==")
    page.goto(f"{BASE}{course_path}")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Account").click()
    box = page.get_by_label("Viewing as")
    box.click()
    box.fill("kim")
    options = page.get_by_role("option").all_inner_texts()
    if options != ["Alex Kim"]:
        failures.append(f"role switcher filter 'kim' showed {options}")
    page.get_by_role("option", name="Alex Kim").click()
    page.wait_for_load_state("networkidle")
    page.screenshot(path=OUT / "role-switch.png")
    nav = page.locator("nav[aria-label='Course navigation'] a").all_inner_texts()
    ok = "Learning Insights" in nav and "Instructor Analytics" not in nav
    print(f"  {'ok ' if ok else 'FAIL'} filtered to {options}, nav now {nav[-1]!r}")
    if not ok:
        failures.append(f"after switching to Alex Kim the nav is {nav}")


def ids(page: Page) -> dict[str, int]:
    groups = api(page, TEACHER, f"/courses/{ISE}/assignment_groups")
    by_title = {a["title"].split(":")[0]: a["id"] for g in groups for a in g["assessments"]}
    alex_mid = api(page, ALEX, f"/courses/{ISE}/assessments/{by_title['Midterm Exam']}")["my_submission"]["id"]
    alex_q1 = api(page, ALEX, f"/courses/{ISE}/assessments/{by_title['Quiz 1']}")["my_submission"]["id"]
    marcus_mid = next(s["id"] for s in api(page, TEACHER, f"/courses/{ISE}/assessments/{by_title['Midterm Exam']}/submissions")
                      if s["user_name"] == "Marcus Bell")
    files = api(page, TEACHER, f"/courses/{ISE}/materials")[0]["materials"][0]["file"]["id"]
    return {**by_title, "alex_midterm": alex_mid, "alex_quiz1": alex_q1, "marcus_midterm": marcus_mid, "first_file": files}


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.set_default_timeout(45_000)
        i = ids(page)
        c = f"/courses/{ISE}"
        common = {
            "dashboard": Check("/", ["Linear Optimization", "Introduction to Statistical Reasoning"]),
            "home": Check(c, ["Coming Up"]),
            "syllabus": Check(f"{c}/syllabus", ["Learning Objectives", "LO1", "Course Summary", "Midterm Exam"]),
            "assignments": Check(f"{c}/assignments", ["Homework", "30% of total", "HW1: Modeling"]),
            "hw2": Check(f"{c}/assignments/{i['HW2']}", ["Rubric", "Standard form (Q1)"]),
            "quizzes": Check(f"{c}/quizzes", ["Quiz 1: Formulation", "Quiz 3: Duality"]),
            "quiz1": Check(f"{c}/quizzes/{i['Quiz 1']}", ["Quiz 1: Formulation"]),
            "midterm-scan": Check(f"{c}/submissions/{i['alex_midterm']}", ["Question scores", "Q3b"], selector="iframe"),
            "quiz1-submission": Check(f"{c}/submissions/{i['alex_quiz1']}", ["Correct answer"]),
            "files": Check(f"{c}/files?file={i['first_file']}", ["Week 1: Introduction & LP Modeling"], selector="iframe"),
            "stat-home": Check(f"/courses/{STAT}", ["Introduction to Statistical Reasoning"]),
        }
        run_as(page, TEACHER, "teacher", {
            **common,
            "home": Check(c, ["To Do", "Grade HW3"]),
            "hw1": Check(f"{c}/assignments/{i['HW1']}", ["Submissions", "Alex Kim", "Answer key"]),
            "quiz3": Check(f"{c}/quizzes/{i['Quiz 3']}", ["(correct answer)", "Aligned outcomes"]),
            "gradebook": Check(f"{c}/grades", ["Gradebook", "Kim, Alex", "82.11%"]),
            "alex-grades": Check(f"{c}/grades/{ALEX}", ["Grades for Alex Kim", "82.11%"]),
            "marcus-private-note": Check(f"{c}/submissions/{i['marcus_midterm']}", ["Teacher only", "tutoring center"]),
            "analytics": Check(f"{c}/analytics", ["Coming in Phase 7"]),
        })
        switch_user_via_tray(page, c)
        page.close()

        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.set_default_timeout(45_000)
        run_as(page, ALEX, "student", {
            **common,
            "home": Check(c, ["Recent Feedback", "Coming Up", "HW3: Duality"]),
            "hw1": Check(f"{c}/assignments/{i['HW1']}", ["Your submission", "32 / 40"]),
            "hw3": Check(f"{c}/assignments/{i['HW3']}", ["Not graded yet", "Q1a"]),
            "quiz1": Check(f"{c}/quizzes/{i['Quiz 1']}", ["Your submission", "Your answer"]),
            "quiz3": Check(f"{c}/quizzes/{i['Quiz 3']}", ["Questions are shown after you take this quiz."]),
            "grades": Check(f"{c}/grades", ["Grades for Alex Kim", "82.11%", "Calculated from graded work only"]),
            "insights": Check(f"{c}/insights", ["Coming in Phase 6"]),
            "analytics-by-url": Check(f"{c}/analytics", ["Access denied"], allow_403=True),
        })
        nav = page.locator("nav[aria-label='Course navigation'] a").all_inner_texts()
        if "Instructor Analytics" in nav:
            failures.append("student nav shows Instructor Analytics")
        browser.close()

    print(f"\nScreenshots: {OUT}")
    if failures:
        print(f"{len(failures)} FAILURE(S):\n  " + "\n  ".join(failures))
        return 1
    print("All pages passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Build the VIBE 101 mock course from the markdown in ../CourseContent.

    python build_course.py        # writes fixtures/vibe101.json

Re-run after editing the markdown. Mapping:
  syllabus        -> course syllabus + "Syllabus" page
  textbook        -> one page per chapter + glossary page
  lecture slides  -> one PDF per lecture (one PDF page per slide)
  assignments     -> assignments with rubrics
  quizzes, exams  -> assignments (exams get a per-question rubric)
  written feedback-> graded submissions for the mock student (rubric notes + comment)
  schedule table  -> modules: Start Here, Week 1..14, Finals

Answer keys and the TA comment bank are instructor-only and are NOT copied into the course,
which is the student's view.
"""

import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "CourseContent"
OUT = HERE / "fixtures" / "vibe101.json"

COURSE_ID = 1001
TERM = "Spring 2026"
WEEK1_MONDAY = datetime(2026, 1, 12)
FINAL_EXAM_AT = datetime(2026, 4, 28, 10, 0)
SELF_USER = {"id": 5001, "name": "Test Student"}
STAFF = {"Dr. Quinn Ferrous": 9001, "Maya Okafor": 9002, "Dev Raman": 9003}
ROSTER = [
    {"id": 9001, "name": "Dr. Quinn Ferrous", "role": "Teacher", "section": "VIBE 101"},
    {"id": 9002, "name": "Maya Okafor", "role": "Teaching Assistant", "section": "VIBE 101"},
    {"id": 9003, "name": "Dev Raman", "role": "Teaching Assistant", "section": "VIBE 101"},
    {"id": 5001, "name": "Test Student", "role": "Student", "section": "VIBE 101"},
    {"id": 5002, "name": "Avery Chen", "role": "Student", "section": "VIBE 101"},
    {"id": 5003, "name": "Jordan Patel", "role": "Student", "section": "VIBE 101"},
    {"id": 5004, "name": "Morgan Williams", "role": "Student", "section": "VIBE 101"},
    {"id": 5005, "name": "Riley Thompson", "role": "Student", "section": "VIBE 101"},
    {"id": 5006, "name": "Casey Nguyen", "role": "Student", "section": "VIBE 101"},
    {"id": 5007, "name": "Samira Hassan", "role": "Student", "section": "VIBE 101"},
    {"id": 5008, "name": "Elliot Brooks", "role": "Student", "section": "VIBE 101"},
    {"id": 5009, "name": "Nia Robinson", "role": "Student", "section": "VIBE 101"},
    {"id": 5010, "name": "Leo Martinez", "role": "Student", "section": "VIBE 101"},
    {"id": 5011, "name": "Priya Shah", "role": "Student", "section": "VIBE 101"},
    {"id": 5012, "name": "Kai Anderson", "role": "Student", "section": "VIBE 101"},
    {"id": 5013, "name": "Isabel Rivera", "role": "Student", "section": "VIBE 101"},
    {"id": 5014, "name": "Noah Kim", "role": "Student", "section": "VIBE 101"},
    {"id": 5015, "name": "Zoe Campbell", "role": "Student", "section": "VIBE 101"},
]


def read(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def html(md: str) -> str:
    # Python-Markdown needs a blank line before a list; the course files often omit it.
    md = re.sub(r"^((?![ \t]*(?:[-*]|\d+\.)[ \t]).+)\n(?=[ \t]*(?:[-*]|\d+\.)[ \t])", r"\1\n\n", md, flags=re.M)
    return markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])


def chunks(text: str) -> list[str]:
    """Split a file on its horizontal rules (a line that is exactly ---)."""
    return [c.strip() for c in re.split(r"^---\s*$", text, flags=re.M) if c.strip()]


def cut(text: str, heading_re: str) -> str:
    """Drop everything from the first heading matching heading_re onward."""
    m = re.search(heading_re, text, flags=re.M)
    return text[:m.start()].rstrip() if m else text


def table_rows(text: str, after: str) -> list[list[str]]:
    """Body rows of the first markdown table following the `after` heading."""
    start = text.find(after)
    if start < 0:
        return []
    rows = []
    for line in text[start:].splitlines()[1:]:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not set("".join(cells)) <= set("-: "):
                rows.append(cells)
        elif rows:
            break
    return rows[1:]  # drop header


def due(week: int, hour=23, minute=59) -> str:
    """Thursday of the given week (lectures are Tue/Thu)."""
    d = WEEK1_MONDAY + timedelta(weeks=week - 1, days=3)
    return d.replace(hour=hour, minute=minute).isoformat()


def plain(md: str) -> str:
    """Markdown -> readable plain text (for comments and slide PDFs)."""
    t = re.sub(r"```\w*\n?", "", md)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    return t.strip()


def pdf_safe(text: str) -> str:
    """Slides are drawn with a Latin-1 PDF font, so swap symbols it can't show."""
    for a, b in {"`": "", "→": "->", "❌": "[no]", "✅": "[yes]", "⚠️": "(!)", "⚠": "(!)", "—": " - ", "–": "-",
                 "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "·": "-"}.items():
        text = text.replace(a, b)
    return unicodedata.normalize("NFKD", text).encode("latin-1", "ignore").decode("latin-1")


# ---------------------------------------------------------------- syllabus + textbook

def build_pages():
    syllabus_md = read("01_syllabus.md")
    pages = [{"url": "syllabus", "title": "Syllabus", "body": html(syllabus_md)}]

    book = read("02_textbook.md")
    for part in re.split(r"^(?=## )", book, flags=re.M)[1:]:
        title = part.splitlines()[0].lstrip("# ").strip()
        body = part.split("\n", 1)[1].strip().rstrip("-").strip()
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        pages.append({"url": slug, "title": f"Textbook {title}" if title.startswith("Chapter") else f"Textbook: {title}",
                      "body": html(body)})
    return syllabus_md, pages


# ---------------------------------------------------------------- slides

def build_slides():
    """Group slides into lectures; a slide titled 'Lecture N: ...' starts a new deck."""
    decks, current = [], None
    for slide in chunks(read("03_lecture_slides.md")):
        slide = re.sub(r"<!--.*?-->", "", slide, flags=re.S).strip()
        if not slide or slide.startswith("marp:"):
            continue
        m = re.search(r"Lecture (\d+): (.+)", slide)
        if m and (current is None or int(m.group(1)) != current["n"]):
            current = {"n": int(m.group(1)), "title": m.group(2).strip(), "slides": []}
            decks.append(current)
        current["slides"].append(pdf_safe(plain(slide)))
    files = []
    for d in decks:
        name = f"Lecture{d['n']:02d}-{re.sub(r'[^A-Za-z]+', '-', d['title']).strip('-')}.pdf"
        f = {"id": 300 + d["n"], "display_name": name, "title": f"Lecture {d['n']} slides: {d['title']}",
             "pages": d["slides"]}
        if (HERE / "fixtures" / "slides" / name).exists():  # designed deck (fixtures/slides/*.html), served as-is
            f["path"] = f"slides/{name}"
        files.append(f)
    return files


# ---------------------------------------------------------------- assignments, quizzes, exams

SUBMIT = {"assignment": ["online_upload"], "quiz": ["online_quiz"], "exam": ["on_paper"]}


def build_assignments():
    out = []
    text = read("04_assignments.md")
    general = chunks(text)[0].split("\n", 1)[1].strip()
    for n, part in enumerate(c for c in chunks(text) if c.startswith("## ")):
        title = part.splitlines()[0].lstrip("# ").strip()
        weeks = dict(re.findall(r"\*\*(Assigned|Proposal|Due):\*\* Week (\d+)", part))
        points = int(re.search(r"\*\*Points:\*\* (\d+)", part).group(1))
        rubric = [{"id": f"_r{i}", "description": crit, "points": int(pts)}
                  for i, (crit, pts) in enumerate(table_rows(part, "### Rubric"), 1)]
        body = cut(part.split("\n", 1)[1], r"^### (Rubric|Instructor Answer Key)")
        group = "Final Project" if title.startswith("Final Project") else "Assignments"
        out.append({
            "id": 2001 + n, "name": title, "points_possible": points, "due_at": due(int(weeks["Due"])),
            "assignment_group": group, "submission_types": SUBMIT["assignment"],
            "description": html(body + "\n\n---\n\n" + general), "rubric": rubric,
            "_weeks": {"open": int(weeks.get("Assigned") or weeks.get("Proposal")), "due": int(weeks["Due"])},
        })

    for n, part in enumerate(c for c in chunks(read("05_quizzes.md")) if c.startswith("## Quiz")):
        title = part.splitlines()[0].lstrip("# ").strip()
        week = int(re.search(r"\(Week (\d+)\)", title).group(1))
        key_text = part.split("### Answer Key", 1)[1] if "### Answer Key" in part else ""
        answer_key = {int(number): ord(letter) - ord("A")
                      for number, letter in re.findall(r"(?:^|\s)(\d+)\.\s*([A-D])\b", key_text)}
        out.append({
            "id": 2101 + n, "name": re.sub(r"\s*\(Week \d+\)", "", title),
            "points_possible": int(re.search(r"Total: (\d+) points", part).group(1)), "due_at": due(week, 12, 30),
            "assignment_group": "Quizzes", "submission_types": SUBMIT["quiz"],
            "description": html(cut(part.split("\n", 1)[1], r"^### Answer Key")), "rubric": [],
            "_answer_key": answer_key,
            "_weeks": {"open": week, "due": week},
        })

    preface = chunks(read("06_exams.md"))[0].split("\n", 1)[1].strip()
    for part in (c for c in chunks(read("06_exams.md")) if re.match(r"# (MIDTERM|FINAL) EXAM", c)):
        is_final = part.startswith("# FINAL")
        rubric = []
        m = re.search(r"\*\*Part I:\*\* (.+?) = (\d+)", part)
        rubric.append({"description": f"Part I: {m.group(1)}", "points": int(m.group(2))})
        for frq in re.split(r"^(?=\*\*FRQ \d)", part, flags=re.M)[1:]:
            head = re.match(r"\*\*FRQ (\d) \((\d+) pts\): (.+?)\.?\*\*", frq)
            parts = re.findall(r"^\(([a-z])\) \((\d+) pts\)", frq, flags=re.M)
            for letter, pts in parts:
                rubric.append({"description": f"FRQ {head.group(1)} ({letter}): {head.group(3)}", "points": int(pts)})
            if not parts:  # a single-part question
                rubric.append({"description": f"FRQ {head.group(1)}: {head.group(3)}", "points": int(head.group(2))})
        rubric = [{"id": f"_r{i}", **r} for i, r in enumerate(rubric, 1)]
        name = "Final Exam" if is_final else "Midterm Exam"
        out.append({
            "id": 2202 if is_final else 2201, "name": name, "points_possible": sum(r["points"] for r in rubric),
            "due_at": FINAL_EXAM_AT.isoformat() if is_final else due(8, 12, 30),
            "assignment_group": name, "submission_types": SUBMIT["exam"],
            "description": html(preface + "\n\n" + part.split("\n", 1)[1]), "rubric": rubric,
            "_weeks": {"open": 15 if is_final else 8, "due": 15 if is_final else 8},
        })
    return out


# ---------------------------------------------------------------- feedback -> submissions

def build_submissions(assignments: list[dict]) -> dict:
    by_name = {a["name"]: a for a in assignments}
    graders = {"Assignment 1": "Maya Okafor", "Assignment 3": "Dev Raman",
               "Midterm": "Dr. Quinn Ferrous", "Final Exam": "Dr. Quinn Ferrous"}
    subs = {}
    for part in chunks(read("07_written_feedback.md")):
        head = re.match(r"## (Assignment \d|Midterm|Final Exam) Feedback(?:: FRQ (\d))?", part)
        if not head:
            continue
        key, frq = head.group(1), head.group(2)
        a = next(v for k, v in by_name.items() if k.startswith(key))
        rows = table_rows(part, "### Rubric Breakdown")
        assessment = {}
        for i, (crit, score, notes) in enumerate(rows):
            got = float(score.split("/")[0])
            if frq:  # exam rows are "(a)", "(b)"... of one FRQ
                r = next(r for r in a["rubric"] if r["description"].startswith(f"FRQ {frq} {crit}"))
            else:
                r = next((r for r in a["rubric"] if r["description"].lower().startswith(crit.lower())), a["rubric"][i])
            assessment[r["id"]] = {"points": got, "comments": notes}
        # Exam feedback covers one question; other questions get full credit so the exam has a total.
        for r in a["rubric"]:
            assessment.setdefault(r["id"], {"points": float(r["points"]), "comments": ""})

        grader = graders[key]
        written = part.split("### Written Feedback", 1)[1].strip()
        graded_at = datetime.fromisoformat(a["due_at"]) + timedelta(days=6)
        subs[str(a["id"])] = {
            "user_id": SELF_USER["id"], "workflow_state": "graded",
            "score": sum(v["points"] for v in assessment.values()),
            "submitted_at": a["due_at"], "graded_at": graded_at.isoformat(),
            "submission_comments": [{"id": len(subs) + 1, "author_id": STAFF[grader], "author_name": grader,
                                     "created_at": graded_at.isoformat(), "comment": plain(written)}],
            "rubric_assessment": assessment,
        }
    # Quizzes have completed, graded attempts for every student in the roster.
    for a in assignments:
        if a["submission_types"] == SUBMIT["quiz"]:
            result = quiz_results(a)[str(SELF_USER["id"])]
            subs[str(a["id"])] = {"user_id": SELF_USER["id"], "workflow_state": "graded",
                                   "score": result["score"], "submitted_at": a["due_at"],
                                   "graded_at": (datetime.fromisoformat(a["due_at"]) + timedelta(days=1)).isoformat(),
                                   "submission_comments": [], "rubric_assessment": {},
                                   "quiz_responses": result["responses"]}
        else:
            subs.setdefault(str(a["id"]), {"user_id": SELF_USER["id"], "workflow_state": "submitted", "score": None,
                                            "submitted_at": a["due_at"], "submission_comments": [], "rubric_assessment": {}})
    return subs


SHORT_ANSWERS = {
    1: {9: "The developer is responsible for the code they ship, even when an AI helped write it.",
        10: "Write a Python calculator for +, -, *, and /, return a number, and raise an error for invalid operations or division by zero."},
    2: {9: "Trace by hand and check boundaries. Boundary checks cover values such as an empty list or zero.",
        10: "Restore the test, compare it with the spec, and fix the underlying code or test based on that spec."},
    3: {9: "Rotate the exposed key, remove it from the source, and store the replacement in an environment variable.",
        10: "Authentication verifies identity; authorization checks whether that user may access the requested record."},
}


def quiz_results(assignment: dict) -> dict:
    """Create completed, reviewable attempts for every fictional student in the course."""
    quiz_number = assignment["id"] - 2100
    questions = re.findall(r"<p><strong>(\d+)\.</strong>(.*?)</p>", assignment["description"], flags=re.S)
    answer_key = assignment.get("_answer_key", {})
    mc_numbers = set(answer_key)
    students = [person for person in ROSTER if person["role"] == "Student"]
    per_question = assignment["points_possible"] / len(questions) if questions else 0
    results = {}
    for student_index, person in enumerate(students):
        responses, score = {}, 0
        for number, _stem in questions:
            n = int(number)
            if n in mc_numbers:
                correct = answer_key[n]
                missed = (student_index * 3 + quiz_number + n) % 5 == 0
                selected = (correct + 1 + student_index % 3) % 4 if missed else correct
                earned = 0 if missed else per_question
                response = {"selected_index": selected, "correct_index": correct,
                            "earned": earned, "possible": per_question}
            else:
                answer = SHORT_ANSWERS.get(quiz_number, {}).get(n, "I reviewed the question and explained my reasoning.")
                earned = per_question
                response = {"text": answer, "earned": earned, "possible": per_question,
                            "feedback": "Your response addresses the key idea."}
            responses[str(n)] = response
            score += earned
        results[str(person["id"])] = {"user_id": person["id"], "user_name": person["name"],
                                       "workflow_state": "graded", "score": score,
                                       "submitted_at": assignment["due_at"], "responses": responses}
    return results


def build_student_data(assignments: list[dict], submissions: dict, all_quiz_results: dict) -> tuple[dict, dict]:
    students = [person for person in ROSTER if person["role"] == "Student"]
    grades, activity = {}, {}
    for student_index, person in enumerate(students):
        user_id = str(person["id"])
        items = []
        for item_index, assignment in enumerate(assignments):
            aid = str(assignment["id"])
            possible = float(assignment.get("points_possible") or 0)
            attempt = all_quiz_results.get(aid, {}).get(user_id)
            own_submission = submissions.get(aid, {}) if person["id"] == SELF_USER["id"] else {}
            score = attempt.get("score") if attempt else own_submission.get("score")
            if score is None:
                percent = 72 + ((student_index * 7 + item_index * 11) % 25)
                score = round(possible * percent / 100, 1)
            due_at = datetime.fromisoformat(assignment["due_at"])
            graded_at = due_at + timedelta(days=2 + (student_index + item_index) % 5)
            items.append({"assignment_id": assignment["id"], "name": assignment["name"],
                          "score": score, "points_possible": possible, "status": "graded",
                          "graded_at": graded_at.isoformat(), "missing": False, "late": False})
        grades[user_id] = items
        activity[user_id] = {
            "participation": 30 + ((student_index * 17 + 18) % 70),
            "page_views": 45 + ((student_index * 29 + 31) % 150),
        }
    return grades, activity


# ---------------------------------------------------------------- modules

def build_modules(syllabus_md: str, pages: list[dict], files: list[dict], assignments: list[dict]) -> list[dict]:
    chapter_page = {int(re.search(r"Chapter (\d+)", p["title"]).group(1)): p for p in pages if "Chapter" in p["title"]}
    lecture_for_chapter = {int(re.search(r"Lecture (\d+)", f["title"]).group(1)): f for f in files}
    item_id = iter(range(10_000, 99_999))
    lectures_placed = set()

    modules = [{"id": 1, "name": "Start Here", "items": [
        {"id": next(item_id), "title": "Syllabus", "type": "Page", "page_url": "syllabus"},
        *[{"id": next(item_id), "title": p["title"], "type": "Page", "page_url": p["url"]}
          for p in pages if p["url"] != "syllabus" and "Chapter" not in p["title"]],
    ]}]

    rows = table_rows(syllabus_md, "## Weekly Schedule")
    for week_label, topic, reading, _due in rows:
        week = 15 if week_label == "Finals" else int(week_label)
        items = []
        chapters = [int(x) for x in re.findall(r"\d+", reading)]
        if "–" in reading or "-" in reading:  # "Ch. 1–4" means review of a range
            chapters = []
        if chapters:
            items.append({"id": next(item_id), "title": "Read", "type": "SubHeader"})
            for ch in chapters:
                items.append({"id": next(item_id), "title": chapter_page[ch]["title"], "type": "Page",
                              "page_url": chapter_page[ch]["url"], "indent": 1})
            for ch in chapters:
                deck = lecture_for_chapter.get(ch)
                if deck and ch not in lectures_placed:
                    lectures_placed.add(ch)
                    items.append({"id": next(item_id), "title": deck["title"], "type": "File",
                                  "content_id": deck["id"], "indent": 1})
        elif reading:
            items.append({"id": next(item_id), "title": f"Review: {reading.replace('Ch.', 'Chapters')}", "type": "SubHeader"})
        work = [a for a in assignments if a["_weeks"]["open"] == week]
        if work:
            items.append({"id": next(item_id), "title": "Assignments and assessments", "type": "SubHeader"})
            items += [{"id": next(item_id), "title": a["name"], "type": "Assignment", "content_id": a["id"], "indent": 1}
                      for a in work]
        # Multi-week work is linked again in the week it's due; the schedule's milestone (e.g. "draft") is the label.
        due_now = [a for a in assignments if a["_weeks"]["due"] == week and a["_weeks"]["open"] != week]
        milestone = [a for a in assignments if a["_weeks"]["open"] < week < a["_weeks"]["due"]
                     and a["name"].split(":")[0].lower() in _due.lower()]
        if due_now or milestone:
            items.append({"id": next(item_id), "title": f"Due this week: {_due}", "type": "SubHeader"})
            items += [{"id": next(item_id), "title": a["name"], "type": "Assignment", "content_id": a["id"], "indent": 1}
                      for a in due_now + milestone]
        name = "Finals Week: Final Exam" if week == 15 else f"Week {week}: {topic.replace('**', '')}"
        modules.append({"id": week + 1, "name": name, "items": items})
    return modules


def main():
    syllabus_md, pages = build_pages()
    files = build_slides()
    assignments = build_assignments()
    all_quiz_results = {str(a["id"]): quiz_results(a) for a in assignments if a["submission_types"] == SUBMIT["quiz"]}
    submissions = build_submissions(assignments)
    student_grades, student_activity = build_student_data(assignments, submissions, all_quiz_results)
    fixture = {
        "course": {"id": COURSE_ID, "name": "VIBE 101: Vibe Coding 101", "course_code": "VIBE 101", "term": TERM,
                   "syllabus_body": html(syllabus_md)},
        "self_user_id": SELF_USER["id"], "self_user_name": SELF_USER["name"],
        "users": ROSTER,
        "assignment_groups": [{"name": n, "group_weight": w} for n, w in
                              [("Assignments", 30), ("Final Project", 10), ("Quizzes", 15),
                               ("Midterm Exam", 15), ("Final Exam", 20)]],
        "modules": build_modules(syllabus_md, pages, files, assignments),
        "pages": pages,
        "files": [{k: v for k, v in f.items() if k != "title"} for f in files],
        "assignments": [{k: v for k, v in a.items() if not k.startswith("_")} for a in assignments],
        "submissions": submissions,
        "quiz_results": all_quiz_results,
        "student_grades": student_grades,
        "student_activity": student_activity,
    }
    OUT.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
    graded = [a["name"] for a in assignments if fixture["submissions"][str(a["id"])]["score"] is not None]
    print(f"Wrote {OUT.relative_to(HERE)}: {len(fixture['modules'])} modules, {len(pages)} pages, "
          f"{len(files)} slide decks ({sum(len(f['pages']) for f in files)} slides), {len(assignments)} assignments, "
          f"graded: {', '.join(graded)}")


if __name__ == "__main__":
    main()

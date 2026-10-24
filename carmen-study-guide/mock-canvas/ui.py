"""
Canvas-styled HTML pages for the mock: global nav + trays, course nav, modules, assignments,
grades, pages and files. Fixture HTML (descriptions, page bodies) is inserted as-is; every
other fixture string goes through esc().
"""

import re
from datetime import datetime
from html import escape as esc, unescape
from math import cos, pi, sin
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from data import assignment, course, load_courses, self_user, submission

EXTENSION = Path(__file__).resolve().parent.parent / "extension"
router = APIRouter()


# ---------------------------------------------------------------- icons

def svg(body: str, size: int = 26, view: int = 28) -> str:
    return (f'<svg class="ic" width="{size}" height="{size}" viewBox="0 0 {view} {view}" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{body}</svg>')


LOGO = ('<svg width="56" height="56" viewBox="0 0 56 56" aria-hidden="true">'
        + "".join(f'<circle cx="{28 + 20 * cos(i * pi / 4):.1f}" cy="{28 + 20 * sin(i * pi / 4):.1f}" r="4.2" fill="#fff"/>'
                  + f'<circle cx="{28 + 11 * cos(i * pi / 4 + pi / 8):.1f}" cy="{28 + 11 * sin(i * pi / 4 + pi / 8):.1f}" r="2.4" fill="#fff"/>'
                  for i in range(8))
        + "</svg>")

ICONS = {
    "dashboard": svg('<path d="M4 19a10 10 0 1 1 20 0"/><path d="M14 19l5-6"/><circle cx="14" cy="19" r="1.5"/>'),
    "courses": svg('<path d="M7 4h13a1 1 0 0 1 1 1v19H8a2 2 0 0 1-2-2V5a1 1 0 0 1 1-1z"/><path d="M6 21a2 2 0 0 1 2-2h13M11 9h6M11 13h6"/>'),
    "calendar": svg('<rect x="5" y="6" width="18" height="17" rx="1"/><path d="M5 11h18M10 4v4M18 4v4M9 15h2M13 15h2M17 15h2M9 19h2M13 19h2"/>'),
    "inbox": svg('<path d="M5 15l3-9h12l3 9v7H5z"/><path d="M5 15h6l1 2h4l1-2h6"/>'),
    "history": svg('<circle cx="14" cy="14" r="10"/><path d="M14 8v6l4 3"/>'),
    "help": svg('<circle cx="14" cy="14" r="10"/><path d="M11 11a3 3 0 1 1 4 3c-1 .5-1 1-1 2.2M14 19.5v.3"/>'),
    "collapse": svg('<path d="M6 5v18M24 14H11M16 9l-5 5 5 5"/>'),
    "hamburger": svg('<path d="M4 8h20M4 14h20M4 20h20"/>', 22),
    "close": svg('<path d="M8 8l12 12M20 8L8 20"/>', 18),
    "caret": svg('<path d="M10 7l7 7-7 7"/>', 14),
    "assignment": svg('<path d="M7 4h10l5 5v15H7z"/><path d="M17 4v5h5M11 15l2 2 4-5"/>', 18),
    "page": svg('<path d="M7 4h10l5 5v15H7z"/><path d="M17 4v5h5M10 14h8M10 18h8"/>', 18),
    "file": svg('<path d="M18 9l-7.5 7.5a2.5 2.5 0 0 0 3.5 3.5L22 12a5 5 0 0 0-7-7l-8.5 8.5a7.5 7.5 0 0 0 10.6 10.6L22 19"/>', 18),
    "link": svg('<path d="M12 16a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M16 12a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>', 18),
    "discussion": svg('<path d="M4 6h14v10H9l-5 4z"/><path d="M18 10h6v10l-4-3h-7v-1"/>', 18),
    "stream": svg('<path d="M5 22V12M10 22V6M15 22V10M20 22V14M3 23h22"/>', 18),
    "drop": svg('<path d="M8 8l12 12M20 8L8 20"/>', 18),
    "bell": svg('<path d="M8 19V13a6 6 0 0 1 12 0v6l2 2H6z"/><path d="M12 23h4"/>', 18),
    "export": svg('<path d="M14 4v13M9 9l5-5 5 5M5 17v6h18v-6"/>', 18),
    "check": svg('<path d="M6 14l5 5 11-11"/>', 18),
}
ITEM_ICON = {"Assignment": "assignment", "Page": "page", "File": "file", "ExternalUrl": "link",
             "Discussion": "discussion", "Quiz": "assignment"}
HERO_COLORS = ["#BB0000", "#0B874B", "#0374B5", "#8F3E97", "#D97900", "#2D3B45"]


# ---------------------------------------------------------------- helpers

def item_url(base: str, course_id, it: dict) -> str:
    """Where a module item links, in Canvas's URL scheme (used by the API too)."""
    if it.get("html_url"):
        return it["html_url"]
    kind = {"Page": "pages", "File": "files", "Assignment": "assignments",
            "Discussion": "discussion_topics", "Quiz": "quizzes"}.get(it["type"])
    key = it.get("page_url") if it["type"] == "Page" else it.get("content_id")
    return f"{base}/courses/{course_id}/{kind}/{key}" if kind else f"{base}/courses/{course_id}/modules"


def fmt_due(iso: str | None) -> str:
    if not iso:
        return "No due date"
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"{d:%b} {d.day} by {d.strftime('%I:%M%p').lstrip('0').lower()}"


def rich(text: str) -> str:
    """Escape grader text, then show `code` spans the way Canvas renders them."""
    return re.sub(r"`([^`\n]+)`", r"<code>\1</code>", esc(text or ""))


def fmt_when(iso: str) -> str:
    return fmt_due(iso).replace(" by ", " at ")


def fmt_score(n) -> str:
    return "-" if n is None else (f"{n:g}" if isinstance(n, (int, float)) else str(n))


def initials(name: str) -> str:
    return "".join(p[0] for p in name.split()[:2]).upper()


def hero(cid: str) -> str:
    return HERO_COLORS[int(cid) % len(HERO_COLORS)] if cid.isdigit() else HERO_COLORS[0]


# ---------------------------------------------------------------- layout

def global_nav(active: str) -> str:
    def link(key, label, href, tray=None, badge=""):
        attrs = f'data-tray="{tray}" href="#"' if tray else f'href="{href}"'
        cls = "gnav-item" + (" active" if key == active else "")
        return f'<a class="{cls}" {attrs}>{ICONS[key]}{badge}<span>{label}</span></a>'

    return f"""
<nav id="global-nav" aria-label="Global">
  <a class="gnav-logo" href="/">{LOGO}</a>
  <a class="gnav-item gnav-account" data-tray="account" href="#">
    <span class="avatar-sm"><svg viewBox="0 0 36 36" width="36" height="36" aria-hidden="true">
      <circle cx="18" cy="14" r="6.5" fill="#fff"/><path d="M6 32c1.5-7 6-10 12-10s10.5 3 12 10z" fill="#fff"/></svg></span>
    <span>Account</span></a>
  {link("dashboard", "Dashboard", "/")}
  {link("courses", "Courses", None, "courses")}
  {link("calendar", "Calendar", "/calendar")}
  {link("inbox", "Inbox", "/conversations")}
  {link("history", "History", None, "history")}
  {link("help", "Help", None, "help", '<b class="badge">10</b>')}
  <button class="gnav-collapse" id="gnav-collapse" title="Minimize global navigation">{ICONS["collapse"]}</button>
</nav>"""


def trays() -> str:
    user = self_user()
    course_links = "".join(f'<li><a href="/courses/{cid}">{esc(c["course"]["name"])}</a>'
                           f'<div class="muted small">{esc(c["course"].get("term", "Autumn 2026"))}</div></li>'
                           for cid, c in load_courses().items())
    return f"""
<div id="tray-backdrop"></div>
<aside class="tray" id="tray-account" aria-label="Account">
  <button class="tray-close" aria-label="Close">{ICONS["close"]}</button>
  <div class="tray-profile">
    <div class="avatar-lg">{esc(initials(user["name"]))}</div>
    <h2>{esc(user["name"])}</h2>
    <button class="btn">Logout</button>
  </div>
  <hr>
  <ul class="tray-links">
    <li><a href="#">Notifications</a></li><li><a href="#">Profile</a></li><li><a href="#">Files</a></li>
    <li><a href="#">Settings</a></li><li><a href="#">Shared Content</a></li>
    <li><a href="#">QR for Mobile Login</a></li><li><a href="#">Global Announcements</a></li>
  </ul>
  <hr>
  <h2 class="tray-h">Accessibility Settings</h2>
  <label class="toggle"><input type="checkbox" data-pref="high-contrast"><span class="switch"></span>Use High Contrast UI</label>
  <label class="toggle"><input type="checkbox" data-pref="dyslexia-font"><span class="switch"></span>Use a Dyslexia Friendly Font</label>
</aside>
<aside class="tray" id="tray-courses" aria-label="Courses">
  <button class="tray-close" aria-label="Close">{ICONS["close"]}</button>
  <h2 class="tray-title">Courses</h2><hr>
  <ul class="tray-courses">{course_links}</ul><hr>
  <a href="/courses">All Courses</a>
</aside>
<aside class="tray" id="tray-history" aria-label="History">
  <button class="tray-close" aria-label="Close">{ICONS["close"]}</button>
  <h2 class="tray-title">Recent History</h2><hr><p class="muted">Nothing to show in the mock.</p>
</aside>
<aside class="tray" id="tray-help" aria-label="Help">
  <button class="tray-close" aria-label="Close">{ICONS["close"]}</button>
  <h2 class="tray-title">Help</h2><hr>
  <ul class="tray-links"><li><a href="#">Ask Your Instructor a Question</a></li><li><a href="#">Search the Canvas Guides</a></li>
  <li><a href="#">Report a Problem</a></li><li><a href="/docs">Mock API docs</a></li></ul>
</aside>"""


COURSE_NAV = [("home", "Home", ""), ("announcements", "Announcements", "/announcements"),
              ("assignments", "Assignments", "/assignments"), ("discussions", "Discussions", "/discussion_topics"),
              ("grades", "Grades", "/grades"), ("people", "People", "/users"), ("pages", "Pages", "/pages"),
              ("textbook", "Textbook", "/textbook"),
              ("files", "Files", "/files"), ("syllabus", "Syllabus", "/assignments/syllabus"),
              ("modules", "Modules", "/modules")]


def shell(title: str, body: str, *, active_global="courses", head="", scripts="") -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lato:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/canvas.css">{head}
</head><body>
{global_nav(active_global)}{trays()}
<div id="wrapper">{body}</div>
<script src="/static/canvas.js"></script>{scripts}
</body></html>""")


def course_page(c: dict, section: str, crumbs: list[str], main: str, right: str = "", **kw) -> HTMLResponse:
    cid = str(c["course"]["id"])
    nav = "".join(f'<li><a class="{"active" if key == section else ""}" href="/courses/{cid}{path}">{label}</a></li>'
                  for key, label, path in COURSE_NAV)
    trail = [f'<a href="/courses/{cid}">{esc(c["course"].get("course_code") or c["course"]["name"])}</a>'] + \
            [f"<span>{esc(x)}</span>" for x in crumbs]
    body = f"""
<header class="course-header">
  <button class="hamburger" id="course-nav-toggle" aria-label="Hide course navigation">{ICONS["hamburger"]}</button>
  <nav class="breadcrumbs">{' <span class="sep">&rsaquo;</span> '.join(trail)}</nav>
</header>
<div class="course-body{' has-right' if right else ''}">
  <nav class="course-nav" aria-label="Course"><div class="term muted small">{esc(c["course"].get("term", "Autumn 2026"))}</div><ul>{nav}</ul></nav>
  <main class="content">{main}</main>
  {f'<aside class="right-side">{right}</aside>' if right else ''}
</div>"""
    return shell(f"{crumbs[-1] if crumbs else 'Home'}: {c['course']['name']}", body, **kw)


# ---------------------------------------------------------------- sidebar widgets

def todo_and_feedback(c: dict) -> str:
    cid = c["course"]["id"]
    todo, fb = [], []
    for a in c.get("assignments", []):
        s = submission(c, a["id"])
        url = f"/courses/{cid}/assignments/{a['id']}"
        if not s or s.get("workflow_state") == "unsubmitted":
            todo.append(f'<li>{ICONS["assignment"]}<div><a href="{url}">Turn in {esc(a["name"])}</a>'
                        f'<div class="muted small">{fmt_score(a.get("points_possible"))} points &bull; {fmt_due(a.get("due_at"))}</div></div></li>')
        elif s.get("score") is not None:
            comment = next((x["comment"] for x in s.get("submission_comments", []) if x.get("author_id") != s.get("user_id")), "")
            fb.append(f'<li>{ICONS["check"]}<div><a href="{url}">{esc(a["name"])}</a>'
                      f'<div class="score-line"><b>{fmt_score(s["score"])}</b> out of {fmt_score(a.get("points_possible"))}</div>'
                      f'<div class="muted small clamp">{esc(comment)}</div></div></li>')
    none = '<p class="muted">Nothing for now</p>'
    return f"""
<h2 class="side-h">To Do</h2>{f'<ul class="side-list">{"".join(todo)}</ul>' if todo else none}
<h2 class="side-h">Recent Feedback</h2>{f'<ul class="side-list">{"".join(fb)}</ul>' if fb else none}"""


def course_buttons(cid) -> str:
    return f"""
<div class="side-buttons">
  <a class="btn btn-side" href="/courses/{cid}">{ICONS["stream"]} View Course Stream</a>
  <a class="btn btn-side" href="#">{ICONS["drop"]} Drop this Course</a>
  <a class="btn btn-side" href="/calendar">{ICONS["calendar"].replace('width="26" height="26"', 'width="18" height="18"')} View Course Calendar</a>
  <a class="btn btn-side" href="#">{ICONS["bell"]} View Course Notifications</a>
</div>"""


# ---------------------------------------------------------------- pages

@router.get("/", response_class=HTMLResponse)
def dashboard():
    cards = "".join(f"""
<a class="course-card" href="/courses/{cid}">
  <div class="card-hero" style="background:{hero(cid)}"></div>
  <div class="card-body"><h3 style="color:{hero(cid)}">{esc(c["course"]["name"])}</h3>
  <div class="muted small">{esc(c["course"].get("course_code", ""))}</div>
  <div class="muted small">{esc(c["course"].get("term", "Autumn 2026"))}</div></div>
</a>""" for cid, c in load_courses().items())
    body = f"""
<header class="page-header"><h1>Dashboard</h1></header>
<div class="dash"><main class="content"><div class="card-grid">{cards}</div></main>
<aside class="right-side">{"".join(todo_and_feedback(c) for c in load_courses().values())}</aside></div>"""
    return shell("Dashboard", body, active_global="dashboard")


@router.get("/courses", response_class=HTMLResponse)
def all_courses():
    rows = "".join(f'<tr><td><a href="/courses/{cid}">{esc(c["course"]["name"])}</a></td>'
                   f'<td>{esc(c["course"].get("course_code", ""))}</td><td>{esc(c["course"].get("term", "Autumn 2026"))}</td>'
                   f'<td>Student</td></tr>' for cid, c in load_courses().items())
    body = f"""<header class="page-header"><h1>All Courses</h1></header><main class="content padded">
<table class="table"><thead><tr><th>Course</th><th>Nickname</th><th>Term</th><th>Enrolled as</th></tr></thead>
<tbody>{rows}</tbody></table></main>"""
    return shell("Courses", body)


def modules_html(c: dict) -> str:
    cid = c["course"]["id"]
    mods = []
    for m in c.get("modules", []):
        items = []
        for it in m.get("items", []):
            if it["type"] == "SubHeader":
                items.append(f'<li class="mod-item subheader">{esc(it["title"])}</li>')
                continue
            meta = ""
            if it["type"] == "Assignment":
                try:
                    a = assignment(c, it["content_id"])
                    meta = f'<div class="muted small">{fmt_due(a.get("due_at"))} &nbsp;|&nbsp; {fmt_score(a.get("points_possible"))} pts</div>'
                except HTTPException:
                    pass
            target = ' target="_blank" rel="noopener"' if it["type"] == "ExternalUrl" else ""
            items.append(f'<li class="mod-item indent-{it.get("indent", 0)}">'
                         f'<span class="type-ic">{ICONS[ITEM_ICON.get(it["type"], "page")]}</span>'
                         f'<div><a href="{esc(item_url("", cid, it))}"{target}>{esc(it["title"])}</a>{meta}</div></li>')
        mods.append(f"""
<section class="module">
  <button class="mod-header" aria-expanded="true"><span class="caret">{ICONS["caret"]}</span>{esc(m["name"])}</button>
  <ul class="mod-items">{"".join(items)}</ul>
</section>""")
    return f"""
<div class="toolbar"><button class="btn" id="collapse-all">Collapse All</button>
<button class="btn">{ICONS["export"]} Export Course Content</button></div>
{"".join(mods) or '<p class="muted">No modules yet.</p>'}"""


@router.get("/courses/{course_id}", response_class=HTMLResponse)
def course_home(course_id: str):
    c = course(course_id)
    return course_page(c, "home", [], modules_html(c), course_buttons(course_id) + todo_and_feedback(c))


@router.get("/courses/{course_id}/modules", response_class=HTMLResponse)
def course_modules(course_id: str):
    c = course(course_id)
    return course_page(c, "modules", ["Modules"], modules_html(c), course_buttons(course_id) + todo_and_feedback(c))


def groups(c: dict) -> list[tuple[str, float | None, list[dict]]]:
    """Assignments bucketed by assignment_group, in the fixture's group order."""
    weights = {g["name"]: g.get("group_weight") for g in c.get("assignment_groups", [])}
    names = list(weights) + [a.get("assignment_group", "Assignments") for a in c.get("assignments", [])]
    order = list(dict.fromkeys(names))
    return [(n, weights.get(n), [a for a in c.get("assignments", []) if a.get("assignment_group", "Assignments") == n])
            for n in order]


@router.get("/courses/{course_id}/assignments", response_class=HTMLResponse)
def course_assignments(course_id: str):
    c = course(course_id)
    sections = []
    for name, weight, items in groups(c):
        rows = []
        for a in items:
            s = submission(c, a["id"]) or {}
            score = f'<b>{fmt_score(s["score"])}</b>/{fmt_score(a.get("points_possible"))} pts' if s.get("score") is not None \
                else f'-/{fmt_score(a.get("points_possible"))} pts'
            rows.append(f'<li class="mod-item"><span class="type-ic">{ICONS["assignment"]}</span><div class="grow">'
                        f'<a href="/courses/{course_id}/assignments/{a["id"]}">{esc(a["name"])}</a>'
                        f'<div class="muted small"><b>Due</b> {fmt_due(a.get("due_at"))} &nbsp;|&nbsp; {score}</div></div></li>')
        if not rows:
            rows.append('<li class="mod-item muted">No assignments in this group.</li>')
        pct = f'<span class="weight">{weight:g}% of Total</span>' if weight is not None else ""
        sections.append(f"""<section class="module"><button class="mod-header" aria-expanded="true">
<span class="caret">{ICONS["caret"]}</span><span class="grow">{esc(name)}</span>{pct}</button>
<ul class="mod-items">{"".join(rows)}</ul></section>""")
    return course_page(c, "assignments", ["Assignments"], "".join(sections), todo_and_feedback(c))


@router.get("/courses/{course_id}/assignments/syllabus", response_class=HTMLResponse)
def syllabus(course_id: str):
    c = course(course_id)
    rows = "".join(f'<tr><td>{fmt_due(a.get("due_at"))}</td><td><a href="/courses/{course_id}/assignments/{a["id"]}">'
                   f'{esc(a["name"])}</a></td></tr>'
                   for a in sorted(c.get("assignments", []), key=lambda a: a.get("due_at") or ""))
    main = f'<h1>Course Syllabus</h1><div class="user-content">{c["course"].get("syllabus_body", "")}</div>' \
           f'<h2>Course Summary:</h2><table class="table"><thead><tr><th>Date</th><th>Details</th>' \
           f'</tr></thead><tbody>{rows}</tbody></table>'
    return course_page(c, "syllabus", ["Syllabus"], main)


SHIM = """
<script>
  // Stand-in for the extension runtime: content.js sends {type: "analyze"} here,
  // and this posts it to the backend just as background.js would.
  window.chrome = { runtime: { sendMessage: async (msg) => {
    try {
      const res = await fetch("http://localhost:8000/analyze", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(msg.payload) });
      if (!res.ok) throw new Error(`Backend returned ${res.status}: ${await res.text()}`);
      return { ok: true, data: await res.json() };
    } catch (err) { return { ok: false, error: String(err) }; }
  } } };
</script>
<script src="/extension/content.js"></script>"""


SUBMITTING = {"online_upload": "a file upload", "online_text_entry": "a text entry box",
              "online_quiz": "an online quiz", "on_paper": "on paper (in class)", "none": "nothing"}


def is_quiz(a: dict) -> bool:
    return "online_quiz" in (a.get("submission_types") or [])


def quiz_questions(description: str, total_points: float) -> list[dict]:
    matches = list(re.finditer(r"<p><strong>(\d+)\.</strong>(.*?)</p>", description, flags=re.S))
    questions = []
    per_question = total_points / len(matches) if matches else 0
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(description)
        tail = description[match.end():end]
        options = re.findall(r"<li>(.*?)</li>", tail, flags=re.S)
        extras = re.sub(r"<ul>.*?</ul>", "", tail, flags=re.S)
        questions.append({
            "number": int(match.group(1)),
            "stem": f'<p>{match.group(2)}</p>{extras}',
            "options": options,
            "points": per_question,
        })
    return questions


def quiz_overview(course_id: str, a: dict) -> str:
    description = a.get("description", "")
    instructions = re.split(r"<h3>Multiple Choice</h3>|<h3>Short Answer</h3>", description, maxsplit=1)[0]
    return f"""
<div class="quiz-overview">
  <div class="quiz-overview-head"><div><p class="quiz-kicker">Quiz</p><h1>{esc(a["name"])}</h1></div>
    <a class="btn btn-primary" href="/courses/{course_id}/quizzes/{a['id']}">Take the Quiz</a></div>
  <dl class="quiz-facts">
    <div><dt>Due</dt><dd>{fmt_due(a.get("due_at"))}</dd></div>
    <div><dt>Points</dt><dd>{fmt_score(a.get("points_possible"))}</dd></div>
    <div><dt>Questions</dt><dd>{len(quiz_questions(description, a.get("points_possible") or 0))}</dd></div>
    <div><dt>Time limit</dt><dd>15 minutes</dd></div>
    <div><dt>Attempts</dt><dd>Not specified</dd></div>
  </dl>
  <div class="user-content">{instructions}
    <p>This quiz is closed notes and closed AI. Read each question carefully before submitting.</p>
  </div>
  <p class="muted small">Practice preview: this mock quiz does not record or grade responses.</p>
</div>"""


def quiz_attempt(c: dict, a: dict) -> str:
    questions = quiz_questions(a.get("description", ""), a.get("points_possible") or 0)
    if not questions:
        return '<h1>Quiz questions unavailable</h1><p class="muted">No numbered questions were found for this quiz.</p>'
    cid = c["course"]["id"]
    cards, nav = [], []
    for i, question in enumerate(questions):
        number = question["number"]
        answers = "".join(
            f'<li><label><input type="radio" name="question-{number}" value="{option_index}">'
            f'<span>{option}</span></label></li>'
            for option_index, option in enumerate(question["options"])
        )
        response = (f'<ul class="quiz-options">{answers}</ul>' if answers else
                    f'<label class="quiz-response-label" for="response-{number}">Your answer</label>'
                    f'<textarea id="response-{number}" name="question-{number}" rows="5"></textarea>')
        cards.append(f"""
<section class="quiz-question-card" data-question="{i}"{' hidden' if i else ''}>
  <header class="quiz-question-head"><h2>Question {number}</h2><span>{fmt_score(question['points'])} pts</span></header>
  <div class="quiz-question-body"><div class="quiz-question-stem">{question['stem']}</div>{response}</div>
</section>""")
        current_attr = ' aria-current="step"' if i == 0 else ""
        nav.append(f'<button type="button" class="quiz-number{" active" if i == 0 else ""}" '
                   f'data-go="{i}" aria-label="Go to question {number}"{current_attr}>{number}</button>')
    return f"""
<div class="quiz-attempt-top"><div><p class="quiz-kicker">Quiz attempt</p><h1>{esc(a['name'])}</h1></div>
  <div class="quiz-time"><span class="muted small">Time limit</span><b>15 minutes</b></div></div>
<p class="quiz-preview-note">Practice preview. Responses are not saved or graded.</p>
<div class="quiz-layout" id="quiz-attempt">
  <main class="quiz-main">
    <div class="quiz-progress" aria-live="polite">Question 1 of {len(questions)}</div>
    {''.join(cards)}
    <div class="quiz-controls">
      <button type="button" class="btn" id="quiz-previous" disabled>&larr; Previous</button>
      <button type="button" class="btn btn-primary" id="quiz-next">Next Question &rarr;</button>
      <button type="button" class="btn btn-primary" id="quiz-submit" hidden>Submit Quiz</button>
    </div>
    <div class="quiz-submitted" id="quiz-submitted" hidden role="status">
      <b>Practice attempt complete.</b> This mock quiz does not record or grade responses.
      <a href="/courses/{cid}/assignments/{a['id']}">Return to quiz details</a>
    </div>
  </main>
  <aside class="quiz-question-list"><h2>Questions</h2><p class="muted small">{len(questions)} questions</p>
    <div class="quiz-number-grid">{''.join(nav)}</div>
    <a class="quiz-return" href="/courses/{cid}/assignments/{a['id']}">&larr; Quiz details</a>
  </aside>
</div>
<script>
(() => {{
  const root = document.getElementById('quiz-attempt');
  const cards = [...root.querySelectorAll('.quiz-question-card')];
  const numbers = [...root.querySelectorAll('.quiz-number')];
  const previous = document.getElementById('quiz-previous');
  const next = document.getElementById('quiz-next');
  const submit = document.getElementById('quiz-submit');
  const progress = root.querySelector('.quiz-progress');
  let current = 0;
  function show(index) {{
    current = index;
    cards.forEach((card, i) => card.hidden = i !== current);
    numbers.forEach((button, i) => {{
      button.classList.toggle('active', i === current);
      if (i === current) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    }});
    progress.textContent = `Question ${{current + 1}} of ${{cards.length}}`;
    previous.disabled = current === 0;
    next.hidden = current === cards.length - 1;
    submit.hidden = current !== cards.length - 1;
  }}
  numbers.forEach((button) => button.addEventListener('click', () => show(Number(button.dataset.go))));
  previous.addEventListener('click', () => show(Math.max(0, current - 1)));
  next.addEventListener('click', () => show(Math.min(cards.length - 1, current + 1)));
  submit.addEventListener('click', () => {{
    document.getElementById('quiz-submitted').hidden = false;
    root.querySelector('.quiz-question-list').hidden = true;
    root.querySelector('.quiz-progress').hidden = true;
    root.querySelector('.quiz-question-card').hidden = true;
    root.querySelector('.quiz-controls').hidden = true;
  }});
}})();
</script>"""


@router.get("/courses/{course_id}/assignments/{assignment_id}", response_class=HTMLResponse)
def assignment_page(course_id: str, assignment_id: str):
    c = course(course_id)
    a = assignment(c, assignment_id)
    if is_quiz(a):
        main = quiz_overview(course_id, a)
        return course_page(c, "assignments", ["Quizzes", a["name"]], main)
    s = submission(c, assignment_id) or {}
    graded = s.get("score") is not None
    assessed = s.get("rubric_assessment", {})

    rubric_rows = "".join(f"""
<tr><td>{esc(r["description"])}</td>
<td class="rating">{f'<div>{rich(assessed[r["id"]].get("comments", ""))}</div>' if assessed.get(r["id"], {}).get("comments") else '<span class="muted">-</span>'}</td>
<td class="pts">{f'{fmt_score(assessed[r["id"]].get("points"))} / ' if r["id"] in assessed else ''}{fmt_score(r["points"])} pts</td></tr>"""
                          for r in a.get("rubric", []))
    total = sum(v.get("points") or 0 for v in assessed.values())
    rubric = f"""
<div class="rubric"><h3>{esc(a["name"])} Rubric</h3>
<table class="table"><thead><tr><th>Criteria</th><th>Comments</th><th class="pts">Pts</th></tr></thead>
<tbody>{rubric_rows}</tbody>
<tfoot><tr><td colspan="3" class="pts">Total Points: {f"{fmt_score(total)} / " if assessed else ""}{fmt_score(a.get("points_possible"))}</td></tr></tfoot>
</table></div>""" if a.get("rubric") else ""

    main = f"""
<div class="assignment-title"><h1>{esc(a["name"])}</h1>
<button class="btn btn-primary"{" disabled" if graded else ""}>{"Submitted" if s else "Start Assignment"}</button></div>
<ul class="details">
  <li><b>Due</b> {fmt_due(a.get("due_at"))}</li>
  <li><b>Points</b> {fmt_score(a.get("points_possible"))}</li>
  <li><b>Submitting</b> {SUBMITTING.get((a.get("submission_types") or ["online_upload"])[0], "a file upload")}</li>
</ul>
<div class="user-content">{a.get("description", "")}</div>
{rubric}"""

    comments = "".join(f"""
<li><div class="comment">{rich(x["comment"])}</div>
<div class="muted small">{esc(x.get("author_name", ""))}{f", {fmt_when(x['created_at'])}" if x.get("created_at") else ""}</div></li>"""
                       for x in s.get("submission_comments", []))
    if s:
        right = f"""
<h2 class="side-h">Submission</h2>
<div class="submitted">{ICONS["check"]} <b>Submitted!</b></div>
<a href="#" class="small">Submission Details</a>
<div class="grade-box">Grade: <b>{fmt_score(s.get("score"))}</b> ({fmt_score(a.get("points_possible"))} pts possible)</div>
<h3 class="side-sub">Comments:</h3>
{f'<ul class="comments">{comments}</ul>' if comments else '<p class="muted">No comments</p>'}"""
    else:
        right = '<h2 class="side-h">Submission</h2><p class="muted">Not submitted yet.</p>'
    return course_page(c, "assignments", ["Assignments", a["name"]], main, right, scripts=SHIM)


@router.get("/courses/{course_id}/quizzes/{quiz_id}", response_class=HTMLResponse)
def quiz_page(course_id: str, quiz_id: str):
    c = course(course_id)
    a = assignment(c, quiz_id)
    if not is_quiz(a):
        raise HTTPException(404, "quiz not found")
    main = quiz_attempt(c, a)
    return course_page(c, "assignments", ["Quizzes", a["name"], "Take Quiz"], main)


@router.get("/courses/{course_id}/grades", response_class=HTMLResponse)
def grades(course_id: str):
    c = course(course_id)
    rows, breakdown = [], []
    weighted, weight_used = 0.0, 0.0
    for name, weight, items in groups(c):
        earned = possible = 0.0
        for a in sorted(items, key=lambda a: a.get("due_at") or ""):
            s = submission(c, a["id"]) or {}
            if s.get("score") is not None:
                earned += s["score"]
                possible += a.get("points_possible") or 0
            status = "graded" if s.get("score") is not None else (s.get("workflow_state", "") if s else "")
            rows.append((a.get("due_at") or "", f'<tr><td><a href="/courses/{course_id}/assignments/{a["id"]}">{esc(a["name"])}</a>'
                         f'<div class="muted small">{esc(name)}</div></td><td>{fmt_due(a.get("due_at"))}</td>'
                         f'<td>{esc(status)}</td><td><b>{fmt_score(s.get("score"))}</b></td>'
                         f'<td>{fmt_score(a.get("points_possible"))}</td></tr>'))
        group_pct = earned / possible * 100 if possible else None
        if group_pct is not None and weight:
            weighted += group_pct * weight
            weight_used += weight
        breakdown.append(f'<tr><td>{esc(name)}</td><td>{f"{weight:g}%" if weight is not None else ""}</td>'
                         f'<td>{f"{group_pct:.2f}%" if group_pct is not None else "N/A"}</td></tr>')
    total = f"{weighted / weight_used:.2f}%" if weight_used else "N/A"
    main = f"""<h1>Grades for {esc(self_user(c)["name"])}</h1>
<table class="table"><thead><tr><th>Name</th><th>Due</th><th>Status</th><th>Score</th><th>Out of</th></tr></thead>
<tbody>{"".join(r for _, r in sorted(rows))}</tbody>
<tfoot><tr><td colspan="3"><b>Total</b></td><td colspan="2"><b>{total}</b></td></tr></tfoot></table>"""
    right = f"""<h2 class="side-h">Total: {total}</h2>
<p class="muted small">Weighted by assignment group, counting graded work only.</p>
<table class="table small"><thead><tr><th>Group</th><th>Weight</th><th>Score</th></tr></thead>
<tbody>{"".join(breakdown)}</tbody></table>"""
    return course_page(c, "grades", ["Grades"], main, right)


def textbook_pages(c: dict) -> list[dict]:
    return [p for p in c.get("pages", []) if p["title"].startswith("Textbook")]


def textbook_label(page: dict) -> str:
    title = page["title"]
    if title.startswith("Textbook Chapter "):
        return title.removeprefix("Textbook ")
    if title == "Textbook: Glossary":
        return "Glossary"
    return "Start Here"


def textbook_toc(body: str) -> tuple[str, str]:
    links = []
    section_number = 0

    def add_id(match):
        nonlocal section_number
        section_number += 1
        anchor = f"textbook-section-{section_number}"
        heading = match.group(1)
        label = unescape(re.sub(r"<[^>]+>", "", heading))
        links.append(f'<li><a href="#{anchor}">{esc(label)}</a></li>')
        return f'<h3 id="{anchor}">{heading}</h3>'

    body = re.sub(r"<h3>(.*?)</h3>", add_id, body, flags=re.S)
    toc = (f'<nav class="textbook-toc" aria-label="In this chapter"><strong>In this chapter</strong>'
           f'<ol>{"".join(links)}</ol></nav>') if links else ""
    return toc, body


def textbook_pagination(c: dict, page: dict) -> str:
    pages = textbook_pages(c)
    index = next((i for i, item in enumerate(pages) if item["url"] == page["url"]), 0)
    previous = pages[index - 1] if index > 0 else None
    following = pages[index + 1] if index + 1 < len(pages) else None
    cid = c["course"]["id"]
    prev_link = (f'<a class="btn textbook-prev" href="/courses/{cid}/pages/{esc(previous["url"])}">'
                 f'&larr; {esc(textbook_label(previous))}</a>') if previous else '<span></span>'
    next_link = (f'<a class="btn btn-primary textbook-next" href="/courses/{cid}/pages/{esc(following["url"])}">'
                 f'{esc(textbook_label(following))} &rarr;</a>') if following else '<span></span>'
    return (f'<nav class="textbook-pagination" aria-label="Textbook navigation">{prev_link}'
            f'<a class="textbook-index-link" href="/courses/{cid}/textbook">Chapter index</a>{next_link}</nav>')


@router.get("/courses/{course_id}/textbook", response_class=HTMLResponse)
def textbook_index(course_id: str):
    c = course(course_id)
    pages = textbook_pages(c)
    items = "".join(
        f'<li><a href="/courses/{course_id}/pages/{esc(p["url"])}">{esc(textbook_label(p))}</a></li>'
        for p in pages
    )
    main = (f'<h1>Vibes, Prompts, and Production</h1>'
            f'<p class="textbook-subtitle">A Field Guide to Vibe Coding</p>'
            f'<p>Read the introduction, move through the six chapters, and finish with the glossary. '
            f'Each chapter has a section list and links to the previous and next reading.</p>'
            f'<ol class="textbook-index">{items}</ol>')
    return course_page(c, "textbook", ["Textbook"], main)


@router.get("/courses/{course_id}/pages", response_class=HTMLResponse)
def pages_index(course_id: str):
    c = course(course_id)
    rows = "".join(f'<tr><td><a href="/courses/{course_id}/pages/{esc(p["url"])}">{esc(p["title"])}</a></td></tr>'
                   for p in c.get("pages", []))
    return course_page(c, "pages", ["Pages"], f'<h1>Pages</h1><table class="table"><thead><tr><th>Page title</th></tr>'
                                              f'</thead><tbody>{rows}</tbody></table>')


@router.get("/courses/{course_id}/pages/{page_url}", response_class=HTMLResponse)
def page_view(course_id: str, page_url: str):
    c = course(course_id)
    p = next((p for p in c.get("pages", []) if p["url"] == page_url), None)
    if not p:
        raise HTTPException(404, "page not found")
    if p in textbook_pages(c):
        toc, body = textbook_toc(p["body"])
        label = textbook_label(p)
        main = (f'<div class="textbook-return"><a href="/courses/{course_id}/textbook">'
                f'&larr; All textbook chapters</a></div>'
                f'<h1 class="page-title">{esc(label)}</h1>{toc}'
                f'<div class="user-content">{body}</div>{textbook_pagination(c, p)}')
        return course_page(c, "textbook", ["Textbook", label], main)
    return course_page(c, "pages", ["Pages", p["title"]],
                       f'<h1 class="page-title">{esc(p["title"])}</h1><div class="user-content">{p["body"]}</div>')


@router.get("/courses/{course_id}/files", response_class=HTMLResponse)
def files_index(course_id: str):
    c = course(course_id)
    rows = "".join(f'<tr><td>{ICONS["file"]} <a href="/courses/{course_id}/files/{f["id"]}" target="_blank">'
                   f'{esc(f["display_name"])}</a></td><td>PDF</td></tr>' for f in c.get("files", []))
    return course_page(c, "files", ["Files"], f'<h1>Files</h1><table class="table"><thead><tr><th>Name</th><th>Type</th>'
                                              f'</tr></thead><tbody>{rows}</tbody></table>')


@router.get("/courses/{course_id}/{section}", response_class=HTMLResponse)
def placeholder_section(course_id: str, section: str):
    c = course(course_id)
    key, label = next(((k, l) for k, l, p in COURSE_NAV if p == f"/{section}"), ("", section.replace("_", " ").title()))
    return course_page(c, key, [label], f'<h1>{esc(label)}</h1><p class="muted">Not part of the mock yet. Add it in ui.py.</p>')


@router.get("/calendar", response_class=HTMLResponse)
@router.get("/conversations", response_class=HTMLResponse)
def placeholder_global(request: Request):
    name = "Calendar" if request.url.path == "/calendar" else "Inbox"
    body = f'<header class="page-header"><h1>{name}</h1></header><main class="content padded">' \
           f'<p class="muted">Not part of the mock yet.</p></main>'
    return shell(name, body, active_global=name.lower())


@router.get("/extension/{name}")
def extension_file(name: str):
    path = (EXTENSION / name).resolve()
    if path.parent != EXTENSION or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="text/javascript")

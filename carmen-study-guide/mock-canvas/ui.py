"""
Canvas-styled HTML pages for the mock: global nav + trays, course nav, modules, assignments,
grades, pages and files. Fixture HTML (descriptions, page bodies) is inserted as-is; every
other fixture string goes through esc().
"""

import re
from datetime import datetime
from html import escape as esc, unescape
from urllib.parse import quote
from math import cos, pi, sin

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

import ocr
import uploads
from ingest import QUESTION_PART
from data import assignment, course, load_courses, self_user, submission
from tutor.auth import demo_enabled

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
    "expand": svg('<path d="M16 5h7v7M12 23H5v-7M23 5l-7 7M5 23l7-7"/>', 18),
    "shrink": svg('<path d="M23 12h-7V5M5 16h7v7M16 12l7-7M12 16l-7 7"/>', 18),
    "target": svg('<circle cx="14" cy="14" r="9"/><circle cx="14" cy="14" r="4.5"/><circle cx="14" cy="14" r="0.8"/>', 16),
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
    <form method="post" action="/logout"><button class="btn" type="submit">Logout</button></form>
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
              ("modules", "Modules", "/modules"), ("scans", "Scanned Work", "/scans"), ("tutor", "Hue", "/tutor")]


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


def sync_badge(cid: str) -> str:
    """Status line for the background database sync that canvas.js starts on every page load."""
    return f'<span class="sync-status" data-sync="/analytics/sync/{cid}" role="status" aria-live="polite"></span>'


def export_button(cid: str, a: dict) -> str:
    """Export button for one assessment, labeled with it ('Export Quiz 1 for analytics')."""
    short = a["name"].split(":")[0].strip()
    return f"""
  <div class="export-wrap">
    <button class="btn btn-primary" id="export-btn" data-url="/analytics/export/{cid}/assignments/{a['id']}"
            title="Export {esc(a['name'])}, its grades and feedback, and the course material related to it">
      {ICONS["export"]}<span> Export {esc(short)} for analytics</span></button>
    <div class="export-panel" id="export-panel" role="status" hidden></div>
  </div>"""


def goal_button(cid, aid, code: str, title: str) -> str:
    """Target icon: Hue says which learning outcomes this question assesses, and how much (claude_mapper.py, hue.js)."""
    what = "Whole assignment" if code == "WHOLE" else code
    tip = esc(f"Ask Hue which learning goals {'the whole assignment' if code == 'WHOLE' else code} assesses, and how much")
    return f"""<button type="button" class="goal-btn" data-goals="/analytics/outcomes/{cid}/assignments/{aid}/questions/{quote(code)}"
  data-goal="{esc(what)}" data-goal-title="{esc(title)}" title="{tip}" aria-label="{tip}">{ICONS["target"]}</button>"""


def hue_dock(cid: str, open_as: str = "", assignment: str = "") -> str:
    """Hue, the course assistant (hue.js): a chat box at the side of every course page that shows "Analyze goals"
    answers and opens into the study tutor window. open_as='expanded' starts it open as that window (the Hue page);
    assignment (a canvas id) preselects what the student is working on.

    Students sign in to Carmen before it opens, so Hue has no sign-in of its own: it reuses that course session, and in
    demo mode (TUTOR_DEMO_AUTO_SIGNIN) asks the server to start it."""
    return f"""
<aside class="hue" id="hue" data-course="{esc(cid)}" data-open="{esc(open_as)}" data-assignment="{esc(str(assignment))}"
       data-demo="{'1' if demo_enabled() else ''}" aria-label="Hue, course assistant">
  <button type="button" class="hue-launcher" id="hue-launcher" aria-controls="hue-box" aria-expanded="false">
    <span class="hue-avatar" aria-hidden="true"></span>Ask Hue</button>
  <section class="hue-box" id="hue-box" aria-labelledby="hue-title" hidden>
    <header class="hue-head">
      <h2 id="hue-title"><span class="hue-avatar small" aria-hidden="true"></span>Hue</h2>
      <button type="button" class="hue-icon-btn" id="hue-expand" aria-pressed="false" title="Open as tutor window"
              aria-label="Open as tutor window"><span class="ic-expand">{ICONS["expand"]}</span><span class="ic-shrink">{ICONS["shrink"]}</span></button>
      <button type="button" class="hue-icon-btn" id="hue-close" title="Close Hue" aria-label="Close Hue">{ICONS["close"]}</button>
    </header>
    <div class="hue-log" id="hue-log" aria-live="polite">
      <div class="hue-msg hue-bot"><p>Hi, I'm Hue. Ask me about the slides, notes and readings, or click the target icon on a question to see which learning goals it assesses.</p></div>
    </div>
    <div class="hue-tutor">
      <p class="hue-status" id="hue-status" role="status"></p>
      <div class="hue-context hue-when-ready hue-when-expanded">
        <label for="hue-assessment">Working on</label>
        <select id="hue-assessment"><option value="">General study (no assignment)</option></select>
      </div>
      <p class="hue-banner hue-when-ready hue-when-expanded" id="hue-banner"></p>
      <form class="hue-form" id="hue-form">
        <textarea id="hue-input" rows="2" maxlength="4000" placeholder="Ask Hue about the course…" aria-label="Message Hue"
                  required disabled></textarea>
        <button type="submit" class="btn btn-primary" disabled>Send</button>
      </form>
    </div>
  </section>
</aside>"""


def course_page(c: dict, section: str, crumbs: list[str], main: str, right: str = "",
                export_for: dict | None = None, hue: str = "", hue_assignment: str = "", head: str = "",
                scripts: str = "", **kw) -> HTMLResponse:
    cid = str(c["course"]["id"])
    nav = "".join(f'<li><a class="{"active" if key == section else ""}" href="/courses/{cid}{path}">{label}</a></li>'
                  for key, label, path in COURSE_NAV)
    trail = [f'<a href="/courses/{cid}">{esc(c["course"].get("course_code") or c["course"]["name"])}</a>'] + \
            [f"<span>{esc(x)}</span>" for x in crumbs]
    body = f"""
<header class="course-header">
  <button class="hamburger" id="course-nav-toggle" aria-label="Hide course navigation">{ICONS["hamburger"]}</button>
  <nav class="breadcrumbs">{' <span class="sep">&rsaquo;</span> '.join(trail)}</nav>{sync_badge(cid)}{export_button(cid, export_for) if export_for else ""}
</header>
<div class="course-body{' has-right' if right else ''}">
  <nav class="course-nav" aria-label="Course"><div class="term muted small">{esc(c["course"].get("term", "Autumn 2026"))}</div><ul>{nav}</ul></nav>
  <main class="content">{main}</main>
  {f'<aside class="right-side">{right}</aside>' if right else ''}
</div>{hue_dock(cid, hue, hue_assignment or (export_for or {}).get("id", ""))}"""
    return shell(f"{crumbs[-1] if crumbs else 'Home'}: {c['course']['name']}", body,
                 head='<link rel="stylesheet" href="/static/hue.css">' + head,
                 scripts=scripts + '<script src="/static/hue.js"></script>', **kw)


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
<header class="page-header"><h1>Dashboard</h1>{"".join(sync_badge(cid) for cid in load_courses())}</header>
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


def quiz_result(c: dict, a: dict) -> dict:
    attempts = c.get("quiz_results", {}).get(str(a["id"]), {})
    return attempts.get(str(c.get("self_user_id"))) or next(iter(attempts.values()), {})


def quiz_overview(course_id: str, a: dict) -> str:
    description = a.get("description", "")
    instructions = re.split(r"<h3>Multiple Choice</h3>|<h3>Short Answer</h3>", description, maxsplit=1)[0]
    result = quiz_result(course(course_id), a)
    score = result.get("score")
    total = a.get("points_possible") or 0
    return f"""
<div class="quiz-overview">
  <div class="quiz-overview-head"><div><p class="quiz-kicker">Quiz</p><h1>{esc(a["name"])}</h1></div>
    <a class="btn btn-primary" href="/courses/{course_id}/quizzes/{a['id']}">Review Quiz</a></div>
  <div class="quiz-result-summary"><div><span class="quiz-result-label">Attempt status</span><strong>Completed</strong></div>
    <div><span class="quiz-result-label">Your score</span><strong>{fmt_score(score)} / {fmt_score(total)} points</strong></div>
    <div><span class="quiz-result-label">Questions</span><strong>{len(quiz_questions(description, total))}</strong></div></div>
  <dl class="quiz-facts">
    <div><dt>Due</dt><dd>{fmt_due(a.get("due_at"))}</dd></div>
    <div><dt>Points</dt><dd>{fmt_score(a.get("points_possible"))}</dd></div>
    <div><dt>Questions</dt><dd>{len(quiz_questions(description, a.get("points_possible") or 0))}</dd></div>
    <div><dt>Submitted</dt><dd>{fmt_due(result.get("submitted_at"))}</dd></div>
    <div><dt>Attempts</dt><dd>1 completed attempt</dd></div>
  </dl>
  <div class="user-content">{instructions}
    <p>Your attempt has been graded. Review your answers below to see which questions were correct.</p>
  </div>
</div>"""


def quiz_attempt(c: dict, a: dict) -> str:
    questions = quiz_questions(a.get("description", ""), a.get("points_possible") or 0)
    if not questions:
        return '<h1>Quiz questions unavailable</h1><p class="muted">No numbered questions were found for this quiz.</p>'
    cid = c["course"]["id"]
    result = quiz_result(c, a)
    responses = result.get("responses", {})
    cards, nav = [], []
    for question in questions:
        number = question["number"]
        response = responses.get(str(number), {})
        earned, possible = response.get("earned", 0), response.get("possible", question["points"])
        correct = response.get("correct_index")
        selected = response.get("selected_index")
        is_correct = correct is not None and selected == correct
        status = "Correct" if is_correct else ("Incorrect" if correct is not None else "Reviewed")
        if question["options"]:
            options = []
            for option_index, option in enumerate(question["options"]):
                is_answer = option_index == correct
                is_selected = option_index == selected
                classes = "quiz-review-option"
                if is_answer:
                    classes += " correct"
                elif is_selected:
                    classes += " incorrect"
                labels = []
                if is_selected:
                    labels.append("Your answer")
                if is_answer:
                    labels.append("Correct answer")
                suffix = f'<span class="quiz-answer-label">{" · ".join(labels)}</span>' if labels else ""
                options.append(f'<li class="{classes}"><span>{option}</span>{suffix}</li>')
            answer_review = f'<ul class="quiz-review-options">{"".join(options)}</ul>'
        else:
            answer_review = f'''<div class="quiz-short-review"><b>Your answer</b><p>{esc(response.get("text", "No response recorded."))}</p>
              <b>Review note</b><p>{esc(response.get("feedback", "Review the key ideas in your response."))}</p></div>'''
        cards.append(f"""
<section class="quiz-question-card quiz-review-card" id="question-{number}">
  <header class="quiz-question-head"><h2>Question {number}</h2>{goal_button(cid, a["id"], f"Q{number}", a["name"])}<span class="quiz-question-result {"is-correct" if is_correct else "is-incorrect" if correct is not None else "is-reviewed"}">{status} · {fmt_score(earned)} / {fmt_score(possible)} pts</span></header>
  <div class="quiz-question-body"><div class="quiz-question-stem">{question['stem']}</div>{answer_review}</div>
</section>""")
        nav.append(f'<a class="quiz-number" href="#question-{number}" aria-label="Go to question {number}">{number}</a>')
    return f"""
<div class="quiz-review-top"><div><p class="quiz-kicker">Completed attempt</p><h1>{esc(a['name'])}</h1></div>
  <div class="quiz-review-total"><span>Your score</span><strong>{fmt_score(result.get('score'))} / {fmt_score(a.get('points_possible'))}</strong></div></div>
<div class="quiz-layout quiz-review-layout">
  <main class="quiz-main">{''.join(cards)}</main>
  <aside class="quiz-question-list"><h2>Questions</h2><p class="muted small">Completed · {len(questions)} questions</p>
    <div class="quiz-number-grid">{''.join(nav)}</div>
    <a class="quiz-return" href="/courses/{cid}/assignments/{a['id']}">&larr; Quiz details</a>
  </aside>
</div>
"""


@router.get("/courses/{course_id}/assignments/{assignment_id}", response_class=HTMLResponse)
def assignment_page(course_id: str, assignment_id: str, upload: str | None = None):
    c = course(course_id)
    a = assignment(c, assignment_id)
    if is_quiz(a):
        main = quiz_overview(course_id, a)
        return course_page(c, "assignments", ["Quizzes", a["name"]], main, export_for=a)
    s = submission(c, assignment_id) or {}
    graded = s.get("score") is not None
    assessed = s.get("rubric_assessment", {})

    rubric_rows = "".join(f"""
<tr><td>{esc(r["description"])}{goal_button(course_id, a["id"], r["description"].split(":")[0].strip()[:60], a["name"])
                                   if QUESTION_PART.match(r["description"] or "") else ""}</td>
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
<div class="assignment-title"><div class="title-goal"><h1>{esc(a["name"])}</h1>{goal_button(course_id, a["id"], "WHOLE", a["name"])}</div>
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
    right += upload_box(c, a, upload)
    return course_page(c, "assignments", ["Assignments", a["name"]], main, right, export_for=a)


def upload_notice(status: str | None) -> str:
    if not status:
        return ""
    if status == "uploaded":
        return '<p class="notice ok">File uploaded. It will be read (OCR) and synced to the database in the background.</p>'
    return f'<p class="notice err">{esc(status.removeprefix("error:"))}</p>'


def upload_box(c: dict, a: dict, status: str | None) -> str:
    """Submit Assignment: the mock student uploads a PDF or image (scanned or typed work)."""
    cid = c["course"]["id"]
    files = uploads.for_submission(cid, a["id"], self_user(c)["id"])
    items = "".join(f'<li>{ICONS["file"]} <a href="/files/{f["id"]}/download" target="_blank">{esc(f["filename"])}</a>'
                    f'<div class="muted small">{fmt_when(f["uploaded_at"])}</div></li>' for f in files)
    return f"""
<h3 class="side-sub">Your files</h3>{upload_notice(status)}
{f'<ul class="file-list">{items}</ul>' if items else '<p class="muted small">No files submitted.</p>'}
<form class="upload-form" method="post" action="/courses/{cid}/assignments/{a['id']}/submit" enctype="multipart/form-data">
  <input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" required>
  <button class="btn btn-primary" type="submit">Submit Assignment</button>
  <div class="muted small">PDF, PNG or JPEG. Scans of handwritten work are read with OCR.</div>
</form>"""


def ocr_details(f: dict) -> str:
    """OCR result for one uploaded file: summary line plus every extracted line, low-confidence ones highlighted."""
    try:
        r = ocr.analyze(uploads.read(f), f["content_type"], f["sha256"])
    except Exception as e:
        return f'<span class="err small">OCR failed: {esc(str(e)[:200])}</span>'
    conf = f'{r["mean_confidence"]:.0f}% confidence' if r["mean_confidence"] is not None else "text layer (no OCR needed)"
    flags = "".join(f'<span class="flag">{esc(fl.replace("_", " "))}</span>' for fl in r["flags"])
    pages = "".join(
        f'<div class="ocr-page"><div class="muted small">Page {pg["page"]} &middot; {esc(pg["method"].replace("_", " "))}</div>'
        + "".join(f'<div class="ocr-line{" low" if l.get("low_confidence") else ""}"'
                  f'{f" title=" + chr(34) + "confidence " + str(l["confidence"]) + chr(34) if l["confidence"] is not None else ""}>'
                  f'{esc(l["text"])}</div>' for l in pg["lines"])
        + "</div>" for pg in r["pages"])
    return f"""<details class="ocr"><summary>{r["page_count"]} page(s) &middot; {conf} {flags}</summary>
<p class="muted small">Highlighted lines are low confidence. On handwriting, Tesseract can also be wrong while
confident, so check the original.</p>{pages}</details>"""


@router.get("/courses/{course_id}/scans", response_class=HTMLResponse)
def scans_page(course_id: str, upload: str | None = None):
    """Instructor/TA page: upload scanned paper work for a student, and review what OCR read."""
    c = course(course_id)
    students = [u for u in c.get("users", []) if u.get("role", "Student") == "Student"]
    names = {u["id"]: u["name"] for u in c.get("users", [])}
    titles = {a["id"]: a["name"] for a in c.get("assignments", [])}
    student_opts = "".join(f'<option value="{u["id"]}">{esc(u["name"])}</option>' for u in students)
    assignment_opts = "".join(f'<option value="{a["id"]}">{esc(a["name"])}</option>'
                              for a in c.get("assignments", []) if not is_quiz(a))
    rows = "".join(f"""
<tr><td>{esc(names.get(f["user_id"], str(f["user_id"])))}</td><td>{esc(titles.get(f["assignment_id"], ""))}</td>
<td><a href="/files/{f["id"]}/download" target="_blank">{esc(f["filename"])}</a>
<div class="muted small">{"Instructor scan" if f["source"] == "instructor_scan" else "Student upload"} &middot; {fmt_when(f["uploaded_at"])}</div></td>
<td>{ocr_details(f)}</td></tr>""" for f in reversed(uploads.for_course(course_id)))
    main = f"""<h1>Scanned Work</h1>{upload_notice(upload)}
<form class="scan-form card-form" method="post" action="/courses/{c['course']['id']}/scans" enctype="multipart/form-data">
  <label>Student <select name="user_id" required>{student_opts}</select></label>
  <label>Assignment <select name="assignment_id" required>{assignment_opts}</select></label>
  <label>File <input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg" required></label>
  <button class="btn btn-primary" type="submit">Upload scan</button>
</form>
<p class="muted small">Uploads attach to the student's submission. They're read with OCR (typed PDFs use their own
text) and synced to the database with page and line locations for each piece of text.</p>
<table class="table"><thead><tr><th>Student</th><th>Assignment</th><th>File</th><th>What OCR read</th></tr></thead>
<tbody>{rows or '<tr><td colspan="4" class="muted">No submitted files yet.</td></tr>'}</tbody></table>"""
    return course_page(c, "scans", ["Scanned Work"], main)


@router.get("/courses/{course_id}/quizzes/{quiz_id}", response_class=HTMLResponse)
def quiz_page(course_id: str, quiz_id: str):
    c = course(course_id)
    a = assignment(c, quiz_id)
    if not is_quiz(a):
        raise HTTPException(404, "quiz not found")
    main = quiz_attempt(c, a)
    return course_page(c, "assignments", ["Quizzes", a["name"], "Take Quiz"], main, export_for=a)


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


def people_roster(c: dict) -> str:
    people = c.get("users", [])
    cid = c["course"]["id"]
    role_order = {"Teacher": 0, "Teaching Assistant": 1, "Student": 2}
    people = sorted(people, key=lambda person: (role_order.get(person.get("role", "Student"), 3),
                                                person.get("name", "").casefold()))
    rows = []
    for person in people:
        name = person.get("name", "")
        initials = "".join(part[0] for part in name.split()[:2]).upper()
        role = person.get("role", "Student")
        rows.append(f'<tr data-person="{esc(name.casefold())}" data-role="{esc(role.casefold())}">'
                    f'<td><span class="people-avatar" aria-hidden="true">{esc(initials)}</span>'
                    f'<a class="people-name" href="/courses/{cid}/users/{person["id"]}">{esc(name)}</a></td>'
                    f'<td>{esc(role)}</td><td>{esc(person.get("section", c["course"].get("course_code", "")))}</td></tr>')
    return f'''<div class="people-heading"><div><h1>People</h1>
      <p class="muted">{len(people)} people in this course</p></div>
      <label class="people-search-label" for="people-search">Search people</label>
      <input id="people-search" class="people-search" type="search" placeholder="Search by name or role" autocomplete="off"></div>
      <div class="people-table-wrap"><table class="table people-table"><thead><tr>
      <th scope="col">Name</th><th scope="col">Role</th><th scope="col">Section</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table>
      <p id="people-empty" class="muted people-empty" hidden>No people match your search.</p></div>
      <p class="muted small people-note">Course roster · Spring 2026</p>'''


def people_profile_drawer(c: dict, person: dict) -> str:
    cid = c["course"]["id"]
    user_id = str(person["id"])
    grades = c.get("student_grades", {}).get(user_id, [])
    points = sum(item.get("points_possible", 0) for item in grades)
    earned = sum(item.get("score", 0) for item in grades)
    percent = earned / points * 100 if points else 0
    letter = "A" if percent >= 90 else "B" if percent >= 80 else "C" if percent >= 70 else "D" if percent >= 60 else "F"
    missing = sum(item.get("missing", False) for item in grades)
    late = sum(item.get("late", False) for item in grades)
    graded = sorted(grades, key=lambda item: item.get("graded_at", ""), reverse=True)[:10]
    grade_rows = []
    for item in graded:
        possible = item.get("points_possible", 0)
        score = item.get("score", 0)
        ratio = min(100, max(0, score / possible * 100 if possible else 0))
        bar_class = "low" if ratio < 60 else ""
        aid = item["assignment_id"]
        grade_rows.append(f'''<li class="profile-grade-row"><a class="profile-grade-bar {bar_class}" href="/courses/{cid}/assignments/{aid}"
          aria-label="{esc(item['name'])}: {fmt_score(score)} out of {fmt_score(possible)}"><span style="width:{ratio:.1f}%"></span></a>
          <a class="profile-grade-score" href="/courses/{cid}/assignments/{aid}">{fmt_score(score)}/{fmt_score(possible)}</a>
          <span class="profile-grade-name">{esc(item['name'])}</span></li>''')

    student_activity = c.get("student_activity", {})
    classmates = [v for uid, v in student_activity.items() if uid != user_id]
    metrics = student_activity.get(user_id, {})

    def activity_summary(key: str) -> str:
        value = metrics.get(key, 0)
        average = sum(entry.get(key, 0) for entry in classmates) / len(classmates) if classmates else value
        rating = "High" if value >= average * 1.05 else "Moderate" if value >= average * .8 else "Low"
        filled = 3 if rating == "High" else 2 if rating == "Moderate" else 1
        dots = "".join('<span class="activity-dot filled"></span>' if i < filled else '<span class="activity-dot"></span>'
                       for i in range(3))
        label = "Participation" if key == "participation" else "Page Views"
        return f'<div class="profile-activity-item"><span>{label}</span><div class="activity-dots" aria-label="{rating}">{dots}</div><b>{rating}</b></div>'

    role = person.get("role", "Student")
    if grades:
        grade_content = f'''<div class="profile-grade-summary"><span class="profile-grade-letter">{letter}</span><span>Grade</span></div>
          <div class="profile-stat"><strong>{missing}</strong><span>Missing</span></div><div class="profile-stat"><strong>{late}</strong><span>Late</span></div>'''
        item_content = f'''<section class="profile-section" id="profile-grade-items"><h2>Last 10 Graded Items</h2>
          <ol class="profile-grade-list">{"".join(grade_rows)}</ol></section>
          <section class="profile-section" id="profile-activity"><h2>Activity Compared to Class</h2>
            <div class="profile-activity">{activity_summary("participation")}{activity_summary("page_views")}</div></section>'''
    else:
        grade_content = '<div class="profile-staff-note">Student grade summary is available for enrolled students.</div>'
        item_content = '<p class="muted">No student grade items to show for this account.</p>'

    initials = "".join(part[0] for part in person["name"].split()[:2]).upper()
    return f'''<a class="people-profile-backdrop" href="/courses/{cid}/users" aria-label="Close profile"></a>
      <aside class="people-profile-drawer" role="dialog" aria-modal="true" aria-labelledby="profile-name">
        <a class="profile-close" href="/courses/{cid}/users" aria-label="Close profile">Close</a>
        <header class="profile-header"><div class="profile-avatar" aria-hidden="true">{esc(initials)}</div>
          <h1 id="profile-name">{esc(person['name'])}</h1><p class="profile-course">{esc(c['course'].get('name', 'Course'))}</p>
          <p class="muted">{esc(role)} · Section: {esc(person.get('section', c['course'].get('course_code', '')))}</p>
          <p class="muted">Last login: Thursday</p></header>
        <nav class="profile-actions" aria-label="Student details"><a href="#profile-grade-items">Grades</a><a href="#profile-activity">Course Analytics</a></nav>
        <div class="profile-stats">{grade_content}</div>
        {item_content}
      </aside>'''


@router.get("/courses/{course_id}/users", response_class=HTMLResponse)
def people_index(course_id: str):
    c = course(course_id)
    body = people_roster(c)
    script = '''<script>
      (() => {
        const input = document.getElementById("people-search");
        const rows = [...document.querySelectorAll(".people-table tbody tr")];
        const empty = document.getElementById("people-empty");
        input.addEventListener("input", () => {
          const query = input.value.trim().toLowerCase();
          let visible = 0;
          for (const row of rows) {
            const show = row.dataset.person.includes(query) || row.dataset.role.includes(query);
            row.hidden = !show;
            visible += show ? 1 : 0;
          }
          empty.hidden = visible !== 0;
        });
      })();
    </script>'''
    return course_page(c, "people", ["People"], body, scripts=script)


@router.get("/courses/{course_id}/users/{user_id}", response_class=HTMLResponse)
def people_profile(course_id: str, user_id: str):
    c = course(course_id)
    person = next((user for user in c.get("users", []) if str(user.get("id")) == str(user_id)), None)
    if not person:
        raise HTTPException(404, "person not found")
    body = people_roster(c) + people_profile_drawer(c, person)
    return course_page(c, "people", ["People", person["name"]], body)


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

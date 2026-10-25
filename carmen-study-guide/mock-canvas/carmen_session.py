"""
Mock Carmen log in / log out. The mock has one signed-in student, so "logged out" is just a cookie, but it makes
Account > Logout behave like real Canvas: it ends the Study Tutor session too, Carmen pages go to a logged-out
page, and the tutor refuses until the student logs in again.
"""

import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from tutor.auth import COOKIE as TUTOR_COOKIE

LOGGED_OUT_COOKIE = "carmen_logged_out"
# Reachable while logged out: the log in/out pages, their styles, and the Canvas-shaped API (it has its own tokens).
OPEN_PATHS = re.compile(r"^/(logout|login|logged-out|static/|api/|docs|openapi\.json|favicon)")
TUTOR_API = re.compile(r"^/courses/[^/]+/tutor/.+")

router = APIRouter()


def logged_out(request: Request) -> bool:
    return request.cookies.get(LOGGED_OUT_COOKIE) == "1"


async def require_login(request: Request, call_next):
    if not logged_out(request) or OPEN_PATHS.match(request.url.path):
        return await call_next(request)
    if TUTOR_API.match(request.url.path):
        return JSONResponse({"detail": "Log in to Carmen first"}, status_code=401)
    return RedirectResponse("/logged-out", status_code=303)


@router.post("/logout")
def logout():
    r = RedirectResponse("/logged-out", status_code=303)
    r.set_cookie(LOGGED_OUT_COOKIE, "1", httponly=True, samesite="lax", path="/")
    r.delete_cookie(TUTOR_COOKIE, path="/courses", httponly=True, samesite="strict")
    return r


@router.post("/login")
def login():
    r = RedirectResponse("/", status_code=303)
    r.delete_cookie(LOGGED_OUT_COOKIE, path="/", httponly=True, samesite="lax")
    return r


@router.get("/logged-out", response_class=HTMLResponse)
def logged_out_page():
    return HTMLResponse("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Logged out | Carmen</title>
<link href="https://fonts.googleapis.com/css2?family=Lato:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/canvas.css">
<style>
  body { background: #f5f5f5; }
  .logout-card { max-width: 380px; margin: 12vh auto 0; padding: 32px; background: #fff; border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08); text-align: center; }
  .logout-card h1 { font-size: 1.5rem; margin: 0 0 8px; }
  .logout-card form { margin-top: 22px; }
  .logout-card .btn { width: 100%; justify-content: center; }
</style></head>
<body><main class="logout-card">
  <h1>You've been logged out</h1>
  <p class="muted">You're signed out of Carmen and the Study Tutor.</p>
  <form method="post" action="/login"><button class="btn btn-primary" type="submit">Log in</button></form>
</main></body></html>""")

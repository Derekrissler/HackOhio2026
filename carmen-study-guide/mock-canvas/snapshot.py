"""
Pull a real Canvas course's materials into a mock-canvas fixture.

    python snapshot.py <COURSE_ID>

Reads CANVAS_TOKEN / CANVAS_BASE_URL from the environment or ../backend/.env and writes
fixtures/local/course_<id>.json plus its PDFs. Only course material is copied (modules,
pages, PDFs, assignments with rubrics). No student submissions or grades, so add a
"submissions" block by hand to test the extension. fixtures/local/ is gitignored.
"""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parent / "backend" / ".env")

BASE = os.environ.get("CANVAS_BASE_URL", "https://osu.instructure.com").rstrip("/")
TOKEN = os.environ.get("CANVAS_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
MAX_PDF_BYTES = 25 * 1024 * 1024


def get_all(path: str, params: dict | None = None) -> list:
    url, params, out = f"{BASE}/api/v1{path}", {"per_page": 100, **(params or {})}, []
    while url:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data if isinstance(data, list) else [data])
        url, params = r.links.get("next", {}).get("url"), None
    return out


def try_get_all(path: str, params: dict | None = None) -> list:
    try:
        return get_all(path, params)
    except requests.HTTPError as e:
        print(f"  skipped {path}: {e}")
        return []


def main(course_id: str) -> None:
    if not TOKEN or TOKEN == "dev":
        sys.exit("Set a real CANVAS_TOKEN in backend/.env (or the environment) first.")

    out_dir = HERE / "fixtures" / "local"
    pdf_dir = out_dir / f"course_{course_id}_files"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    c = get_all(f"/courses/{course_id}")[0]
    print(f"Snapshotting {c['name']} from {BASE}")

    modules = []
    for m in try_get_all(f"/courses/{course_id}/modules", {"include[]": "items"}):
        items = [{k: it[k] for k in ("id", "title", "type", "page_url", "content_id", "external_url") if k in it}
                 for it in m.get("items", [])]
        for it in items:
            if it["type"] == "ExternalUrl" and "external_url" in it:
                it["html_url"] = it.pop("external_url")
        modules.append({"id": m["id"], "name": m["name"], "items": items})
    print(f"  {len(modules)} modules")

    pages = []
    for p in try_get_all(f"/courses/{course_id}/pages"):
        full = try_get_all(f"/courses/{course_id}/pages/{p['url']}")
        if full:
            pages.append({"url": p["url"], "title": p["title"], "body": full[0].get("body") or ""})
    print(f"  {len(pages)} pages")

    files = []
    for f in try_get_all(f"/courses/{course_id}/files", {"content_types[]": "application/pdf"}):
        if f.get("size", 0) > MAX_PDF_BYTES:
            continue
        r = requests.get(f["url"], headers=HEADERS, timeout=60)
        if not r.ok:
            continue
        name = f"{f['id']}.pdf"
        (pdf_dir / name).write_bytes(r.content)
        files.append({"id": f["id"], "display_name": f["display_name"], "path": f"{pdf_dir.name}/{name}"})
    print(f"  {len(files)} PDFs")

    assignments = [
        {k: a.get(k) for k in ("id", "name", "description", "points_possible")}
        | {"rubric": [{k: r.get(k) for k in ("id", "description", "points")} for r in a.get("rubric", [])]}
        for a in try_get_all(f"/courses/{course_id}/assignments")
    ]
    print(f"  {len(assignments)} assignments")

    fixture = {
        "course": {"id": c["id"], "name": c["name"], "course_code": c.get("course_code", "")},
        "modules": modules, "pages": pages, "files": files, "assignments": assignments,
        "submissions": {},
    }
    path = out_dir / f"course_{course_id}.json"
    path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    print(f"Wrote {path.relative_to(HERE)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])

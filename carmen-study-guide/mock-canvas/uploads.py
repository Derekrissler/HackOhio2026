"""
Uploaded submission files for the mock: student "Submit Assignment" uploads and instructor scan uploads.

Files live in uploads/<course>/<assignment>/<user>/ with a registry in uploads/index.json. The mock API
exposes them as Canvas submission attachments, so the exporter and sync treat them like real Canvas uploads.
uploads/ is gitignored: it holds student work.
"""

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "uploads"
INDEX = ROOT / "index.json"
ALLOWED = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
MAX_BYTES = 25 * 1024 * 1024
FIRST_ID = 900_001  # attachment ids, kept clear of course file ids
_lock = threading.Lock()


def _load() -> list[dict]:
    return json.loads(INDEX.read_text()) if INDEX.is_file() else []


def add(course_id, assignment_id, user_id, filename: str, content_type: str, data: bytes, source: str) -> dict:
    """source: 'student_submission' or 'instructor_scan'."""
    if content_type not in ALLOWED:
        raise ValueError(f"Only PDF, PNG or JPEG files can be submitted (got {content_type or 'unknown type'}).")
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ValueError(f"Files must be under {MAX_BYTES // 2**20} MB.")
    safe = re.sub(r"[^\w.-]+", "_", Path(filename or "submission").name)[:120] or "submission"
    with _lock:
        rows = _load()
        att_id = max([r["id"] for r in rows], default=FIRST_ID - 1) + 1
        folder = ROOT / str(course_id) / str(assignment_id) / str(user_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{att_id}-{safe}"
        path.write_bytes(data)
        row = {"id": att_id, "course_id": int(course_id), "assignment_id": int(assignment_id), "user_id": int(user_id),
               "filename": safe, "content_type": content_type, "size": len(data),
               "sha256": hashlib.sha256(data).hexdigest(), "path": str(path.relative_to(ROOT)),
               "source": source, "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        rows.append(row)
        INDEX.write_text(json.dumps(rows, indent=2))
    return row


def for_submission(course_id, assignment_id, user_id) -> list[dict]:
    return [r for r in _load() if (r["course_id"], r["assignment_id"], r["user_id"]) ==
            (int(course_id), int(assignment_id), int(user_id))]


def for_course(course_id) -> list[dict]:
    return [r for r in _load() if r["course_id"] == int(course_id)]


def get(att_id: int) -> dict | None:
    return next((r for r in _load() if r["id"] == int(att_id)), None)


def read(row: dict) -> bytes:
    return (ROOT / row["path"]).read_bytes()


def attachment_json(base_url: str, row: dict) -> dict:
    """Canvas attachment shape (plus upload_source, which real Canvas doesn't have)."""
    return {"id": row["id"], "display_name": row["filename"], "filename": row["filename"],
            "content-type": row["content_type"], "size": row["size"], "created_at": row["uploaded_at"],
            "url": f"{base_url}/files/{row['id']}/download", "upload_source": row["source"]}

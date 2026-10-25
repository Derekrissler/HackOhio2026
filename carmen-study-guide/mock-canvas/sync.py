"""
Keep the Supabase database in step with the mock Carmen site.

Every course page load (and the dashboard) asks for a sync. A sync runs in a background thread:
it exports the whole course through the Canvas API (ingest.py) into a temporary folder, stores it
(db_store.py), proposes outcome mappings for unmapped questions (outcome_mapper.py) and builds LERs for
the analytics (ler_builder.py). Each step skips work that hasn't changed.

One sync per course at a time. A request that arrives while one is running queues exactly one more
run, so the database ends up matching the latest state even if content was edited mid-sync.
"""

import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import db_store
import ingest
import ler_builder
import outcome_mapper

_lock = threading.Lock()
_state: dict[str, dict] = {}  # course_id -> {running, rerun, status, ...}

STATUS = {"stored": "synced", "unchanged": "up_to_date", "skipped": "not_configured"}


def _public(cid: str) -> dict:
    st = _state.get(cid) or {"status": "never_synced", "running": False}
    return {"course_id": cid, **{k: v for k, v in st.items() if k != "rerun"}}


def status(cid: str) -> dict:
    with _lock:
        return _public(cid)


def request_sync(base_url: str, cid: str) -> dict:
    with _lock:
        st = _state.setdefault(cid, {"running": False, "rerun": False, "status": "never_synced"})
        if st["running"]:
            st["rerun"] = True  # coalesce: at most one queued run
            return _public(cid)
        st.update(running=True, rerun=False, status="syncing")
    threading.Thread(target=_run, args=(base_url, cid), daemon=True, name=f"sync-{cid}").start()
    return status(cid)


def _run(base_url: str, cid: str) -> None:
    while True:
        tmp = Path(tempfile.mkdtemp(prefix="canvas-sync-"))
        update: dict
        try:
            bundle, path = ingest.export_course(base_url, "mock", cid, root=tmp)
            result = db_store.store_export(bundle, path.parent, skip_if_unchanged=True)
            update = {"status": STATUS.get(result["status"], result["status"]), "error": result.get("reason"),
                      "rows_written": result.get("rows_written"), "content_hash": bundle["export"]["content_hash"]}
            if result["status"] in ("stored", "unchanged"):
                code = bundle["course"]["course_code"]
                update["outcome_mapping"] = outcome_mapper.run(code)
                update["lers"] = ler_builder.run(code)
        except Exception as e:  # keep the error visible in the page's status line
            update = {"status": "failed", "error": str(e)[:300]}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        with _lock:
            st = _state[cid]
            st.update(update, finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            if st["rerun"]:
                st.update(rerun=False, status="syncing")
                continue
            st["running"] = False
            return

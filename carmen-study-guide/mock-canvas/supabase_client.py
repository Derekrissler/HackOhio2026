"""
Supabase clients for server code. Nothing in the browser talks to Supabase.

- user_client(jwt): publishable key + the logged-in user's session. Row-level security applies,
  so it's read-only and scoped to what that user may see. Use it for tutor retrieval
  (search_resource_chunks) and anything shown to a user.
- service_client(): service-role key. Bypasses RLS. Only for server-side writes: ingestion,
  LERs, analytics (ARRs), insights (IRs), tutor logs. Never return its key or raw results to a browser.

The schema is already applied to the shared project; never run migrations from here.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv, dotenv_values
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

load_dotenv(Path(__file__).resolve().parent / ".env")
_shared_settings = dotenv_values(Path(__file__).resolve().parents[2] / "apps" / "api" / ".env")


def _env(name: str, *aliases: str) -> str:
    for n in (name, *aliases):
        value = os.environ.get(n, "")
        if value and value not in ("REPLACE_ME", "YOUR-SECRET-KEY"):
            return value
    # Reuse the canonical API settings when Carmen has no usable override.
    # Never borrow another project's key when Carmen selects a different URL.
    selected_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    shared_url = (_shared_settings.get("SUPABASE_URL") or "").rstrip("/")
    if not selected_url or selected_url == shared_url:
        for n in (name, *aliases):
            value = _shared_settings.get(n)
            if value and value not in ("REPLACE_ME", "YOUR-SECRET-KEY"):
                return value
    raise RuntimeError(f"{' or '.join((name, *aliases))} is not set. Add it to mock-canvas/.env (see .env.example).")


# Supabase's newer "secret key" (sb_secret_...) is the replacement for the legacy service_role key.
SERVICE_KEY_NAMES = ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY")


def user_client(access_token: str | None = None) -> Client:
    """Publishable key, optionally acting as a logged-in user (their JWT). RLS applies."""
    client = create_client(_env("SUPABASE_URL"), _env("SUPABASE_PUBLISHABLE_KEY"),
                           options=SyncClientOptions(auto_refresh_token=False, persist_session=False))
    if access_token:
        client.postgrest.auth(access_token)
    return client


def select_all(db: Client, table: str, columns: str, **eq) -> list[dict]:
    """Every matching row, paging past PostgREST's 1000-row default limit."""
    out, start = [], 0
    while True:
        q = db.table(table).select(columns)
        for k, v in eq.items():
            q = q.eq(k, v)
        page = q.range(start, start + 999).execute().data
        out += page
        if len(page) < 1000:
            return out
        start += 1000


@lru_cache(maxsize=1)
def service_client() -> Client:
    """Service role: bypasses RLS. Server-side writes only."""
    return create_client(_env("SUPABASE_URL"), _env(*SERVICE_KEY_NAMES),
                         options=SyncClientOptions(auto_refresh_token=False, persist_session=False))

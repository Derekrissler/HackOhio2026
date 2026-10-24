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

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent / ".env")


def _env(name: str, *aliases: str) -> str:
    for n in (name, *aliases):
        value = os.environ.get(n, "")
        if value and value != "REPLACE_ME":
            return value
    raise RuntimeError(f"{' or '.join((name, *aliases))} is not set. Add it to mock-canvas/.env (see .env.example).")


# Supabase's newer "secret key" (sb_secret_...) is the replacement for the legacy service_role key.
SERVICE_KEY_NAMES = ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY")


def user_client(access_token: str | None = None) -> Client:
    """Publishable key, optionally acting as a logged-in user (their JWT). RLS applies."""
    client = create_client(_env("SUPABASE_URL"), _env("SUPABASE_PUBLISHABLE_KEY"))
    if access_token:
        client.postgrest.auth(access_token)
    return client


@lru_cache(maxsize=1)
def service_client() -> Client:
    """Service role: bypasses RLS. Server-side writes only."""
    return create_client(_env("SUPABASE_URL"), _env(*SERVICE_KEY_NAMES))

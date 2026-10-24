"""Lazy pipeline/user clients. Never touch the mock Canvas DATABASE_URL."""

import os
from pathlib import Path


def _required(name):
    value = os.environ.get(name, "").strip()
    if value in ("", "YOUR-SECRET-KEY", "REPLACE_ME"):
        raise RuntimeError(f"Configure {name} in apps/api/.env")
    return value


def _client(key_name, access_token=None):
    from dotenv import load_dotenv
    from supabase import create_client
    from supabase.lib.client_options import SyncClientOptions

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    client = create_client(
        _required("SUPABASE_URL"), _required(key_name),
        options=SyncClientOptions(auto_refresh_token=False, persist_session=False),
    )
    if access_token:
        client.postgrest.auth(access_token)
    return client


def create_pipeline_client():
    """Trusted job execution only: this client bypasses RLS."""
    return _client("SUPABASE_SECRET_KEY")


def create_user_client(access_token: str):
    """A fresh client per user session; Supabase validates the JWT and applies RLS."""
    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("a logged-in user's access token is required")
    return _client("SUPABASE_PUBLISHABLE_KEY", access_token)

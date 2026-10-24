"""Canonical analytical content, separate from execution IDs and timestamps."""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from importlib.metadata import version
import json
from uuid import UUID

from pydantic import BaseModel

METHOD = "analytics_pipeline_v1.1"


def canonical(value):
    if isinstance(value, BaseModel):
        return canonical(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return sorted((canonical(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("naive timestamps are not reproducible")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    return value


def content_hash(value):
    encoded = json.dumps(canonical(value), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def runtime_versions():
    return {name: version(name) for name in ("pydantic", "numpy", "pandas")}

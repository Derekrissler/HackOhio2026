from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class SourceMixin:
    """Where a row came from, so Canvas data can be re-ingested idempotently later."""

    source: Mapped[str] = mapped_column(String(20), default="canvas")
    external_id: Mapped[str | None] = mapped_column(String(64))

from datetime import UTC, datetime


def get_now() -> datetime:
    """Current time as naive UTC (how timestamps are stored). A dependency so tests can freeze it."""
    return datetime.now(UTC).replace(tzinfo=None)

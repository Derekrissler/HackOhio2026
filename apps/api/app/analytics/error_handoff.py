"""Versioned B-to-D completion metadata; no classification is inferred here."""
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool

from .contracts import Contract, Nonnegative


class ErrorHandoffMetadata(Contract):
    schema_version: Literal["1.0"]
    errors_analyzed: StrictBool | None = None
    outcome_weights: dict[UUID, Nonnegative] = Field(default_factory=dict)
    error_outcomes: dict[UUID, list[UUID]] = Field(default_factory=dict)


def completion_metadata(value):
    """Only the agreed namespace is accepted; malformed metadata stays unknown.

    Existing namespaces can gain a separate explicit adapter when B supplies its
    actual contract. No heuristic maps a score or missing error rows to success.
    """
    # Attribution is checked separately against joined error/outcome ownership.
    # Bad attribution must not turn a completed question classification into an
    # invented association, nor discard otherwise usable score evidence.
    metadata = ErrorHandoffMetadata.model_validate({**value, "error_outcomes": {}})
    return metadata.model_dump(mode="json") | {"error_outcomes": value.get("error_outcomes", {})}

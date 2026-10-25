"""Group approval binds exact source/text/model/configuration, independently of run UUIDs."""
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .contracts import Contract
from .provenance import content_hash


class GroupDecision(Contract):
    group_key: str
    decision: Literal["pending", "approved", "rejected"] = "pending"


class ClusterReview(Contract):
    schema_version: Literal["1.0"] = "1.0"
    binding: str
    reviewer_ref: str | None = Field(default=None, max_length=100)
    reviewed_at: AwareDatetime | None = None
    decisions: list[GroupDecision]

    @model_validator(mode="after")
    def unique_and_attributed(self):
        if len({row.group_key for row in self.decisions}) != len(self.decisions):
            raise ValueError("duplicate group review")
        if any(row.decision != "pending" for row in self.decisions) and (not self.reviewer_ref or not self.reviewed_at):
            raise ValueError("cluster review requires attribution")
        return self


def group_keys(result):
    keys = {}
    for part in result.partitions:
        for group in part.groups:
            members = sorted(item.observation_id for item in part.assignments if item.cluster_id == group.cluster_id)
            keys[group.cluster_id] = content_hash({"members": members, "course": part.course_id,
                "origin": part.assessment_origin, "assistance": part.assistance,
                "model": result.model, "config": result.config})
    return keys


def template(result, source_fingerprint, excerpt_digest):
    binding = content_hash({"source": source_fingerprint, "excerpts": excerpt_digest,
                            "clustering_snapshot": result.input_snapshot})
    return ClusterReview(binding=binding, decisions=[GroupDecision(group_key=key) for key in sorted(group_keys(result).values())])


def approved_ids(review, result, source_fingerprint, excerpt_digest):
    expected = template(result, source_fingerprint, excerpt_digest)
    if review.binding != expected.binding or {d.group_key for d in review.decisions} != {d.group_key for d in expected.decisions}:
        raise ValueError("cluster inputs changed; renewed review required")
    if any(d.decision == "pending" for d in review.decisions):
        raise ValueError("cluster review is incomplete")
    approved = {d.group_key for d in review.decisions if d.decision == "approved"}
    return {cid for cid, key in group_keys(result).items() if key in approved}

"""Private, revision-bound text approval export. Not automated privacy review."""
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .contracts import Contract
from .provenance import content_hash
from .text_preparation import ApprovedErrorText


class ReviewedExcerpt(ApprovedErrorText):
    ler_error_id: UUID
    ler_revision: int = Field(ge=1, strict=True)


class ReviewedExcerptExport(Contract):
    schema_version: Literal["1.0"]
    course_id: UUID
    extraction_version: str = Field(min_length=1, max_length=100)
    reviewer_ref: str = Field(min_length=1, max_length=100)
    reviewed_at: AwareDatetime
    review_revision: str = Field(min_length=1, max_length=100)
    entries: list[ReviewedExcerpt]

    @model_validator(mode="after")
    def unique_entries(self):
        if len({entry.ler_error_id for entry in self.entries}) != len(self.entries):
            raise ValueError("duplicate reviewed error identity")
        return self

    def digest(self):
        return content_hash(self)

    def approved_inputs(self, records, batch, *, live=False, verify_source_rows=False):
        if self.course_id != batch.course_id:
            raise ValueError("review export belongs to another course")
        by_id = {record.ler_id: record for record in records}
        error_rows = {row["id"]: row for row in batch.source_manifest.get("ler_errors", [])}
        result = []
        for entry in self.entries:
            record = by_id.get(entry.ler_id)
            if record is None or not record.is_current or record.revision != entry.ler_revision:
                raise ValueError("review export references an obsolete LER")
            events = [error for error in record.errors if error.code == entry.error_code and error.instructor_status != "rejected"]
            allowed = {ref for error in events for ref in error.evidence_ref_ids}
            if not events or record.errors_analyzed is not True or not set(entry.evidence_ref_ids) <= allowed:
                raise ValueError("review export does not match classified error evidence")
            if live or verify_source_rows or "synthetic_demo_v1" in batch.source_manifest:
                source = error_rows.get(str(entry.ler_error_id))
                if not source or source["ler_id"] != str(entry.ler_id) or source["code"] != entry.error_code or source["instructor_status"] == "rejected":
                    raise ValueError("review export references a different error")
                source_refs = {row["evidence_ref_id"] for row in batch.source_manifest.get("ler_error_evidence", [])
                               if row["ler_error_id"] == str(entry.ler_error_id)}
                if not set(map(str, entry.evidence_ref_ids)) <= source_refs:
                    raise ValueError("review export references unrelated evidence")
            result.append(ApprovedErrorText.model_validate(entry.model_dump(exclude={"ler_error_id", "ler_revision"})))
        return result

    def audit(self):
        return {"digest": self.digest(), "schema_version": self.schema_version,
                "course_id": str(self.course_id), "extraction_version": self.extraction_version,
                "reviewer_ref": self.reviewer_ref, "reviewed_at": self.reviewed_at.isoformat(),
                "review_revision": self.review_revision,
                "entries": [{"ler_id": str(entry.ler_id), "ler_error_id": str(entry.ler_error_id),
                             "ler_revision": entry.ler_revision, "text_digest": content_hash(entry.text)}
                            for entry in self.entries]}

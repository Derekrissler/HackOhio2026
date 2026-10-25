"""Course-scoped, paginated Supabase reads and conservative LER join assembly.

Only the versioned payload.analytics_v1 namespace is requested, never raw answers
or comments. The namespace is a proposed upstream contract, not a new SQL column.
"""

from collections import defaultdict
from uuid import UUID

from pydantic import Field, JsonValue

from .contracts import Contract
from .provenance import content_hash


class RepositoryError(RuntimeError):
    """Only sanitized codes cross this boundary."""


class LoadIssue(Contract):
    ler_id: UUID
    code: str


class EvidenceBatch(Contract):
    course_id: UUID
    envelopes: list[dict[str, JsonValue]]
    issues: list[LoadIssue] = Field(default_factory=list)
    # Minimal source rows include quarantined evidence so freshness changes are detectable.
    source_manifest: dict[str, JsonValue] = Field(default_factory=dict)

    def fingerprint(self):
        return content_hash(self)


LER_FIELDS = ("id,schema_version,course_id,learner_id,assessment_id,question_id,attempt_id,"
              "response_id,practice_attempt_id,revision,is_current,assessment_origin,"
              "assistance_level,hints_used,independent_correctness,analysis_status,"
              "analytics_metadata:payload->analytics_v1")
RELATED = {
    "response": ("responses", "response_id", "id,course_id,learner_id,attempt_id,question_id,points_earned,content_hash,updated_at"),
    "question": ("questions", "question_id", "id,course_id,assessment_id,question_type,points_possible"),
    "attempt": ("attempts", "attempt_id", "id,course_id,learner_id,assessment_id,attempt_number,submitted_at"),
    "assessment": ("assessments", "assessment_id", "id,course_id,assessment_type"),
    "practice": ("practice_attempts", "practice_attempt_id", "id,course_id,learner_id,created_at,hints_used,assistance_level,independent_correctness"),
}


def read_pages(client, table, columns, *, filters=None, in_filter=None, order=("id",), page_size=500):
    if not 1 <= page_size <= 1000:
        raise ValueError("invalid page size")
    rows = []
    offset = 0
    while True:
        try:
            query = client.table(table).select(columns)
            for key, value in (filters or {}).items():
                query = query.eq(key, value)
            if in_filter:
                query = query.in_(*in_filter)
            for column in order:
                query = query.order(column)
            page = query.range(offset, offset + page_size - 1).execute().data
        except Exception:
            raise RepositoryError("database_read_failed") from None
        if not isinstance(page, list):
            raise RepositoryError("invalid_database_response")
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


class SupabaseEvidenceRepository:
    source_kind = "supabase"
    def __init__(self, pipeline_client, *, page_size=500):
        self.client, self.page_size = pipeline_client, page_size

    def _rows(self, table, columns, *, filters=None, ids=None, key="id", order=("id",)):
        if ids is None:
            return read_pages(self.client, table, columns, filters=filters, order=order, page_size=self.page_size)
        values, result = sorted(set(ids)), []
        for start in range(0, len(values), 100):
            result.extend(read_pages(self.client, table, columns, filters=filters,
                                     in_filter=(key, values[start:start + 100]), order=order,
                                     page_size=self.page_size))
        return result

    def load_course(self, course_id: UUID) -> EvidenceBatch:
        course_id = UUID(str(course_id))
        course_filter = {"course_id": str(course_id)}
        lers = self._rows("lers", LER_FIELDS, filters={**course_filter, "is_current": True})
        for row in lers:
            metadata = row.get("analytics_metadata")
            row["analytics_metadata"] = ({key: metadata[key] for key in (
                "schema_version", "errors_analyzed", "outcome_weights", "error_outcomes",
            ) if key in metadata} if isinstance(metadata, dict) else None)
        manifest = {"lers": lers}
        manifest["learners"] = self._rows("learners", "id,course_id", filters=course_filter,
                                          ids=[row["learner_id"] for row in lers])
        learner_ids = {row["id"] for row in manifest["learners"]}
        related = {}
        for name, (table, field, columns) in RELATED.items():
            rows = self._rows(table, columns, filters=course_filter,
                              ids=[row[field] for row in lers if row.get(field)])
            manifest[table] = rows
            related[name] = {row["id"]: row for row in rows}
        child_specs = {
            "ler_outcomes": ("ler_id,outcome_id,provenance,needs_review", "ler_id", [r["id"] for r in lers], ("ler_id", "outcome_id")),
            "ler_errors": ("id,ler_id,code,instructor_status", "ler_id", [r["id"] for r in lers], ("id",)),
            "ler_evidence": ("ler_id,evidence_ref_id,role", "ler_id", [r["id"] for r in lers], ("ler_id", "evidence_ref_id")),
            "question_outcomes": ("question_id,outcome_id,weight,provenance,needs_review", "question_id", list(related["question"]), ("question_id", "outcome_id")),
        }
        for table, (columns, key, ids, order) in child_specs.items():
            manifest[table] = self._rows(table, columns, ids=ids, key=key, order=order)
        manifest["ler_error_evidence"] = self._rows(
            "ler_error_evidence", "ler_error_id,evidence_ref_id", key="ler_error_id",
            ids=[row["id"] for row in manifest["ler_errors"]], order=("ler_error_id", "evidence_ref_id"),
        )
        evidence_ids = [r["evidence_ref_id"] for table in ("ler_evidence", "ler_error_evidence") for r in manifest[table]]
        manifest["evidence_refs"] = self._rows(
            "evidence_refs", "id,course_id,learner_id,content_hash", ids=evidence_ids, filters=course_filter,
        )
        # Validate outcome ownership: FKs alone do not enforce same-course relationships.
        outcome_ids = [r["outcome_id"] for table in ("ler_outcomes", "question_outcomes") for r in manifest[table]]
        manifest["outcomes"] = self._rows("outcomes", "id,course_id", ids=outcome_ids, filters=course_filter)
        return assemble_evidence_batch(course_id, manifest)

    @staticmethod
    def _assemble(course_id, manifest):
        """Pure join assembly shared with complete offline source manifests."""
        lers = manifest["lers"]
        learner_ids = {row["id"] for row in manifest["learners"]}
        related = {name: {row["id"]: row for row in manifest[table]}
                   for name, (table, _, _) in RELATED.items()}
        outcomes = {row["id"] for row in manifest["outcomes"]}
        refs = {row["id"]: row for row in manifest["evidence_refs"]}
        children = {}
        for table, key in (("ler_outcomes", "ler_id"), ("ler_errors", "ler_id"),
                           ("ler_evidence", "ler_id"), ("question_outcomes", "question_id"),
                           ("ler_error_evidence", "ler_error_id")):
            grouped = defaultdict(list)
            for row in manifest[table]:
                grouped[row[key]].append(row)
            children[table] = grouped
        batch = EvidenceBatch(course_id=course_id, envelopes=[], source_manifest=manifest)
        for source in lers:
            ler = {key: value for key, value in source.items() if key != "analytics_metadata"}
            metadata = source.get("analytics_metadata")
            if not isinstance(metadata, dict) or metadata.get("schema_version") != "1.0":
                metadata = {}
                batch.issues.append(LoadIssue(ler_id=ler["id"], code="missing_analytics_metadata"))
            else:
                from .error_handoff import completion_metadata
                try:
                    metadata = completion_metadata(metadata)
                except ValueError:
                    metadata = {}
                    batch.issues.append(LoadIssue(ler_id=ler["id"], code="invalid_analytics_metadata"))
            envelope = {"ler": ler}
            bad = ler["learner_id"] not in learner_ids
            if bad:
                batch.issues.append(LoadIssue(ler_id=ler["id"], code="learner_not_in_course"))
            for name, (_, field, _) in RELATED.items():
                if ler.get(field):
                    row = related[name].get(ler[field])
                    if row is None:
                        batch.issues.append(LoadIssue(ler_id=ler["id"], code=f"missing_referenced_{name}"))
                        bad = True
                    else:
                        envelope[name] = row
                        if name == "practice":
                            for shared in ("hints_used", "independent_correctness"):
                                if ler.get(shared) is None and row.get(shared) is not None:
                                    batch.issues.append(LoadIssue(ler_id=ler["id"], code="practice_metadata_missing_from_ler"))
                                elif row.get(shared) is not None and ler.get(shared) != row[shared]:
                                    batch.issues.append(LoadIssue(ler_id=ler["id"], code="conflicting_practice_metadata"))
                                    bad = True
                            if ler.get("assistance_level") == "independent" and (row.get("hints_used") or 0) > 0:
                                batch.issues.append(LoadIssue(ler_id=ler["id"], code="conflicting_practice_assistance"))
                                bad = True
            qmaps = {r["outcome_id"]: r for r in children["question_outcomes"].get(ler.get("question_id"), [])}
            lmaps = children["ler_outcomes"].get(ler["id"], [])
            mappings = []
            explicit_weights = metadata.get("outcome_weights", {})
            explicit_weights = explicit_weights if isinstance(explicit_weights, dict) else {}
            for mapping in lmaps or list(qmaps.values()):
                oid = mapping["outcome_id"]
                if oid not in outcomes:
                    batch.issues.append(LoadIssue(ler_id=ler["id"], code="outcome_not_in_course"))
                    bad = True
                    continue
                weight = qmaps[oid]["weight"] if oid in qmaps else explicit_weights.get(oid)
                if weight is None:
                    batch.issues.append(LoadIssue(ler_id=ler["id"], code="missing_outcome_weight"))
                    continue
                mappings.append({"outcome_id": oid, "weight": weight,
                                 "provenance": mapping.get("provenance", "question_mapping"),
                                 "needs_review": mapping["needs_review"]})
            errors, all_refs = [], {r["evidence_ref_id"] for r in children["ler_evidence"].get(ler["id"], [])}
            grounded_errors = True
            error_outcomes = metadata.get("error_outcomes", {})
            error_outcomes = error_outcomes if isinstance(error_outcomes, dict) else {}
            for error in children["ler_errors"].get(ler["id"], []):
                error_refs = [r["evidence_ref_id"] for r in children["ler_error_evidence"].get(error["id"], [])]
                if not error_refs and error["instructor_status"] != "rejected":
                    grounded_errors = False
                    batch.issues.append(LoadIssue(ler_id=ler["id"], code="missing_error_evidence"))
                all_refs.update(error_refs)
                associated = error_outcomes.get(error["id"], [])
                if (not isinstance(associated, list) or not all(isinstance(oid, str) for oid in associated)
                        or not set(associated) <= {m["outcome_id"] for m in mappings}):
                    associated = []
                    batch.issues.append(LoadIssue(ler_id=ler["id"], code="invalid_error_outcome_attribution"))
                errors.append({"code": error["code"], "instructor_status": error["instructor_status"],
                               "evidence_ref_ids": error_refs, "outcome_ids": associated})
            if any(ref not in refs or refs[ref].get("learner_id") not in (None, ler["learner_id"]) for ref in all_refs):
                batch.issues.append(LoadIssue(ler_id=ler["id"], code="invalid_evidence_ownership"))
                bad = True
            if bad:
                continue
            analyzed = metadata.get("errors_analyzed")
            if not isinstance(analyzed, bool) or not grounded_errors:
                analyzed = None
            envelope.update(outcome_mappings=mappings, errors=errors, errors_analyzed=analyzed,
                            evidence_ref_ids=sorted(all_refs))
            batch.envelopes.append(envelope)
        return batch


def assemble_evidence_batch(course_id, manifest):
    """Apply the live repository's ownership and join rules without I/O."""
    return SupabaseEvidenceRepository._assemble(UUID(str(course_id)), manifest)

"""Deterministic hypothetical error inputs. No model calls or database writes."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import random
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, Field, model_validator

from .config import AnalyticsConfig
from .contracts import Contract
from .evidence_repository import EvidenceBatch, RELATED, assemble_evidence_batch
from .provenance import content_hash
from .service import _adapt

KIND = "synthetic_error_classification_overlay"
VERSION = "vibe101-overlay-1"
NAMESPACE = uuid5(NAMESPACE_URL, "hackohio2026:synthetic-error-overlay:v1")
VIBE_COURSE = UUID("94c2f9d7-6940-463f-aa55-f09f66a35835")
MARKER = "synthetic_demo_v1"
HASH = r"^sha256:[0-9a-f]{64}$"


def validate_manifest(course_id, manifest, *, taxonomy=None):
    """Complete offline manifests cannot rely on database FK/unique constraints."""
    identities = {name: ("id",) for name in ("lers", "learners", "responses", "questions", "attempts",
                  "assessments", "practice_attempts", "evidence_refs", "outcomes", "ler_errors")}
    identities.update(ler_outcomes=("ler_id", "outcome_id"), ler_evidence=("ler_id", "evidence_ref_id"),
                      ler_error_evidence=("ler_error_id", "evidence_ref_id"),
                      question_outcomes=("question_id", "outcome_id"))
    indexes = {}
    for table, keys in identities.items():
        rows = manifest[table]
        if not isinstance(rows, list):
            raise ValueError("invalid manifest table")
        seen = set()
        for row in rows:
            key = tuple(str(UUID(row[k])) for k in keys)
            if key in seen:
                raise ValueError("duplicate manifest identity")
            seen.add(key)
            if table not in ("ler_errors", "ler_outcomes", "ler_evidence", "ler_error_evidence", "question_outcomes") and row.get("course_id") != str(course_id):
                raise ValueError("cross-course manifest row")
        indexes[table] = {r[keys[0]]: r for r in rows} if keys == ("id",) else {}
    for ler in manifest["lers"]:
        if ler["learner_id"] not in indexes["learners"]:
            raise ValueError("unknown learner")
        for _, (table, field, _) in RELATED.items():
            if ler.get(field) and ler[field] not in indexes[table]:
                raise ValueError("missing related row")
    for table, targets in {
        "responses": {"learner_id": "learners", "attempt_id": "attempts", "question_id": "questions"},
        "questions": {"assessment_id": "assessments"},
        "attempts": {"learner_id": "learners", "assessment_id": "assessments"},
        "practice_attempts": {"learner_id": "learners"},
    }.items():
        for row in manifest[table]:
            if any(row[field] not in indexes[target] for field, target in targets.items()):
                raise ValueError("orphan academic source row")
    for table, targets in {
        "ler_errors": {"ler_id": "lers"}, "ler_outcomes": {"ler_id": "lers", "outcome_id": "outcomes"},
        "ler_evidence": {"ler_id": "lers", "evidence_ref_id": "evidence_refs"},
        "ler_error_evidence": {"ler_error_id": "ler_errors", "evidence_ref_id": "evidence_refs"},
        "question_outcomes": {"question_id": "questions", "outcome_id": "outcomes"},
    }.items():
        for row in manifest[table]:
            if any(row[field] not in indexes[target] for field, target in targets.items()):
                raise ValueError("orphan manifest relationship")
    if taxonomy is not None:
        codes = {r["code"] for r in taxonomy}
        if any(r["code"] not in codes for r in manifest["ler_errors"]):
            raise ValueError("error category missing from taxonomy")
    batch = assemble_evidence_batch(course_id, manifest)
    records, _, _ = _adapt(batch, AnalyticsConfig(), None)
    if len(batch.envelopes) != len(manifest["lers"]) or len(records) != len(batch.envelopes):
        raise ValueError("invalid manifest joins or analytical contracts")
    return batch


class DemoSourceSnapshot(Contract):
    schema_version: Literal["1.0"] = "1.0"
    captured_at: AwareDatetime
    base_batch: EvidenceBatch
    context: dict[str, list[dict]]
    snapshot_digest: str = Field(pattern=HASH)

    def digest(self):
        return content_hash({"base_batch": self.base_batch, "context": self.context})

    @model_validator(mode="after")
    def consistent(self):
        if self.snapshot_digest != self.digest():
            raise ValueError("source snapshot digest mismatch")
        rebuilt = validate_manifest(self.base_batch.course_id, self.base_batch.source_manifest,
                                    taxonomy=self.context["error_taxonomy"])
        if rebuilt.fingerprint() != self.base_batch.fingerprint():
            raise ValueError("source snapshot joins differ")
        manifest = self.base_batch.source_manifest
        for table in ("lers", "responses", "questions", "outcomes", "evidence_refs"):
            context = {r["id"]: r for r in self.context[table]}
            if len(context) != len(self.context[table]):
                raise ValueError("duplicate source context")
            for row in manifest[table]:
                full = context[row["id"]]
                for field, value in row.items():
                    expected = full.get(field)
                    if table == "lers" and field == "analytics_metadata":
                        raw = full.get("payload", {}).get("analytics_v1")
                        expected = ({k: raw[k] for k in ("schema_version", "errors_analyzed", "outcome_weights", "error_outcomes")
                                     if k in raw} if isinstance(raw, dict) else None)
                    if content_hash(value) != content_hash(expected):
                        raise ValueError("source context differs from analytical snapshot")
        if len({r["code"] for r in self.context["error_taxonomy"]}) != len(self.context["error_taxonomy"]):
            raise ValueError("duplicate taxonomy code")
        for row in self.context["feedback"]:
            response = next((r for r in self.context["responses"] if r["id"] == row["response_id"]), None)
            if (not response or row["course_id"] != str(self.base_batch.course_id)
                    or row["learner_id"] != response["learner_id"]):
                raise ValueError("feedback context ownership mismatch")
        return self


class SyntheticGenerationConfig(Contract):
    generator_version: Literal["vibe101-overlay-1"] = VERSION
    seed: int = Field(default=2026, ge=0, strict=True)
    target_error_lers: int = Field(default=60, ge=1, le=80, strict=True)
    no_error_cases: int = Field(default=10, ge=0, le=30, strict=True)
    not_completed_cases: int = Field(default=5, ge=0, le=30, strict=True)
    ambiguous_cases: int = Field(default=5, ge=0, le=30, strict=True)


class ThemeBinding(Contract):
    question_id: UUID
    question_digest: str = Field(pattern=HASH)
    code: str
    outcome_ids: list[UUID] = Field(min_length=1)


class SyntheticError(Contract):
    id: UUID
    code: str
    description: str = Field(min_length=1, max_length=1000)
    instructor_status: Literal["unreviewed"] = "unreviewed"
    outcome_ids: list[UUID] = Field(min_length=1)
    evidence_ref_ids: list[UUID] = Field(min_length=1)


class SyntheticClassification(Contract):
    ler_id: UUID
    ler_revision: int = Field(ge=1, strict=True)
    learner_id: UUID
    question_id: UUID
    state: Literal["completed_with_errors", "completed_no_errors", "not_completed", "ambiguous"]
    selection_basis: Literal["hypothetical_from_question_context"] = "hypothetical_from_question_context"
    response_text_available: bool
    errors: list[SyntheticError]

    @model_validator(mode="after")
    def consistent(self):
        if bool(self.errors) != (self.state == "completed_with_errors"):
            raise ValueError("synthetic classification state contradicts errors")
        if len({e.code for e in self.errors}) != len(self.errors):
            raise ValueError("duplicate synthetic LER/code")
        return self


class SyntheticEvidence(Contract):
    id: UUID
    course_id: UUID
    learner_id: UUID
    source_type: Literal["manual"] = "manual"
    document_id: None = None
    page: None = None
    bbox_norm: None = None
    canvas_ref: str
    excerpt: str
    content_hash: str = Field(pattern=HASH)
    synthetic: Literal[True] = True
    source_ler_id: UUID
    source_question_id: UUID
    source_response_id: UUID


class ExcerptCandidate(Contract):
    ler_id: UUID
    ler_revision: int
    ler_error_id: UUID
    error_code: str
    text: str = Field(min_length=1, max_length=1000)
    source_kind: Literal["error_description"] = "error_description"
    evidence_ref_ids: list[UUID] = Field(min_length=1)
    decision: Literal["pending"] = "pending"
    privacy_reviewed: Literal[False] = False
    context_reviewed: Literal[False] = False
    reviewer_ref: None = None
    reviewed_at: None = None


class SyntheticDemoProvenance(Contract):
    schema_version: Literal["1.0"]
    dataset_kind: Literal["synthetic_error_classification_overlay"]
    dataset_id: UUID
    content_digest: str = Field(pattern=HASH)
    source_snapshot_digest: str = Field(pattern=HASH)
    original_source_fingerprint: str = Field(pattern=HASH)
    seed: int = Field(ge=0, strict=True)
    generator_version: Literal["vibe101-overlay-1"]
    original_performance_retained: Literal[True]
    synthetic_classifications: Literal[True]
    interpretation_limit: str = Field(min_length=1)


class SyntheticDataset(Contract):
    schema_version: Literal["1.0"] = "1.0"
    dataset_kind: Literal["synthetic_error_classification_overlay"]
    dataset_id: UUID
    course_id: UUID
    source_snapshot_digest: str = Field(pattern=HASH)
    original_source_fingerprint: str = Field(pattern=HASH)
    generated_at: AwareDatetime
    config: SyntheticGenerationConfig
    bindings: list[ThemeBinding]
    classifications: list[SyntheticClassification]
    evidence: list[SyntheticEvidence]
    taxonomy: list[dict[str, str]]
    excerpt_candidates: list[ExcerptCandidate]
    content_digest: str = Field(pattern=HASH)

    def digest(self):
        return content_hash(self.model_dump(mode="json", exclude={"generated_at", "content_digest"}))

    @model_validator(mode="after")
    def consistent(self):
        if self.content_digest != self.digest():
            raise ValueError("synthetic content digest mismatch")
        if len({c.ler_id for c in self.classifications}) != len(self.classifications):
            raise ValueError("duplicate overlay LER")
        return self

    def provenance(self):
        return SyntheticDemoProvenance.model_validate({"schema_version": "1.0", "dataset_kind": KIND, "dataset_id": str(self.dataset_id),
                "content_digest": self.content_digest, "source_snapshot_digest": self.source_snapshot_digest,
                "original_source_fingerprint": self.original_source_fingerprint,
                "seed": self.config.seed, "generator_version": VERSION,
                "original_performance_retained": True, "synthetic_classifications": True,
                "interpretation_limit": "Original recorded scores with hypothetical error classifications; not measured learner misconceptions."}).model_dump(mode="json")


# Exact curriculum anchors resolve to pinned question UUID/content bindings.
# Quotas are input selection limits, never desired DBSCAN groups.
THEMES = {
    "missing_prompt_constraints": ("Missing prompt constraints", "LO-02", 14,
        ("Build a command-line to-do app", "The five parts of a good prompt are:",
         "Which prompt is the strongest?", "Rewrite this weak prompt"),
        ("The prompt omits required constraints on the generated program's behavior.",
         "The specification leaves out restrictions that the implementation must satisfy.",
         "The request describes the goal but does not state the required implementation constraints.",
         "The prompt fails to tell the assistant which requirements its solution must obey.",
         "Important limits on acceptable behavior are missing from the written specification.",
         "The instructions omit constraints needed to distinguish a valid solution from a plausible one.")),
    "missing_edge_case_tests": ("Missing edge-case tests", "LO-04", 14,
        ("Practice test-first development.", "You are the code reviewer.",
         "Which is an edge case for a function that finds the maximum", "In test-first prompting"),
        ("Tests cover ordinary lists but never check an empty list.",
         "The proposed tests omit the empty-input boundary case.",
         "The test plan never exercises a collection with zero elements.",
         "The function is accepted without testing how it handles an empty collection.",
         "Only nonempty examples are tested, leaving empty-input behavior unchecked.",
         "The boundary test for a list containing no values is missing.")),
    "sql_injection_risk": ("SQL injection risk", "LO-05", 10,
        ("You are the code reviewer.", "Which code is vulnerable to SQL injection?"),
        ("The SQL query concatenates user input instead of binding parameters.",
         "Untrusted text is inserted directly into the database query string.",
         "The proposed database call builds SQL from user-supplied strings without parameters.",
         "User input becomes executable SQL because the query is assembled by concatenation.",
         "The repair leaves string-built SQL in place instead of using a parameterized statement.",
         "The query treats supplied text as SQL syntax rather than a bound value.")),
    "unsafe_secret_handling": ("Unsafe secret handling", "LO-05", 10,
        ("You are the code reviewer.", "Where should an API key be stored?",
         "You accidentally committed an API key"),
        ("The proposed solution keeps an API key directly in source code.",
         "A service credential remains hard-coded in the submitted program.",
         "The implementation embeds a secret in a file that can be committed.",
         "The repair does not move the hard-coded credential out of version-controlled code.",
         "The code stores an access secret as a source-code literal.",
         "Secret configuration is left inside the program instead of private runtime settings.")),
    "debugging_by_regeneration": ("Debugging by regeneration", "LO-02", 3,
        ("You've rewritten your prompt six times",),
        ("Repeated prompt changes replace isolating why the generated program fails.",
         "The debugging approach retries prompts without diagnosing the underlying failure.",
         "The response proposes another regeneration rather than investigating the reproducible bug.")),
    "mutable_default_argument": ("Mutable default argument", "LO-03", 3,
        ("def add(x, items=[])", "You are the code reviewer."),
        ("The function shares a default list between calls instead of creating fresh state.",
         "A mutable default argument retains data from earlier calls.",
         "The default list is reused, allowing one call to affect the next call.")),
    "license_attribution_omitted": ("Missing license check", "LO-05", 3,
        ("Generated code closely resembles a known open-source library.",),
        ("The response accepts copied-looking code without checking its license obligations.",
         "Reuse proceeds without verifying attribution and redistribution requirements.",
         "The proposed action omits a license review before incorporating the generated code.")),
}


def bind_themes(snapshot):
    """Pin task-specific rules to actual question identities and valid mappings."""
    questions = {r["id"]: r for r in snapshot.context["questions"]}
    outcomes = {r["id"]: r["code"] for r in snapshot.context["outcomes"]}
    records, _, _ = _adapt(snapshot.base_batch, AnalyticsConfig(), None)
    bindings = {}
    for record in records:
        question = questions[str(record.question_id)]
        for code, (_, outcome_code, _, anchors, _) in THEMES.items():
            # Grade/excerpt contents never act as a classifier here.
            if not any(anchor.casefold() in question["text"].casefold() for anchor in anchors):
                continue
            allowed = sorted((m.outcome_id for m in record.outcome_mappings
                              if m.weight > 0 and outcomes.get(str(m.outcome_id)) == outcome_code), key=str)
            if allowed:
                binding = ThemeBinding(question_id=record.question_id, question_digest=content_hash(question),
                                       code=code, outcome_ids=allowed)
                key = (str(record.question_id), code)
                if key in bindings and bindings[key] != binding:
                    raise ValueError("inconsistent per-LER theme mapping")
                bindings[key] = binding
    return [bindings[key] for key in sorted(bindings)]


def generate_dataset(snapshot, config=None, *, generated_at=None):
    snapshot = DemoSourceSnapshot.model_validate_json(snapshot.model_dump_json())
    config = config or SyntheticGenerationConfig()
    if snapshot.base_batch.course_id != VIBE_COURSE:
        raise ValueError("generator is scoped to the existing VIBE 101 course")
    bindings = bind_themes(snapshot)
    token = content_hash({"source": snapshot.snapshot_digest, "config": config, "bindings": bindings})
    dataset_id = uuid5(NAMESPACE, token)
    rng = random.Random(config.seed)
    records, features, _ = _adapt(snapshot.base_batch, AnalyticsConfig(), None)
    primary = set(features.observations.loc[features.observations.primary_score, "ler_id"])
    existing_errors = {row["ler_id"] for row in snapshot.base_batch.source_manifest["ler_errors"]}
    eligible = [r for r in records if str(r.ler_id) in primary and r.analysis_status == "analyzed"
                and r.assistance == "independent" and r.assessment_origin == "graded_canvas"
                and r.errors_analyzed is not True and str(r.ler_id) not in existing_errors]
    eligible.sort(key=lambda r: str(r.ler_id))
    responses = {r["id"]: r for r in snapshot.context["responses"]}
    bound = {(str(b.question_id), b.code): b for b in bindings}
    selected, classifications, evidence, candidates = set(), [], [], []
    learner_counts = Counter()

    def classification(record, state, errors):
        return SyntheticClassification(ler_id=record.ler_id, ler_revision=record.revision,
            learner_id=record.learner_id, question_id=record.question_id, state=state, errors=errors,
            response_text_available=bool(responses[str(record.response_id)].get("response_text")))

    pools = {}
    for code in THEMES:
        pool = [r for r in eligible if r.points_earned < r.points_possible
                and (str(r.question_id), code) in bound]
        rng.shuffle(pool)
        pools[code] = pool
    counts = Counter()
    # Round-robin themes, preferring distinct learners within each theme.
    while len(selected) < config.target_error_lers:
        progressed = False
        for code, (_, _, quota, _, variants) in THEMES.items():
            pool = [r for r in pools[code] if r.ler_id not in selected]
            if not pool or counts[code] >= quota or len(selected) >= config.target_error_lers:
                continue
            record = min(pool, key=lambda r: learner_counts[(code, r.learner_id)])
            binding = bound[(str(record.question_id), code)]
            error_id = uuid5(dataset_id, f"error:{record.ler_id}:{code}")
            ref_id = uuid5(dataset_id, f"evidence:{record.ler_id}:{code}")
            text = variants[counts[code] % len(variants)]
            excerpt = "SYNTHETIC DEMONSTRATION: hypothetical classification from question context; not an instructor annotation or observed learner quotation. " + text
            evidence.append(SyntheticEvidence(id=ref_id, course_id=VIBE_COURSE, learner_id=record.learner_id,
                canvas_ref=f"synthetic-demo://{dataset_id}/{ref_id}", excerpt=excerpt, content_hash=content_hash(excerpt),
                source_ler_id=record.ler_id, source_question_id=record.question_id, source_response_id=record.response_id))
            error = SyntheticError(id=error_id, code=code, description=text,
                                   outcome_ids=binding.outcome_ids, evidence_ref_ids=[ref_id])
            classifications.append(classification(record, "completed_with_errors", [error]))
            candidates.append(ExcerptCandidate(ler_id=record.ler_id, ler_revision=record.revision,
                ler_error_id=error_id, error_code=code, text=text, evidence_ref_ids=[ref_id]))
            selected.add(record.ler_id)
            counts[code] += 1
            learner_counts[(code, record.learner_id)] += 1
            progressed = True
        if not progressed:
            break
    remaining = [r for r in eligible if r.ler_id not in selected]
    rng.shuffle(remaining)
    for state, count in (("completed_no_errors", config.no_error_cases),
                         ("not_completed", config.not_completed_cases), ("ambiguous", config.ambiguous_cases)):
        chosen, remaining = remaining[:count], remaining[count:]
        classifications.extend(classification(r, state, []) for r in chosen)
    fields = dict(dataset_kind=KIND, dataset_id=dataset_id, course_id=VIBE_COURSE,
        source_snapshot_digest=snapshot.snapshot_digest, original_source_fingerprint=snapshot.base_batch.fingerprint(),
        generated_at=generated_at or datetime.now(timezone.utc), config=config, bindings=bindings,
        classifications=sorted(classifications, key=lambda c: str(c.ler_id)),
        evidence=sorted(evidence, key=lambda e: str(e.id)),
        taxonomy=[{"code": code, "label": THEMES[code][0]} for code in sorted(counts)],
        excerpt_candidates=sorted(candidates, key=lambda e: str(e.ler_error_id)))
    existing_taxonomy = {r["code"]: r for r in snapshot.context["error_taxonomy"]}
    if any(row["code"] in existing_taxonomy and existing_taxonomy[row["code"]]["label"] != row["label"]
           for row in fields["taxonomy"]):
        raise ValueError("synthetic taxonomy conflicts with an existing category")
    unvalidated = SyntheticDataset.model_construct(**fields, content_digest="")
    fields["content_digest"] = unvalidated.digest()
    return SyntheticDataset(**fields)


def materialize(snapshot, dataset):
    """Reproduce the overlay exactly before assembling full-manifest input."""
    snapshot = DemoSourceSnapshot.model_validate_json(snapshot.model_dump_json())
    dataset = SyntheticDataset.model_validate_json(dataset.model_dump_json())
    expected = generate_dataset(snapshot, dataset.config, generated_at=dataset.generated_at)
    if expected != dataset:
        raise ValueError("dataset does not reproduce from its source and rules")
    manifest = deepcopy(snapshot.base_batch.source_manifest)
    original_ids = {r["id"] for table in ("lers", "ler_errors", "evidence_refs") for r in manifest[table]}
    generated_ids = [str(e.id) for e in dataset.evidence] + [str(e.id) for c in dataset.classifications for e in c.errors]
    if len(generated_ids) != len(set(generated_ids)) or original_ids.intersection(generated_ids):
        raise ValueError("generated ID collision")
    lers = {r["id"]: r for r in manifest["lers"]}
    for item in dataset.classifications:
        ler = lers[str(item.ler_id)]
        meta = deepcopy(ler.get("analytics_metadata") or {})
        meta.update(schema_version="1.0", errors_analyzed={"completed_with_errors": True,
            "completed_no_errors": True, "not_completed": False, "ambiguous": None}[item.state])
        attribution = deepcopy(meta.get("error_outcomes", {}))
        for error in item.errors:
            manifest["ler_errors"].append({"id": str(error.id), "ler_id": str(item.ler_id),
                "code": error.code, "instructor_status": "unreviewed"})
            attribution[str(error.id)] = list(map(str, error.outcome_ids))
            for ref in error.evidence_ref_ids:
                manifest["ler_error_evidence"].append({"ler_error_id": str(error.id), "evidence_ref_id": str(ref)})
                manifest["ler_evidence"].append({"ler_id": str(item.ler_id), "evidence_ref_id": str(ref),
                                                "role": "synthetic_classification"})
        meta["error_outcomes"] = attribution
        ler["analytics_metadata"] = meta
    manifest["evidence_refs"].extend(e.model_dump(mode="json") for e in dataset.evidence)
    # The complete synthetic scenario and its reviewed candidate text live in the
    # dataset artifact; the analytical row projection remains the standard one.
    manifest[MARKER] = dataset.provenance()
    return validate_manifest(dataset.course_id, manifest,
                             taxonomy=snapshot.context["error_taxonomy"] + dataset.taxonomy)

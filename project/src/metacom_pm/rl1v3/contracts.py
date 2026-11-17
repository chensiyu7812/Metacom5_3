"""C0 exchange contracts (WS-A authored, WS-B review required before freeze).

All records are frozen dataclasses with recursively immutable fields. Private
records must never be serialized as observations. Only Observation/ReadingView
and VisiblePrefix cross the actor/critic/Generator boundary. Source text remains
untrusted data, even when a span has been mechanically verified.

TimePoint carries calendar time only when present in the source. A rank is local
to one owner, never globally comparable. invalid_at is *knowledge* time;
valid_to is the reported end of the *fact's* validity and stays null if unknown.
Resource body is a private canonical-JSON string for type-specific/legacy data;
it is not a rendering surface. Fields cannot be added without schema versioning.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, TypeAdapter, model_validator
from pydantic.dataclasses import dataclass

from .io import SCHEMA_VERSION, object_sha256, sha256_text

Id = Annotated[str, Field(min_length=1)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Nonnegative = Annotated[int, Field(ge=0)]
Positive = Annotated[int, Field(gt=0)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Cost = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Head = Literal["RS", "MP", "ME", "MS"]
Role = Literal["seeker", "supporter"]
Stage = Literal["suggested", "intended", "attempted", "completed", "outcome_reported", "unknown"]
Verdict = Literal["pass", "fail", "uncertain"]
Review = Literal["unverified", "development_reviewed", "independent_reviewed", "professional_approved", "rejected", "unusable"]
Semantic = Literal["unverified", "supported", "uncertain", "rejected"]
Epistemic = Literal["user_reported", "supporter_suggestion", "reported_intention", "inferred_unverified", "unknown"]
Tier = Literal["engineering_only", "research_qualified", "human_confirmed"]
Stratum = Literal["history", "method", "both", "none"]
Action = Literal["GET_RS", "GET_MP", "GET_ME", "GET_MS", "STOP", "EXPAND_MS"]


def contract(cls):
    return dataclass(cls, frozen=True, slots=True, kw_only=True,
                     config=ConfigDict(extra="forbid", strict=True, validate_default=True))


@contract
class Contract:
    schema_version: Literal["pmrl1v3-contracts-0.1.0"] = SCHEMA_VERSION

    @property
    def sha256(self) -> str:
        return object_sha256(self)


def check_schema_version(value):
    if isinstance(value, dict):
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("explicit supported schema_version required on every contract")
        for nested in value.values():
            check_schema_version(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            check_schema_version(nested)


@contract
class TimePoint(Contract):
    """Null calendar date never means epoch; at least one coordinate is known."""
    date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None
    session_rank: Nonnegative | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.date is None and self.session_rank is None:
            raise ValueError("time needs date or rank; use null for unknown time")
        if self.date is not None:
            date.fromisoformat(self.date)
        return self


def _not_before(later: TimePoint | None, earlier: TimePoint | None, label: str):
    if later is None or earlier is None:
        return
    if later.session_rank is not None and earlier.session_rank is not None:
        if later.session_rank < earlier.session_rank:
            raise ValueError(label + " precedes earlier rank")
    if later.date is not None and earlier.date is not None and later.date < earlier.date:
        raise ValueError(label + " precedes earlier date")


@contract
class SourceTurn(Contract):
    turn_index: Nonnegative
    role: Role
    text: str  # empty original turns are preserved, not silently removed

    @property
    def raw_turn_sha256(self):
        return sha256_text(self.text)


@contract
class SourceSession(Contract):
    owner_id: Id
    session_id: Id
    chronological_rank: Nonnegative
    date: str | None
    turns: Annotated[tuple[SourceTurn, ...], Field(min_length=1)]
    raw_sha256: Sha256  # exact source file bytes, NOT reserialized source objects
    dataset: Id
    family_id: Id
    license: Id  # unknown is explicit, not assumed permission
    provenance_version: Id
    source_uri: Id
    transcript_sha256: Sha256
    source_split: Literal["train", "dev", "validation", "test", "unassigned", "negative_only"]
    ancestor_family_ids: tuple[Id, ...] = ()
    excluded_for_overlap: bool = False
    complete: bool = True

    @model_validator(mode="after")
    def valid(self):
        if self.date is not None:
            date.fromisoformat(self.date)
        if tuple(t.turn_index for t in self.turns) != tuple(range(len(self.turns))):
            raise ValueError("source turns must be contiguous in original order")
        if self.transcript_sha256 != object_sha256([(t.role, t.text) for t in self.turns]):
            raise ValueError("transcript hash mismatch")
        return self


@contract
class SourceSpan(Contract):
    source_key: Id
    owner_id: Id
    session_id: Id
    source_rank: Nonnegative
    turn_index: Nonnegative
    speaker: Role
    start_char: Nonnegative
    end_char: Positive
    exact_quote: Annotated[str, Field(min_length=1)]
    raw_turn_sha256: Sha256

    @model_validator(mode="after")
    def valid(self):
        if self.end_char <= self.start_char or self.end_char - self.start_char != len(self.exact_quote):
            raise ValueError("span offsets must match Unicode quote length")
        return self

    def verify(self, source: SourceSession) -> None:
        if (self.owner_id, self.session_id, self.source_rank) != (
                source.owner_id, source.session_id, source.chronological_rank):
            raise ValueError("span source identity mismatch")
        if self.turn_index >= len(source.turns):
            raise ValueError("span turn missing")
        turn = source.turns[self.turn_index]
        expected_key = f"{source.dataset}:{source.owner_id}:{source.session_id}:{self.turn_index}"
        if self.source_key != expected_key:
            raise ValueError("unmapped source_key")
        if turn.role != self.speaker or turn.raw_turn_sha256 != self.raw_turn_sha256:
            raise ValueError("span role/hash mismatch")
        if turn.text[self.start_char:self.end_char] != self.exact_quote:
            raise ValueError("span quote mismatch")


@contract
class PrefixSpec(Contract):
    """Execution-private routing envelope; use visible() for model input."""
    prefix_id: Id
    owner_id: Id
    session_id: Id
    cut_turn: Nonnegative  # inclusive, zero based
    turns: Annotated[tuple[SourceTurn, ...], Field(min_length=1)]
    cutoff_rank: Nonnegative
    timestamp: str | None
    dataset: Id
    family_id: Id
    ancestor_family_ids: tuple[Id, ...] = ()
    stratum: Stratum | None = None  # evaluation only
    split: Literal["train", "dev", "test", "unassigned"] = "unassigned"
    fold: Nonnegative | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.timestamp is not None:
            date.fromisoformat(self.timestamp)
        if tuple(t.turn_index for t in self.turns) != tuple(range(self.cut_turn + 1)):
            raise ValueError("prefix must contain exactly turns 0..cut_turn")
        if self.turns[-1].role != "seeker":
            raise ValueError("reply prefix must end with seeker")
        return self

    def visible(self) -> VisiblePrefix:
        return VisiblePrefix(turns=self.turns, timestamp=self.timestamp)

    @classmethod
    def from_legacy(cls, prefix, *, dataset: str, family_id: str,
                    ancestor_family_ids: tuple[str, ...] = ()) -> PrefixSpec:
        """Adapter for rl1.schema.PrefixSpec; no dependency on legacy runtime."""
        return cls(prefix_id=prefix.identity, owner_id=prefix.owner_id,
                   session_id=prefix.session_id, cut_turn=prefix.cut_after_turn_index,
                   cutoff_rank=prefix.cutoff_rank, timestamp=prefix.timestamp,
                   turns=tuple(SourceTurn(turn_index=i, role=t.role, text=t.content)
                               for i, t in enumerate(prefix.turns)),
                   dataset=dataset, family_id=family_id,
                   ancestor_family_ids=ancestor_family_ids, split=prefix.split)


@contract
class VisiblePrefix(Contract):
    turns: Annotated[tuple[SourceTurn, ...], Field(min_length=1)]
    timestamp: str | None


@contract
class ResourceRecord(Contract):
    record_id: Id
    bank_version: Id
    head: Head
    view: Literal["method", "case", "assertion", "event", "sum", "raw"]
    owner_id: Id | None
    source_refs: tuple[SourceSpan, ...]
    reported_at: TimePoint | None
    event_time: TimePoint | None
    valid_from: TimePoint | None
    invalid_at: TimePoint | None
    stage: Stage | None
    body: str
    reading_text: Annotated[str, Field(min_length=1)]
    index_keys: tuple[Id, ...]
    review_status: Review
    writer_identity: Id
    source_rank: Nonnegative | None
    ready_at: TimePoint | None
    origin_dataset: Id
    family_id: Id
    original_raw_identity: Sha256
    valid_to: TimePoint | None = None
    invalidated_knowledge_rank: Nonnegative | None = None
    invalidation_source_refs: tuple[SourceSpan, ...] = ()
    ancestor_family_ids: tuple[Id, ...] = ()
    subject_id: Id | None = None
    entity_ids: tuple[Id, ...] = ()
    parent_session_id: Id | None = None
    raw_parent_id: Id | None = None
    parent_event_id: Id | None = None
    related_claim_ids: tuple[Id, ...] = ()
    evidence_status: Literal["exact_span_verified", "semantically_supported", "uncertain", "rejected"] = "uncertain"
    epistemic_status: Epistemic = "unknown"
    raw_view_identity: Sha256 | None = None
    summary_view_identity: Sha256 | None = None
    relation_index_version: Id | None = None
    license_scope: Id = "unknown"
    risk_tier: Literal["ordinary", "high", "unknown"] = "unknown"
    usage_scope: Literal["engineering_only", "research_only", "deployment"] = "engineering_only"
    source_split: Literal["train", "dev", "validation", "test", "unassigned", "negative_only"] = "unassigned"
    positive_eligible: bool = False

    @model_validator(mode="after")
    def valid(self):
        allowed = {"RS": ("method", "case"), "MP": ("assertion",), "ME": ("event",), "MS": ("sum", "raw")}
        if self.view not in allowed[self.head]:
            raise ValueError("head/view mismatch")
        if self.head == "RS":
            if self.owner_id is not None or self.stage is not None:
                raise ValueError("RS has no personal owner/stage")
            if self.risk_tier != "ordinary" and self.usage_scope == "deployment" and self.review_status != "professional_approved":
                raise ValueError("high/unknown-risk deployment needs professional approval")
            if self.positive_eligible and self.source_split == "negative_only":
                raise ValueError("negative sources cannot become positive cases")
        else:
            if self.owner_id is None or self.source_rank is None or self.reported_at is None or self.ready_at is None or not self.source_refs:
                raise ValueError("memory needs owner, rank, report, readiness and spans")
            if any(s.owner_id != self.owner_id or s.source_rank > self.source_rank for s in self.source_refs):
                raise ValueError("memory dependency owner/rank mismatch")
            if self.reported_at.session_rank != self.source_rank:
                raise ValueError("reported_at rank must bind source_rank")
        if (self.head == "ME") != (self.stage is not None):
            raise ValueError("only ME has a mandatory stage")
        if self.epistemic_status == "supporter_suggestion" and self.stage not in (None, "suggested", "unknown"):
            raise ValueError("suggestion is not user execution")
        if self.view == "sum" and (self.raw_parent_id is None or self.parent_session_id is None):
            raise ValueError("SUM needs distinct RAW parent and session")
        if self.raw_parent_id == self.record_id:
            raise ValueError("resource cannot be its own parent")
        if self.evidence_status == "semantically_supported" and self.review_status in ("unverified", "rejected", "unusable"):
            raise ValueError("unreviewed/rejected record cannot assert semantic support")
        if self.invalidated_knowledge_rank is not None:
            if self.invalid_at is None or self.invalid_at.session_rank != self.invalidated_knowledge_rank or not self.invalidation_source_refs:
                raise ValueError("knowledge invalidation needs matching time and evidence")
            if (max(s.source_rank for s in self.invalidation_source_refs) != self.invalidated_knowledge_rank
                    or any(s.owner_id != self.owner_id for s in self.invalidation_source_refs)):
                raise ValueError("invalidation source owner/rank mismatch")
        elif self.invalid_at is not None:
            raise ValueError("invalid_at needs explicit invalidated_knowledge_rank")
        _not_before(self.ready_at, self.reported_at, "ready_at")
        _not_before(self.invalid_at, self.reported_at, "invalid_at")
        _not_before(self.valid_to, self.valid_from, "valid_to")
        return self


@contract
class TemporalClaim(Contract):
    claim_id: Id
    head: Literal["MP", "ME"]
    subject_id: Id
    predicate: Id
    object: Id
    reported_at: TimePoint
    source_rank: Nonnegative
    event_time: TimePoint | None
    valid_from: TimePoint | None
    valid_to: TimePoint | None
    invalidated_knowledge_rank: Nonnegative | None
    epistemic_status: Epistemic
    evidence_spans: Annotated[tuple[SourceSpan, ...], Field(min_length=1)]
    semantic_support: Semantic
    version_group: Id
    invalidation_source_refs: tuple[SourceSpan, ...] = ()

    @model_validator(mode="after")
    def valid(self):
        if self.reported_at.session_rank != self.source_rank or any(s.source_rank > self.source_rank for s in self.evidence_spans):
            raise ValueError("claim source/report rank mismatch")
        if len({s.owner_id for s in self.evidence_spans}) != 1:
            raise ValueError("claim has mixed owners")
        if self.invalidated_knowledge_rank is not None and (self.invalidated_knowledge_rank < self.source_rank or not self.invalidation_source_refs):
            raise ValueError("claim invalidation needs subsequent evidence")
        if self.invalidated_knowledge_rank is not None:
            if (max(s.source_rank for s in self.invalidation_source_refs) != self.invalidated_knowledge_rank
                    or any(s.owner_id != self.evidence_spans[0].owner_id for s in self.invalidation_source_refs)):
                raise ValueError("claim invalidation source owner/rank mismatch")
        _not_before(self.valid_to, self.valid_from, "valid_to")
        return self


@contract
class TemporalRelation(Contract):
    edge_id: Id
    relation_type: Literal["updates", "contradicts", "follows", "follow_up", "outcome_of", "mentions", "derived_from", "parent_session", "about_entity", "same_event_group"]
    left_id: Id
    right_id: Id
    direction: Literal["left_to_right", "symmetric"]
    evidence_spans: tuple[SourceSpan, ...]
    reported_at: TimePoint
    derivation_identity: Id
    review_status: Review
    semantic_support: Semantic

    @model_validator(mode="after")
    def valid(self):
        if self.left_id == self.right_id:
            raise ValueError("self relation is not evidence")
        if self.semantic_support == "supported" and (not self.evidence_spans or self.review_status in ("unverified", "rejected", "unusable")):
            raise ValueError("supported relation requires evidence and review")
        if self.relation_type not in ("contradicts", "same_event_group") and self.direction != "left_to_right":
            raise ValueError("directed relation cannot be symmetric")
        return self


@contract
class ReadingView(Contract):
    head: Head
    ordinal: Positive
    reading_text: Annotated[str, Field(min_length=1)]
    reported_at: TimePoint | None
    tokens: Nonnegative
    stage: Stage | None = None

    @model_validator(mode="after")
    def valid(self):
        if (self.head == "ME") != (self.stage is not None):
            raise ValueError("ME reading requires stage; other heads have no stage")
        return self


@contract
class HeadAvailability(Contract):
    head: Head
    available: bool
    count: Nonnegative

    @model_validator(mode="after")
    def valid(self):
        if self.available != (self.count > 0):
            raise ValueError("availability/count mismatch")
        return self


@contract
class Observation(Contract):
    """Same whitelist for actor and critic. No IDs, ranks or reward labels."""
    prefix: VisiblePrefix
    acquired: tuple[ReadingView, ...]
    availability: tuple[HeadAvailability, ...]
    action_mask: tuple[Action, ...]
    input_tokens: Nonnegative

    @model_validator(mode="after")
    def valid(self):
        if tuple(x.ordinal for x in self.acquired) != tuple(range(1, len(self.acquired) + 1)):
            raise ValueError("reading ordinals must match acquisition order")
        if len({x.head for x in self.availability}) != len(self.availability):
            raise ValueError("duplicate availability head")
        if len(set(self.action_mask)) != len(self.action_mask):
            raise ValueError("duplicate action")
        return self


@contract
class ScoreComponent(Contract):
    name: Literal["lexical", "dense", "bm25", "rrf", "temporal", "graph", "entity", "slot"]
    score: Finite
    rank: Positive | None = None


@contract
class RankedCandidate(Contract):
    record_id: Id
    score: Finite
    components: tuple[ScoreComponent, ...]


@contract
class RetrievalResult(Contract):
    """Private execution envelope, never an Observation field."""
    head: Head
    ranked: tuple[RankedCandidate, ...]
    query_identity: Sha256
    filters_applied: tuple[Id, ...]
    bank_version: Id
    index_version: Id

    @model_validator(mode="after")
    def valid(self):
        if len({x.record_id for x in self.ranked}) != len(self.ranked):
            raise ValueError("duplicate retrieval candidates")
        return self


@contract
class IndexManifest(Contract):
    index_version: Id
    bank_version: Id
    bank_sha256: Sha256
    head: Head
    encoder_id: Id
    encoder_revision: Id
    encoder_sha256: Sha256
    encoder_dimension: Positive
    encoder_max_tokens: Positive
    sparse_method: Literal["bm25"]
    sparse_identity: Id
    normalization: Literal["l2"]
    pooling: Literal["cls"]
    chunker_identity: Id
    records_sha256: Sha256
    vectors_sha256: Sha256
    built_at: Id
    rrf_k: Positive = 60


@contract
class Rejection(Contract):
    record_id: Id
    reason: Id


@contract
class RetrievalTrace(Contract):
    prefix_sha256: Sha256
    query_identity: Sha256
    query_text: str
    query_mode: Literal["static", "adaptive"]
    acquired_view_sha256: tuple[Sha256, ...]
    bank_version: Id
    index_version: Id
    result: RetrievalResult
    rejected: tuple[Rejection, ...]
    elapsed_ms: Cost
    retrieval_identity: Id

    @model_validator(mode="after")
    def valid(self):
        if (self.query_identity, self.bank_version, self.index_version) != (self.result.query_identity, self.result.bank_version, self.result.index_version):
            raise ValueError("trace/result identity mismatch")
        return self


@contract
class HistoryItem(Contract):
    record_id: Id | None
    spans: Annotated[tuple[SourceSpan, ...], Field(min_length=1)]
    role: Literal["required", "relevant_optional", "must_not_contradict"]
    source_role: Role
    source_rank: Nonnegative

    @model_validator(mode="after")
    def valid(self):
        if any(s.speaker != self.source_role or s.source_rank != self.source_rank for s in self.spans):
            raise ValueError("history role/rank mismatch")
        return self


@contract
class NeedCard(Contract):
    prefix_id: Id
    stratum: Stratum
    history_items: tuple[HistoryItem, ...]
    failed_or_rejected: tuple[SourceSpan, ...]
    outdated_facts: tuple[SourceSpan, ...]
    method_need: Id | None
    risk_flags: tuple[Id, ...]
    visibility_scope: Literal["evaluation_only"] = "evaluation_only"


@contract
class ChecklistItem(Contract):
    item_id: Id
    category: Literal["H+", "H-", "R", "G", "I", "S"]
    constraint_type: Literal["hard_factual", "hard_safety", "soft_support", "relevance"]
    text: Id
    evidence_spans: tuple[SourceSpan, ...]
    weight: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    applies_to: Literal["all_terminals"]
    visibility_scope: Literal["evaluation_only"]
    review_status: Review


@contract
class TerminalKey(Contract):
    prefix_id: Id
    bank_version: Id
    index_version: Id
    ordered_path: tuple[Id, ...]  # EXPAND_MS(j) keeps its visible ordinal in the string
    acquired_record_ids: tuple[Id, ...]
    renderer_id: Id
    step2_id: Id
    g_id: Id
    decode_id: Id  # seed, limits, sampling and backend belong to this frozen identity

    @model_validator(mode="after")
    def valid(self):
        import re
        if not self.ordered_path or self.ordered_path[-1] != "STOP" or "STOP" in self.ordered_path[:-1]:
            raise ValueError("terminal path must end with exactly one STOP")
        if any(a not in ("GET_RS", "GET_MP", "GET_ME", "GET_MS", "STOP") and not re.fullmatch(r"EXPAND_MS\([1-9][0-9]*\)", a) for a in self.ordered_path):
            raise ValueError("invalid terminal action")
        if len(set(self.acquired_record_ids)) != len(self.acquired_record_ids):
            raise ValueError("duplicate acquired record")
        if self.ordered_path == ("STOP",) and self.acquired_record_ids:
            raise ValueError("OFF cannot contain acquired resources")
        return self


@contract
class ItemVerdict(Contract):
    item_id: Id
    J1: Verdict
    J2: Verdict
    final: Verdict


@contract
class PairwiseQuality(Contract):
    comparator_key_sha256: Sha256
    verdict: Literal["win", "tie", "loss", "uncertain"]
    judge_identity: Id
    qualification_tier: Tier


@contract
class TerminalRecord(Contract):
    key: TerminalKey
    request_sha256: Sha256
    response: str
    response_sha256: Sha256
    item_verdicts: tuple[ItemVerdict, ...]
    gsc_lower: Probability | None
    gsc_upper: Probability | None
    hard_factual: Verdict
    hard_safety: Verdict
    soft_quality_pairwise: tuple[PairwiseQuality, ...]
    qualification_tier: Tier
    misuse_flags: tuple[Id, ...]
    latency_pred: Cost | None  # seconds; no estimate until measured/calibrated
    latency_measured: Cost | None

    @model_validator(mode="after")
    def valid(self):
        if sha256_text(self.response) != self.response_sha256:
            raise ValueError("response hash mismatch")
        if (self.gsc_lower is None) != (self.gsc_upper is None):
            raise ValueError("GSC interval needs both bounds or neither")
        if self.gsc_lower is not None and self.gsc_lower > self.gsc_upper:
            raise ValueError("reversed GSC interval")
        if len({v.item_id for v in self.item_verdicts}) != len(self.item_verdicts):
            raise ValueError("duplicate checklist verdict")
        return self


CONTRACT_TYPES = (TimePoint, SourceTurn, SourceSession, SourceSpan, PrefixSpec, VisiblePrefix,
                  ResourceRecord, TemporalClaim, TemporalRelation, ReadingView, HeadAvailability,
                  Observation, ScoreComponent, RankedCandidate, RetrievalResult, IndexManifest,
                  Rejection, RetrievalTrace, HistoryItem, NeedCard, ChecklistItem, TerminalKey,
                  ItemVerdict, PairwiseQuality, TerminalRecord)


def json_schema(cls) -> dict:
    """Draft 2020-12 structure; cross-field/source checks also require decoding."""
    schema = TypeAdapter(cls).json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"urn:metacom:rl1v3:{SCHEMA_VERSION}:{cls.__name__}"
    # Require explicit version on the wire, even though Python constructors default it.
    for node in (schema, *schema.get("$defs", {}).values()):
        if "schema_version" in node.get("properties", {}):
            node.setdefault("required", []).append("schema_version")
    return schema

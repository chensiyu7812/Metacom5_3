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
from decimal import Decimal
from collections import Counter
import re
from typing import Annotated, Literal, Union

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
HEAD_ORDER = ("RS", "MP", "ME", "MS")
Domain = Literal["finite_head_v1", "adaptive_v1"]
View = Literal["method", "case", "assertion", "event", "sum", "raw"]
Action = Annotated[str, Field(pattern=r"^(STOP|GET_(RS|MP|ME|MS)|EXPAND_MS\([1-9][0-9]*\))$")]
B0_PREFIX_PROTOCOL = "pmrl1v3-b0-prefix-census-v1"


def prefix_identity(*, protocol, dataset, owner_id, session_id, cut_turn, turns):
    return object_sha256(dict(protocol=protocol, dataset=dataset, owner_id=owner_id,
        session_id=session_id, cut_turn=cut_turn,
        prefix_sha256=object_sha256([(t.role, t.text) for t in turns])))


def _check_view(head, view):
    if view not in {"RS": ("method", "case"), "MP": ("assertion",),
                    "ME": ("event",), "MS": ("sum", "raw")}[head]:
        raise ValueError("head/view mismatch")


def _expand_ordinal(action):
    match = re.fullmatch(r"EXPAND_MS\(([1-9][0-9]*)\)", action)
    return int(match[1]) if match else None


def _validate_path(domain, path, groups):
    if not path or path[-1] != "STOP" or "STOP" in path[:-1]:
        raise ValueError("terminal path must end with exactly one STOP")
    if len(groups) != len(path)-1 or any(not g for g in groups):
        raise ValueError("each GET/EXPAND must bind one nonempty record group")
    flat = [r for group in groups for r in group]
    if len(set(flat)) != len(flat):
        raise ValueError("duplicate acquired record")
    gets = Counter(a for a in path if a.startswith("GET_"))
    if domain == "finite_head_v1":
        if any(_expand_ordinal(a) for a in path) or any(n > 1 for n in gets.values()):
            raise ValueError("finite domain has no EXPAND or repeated head")
    else:
        if len(groups) > 5 or any(n > 2 for n in gets.values()):
            raise ValueError("adaptive read budget exceeded")
        expanded = set()
        for i, action in enumerate(path[:-1], 1):
            j = _expand_ordinal(action)
            if j is not None:
                if j >= i or path[j-1] != "GET_MS" or j in expanded:
                    raise ValueError("EXPAND must name a previously read, unexpanded MS ordinal")
                expanded.add(j)



def contract(cls):
    return dataclass(cls, frozen=True, slots=True, kw_only=True,
                     config=ConfigDict(extra="forbid", strict=True, validate_default=True))


@contract
class Contract:
    schema_version: Literal["pmrl1v3-contracts-0.2.0"] = SCHEMA_VERSION

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
    """Private B0-bound envelope. Ancestors cover current + ALL strict-past families.

    Family closure is input lineage, never text matching or an actor feature.
    verify_source_context checks it against sources before any resource access.
    """
    prefix_id: Sha256
    owner_id: Id
    session_id: Id
    cut_turn: Nonnegative  # inclusive, zero based
    turns: Annotated[tuple[SourceTurn, ...], Field(min_length=1)]
    cutoff_rank: Nonnegative
    timestamp: str | None
    dataset: Id
    family_id: Id
    ancestor_family_ids: Annotated[tuple[Id, ...], Field(min_length=1)]
    prefix_protocol: Id = B0_PREFIX_PROTOCOL
    identity_scope: Literal["v3", "historical_legacy"] = "v3"
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
        if self.family_id not in self.ancestor_family_ids or len(set(self.ancestor_family_ids)) != len(self.ancestor_family_ids):
            raise ValueError("family closure must include current family without duplicates")
        object.__setattr__(self, "ancestor_family_ids", tuple(sorted(self.ancestor_family_ids)))
        if self.identity_scope == "v3":
            expected = prefix_identity(protocol=self.prefix_protocol, dataset=self.dataset,
                owner_id=self.owner_id, session_id=self.session_id, cut_turn=self.cut_turn, turns=self.turns)
        else:
            if self.prefix_protocol != "legacy-rl1-v1":
                raise ValueError("legacy identity requires explicit historical protocol")
            expected = object_sha256(dict(owner_id=self.owner_id, session_id=self.session_id,
                cutoff_rank=self.cutoff_rank, cut_after_turn_index=self.cut_turn, timestamp=self.timestamp,
                split=self.split, turns=[dict(role=t.role, content=t.text) for t in self.turns]))
        if self.prefix_id != expected:
            raise ValueError("prefix_id does not bind protocol/owner/session/cut/content")
        return self

    @classmethod
    def create(cls, **kwargs):
        """Construct a V3 identity from actual visible turns, independent of fold/stratum."""
        protocol = kwargs.get("prefix_protocol", B0_PREFIX_PROTOCOL)
        identity = prefix_identity(protocol=protocol, **{k: kwargs[k] for k in
            ("dataset", "owner_id", "session_id", "cut_turn", "turns")})
        return cls(prefix_id=identity, **kwargs)

    @property
    def runtime_sha256(self):
        # A date/rank/lineage change must invalidate requests; folds/labels must not.
        return object_sha256({k: getattr(self, k) for k in ("schema_version", "prefix_id",
            "prefix_protocol", "identity_scope", "owner_id", "session_id", "cut_turn", "turns",
            "cutoff_rank", "timestamp", "dataset", "family_id", "ancestor_family_ids")})

    def verify_source_context(self, current: SourceSession, history: tuple[SourceSession, ...]):
        if self.identity_scope != "v3":
            raise ValueError("legacy identities are historical only")
        if (current.owner_id, current.session_id, current.chronological_rank, current.date, current.dataset) != (
                self.owner_id, self.session_id, self.cutoff_rank, self.timestamp, self.dataset):
            raise ValueError("prefix/current source identity mismatch")
        if current.turns[:self.cut_turn+1] != self.turns:
            raise ValueError("prefix text differs from source")
        if self.cut_turn+1 >= len(current.turns) or current.turns[self.cut_turn+1].role != "supporter":
            raise ValueError("prefix is not a real seeker/supporter cut")
        if sorted(s.chronological_rank for s in history) != list(range(self.cutoff_rank)):
            raise ValueError("history must contain all and only strictly-past sessions")
        if any(s.owner_id != self.owner_id or s.dataset != self.dataset or not s.complete
               or (s.date is not None and self.timestamp is not None and s.date > self.timestamp) for s in history):
            raise ValueError("illegal history owner/dataset/completion/time")
        expected = {f for s in (current, *history) for f in (s.family_id, *s.ancestor_family_ids)}
        if self.family_id != current.family_id or set(self.ancestor_family_ids) != expected:
            raise ValueError("incomplete or future-contaminated family closure")

    def visible(self) -> VisiblePrefix:
        return VisiblePrefix(turns=self.turns, timestamp=self.timestamp)

    @classmethod
    def from_legacy(cls, prefix, *, dataset: str, family_id: str,
                    ancestor_family_ids: tuple[str, ...] = ()) -> PrefixSpec:
        """Historical-only adapter; never accepts legacy split-bound IDs as V3 IDs."""
        return cls(prefix_id=prefix.identity, owner_id=prefix.owner_id,
                   session_id=prefix.session_id, cut_turn=prefix.cut_after_turn_index,
                   cutoff_rank=prefix.cutoff_rank, timestamp=prefix.timestamp,
                   turns=tuple(SourceTurn(turn_index=i, role=t.role, text=t.content)
                               for i, t in enumerate(prefix.turns)),
                   dataset=dataset, family_id=family_id,
                   ancestor_family_ids=tuple(sorted(set((family_id, *ancestor_family_ids)))),
                   prefix_protocol="legacy-rl1-v1", identity_scope="historical_legacy", split=prefix.split)


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
    """Public text and legal report time; session_rank is allowed time, not an identity."""
    head: Head
    view: View
    expandable: bool = False
    expanded_from_ordinal: Positive | None = None
    ordinal: Positive
    reading_text: Annotated[str, Field(min_length=1)]
    reported_at: TimePoint | None
    tokens: Positive
    stage: Stage | None = None

    @model_validator(mode="after")
    def valid(self):
        if (self.head == "ME") != (self.stage is not None):
            raise ValueError("ME reading requires stage; other heads have no stage")
        _check_view(self.head, self.view)
        if not self.reading_text.strip():
            raise ValueError("empty reading text")
        if self.expandable and (self.head, self.view) != ("MS", "sum"):
            raise ValueError("only a validated SUM can advertise expansion")
        if self.expanded_from_ordinal is not None and ((self.head, self.view) != ("MS", "raw") or self.expanded_from_ordinal >= self.ordinal):
            raise ValueError("expansion must be RAW from an earlier public ordinal")
        return self


@contract
class HeadAvailability(Contract):
    """Query-independent legal candidate-pool size AFTER owner/cutoff/ready/family gates.

    Identical for every arm. Not delivered unit count, top-k, score, or capacity.
    Phase-1 GET buys one deterministic unit, which can contain several records.
    """
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
    """Same actor/critic whitelist: no private IDs/scores/labels; legal report time allowed."""
    domain_id: Domain
    history_sessions: Nonnegative
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
        counts = Counter(v.head for v in self.acquired if v.expanded_from_ordinal is None)
        expanded = [v.expanded_from_ordinal for v in self.acquired if v.expanded_from_ordinal is not None]
        if len(set(expanded)) != len(expanded) or any(not self.acquired[j-1].expandable for j in expanded):
            raise ValueError("invalid or repeated expansion")
        if self.domain_id == "finite_head_v1" and (expanded or any(n > 1 for n in counts.values())):
            raise ValueError("finite domain cannot expand or read a head twice")
        if self.domain_id == "adaptive_v1" and (len(self.acquired) > 5 or any(n > 2 for n in counts.values())):
            raise ValueError("adaptive read budget exceeded")
        available = {a.head: a.available for a in self.availability}
        for action in self.action_mask:
            if action.startswith("GET_"):
                head = action[4:]
                if not available.get(head, False):
                    raise ValueError("GET masked when legal pool is empty")
                if counts[head] >= (1 if self.domain_id == "finite_head_v1" else 2):
                    raise ValueError("GET exceeds per-head budget")
            j = _expand_ordinal(action)
            if j is not None:
                if self.domain_id != "adaptive_v1" or j > len(self.acquired) or not self.acquired[j-1].expandable or j in expanded:
                    raise ValueError("EXPAND not permitted for this domain/ordinal/view")
            if self.domain_id == "adaptive_v1" and len(self.acquired) >= 5 and action != "STOP":
                raise ValueError("adaptive total read budget exhausted")
        return self


    @property
    def remaining_gets(self):
        """Public derived budget; EXPAND consumes one of the five adaptive reads."""
        return (4 if self.domain_id == "finite_head_v1" else 5) - len(self.acquired)


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
    delivery_record_ids: tuple[Id, ...] = ()
    delivery_tokens: Positive | None = None  # private native-token count for the packed unit

    @model_validator(mode="after")
    def valid(self):
        if bool(self.delivery_record_ids) != (self.delivery_tokens is not None):
            raise ValueError("packed delivery needs records and a measured token count together")
        if not set(self.delivery_record_ids) <= {x.record_id for x in self.ranked} or len(set(self.delivery_record_ids)) != len(self.delivery_record_ids):
            raise ValueError("delivery must bind unique ranked records")
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


def verify_legal_span(span: SourceSpan, prefix: PrefixSpec, source: SourceSession):
    """Exact source evidence, current visible cut or complete strict-past only."""
    span.verify(source)
    if source.owner_id != prefix.owner_id or source.dataset != prefix.dataset:
        raise ValueError("foreign owner/dataset evidence")
    if source.family_id not in prefix.ancestor_family_ids:
        raise ValueError("evidence outside family closure")
    if source.chronological_rank == prefix.cutoff_rank:
        if source.session_id != prefix.session_id or span.turn_index > prefix.cut_turn:
            raise ValueError("future turn evidence")
        if source.turns[:prefix.cut_turn+1] != prefix.turns:
            raise ValueError("prefix/source content mismatch")
    elif source.chronological_rank > prefix.cutoff_rank or not source.complete:
        raise ValueError("future or incomplete history evidence")
    if source.date and prefix.timestamp and source.date > prefix.timestamp:
        raise ValueError("future dated evidence")


@contract
class OutdatedFact(Contract):
    old_span: SourceSpan
    new_span: SourceSpan

    @model_validator(mode="after")
    def valid(self):
        if self.old_span.owner_id != self.new_span.owner_id or (self.old_span.source_rank, self.old_span.turn_index) >= (self.new_span.source_rank, self.new_span.turn_index):
            raise ValueError("correction needs later same-owner evidence")
        return self


@contract
class NeedCard(Contract):
    prefix_id: Sha256
    stratum: Stratum
    history_items: tuple[HistoryItem, ...]
    failed_or_rejected: tuple[SourceSpan, ...]
    outdated_facts: tuple[OutdatedFact, ...]
    method_need: Id | None
    risk_flags: tuple[Id, ...]
    writer_identity: Id
    input_sha256: Sha256
    span_validation_status: Literal["pending", "verified", "failed"]
    visibility_scope: Literal["evaluation_only"] = "evaluation_only"

    def verify_evidence(self, prefix: PrefixSpec, sources: tuple[SourceSession, ...]):
        if self.prefix_id != prefix.prefix_id:
            raise ValueError("NeedCard/prefix mismatch")
        spans = [s for h in self.history_items for s in h.spans] + list(self.failed_or_rejected)
        spans += [s for pair in self.outdated_facts for s in (pair.old_span, pair.new_span)]
        by_id = {(s.owner_id, s.session_id): s for s in sources}
        for span in spans:
            verify_legal_span(span, prefix, by_id[(span.owner_id, span.session_id)])


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
class Checklist(Contract):
    prefix_id: Sha256
    needcard_sha256: Sha256
    items: Annotated[tuple[ChecklistItem, ...], Field(min_length=1)]
    total_weight: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    writer_identity: Id

    @model_validator(mode="after")
    def valid(self):
        if len({i.item_id for i in self.items}) != len(self.items):
            raise ValueError("duplicate checklist item")
        if Decimal(str(self.total_weight)) != sum(Decimal(str(i.weight)) for i in self.items):
            raise ValueError("checklist denominator differs from sum of all weights")
        return self

    def verify_needcard(self, need: NeedCard):
        if (self.prefix_id, self.needcard_sha256) != (need.prefix_id, need.sha256):
            raise ValueError("checklist/NeedCard mismatch")


@contract
class TerminalKey(Contract):
    domain_id: Domain
    owner_id: Id
    prefix_id: Sha256
    prefix_context_sha256: Sha256
    bank_version: Id
    index_version: Id
    ordered_path: tuple[Action, ...]
    acquired: tuple[tuple[Id, ...], ...]
    renderer_id: Id
    step2_id: Id
    g_id: Id
    decode_id: Id

    @model_validator(mode="after")
    def valid(self):
        _validate_path(self.domain_id, self.ordered_path, self.acquired)
        if self.domain_id == "finite_head_v1":
            pairs = sorted(zip(self.ordered_path[:-1], self.acquired), key=lambda p: HEAD_ORDER.index(p[0][4:]))
            object.__setattr__(self, "ordered_path", tuple(a for a, _ in pairs) + ("STOP",))
            object.__setattr__(self, "acquired", tuple(g for _, g in pairs))
        return self

    @classmethod
    def for_prefix(cls, prefix: PrefixSpec, **kwargs):
        if prefix.identity_scope != "v3":
            raise ValueError("historical prefix is not a V3 terminal")
        return cls(owner_id=prefix.owner_id, prefix_id=prefix.prefix_id,
                   prefix_context_sha256=prefix.runtime_sha256, **kwargs)


@contract
class ExecutionTrace(Contract):
    """Actual order, independent of finite-domain canonical reply identity."""
    domain_id: Domain
    ordered_path: tuple[Action, ...]
    acquired: tuple[tuple[Id, ...], ...]
    readings: tuple[ReadingView, ...]

    @model_validator(mode="after")
    def valid(self):
        _validate_path(self.domain_id, self.ordered_path, self.acquired)
        if len(self.readings) != len(self.acquired):
            raise ValueError("one reading per successful action")
        for ordinal, (action, view) in enumerate(zip(self.ordered_path, self.readings), 1):
            if ordinal != view.ordinal:
                raise ValueError("execution ordinal mismatch")
            j = _expand_ordinal(action)
            if j is not None:
                if not self.readings[j-1].expandable or view.expanded_from_ordinal != j:
                    raise ValueError("unexpandable or mismatched SUM parent ordinal")
            elif action != "GET_" + view.head or view.expanded_from_ordinal is not None:
                raise ValueError("action/reading head mismatch")
        return self

    def verify_key(self, key: TerminalKey):
        from dataclasses import replace
        if self.domain_id != key.domain_id or replace(key, ordered_path=self.ordered_path, acquired=self.acquired) != key:
            raise ValueError("execution does not reproduce terminal identity")


@contract
class HumanAdjudication(Contract):
    reviewer_id: Id
    record_uri: Id
    record_sha256: Sha256
    response_sha256: Sha256
    verdict: Verdict
    reason: Id


@contract
class ItemVerdict(Contract):
    item_id: Id
    J1: Verdict | None
    J2: Verdict | None
    final: Verdict | None
    J1_quote: Id | None = None
    J1_source_span: SourceSpan | None = None
    J2_quote: Id | None = None
    J2_source_span: SourceSpan | None = None
    human_adjudication: HumanAdjudication | None = None

    @model_validator(mode="after")
    def valid(self):
        for verdict, quote, span in ((self.J1, self.J1_quote, self.J1_source_span), (self.J2, self.J2_quote, self.J2_source_span)):
            if verdict is None and (quote is not None or span is not None):
                raise ValueError("unrun judge cannot supply evidence")
        if self.human_adjudication is not None:
            if self.final != self.human_adjudication.verdict:
                raise ValueError("final differs from explicit human adjudication")
        elif self.J1 is not None and self.J2 is not None:
            expected = self.J1 if self.J1 == self.J2 else "uncertain"
            if self.final != expected:
                raise ValueError("judge disagreement cannot be certified without human adjudication")
        elif self.final is not None and self.final not in (self.J1, self.J2):
            raise ValueError("final lacks a judge or human decision")
        return self

    @property
    def pending(self):
        return self.human_adjudication is None and (self.J1 is None or self.J2 is None or self.final is None)

    def verify_evidence(self, response: str, prefix: PrefixSpec, sources: tuple[SourceSession, ...]):
        by_id = {(s.owner_id, s.session_id): s for s in sources}
        for quote, span in ((self.J1_quote, self.J1_source_span), (self.J2_quote, self.J2_source_span)):
            if quote is not None and quote not in response:
                raise ValueError("judge quote absent from response")
            if span is not None:
                verify_legal_span(span, prefix, by_id[(span.owner_id, span.session_id)])
        if self.human_adjudication and self.human_adjudication.response_sha256 != sha256_text(response):
            raise ValueError("human adjudication belongs to another response")


def gsc_interval(checklist: Checklist, verdicts: tuple[ItemVerdict, ...]):
    by_id = {v.item_id: v for v in verdicts}
    if len(by_id) != len(verdicts) or set(by_id) != {i.item_id for i in checklist.items}:
        raise ValueError("verdict coverage differs from frozen checklist")
    if any(v.pending for v in verdicts):
        return None, None
    denominator = Decimal(str(checklist.total_weight))
    lower = sum(Decimal(str(i.weight)) for i in checklist.items if by_id[i.item_id].final == "pass")
    upper = sum(Decimal(str(i.weight)) for i in checklist.items if by_id[i.item_id].final != "fail")
    return float(lower / denominator), float(upper / denominator)


@contract
class ReadSuccess(Contract):
    status: Literal["ok"] = "ok"
    reading: ReadingView
    record_ids: Annotated[tuple[Id, ...], Field(min_length=1)]
    input_tokens_before: Nonnegative
    input_tokens_after: Positive
    native_context_tokens: Positive
    output_reserve_tokens: Positive
    elapsed_ms: Cost

    @model_validator(mode="after")
    def valid(self):
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("duplicate delivery record")
        if self.input_tokens_after < self.input_tokens_before + self.reading.tokens:
            raise ValueError("delivered reading not charged to input")
        if self.input_tokens_after + self.output_reserve_tokens > self.native_context_tokens:
            raise ValueError("reading exceeds native model capacity")
        return self


@contract
class ReadFailure(Contract):
    status: Literal["rejected"] = "rejected"
    reason: Literal["empty", "capacity", "owner", "family", "future_source", "not_ready", "invalid_action", "integrity", "unavailable"]
    detail: Id
    input_tokens_unchanged: Nonnegative
    elapsed_ms: Cost


ReadResult = Annotated[Union[ReadSuccess, ReadFailure], Field(discriminator="status")]


@contract
class PairwiseQuality(Contract):
    comparator_key_sha256: Sha256
    verdict: Literal["win", "tie", "loss", "uncertain"]
    judge_identity: Id
    qualification_tier: Tier


@contract
class TerminalRecord(Contract):
    key: TerminalKey
    execution: ExecutionTrace
    checklist: Checklist
    checklist_sha256: Sha256
    feedback_id: Id  # separately versioned judge models/prompts/parsers/aggregation manifest
    evidence_validation: Literal["pending", "verified", "failed"] = "pending"
    request_sha256: Sha256
    response: str
    response_sha256: Sha256
    item_verdicts: tuple[ItemVerdict, ...]
    gsc_lower: Probability | None
    gsc_upper: Probability | None
    hard_factual: Verdict | None
    hard_safety: Verdict | None
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
        self.execution.verify_key(self.key)
        if self.checklist_sha256 != self.checklist.sha256 or self.checklist.prefix_id != self.key.prefix_id:
            raise ValueError("terminal/checklist binding mismatch")
        if (self.gsc_lower, self.gsc_upper) != gsc_interval(self.checklist, self.item_verdicts):
            raise ValueError("GSC does not use the frozen denominator or has pending judgements")
        for v in self.item_verdicts:
            for quote in (v.J1_quote, v.J2_quote):
                if quote is not None and quote not in self.response:
                    raise ValueError("judge quote absent from response")
            if v.human_adjudication and v.human_adjudication.response_sha256 != self.response_sha256:
                raise ValueError("human adjudication response mismatch")
        if self.qualification_tier != "engineering_only" and (self.hard_factual is None or self.hard_safety is None or any(v.pending for v in self.item_verdicts) or self.evidence_validation != "verified"):
            raise ValueError("pending constraints/evidence cannot enter research certification")
        return self

    def verify_evidence(self, prefix: PrefixSpec, sources: tuple[SourceSession, ...]):
        if (self.key.owner_id, self.key.prefix_id, self.key.prefix_context_sha256) != (prefix.owner_id, prefix.prefix_id, prefix.runtime_sha256):
            raise ValueError("terminal/prefix context mismatch")
        by_id = {(s.owner_id, s.session_id): s for s in sources}
        for item in self.checklist.items:
            for span in item.evidence_spans:
                verify_legal_span(span, prefix, by_id[(span.owner_id, span.session_id)])
        for verdict in self.item_verdicts:
            verdict.verify_evidence(self.response, prefix, sources)



CONTRACT_TYPES = (TimePoint, SourceTurn, SourceSession, SourceSpan, PrefixSpec, VisiblePrefix,
                  ResourceRecord, TemporalClaim, TemporalRelation, ReadingView, HeadAvailability,
                  Observation, ScoreComponent, RankedCandidate, RetrievalResult, IndexManifest,
                  Rejection, RetrievalTrace, HistoryItem, NeedCard, ChecklistItem, TerminalKey,
                  ItemVerdict, PairwiseQuality, TerminalRecord, OutdatedFact, Checklist, ExecutionTrace,
                  HumanAdjudication, ReadSuccess, ReadFailure)


def json_schema(cls) -> dict:
    """Draft 2020-12 structure; cross-field/source checks also require decoding."""
    schema = TypeAdapter(cls).json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    name = "ReadResult" if cls is ReadResult else cls.__name__
    schema["$id"] = f"urn:metacom:rl1v3:{SCHEMA_VERSION}:{name}"
    # Require explicit version on the wire, even though Python constructors default it.
    for node in (schema, *schema.get("$defs", {}).values()):
        if "schema_version" in node.get("properties", {}):
            node.setdefault("required", []).append("schema_version")
    return schema

"""Opt-in, construction-domain evidence index. No models, rewards or actor API.

Every instance is bound to one train/dev prefix. Filter sources BEFORE building
it; foreign/future inputs are rejected, not silently hidden after derivation.
Exact quotations establish provenance, never semantic truth or human approval.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date
import re

from .schema import PrefixSpec, digest

VERSION = "pm-rl1-temporal-evidence-ledger-min-v1"
STAGES = {"unknown", "hypothetical", "suggested", "intention", "attempted", "completed", "observed", "not_applicable"}
RELATIONS = {"updates", "contradicts", "follow_up", "outcome_of"}


@dataclass(frozen=True)
class SourceTurn:
    owner_id: str
    session_id: str
    session_rank: int
    turn_index: int
    speaker: str
    text: str
    reported_at: str

    @property
    def key(self):
        return f"{self.owner_id}/{self.session_id}:{self.turn_index}"

    @property
    def identity(self):
        return digest(asdict(self))


def words(text):
    """Literal lexical index only; no entity resolution or relevance labels."""
    return frozenset(re.findall(r"\w+", text.casefold()))


class TemporalEvidenceLedger:
    def __init__(self, prefix: PrefixSpec, turns, *, provenance_identity: str):
        if prefix.split not in ("train", "dev") or not provenance_identity:
            raise ValueError("only explicitly bound train/dev sources allowed")
        self.prefix = prefix
        self.provenance_identity = provenance_identity
        self._turns = {}
        self._claims = {}
        self._relations = {}
        self._postings = defaultdict(set)
        sessions = {}
        date.fromisoformat(prefix.timestamp)
        for turn in turns:
            if type(turn) is not SourceTurn or turn.owner_id != prefix.owner_id:
                raise ValueError("foreign owner or source type")
            if (type(turn.session_rank) is not int or turn.session_rank < 0
                    or type(turn.turn_index) is not int or turn.turn_index < 0
                    or turn.speaker not in ("seeker", "supporter") or not turn.text.strip()
                    or not turn.reported_at or turn.reported_at > prefix.timestamp):
                raise ValueError("invalid source metadata or future report")
            date.fromisoformat(turn.reported_at)
            if turn.session_id == prefix.session_id:
                if (turn.session_rank != prefix.cutoff_rank
                        or turn.reported_at != prefix.timestamp
                        or turn.turn_index > prefix.cut_after_turn_index
                        or turn.turn_index >= len(prefix.turns)
                        or turn.speaker != prefix.turns[turn.turn_index].role
                        or turn.text != prefix.turns[turn.turn_index].content):
                    raise ValueError("current source differs from legal prefix")
            elif turn.session_rank >= prefix.cutoff_rank:
                raise ValueError("future/non-past session")
            session_identity = (turn.session_rank, turn.reported_at)
            if sessions.setdefault(turn.session_id, session_identity) != session_identity:
                raise ValueError("inconsistent session metadata")
            if turn.key in self._turns:
                raise ValueError("duplicate source turn")
            self._turns[turn.key] = turn
            for word in words(turn.text):
                self._postings[word].add(turn.key)

    def span(self, key, start, end, quote):
        turn = self._turns[key]
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(turn.text)
                or not quote or turn.text[start:end] != quote):
            raise ValueError("quote/Unicode character offsets mismatch")
        return dict(source_key=key, source_identity=turn.identity,
                    source_text_identity=digest(turn.text), speaker=turn.speaker,
                    start_char=start, end_char=end, exact_quote=quote)

    def _validate_spans(self, spans):
        if not spans:
            raise ValueError("derived material requires evidence")
        for s in spans:
            expected = self.span(s["source_key"], s["start_char"], s["end_char"], s["exact_quote"])
            if s != expected:
                raise ValueError("stale/tampered evidence")

    def locate_quote(self, session_id, speaker, start, end, quote):
        """Resolve a quotation in a session, without equating source IDs to ordinals.

        Legacy raw turn idx and blinded H:T ordinal are different namespaces.
        This verifies the exact location; it does NOT certify the legacy idx.
        Repeated identical matches are ambiguous and fail closed.
        """
        matches = [t for t in self._turns.values() if t.session_id == session_id
                   and t.speaker == speaker and type(start) is int and type(end) is int
                   and 0 <= start < end <= len(t.text) and t.text[start:end] == quote]
        if len(matches) != 1:
            raise ValueError("quote location missing or ambiguous")
        return self.span(matches[0].key, start, end, quote)

    def add_claim(self, *, candidate_id, head, statement, spans, input_source_keys,
                  derivation_method, derivation_identity, subject=None, stage="unknown",
                  event_time=None, outcome=None, review_status="unverified"):
        if (head not in ("MP", "ME", "MS") or not candidate_id or not statement
                or stage not in STAGES or not derivation_method or not derivation_identity
                or review_status not in ("unverified", "existing_source_review_not_human_gold")):
            raise ValueError("invalid derived claim contract")
        self._validate_spans(spans)
        # Complete declared input dependency closure, not only the cited excerpt.
        # Caller must supply it honestly; it is recorded, not independently inferred.
        inputs = sorted(set(input_source_keys))
        if not inputs or any(k not in self._turns for k in inputs):
            raise ValueError("derivation used unregistered/future/foreign input")
        if not {s["source_key"] for s in spans}.issubset(inputs):
            raise ValueError("citation missing from derivation dependencies")
        record = dict(candidate_id=candidate_id, head=head, statement=statement,
                      subject=subject, stage=stage, event_time=event_time, outcome=outcome,
                      epistemic_status="source_report_not_verified_world_fact", spans=deepcopy(spans),
                      input_source_keys=inputs, derivation_method=derivation_method,
                      derivation_identity=derivation_identity, review_status=review_status,
                      semantic_support="unverified", training_label=False)
        key = digest(record)
        self._claims[key] = record
        return key

    def add_relation(self, *, kind, left, right, spans, input_source_keys,
                     derivation_method, derivation_identity):
        if kind not in RELATIONS or left not in self._claims or right not in self._claims or left == right:
            raise ValueError("invalid relation/endpoints")
        self._validate_spans(spans)
        inputs = sorted(set(input_source_keys))
        required = {s["source_key"] for s in spans}
        required.update(self._claims[left]["input_source_keys"])
        required.update(self._claims[right]["input_source_keys"])
        if (not required.issubset(inputs) or any(k not in self._turns for k in inputs)
                or not derivation_method or not derivation_identity):
            raise ValueError("relation dependency closure invalid")
        record = dict(kind=kind, left=left, right=right, spans=deepcopy(spans),
                      input_source_keys=inputs, derivation_method=derivation_method,
                      derivation_identity=derivation_identity, semantic_support="unverified",
                      effect="index_only_no_automatic_supersession", training_label=False)
        key = digest(record)
        self._relations[key] = record
        return key

    def lookup(self, query, *, limit=10, historical_only=True):
        """Offline source locations; never a replacement for frozen BGE rank."""
        if type(limit) is not int or limit < 1:
            raise ValueError("positive limit required")
        query_words = words(query)
        keys = set().union(*(self._postings.get(w, set()) for w in query_words))
        hits = []
        for key in keys:
            turn = self._turns[key]
            if historical_only and turn.session_id == self.prefix.session_id:
                continue
            overlap = sorted(query_words & words(turn.text))
            hits.append(dict(source_key=key, source_identity=turn.identity,
                             ranking_method="literal_unique_word_overlap_v1",
                             ranking_score=len(overlap), matched_terms=overlap,
                             bge_similarity=None, actor_visible=False))
        return sorted(hits, key=lambda r: (-r["ranking_score"], r["source_key"]))[:limit]

    def export(self):
        sessions = defaultdict(list)
        for t in self._turns.values():
            if t.session_id != self.prefix.session_id:
                sessions[t.session_id].append(t)
        directory = [dict(session_id=sid, session_rank=ts[0].session_rank,
                          reported_at=ts[0].reported_at, source_keys=[t.key for t in sorted(ts, key=lambda t:t.turn_index)],
                          summary=None, topics=None, summary_status="not_derived",
                          completeness="registered_turns_only_not_certified_complete_session")
                     for sid, ts in sorted(sessions.items())]
        value = dict(version=VERSION, prefix_identity=self.prefix.identity,
                     provenance_identity=self.provenance_identity, audience="construction_evaluator_only",
                     source_turns={k:dict(**asdict(t), identity=t.identity) for k,t in sorted(self._turns.items())},
                     session_directory=directory, claims=deepcopy(self._claims), relations=deepcopy(self._relations),
                     unknown_is_not_false=True, main_retrieval_changed=False,
                     model_calls=0, semantic_labels_created=0)
        value["identity"] = digest(value)
        return value

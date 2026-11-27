"""Private chronological sidecar; does not alter C0 or bank-v0.

Ranks are local to an owner. Report rank r is inside session r; knowledge and
readiness ranks are *boundaries*, with r+1 the earliest completed-session commit.
These are logical replay clocks, never measurements of asynchronous latency.
RAW is mechanically usable; semantic claims need explicit human approval.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol
import json

from .. import contracts as K
from ..io import canonical_json, decode_contract, file_sha256, object_sha256, write_json_once
from ..sources.source_registry import span

PROTOCOL = 'pmrl1v3-asof-sidecar-1'
STAGES = ('suggested', 'intended', 'attempted', 'completed', 'outcome_reported', 'rejected', 'unknown')
REVIEWS = ('pending', 'developer_inspected', 'human_approved', 'unusable')


def writer_identity():
    return 'writer:' + object_sha256(dict(protocol=PROTOCOL, code_sha256=file_sha256(__file__),
        extraction='explicit-span-fixtures-only; model-extractor-pending',
        time_basis='logical_completed_session_boundary_not_measured'))


def source_binding(source):
    """Local source identity: future changes to a corpus file cannot rename r0.

    Whole-file hash, registry version, fold and exposure are preserved separately
    in the input audit. They must not influence a historical snapshot identity.
    """
    return {k: getattr(source, k) for k in ('owner_id', 'session_id', 'dataset',
        'chronological_rank', 'date', 'family_id', 'ancestor_family_ids', 'license',
        'complete', 'transcript_sha256')}


def source_sha(source):
    return object_sha256(source_binding(source))


def at_or_before(clock, cutoff):
    if clock.session_rank is None:
        raise ValueError('personal replay clocks require an owner-local rank')
    return clock.session_rank <= cutoff.cutoff_rank and (clock.date is None or
        (cutoff.timestamp is not None and clock.date <= cutoff.timestamp))


def fact_at_or_before(clock, cutoff):
    """Tri-state comparison; event dates are not knowledge ranks."""
    comparisons = []
    if clock.session_rank is not None:
        comparisons.append(clock.session_rank <= cutoff.cutoff_rank)
    if clock.date is not None and cutoff.timestamp is not None:
        comparisons.append(clock.date <= cutoff.timestamp)
    return all(comparisons) if comparisons else None


@dataclass(frozen=True)
class PrefixAsOf:
    prefix_context_sha256: str
    owner_id: str
    dataset: str
    family_id: str
    ancestor_family_ids: tuple[str, ...]
    cutoff_rank: int
    timestamp: str | None
    protocol: str = PROTOCOL

    @classmethod
    def from_prefix(cls, registry, prefix):
        registry.context(prefix)
        return cls(prefix.runtime_sha256, prefix.owner_id, prefix.dataset, prefix.family_id,
            prefix.ancestor_family_ids, prefix.cutoff_rank, prefix.timestamp)


@dataclass(frozen=True)
class SourceFrontier:
    as_of: PrefixAsOf
    sources: tuple[dict, ...]

    @property
    def sha256(self):
        return object_sha256(self)


@dataclass(frozen=True)
class LedgerRecord:
    record_id: str
    writer_identity: str
    owner_id: str
    dataset: str
    family_id: str
    session_id: str
    source_sha256: str
    kind: str
    text: str
    source_refs: tuple[K.SourceSpan, ...]
    reported_at: K.TimePoint
    known_at: K.TimePoint
    ready_at: K.TimePoint
    subject: str = 'unknown'
    slot: str | None = None
    stage: str = 'unknown'
    event_time: K.TimePoint | None = None
    valid_from: K.TimePoint | None = None
    valid_to: K.TimePoint | None = None
    operation: str = 'ADD'
    target_id: str | None = None
    raw_parent_id: str | None = None
    review_status: str = 'pending'
    approval_ref: str | None = None
    protocol: str = PROTOCOL

    def __post_init__(self):
        if self.protocol != PROTOCOL or self.kind not in ('MP', 'ME', 'MS_RAW', 'MS_SUM', 'RELATION'):
            raise ValueError('unsupported sidecar kind/version')
        if self.stage not in STAGES or self.review_status not in REVIEWS:
            raise ValueError('unknown stage/review')
        if self.subject not in ('unknown','user','supporter','partner','family_member','therapist','external_person','session'):
            raise ValueError('subject must be a public role, never a private identity')
        if self.kind != 'ME' and self.stage != 'unknown':
            raise ValueError('only events carry a stage')
        if self.operation not in ('ADD', 'UPDATE', 'INVALIDATE', 'CONTRADICTS'):
            raise ValueError('unknown operation')
        if self.kind == 'RELATION':
            if self.operation == 'ADD' or not self.target_id:
                raise ValueError('relation needs a target and operation')
        elif self.operation != 'ADD' or self.target_id:
            raise ValueError('corrections must be separate append-only relation rows')
        if not self.text or not self.source_refs:
            raise ValueError('no text/evidence')
        if self.review_status == 'human_approved' and not self.approval_ref:
            raise ValueError('human approval needs an auditable receipt')
        ranks = [r.source_rank for r in self.source_refs]
        if any(r.owner_id != self.owner_id for r in self.source_refs):
            raise ValueError('cross-owner evidence')
        if self.reported_at.session_rank != max(ranks):
            raise ValueError('reported rank differs from latest source')
        if self.known_at.session_rank is None or self.known_at.session_rank <= max(ranks):
            raise ValueError('knowledge is committed only after source session completion')
        if self.ready_at.session_rank is None or self.ready_at.session_rank < self.known_at.session_rank:
            raise ValueError('ready precedes known')
        K._not_before(self.ready_at, self.known_at, 'ready_at')
        K._not_before(self.known_at, self.reported_at, 'known_at')
        K._not_before(self.valid_to, self.valid_from, 'valid_to')
        if self.kind == 'MP' and not self.slot:
            raise ValueError('MP needs explicit slot (unknown is allowed)')
        if self.kind == 'MS_SUM' and (not self.raw_parent_id or len(self.source_refs) != 1):
            raise ValueError('minimal SUM is one proposition with one precise parent span')
        if self.stage in ('intended', 'attempted', 'completed', 'outcome_reported', 'rejected'):
            if not any(r.speaker == 'seeker' for r in self.source_refs):
                raise ValueError('supporter suggestion cannot become user execution')
        if self.subject == 'user' and self.kind == 'MP' and not any(r.speaker == 'seeker' for r in self.source_refs):
            raise ValueError('supporter cannot establish self-report')
        if self.record_id != 'pending' and self.record_id != self.content_id:
            raise ValueError('ledger content hash mismatch')

    @property
    def content_id(self):
        return 'asof-record:' + object_sha256(replace(self, record_id='pending'))

    @property
    def semantically_approved(self):
        return self.review_status == 'human_approved' and self.subject != 'unknown'


def record_from_source(entry, *, kind, refs=None, text=None, writer=None, **kwargs):
    s = entry.source
    refs = tuple(refs) if refs is not None else tuple(span(s, i) for i,t in enumerate(s.turns) if t.text)
    row = LedgerRecord(record_id='pending', writer_identity=writer or writer_identity(),
        owner_id=s.owner_id, dataset=s.dataset, family_id=s.family_id, session_id=s.session_id,
        source_sha256=source_sha(s), kind=kind,
        text=text if text is not None else '\n'.join(f'{t.role}: {t.text}' for t in s.turns),
        source_refs=refs, reported_at=K.TimePoint(date=s.date, session_rank=s.chronological_rank),
        known_at=kwargs.pop('known_at', K.TimePoint(session_rank=s.chronological_rank+1)),
        ready_at=kwargs.pop('ready_at', K.TimePoint(session_rank=s.chronological_rank+1)), **kwargs)
    return replace(row, record_id=row.content_id)


class SemanticExtractor(Protocol):
    """Future adapter must consume ONLY this completed session and prior snapshot."""
    def extract(self, completed_source: K.SourceSession, prior_snapshot: dict) -> tuple[LedgerRecord, ...]: ...


class PendingExtractor:
    def extract(self, completed_source, prior_snapshot):
        raise NotImplementedError('model semantic extraction pending separate authorization and validation')


def verify_record(row, registry):
    s = registry.entry(row.owner_id, row.session_id).source
    if not s.complete or (row.dataset, row.family_id, row.source_sha256) != (s.dataset, s.family_id, source_sha(s)):
        raise ValueError('source completion/owner/family/content mismatch')
    for ref in row.source_refs:
        ref.verify(registry.entry(ref.owner_id, ref.session_id).source)
        if ref.session_id != s.session_id:
            raise ValueError('minimal writer accepts only one completed session per record')
    if row.kind == 'MS_RAW':
        if row.text != '\n'.join(f'{t.role}: {t.text}' for t in s.turns):
            raise ValueError('RAW changed or truncated')
        if row.source_refs != tuple(span(s,i) for i,t in enumerate(s.turns) if t.text):
            raise ValueError('RAW source closure incomplete')


class Ledger:
    """One atomic immutable file per append. Identical retry is a NOOP.

    Single-writer contract. No process locking/WAL service is claimed. A failed
    atomic publication leaves no partial row; restart validates every content ID.
    """
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self._rows = {}
        if self.path and self.path.exists():
            for p in sorted(self.path.glob('*.json')):
                data = json.loads(p.read_text())
                for key in ('reported_at','known_at','ready_at','event_time','valid_from','valid_to'):
                    if data[key] is not None:
                        data[key] = decode_contract(K.TimePoint, canonical_json(data[key]))
                data['source_refs'] = tuple(decode_contract(K.SourceSpan, canonical_json(r)) for r in data['source_refs'])
                row = LedgerRecord(**data)
                if p.stem != row.record_id.split(':')[1] or row.record_id in self._rows:
                    raise ValueError('ledger file identity mismatch')
                self._rows[row.record_id] = row

    @property
    def rows(self):
        order = {'MS_RAW':0, 'MP':1, 'ME':1, 'RELATION':2, 'MS_SUM':3}
        return tuple(sorted(self._rows.values(), key=lambda r: (r.ready_at.session_rank, order[r.kind], r.record_id)))

    def append(self, row, registry):
        if row.record_id != row.content_id:
            raise ValueError('append requires a finalized content identity')
        verify_record(row, registry)
        if row.record_id in self._rows:
            if self._rows[row.record_id] != row:
                raise ValueError('conflicting duplicate')
            return False
        previous = [r for r in self.rows if r.owner_id == row.owner_id]
        if previous and row.ready_at.session_rank < max(r.ready_at.session_rank for r in previous):
            raise ValueError('backdated append; preserve actual commit readiness')
        for target_id in (row.target_id, row.raw_parent_id):
            if target_id is None:
                continue
            target = self._rows.get(target_id)
            if target is None or (target.owner_id, target.dataset) != (row.owner_id, row.dataset):
                raise ValueError('missing or cross-owner relation/parent')
            if row.kind == 'RELATION' and (target.kind != 'MP' or
                    (row.subject, row.slot) != (target.subject, target.slot)):
                raise ValueError('correction subject/slot mismatch')
            if row.kind == 'MS_SUM' and (target.kind != 'MS_RAW' or target.session_id != row.session_id):
                raise ValueError('SUM parent mismatch')
        if self.path:
            write_json_once(self.path / (row.record_id.split(':')[1]+'.json'), row)
        self._rows[row.record_id] = row
        return True


def decode_record(data):
    data = dict(data)
    for key in ('reported_at','known_at','ready_at','event_time','valid_from','valid_to'):
        if data[key] is not None:
            data[key] = decode_contract(K.TimePoint, canonical_json(data[key]))
    data['source_refs'] = tuple(decode_contract(K.SourceSpan, canonical_json(r)) for r in data['source_refs'])
    return LedgerRecord(**data)


def materialize(registry, prefix, ledger, *, writer=None):
    writer = writer or writer_identity()
    cutoff = PrefixAsOf.from_prefix(registry, prefix)
    entries = sorted(registry.visible(prefix), key=lambda e: e.source.chronological_rank)
    frontier = SourceFrontier(cutoff, tuple(dict(source_binding(e.source),
        source_sha256=source_sha(e.source), reported_at=e.reported_at,
        known_at=K.TimePoint(session_rank=e.source.chronological_rank+1),
        ready_at=e.ready_at) for e in entries))
    admitted = {(e.source.owner_id,e.source.session_id): e for e in entries}
    rows = []
    for row in ledger.rows:
        if (row.owner_id,row.session_id) not in admitted or row.writer_identity != writer:
            continue
        verify_record(row, registry)
        if at_or_before(row.known_at, cutoff) and at_or_before(row.ready_at, cutoff):
            rows.append(row)
    rows.sort(key=lambda r: (r.reported_at.session_rank,r.record_id))
    ids = {r.record_id for r in rows}
    state = {r.record_id: ('raw_available' if r.kind == 'MS_RAW' else
        'supported_report' if r.semantically_approved else 'quarantine') for r in rows}
    invalidations = []
    for row in rows:
        if row.kind == 'RELATION' and row.semantically_approved and row.target_id in ids:
            state[row.target_id] = 'conflict' if row.operation == 'CONTRADICTS' else 'superseded'
            invalidations.append(dict(target_id=row.target_id, relation_id=row.record_id,
                invalidated_knowledge_time=row.known_at, readable_at=row.ready_at,
                fact_valid_to=row.valid_to))
    # No latest-wins projection. Unlinked approved alternatives remain conflicts.
    slots = {}
    for row in rows:
        if row.kind == 'MP' and state[row.record_id] == 'supported_report':
            slots.setdefault((row.subject,row.slot), []).append(row)
    for claims in slots.values():
        if len({r.text for r in claims}) > 1:
            for r in claims: state[r.record_id] = 'conflict'
    views = []
    for row in rows:
        validity = 'unknown'
        if row.valid_to and fact_at_or_before(row.valid_to, cutoff) is True:
            validity = 'expired_as_reported'
        elif row.valid_from and fact_at_or_before(row.valid_from, cutoff) is False:
            validity = 'not_yet_valid_as_reported'
        elif row.valid_from and row.valid_to and fact_at_or_before(row.valid_from, cutoff) is True and fact_at_or_before(row.valid_to, cutoff) is False:
            validity = 'within_reported_interval'
        if state[row.record_id] == 'superseded': validity = 'superseded_as_known'
        views.append(dict(record=row, disposition=state[row.record_id], current_validity=validity))
    payload = dict(protocol=PROTOCOL, as_of=cutoff, writer_identity=writer,
        source_frontier=frontier, source_frontier_sha256=frontier.sha256,
        ledger_prefix=tuple(rows), views=views, invalidations=invalidations,
        time_basis='logical_replay; no measured historical writer deployment',
        qualification='engineering_only')
    return dict(payload, snapshot_sha=object_sha256(payload))


def verify_snapshot(snapshot):
    if snapshot.get('protocol') != PROTOCOL or snapshot.get('snapshot_sha') != object_sha256(
            {k:v for k,v in snapshot.items() if k != 'snapshot_sha'}):
        raise ValueError('snapshot integrity')


def load_snapshot(path, *, expected_sha):
    """Read a frozen snapshot against the independently recorded manifest SHA."""
    payload = json.loads(Path(path).read_text())
    verify_snapshot(payload)
    if payload['snapshot_sha'] != expected_sha:
        raise ValueError('snapshot differs from pinned identity')
    def as_of(raw):
        return PrefixAsOf(**dict(raw, ancestor_family_ids=tuple(raw['ancestor_family_ids'])))
    payload['as_of'] = as_of(payload['as_of'])
    f = payload['source_frontier']; sources = []
    for raw in f['sources']:
        s = dict(raw, ancestor_family_ids=tuple(raw['ancestor_family_ids']))
        for key in ('reported_at','known_at','ready_at'):
            s[key] = decode_contract(K.TimePoint,canonical_json(s[key]))
        sources.append(s)
    payload['source_frontier'] = SourceFrontier(as_of(f['as_of']),tuple(sources))
    payload['ledger_prefix'] = tuple(decode_record(r) for r in payload['ledger_prefix'])
    payload['views'] = [dict(v,record=decode_record(v['record'])) for v in payload['views']]
    verify_snapshot(payload)
    if payload['source_frontier'].sha256 != payload['source_frontier_sha256']:
        raise ValueError('source frontier integrity')
    return payload


def candidate_ids(snapshot, head):
    verify_snapshot(snapshot)
    kinds = {'MP':('MP',), 'ME':('ME',), 'MS':('MS_RAW',)}
    if head not in kinds:
        raise ValueError('external RS uses separate versioned candidates')
    return tuple(v['record'].record_id for v in snapshot['views'] if v['record'].kind in kinds[head]
        and v['disposition'] in ('raw_available','supported_report','conflict'))


def read(snapshot, head, *, ordinal, token_counter, context_remaining):
    """Controlled GET, deterministic chronological order, no utility rank claims.

    Caller must supply a tokenizer with an explicit identity. Tests may use a
    named fixture counter; no estimated number is labelled native tokens.
    """
    ids = candidate_ids(snapshot, head)
    if not getattr(token_counter, 'identity', None):
        raise ValueError('explicit token counter identity required')
    if not ids:
        return {'status':'unavailable', 'head':head}
    item = next(v for v in snapshot['views'] if v['record'].record_id == ids[-1])
    row = item['record']
    if item['disposition'] == 'conflict':
        return {'status':'conflict_requires_review', 'head':head}
    stage = 'unknown' if row.stage == 'rejected' else row.stage
    text = ('Quoted historical evidence; optional even if related. Do not infer current truth, '
        'execution from suggestions, or an objective treatment effect.\n'
        f'Subject: {row.subject}; stage: {row.stage}; validity: {item["current_validity"]}.\n'+row.text)
    tokens = token_counter.count(text)
    if tokens > context_remaining:
        return {'status':'capacity', 'head':head}
    return K.ReadingView(head=head, view={'MP':'assertion','ME':'event','MS':'raw'}[head],
        ordinal=ordinal, reading_text=text, reported_at=row.reported_at, tokens=tokens,
        stage=stage if head == 'ME' else None)


def summary_or_raw(snapshot, summary_id):
    """Private planning result. No EXPAND action or free RAW read is introduced."""
    verify_snapshot(snapshot)
    by_id = {v['record'].record_id:v for v in snapshot['views']}
    item = by_id.get(summary_id)
    if item is None or item['record'].kind != 'MS_SUM':
        raise ValueError('summary unavailable at this cutoff')
    row = item['record']; parent = by_id.get(row.raw_parent_id)
    if parent is None or parent['record'].kind != 'MS_RAW':
        raise ValueError('RAW parent unavailable')
    fallback = item['disposition'] != 'supported_report' or row.review_status == 'unusable'
    condition = 'SUM_TO_RAW_FALLBACK' if fallback else 'SUM'
    return dict(condition=condition, selected_id=row.raw_parent_id if fallback else row.record_id,
        view_identity=object_sha256(dict(snapshot=snapshot['snapshot_sha'], summary=summary_id,
            parent=row.raw_parent_id, condition=condition)), reason='summary_unusable_or_unreviewed' if fallback else None)

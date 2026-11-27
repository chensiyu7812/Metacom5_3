"""NAA Memory Writer: offline, source-bound projection of legal history into memory units.

Input is ONLY the EvidenceRecords that A's HistoryResolver returns for one owner,
already cut at the task boundary. The writer never receives the user query, MCQ
options, evaluation fields or Direct manifests, so a stored unit cannot encode a
target. Every unit keeps the original text, its hash and coordinates; projections
(identity, subject, order, constraint candidates) are deterministic host facts or
explicit pattern candidates, never model inferences and never "confirmed".

Reuses the semcap identity contract (classify_source / attribute_history /
is_current_user) instead of inventing a second role vocabulary. The historical
semcap/GE2 modules are imported, not modified.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re

from ..data.contracts import EvidenceRecord, digest, text_hash
from ...rl1v3.semcap import identity as I

WRITER_VERSION = 'naa-memory-writer-v1'
DATASET = 'PersonaMem-v2'

# PersonaMem roles -> semcap identity roles. Earlier assistant replies were produced by
# the dataset's generation pipeline, not by this deployed agent: their author is not
# established (U), so they are never presented as this agent's own experiences.
ROLE_TO_IDENTITY = {'user': 'seeker', 'assistant': 'supporter'}

# Explicit, conservative user-issued constraint patterns. A hit is a *candidate* that the
# reader must surface with its source; it never deletes or overwrites a unit.
# Imperative only ("please forget ...", "can you forget ..."), not "I always forget my keys";
# editing/narrative verbs (ignore/delete/erase) are excluded after inspecting real hits.
_A = r"[\u2019']"
_FORGET = re.compile(
    r"(?:^|[.!?]\s+|\bplease\s+|\b(?:can|could|would)\s+you\s+(?:please\s+)?)forget\b[^.?!\n]{0,60}?"
    r"\b(?:that|this|my|the|about|what|everything|anything)\b"
    r"|\b(?:don" + _A + r"t|do\s+not)\s+(?:remember|keep|store|save)\s+(?:that|this|what|my|it)\b"
    r"|\bstop\s+remembering\b"
    r"|\b(?:erase|delete|remove|wipe)\s+(?:that|this|it|my\s+\w+)\s+from\s+(?:your|the)\s+memory\b",
    re.IGNORECASE)
# Explicit change-over-time statements only ("lately I've been ..." is not an update).
_UPDATE = re.compile(
    r"\bi\s+(?:no\s+longer|used\s+to|(?:have\s+|" + _A + r"ve\s+)?changed\s+my\s+mind|"
    r"(?:don" + _A + r"t|do\s+not)\s+\w+\s+(?:anymore|any\s+more))\b|\bnot\s+anymore\b",
    re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("""a an and are as at be but by for from has have i i'm im in is it its me my of on or our
please forget that the this to was were with you your about preference preferences detail details like
mentioned said told shared what which who really also just very so""".split())
FORGET_LINK_MIN = 0.6


def _content(text):
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def link_forget_requests(units):
    """Deterministic lexical link from a forget request to the earlier user statement it names.

    Candidate only (overlap of the request's content words with one earlier user message);
    ambiguous or unspecific requests stay unlinked. Nothing is deleted.
    """
    links = []
    for f in units:
        if 'forget_request' not in f.constraint_candidates:
            continue
        m = _FORGET.search(f.original_text)
        clause = _content(f.original_text[m.start():])
        best, score = None, 0.
        if len(clause) >= 2:
            for u in units:
                if u.order >= f.order or not u.is_current_user or 'forget_request' in u.constraint_candidates:
                    continue
                s = len(clause & _content(u.original_text)) / len(clause)
                if s > score or (s == score and best is not None and u.order > best.order):
                    best, score = u, s
        linked = best is not None and score >= FORGET_LINK_MIN
        links.append(dict(type='forget_request', unit_id=f.unit_id, order=f.order,
                          target_unit_id=best.unit_id if linked else None,
                          overlap=round(score, 3), basis='lexical_candidate_not_verified'))
    return links


@dataclass(frozen=True)
class MemoryUnit:
    unit_id: str            # == A's EvidenceRecord.source_id (stable join key)
    owner_id: str
    source_family: str
    order: int              # original message index; the only time axis available
    speaker: str            # user | assistant
    speaker_label: str      # identity-contract label rendered to the Generator
    situation: str
    is_current_user: bool   # subject binding: a statement BY the current user
    subject: str            # current_user_self_report | earlier_assistant_reply
    reported_at: object     # None: PersonaMem gives no wall-clock time; never fabricated
    time_basis: str
    status: str             # reported (verbatim) -- never "confirmed"
    constraint_candidates: tuple  # ('forget_request',) / ('possible_update',) from explicit text
    original_text: str
    original_text_sha256: str
    coordinates: dict

    def to_dict(self):
        d = asdict(self)
        d['constraint_candidates'] = list(self.constraint_candidates)
        return d

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        d['constraint_candidates'] = tuple(d['constraint_candidates'])
        unit = cls(**d)
        if text_hash(unit.original_text) != unit.original_text_sha256:
            raise ValueError('memory unit text hash mismatch')
        return unit


@dataclass
class MemoryStore:
    store_id: str
    writer_version: str
    owner_id: str
    source_family: str
    cutoff: int
    situation: str
    situation_basis: str
    units: list
    excluded: list = field(default_factory=list)
    constraints: list = field(default_factory=list)

    def by_id(self):
        return {u.unit_id: u for u in self.units}

    def to_dict(self):
        return dict(store_id=self.store_id, writer_version=self.writer_version, owner_id=self.owner_id,
                    source_family=self.source_family, cutoff=self.cutoff, situation=self.situation,
                    situation_basis=self.situation_basis, units=[u.to_dict() for u in self.units],
                    excluded=list(self.excluded), constraints=list(self.constraints))

    @classmethod
    def from_dict(cls, d):
        store = cls(store_id=d['store_id'], writer_version=d['writer_version'], owner_id=d['owner_id'],
                    source_family=d['source_family'], cutoff=d['cutoff'], situation=d['situation'],
                    situation_basis=d['situation_basis'],
                    units=[MemoryUnit.from_dict(u) for u in d['units']], excluded=list(d['excluded']),
                    constraints=list(d['constraints']))
        if store.store_id != store_identity(store):
            raise ValueError('memory store identity mismatch')
        return store


def store_identity(store):
    return 'naamem:' + digest(dict(writer=store.writer_version, owner=store.owner_id,
        family=store.source_family, cutoff=store.cutoff, situation=store.situation,
        units=[(u.unit_id, u.original_text_sha256, u.subject, list(u.constraint_candidates)) for u in store.units],
        excluded=[(x['source_id'], x['original_text_sha256'], x['reason']) for x in store.excluded],
        constraints=store.constraints))


class MemoryWriter:
    """Write one owner's pre-cutoff history. No query, options or evaluation input exists here."""

    def __init__(self, dataset=DATASET):
        source = I.classify_source(dataset)
        self.situation, self.basis = source.situation, source.basis

    def write(self, records, *, owner_id, source_family, cutoff):
        if not records and cutoff:
            raise ValueError('empty history for positive cutoff')
        units, excluded, seen = [], [], set()
        for record in records:
            if not isinstance(record, EvidenceRecord):
                raise TypeError('writer accepts only resolver EvidenceRecords')
            if record.owner_id != owner_id or record.source_family != source_family:
                raise ValueError('wrong owner/source family record')
            if record.order >= cutoff:
                raise ValueError('record at/after cutoff (future information)')
            if record.source_id in seen:
                raise ValueError('duplicate source id')
            seen.add(record.source_id)
            if record.speaker == 'system' or record.validity == 'excluded':
                # PersonaMem message 0 is the generator's persona profile. It is a research
                # label, not something a deployed agent would observe; keep only its hash.
                excluded.append(dict(source_id=record.source_id, order=record.order, speaker=record.speaker,
                    original_text_sha256=record.original_text_sha256,
                    reason='system_profile_not_deployable' if record.speaker == 'system' else 'excluded_by_source'))
                continue
            role = ROLE_TO_IDENTITY[record.speaker]
            current_user = I.is_current_user(role, self.situation)
            candidates = ()
            if current_user:
                hits = []
                if _FORGET.search(record.original_text):
                    hits.append('forget_request')
                if _UPDATE.search(record.original_text):
                    hits.append('possible_update')
                candidates = tuple(hits)
            units.append(MemoryUnit(
                unit_id=record.source_id, owner_id=owner_id, source_family=source_family,
                order=record.order, speaker=record.speaker,
                speaker_label=I.attribute_history(role, self.situation), situation=self.situation,
                is_current_user=current_user,
                subject='current_user_self_report' if current_user else 'earlier_assistant_reply',
                reported_at=record.reported_at, time_basis='message_order_only_no_wall_clock',
                status='reported', constraint_candidates=candidates,
                original_text=record.original_text, original_text_sha256=record.original_text_sha256,
                coordinates=dict(record.coordinates)))
        units.sort(key=lambda u: u.order)
        store = MemoryStore(store_id='', writer_version=WRITER_VERSION, owner_id=owner_id,
                            source_family=source_family, cutoff=cutoff, situation=self.situation,
                            situation_basis=self.basis, units=units, excluded=excluded,
                            constraints=link_forget_requests(units))
        store.store_id = store_identity(store)
        return store


class StoreCache:
    """Private on-disk cache: one immutable store per (owner, family, cutoff, writer version)."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, store_id):
        return self.root / (store_id.replace(':', '_') + '.json')

    def put(self, store):
        p = self.path(store.store_id)
        data = json.dumps(store.to_dict(), ensure_ascii=False, sort_keys=True)
        if p.exists():
            if p.read_text() != data:
                raise ValueError('existing store differs from deterministic rewrite')
            return p
        tmp = p.with_suffix('.tmp')
        tmp.write_text(data)
        tmp.replace(p)
        return p

    def get(self, store_id):
        return MemoryStore.from_dict(json.loads(self.path(store_id).read_text()))


def write_for_task(resolver, writer, task):
    """Resolver enforces hash/owner/cutoff; only records (not the task) reach the writer."""
    records = resolver.resolve(task)
    return writer.write(records, owner_id=task.persona_group, source_family=task.source_family, cutoff=task.cutoff)

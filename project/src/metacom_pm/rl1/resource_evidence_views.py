"""Deterministic source views; no summarizer, inferred relations or reward labels.

The MS alternative retains EVERY registered turn in original order. It is an
explicit presentation treatment, not a token cap or a purported summary.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, replace
import json

from .schema import digest
from .temporal_evidence_ledger import SourceTurn, TemporalEvidenceLedger, words

VERSION = "pmrl1-source-views-v2-20261030"


class EvidenceViews:
    def __init__(self, prefix, exported):
        if (exported.get("identity") != digest({k: v for k, v in exported.items() if k != "identity"})
                or exported["prefix_identity"] != prefix.identity):
            raise ValueError("source export identity mismatch")
        turns = []
        for key, row in exported["source_turns"].items():
            turn = SourceTurn(**{k: v for k, v in row.items() if k != "identity"})
            if turn.key != key or turn.identity != row["identity"]:
                raise ValueError("source turn identity mismatch")
            turns.append(turn)
        self.ledger = TemporalEvidenceLedger(prefix, turns, provenance_identity=exported["provenance_identity"])
        self.exported = deepcopy(exported)
        self.prefix = prefix
        self.turns = {t.key: t for t in turns}
        self.claims = defaultdict(list)
        for key, claim in exported["claims"].items():
            if key != digest(claim):
                raise ValueError("claim identity mismatch")
            self.ledger._validate_spans(claim["spans"])
            inputs = set(claim["input_source_keys"])
            if not inputs <= self.turns.keys() or not {s['source_key'] for s in claim['spans']} <= inputs:
                raise ValueError("claim dependency closure mismatch")
            self.claims[claim["candidate_id"]].append(dict(identity=key, **deepcopy(claim)))
        self.identity = digest(dict(version=VERSION, source=exported["identity"], prefix=prefix.identity))

    def binding(self, item):
        if item.head == 'RS':
            raise ValueError('RS conditions need separate source/review evidence')
        if (item.owner_id != self.prefix.owner_id or item.source_rank >= self.prefix.cutoff_rank
                or item.reported_at > self.prefix.timestamp):
            raise ValueError('foreign or non-past item')
        if item.head in ('MP', 'ME'):
            claims = self.claims.get(item.key, [])
            for claim in claims:
                if claim['head'] != item.head or claim['statement'] != json.loads(item.content)['past_report']:
                    raise ValueError('mapped claim differs from resource')
                if any(self.turns[k].session_id not in item.source_ids for k in claim['input_source_keys']):
                    raise ValueError('claim includes an unacquired source')
            return dict(resource_identity=item.identity, view_identity=self.identity,
                        claims=deepcopy(claims), status='located' if claims else 'source_missing',
                        semantic_support='unverified', training_label=False)
        if item.head != 'MS' or len(item.source_ids) != 1:
            raise ValueError('one complete MS session required')
        turns = sorted((t for t in self.turns.values() if t.session_id == item.source_ids[0]),
                       key=lambda t: t.turn_index)
        if not turns:
            return dict(resource_identity=item.identity, status='source_missing')
        raw = json.loads(item.content)['full_source_conversation']
        if '\n'.join(t.speaker + ': ' + t.text for t in turns) != raw:
            raise ValueError('registered session differs from full delivered MS')
        if any(t.session_rank != item.source_rank or t.reported_at != item.reported_at for t in turns):
            raise ValueError('session time differs from resource')
        return dict(resource_identity=item.identity, status='located', turns=[asdict(t) for t in turns],
                    raw_transcript_identity=digest(raw), semantic_support='unverified')

    def ms_turn_view(self, item):
        bound = self.binding(item)
        if bound['status'] != 'located':
            raise ValueError('complete registered MS required; no partial replacement')
        records = []; matches = []
        for row in bound['turns']:
            t = SourceTurn(**row)
            records.append([t.turn_index, t.speaker, t.text])
            matches.append(dict(turn_index=t.turn_index,
                                matched_public_terms=sorted(words(self.prefix.query) & words(t.text))))
        body = dict(schema=VERSION, kind='MS', reported_at=item.reported_at,
                    source_scope='One already selected past session; complete ordered turns; no inferred facts.',
                    turn_fields=['turn_index', 'speaker', 'text'], turns=records, summary=None, omitted_turns=0)
        content = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        changed = replace(item, content=content,
            source_identity=digest(dict(original=item.source_identity, view=self.identity, body=body)))
        receipt = dict(version=VERSION, source_item_identity=item.identity,
                       new_item_identity=changed.identity, source_ids=list(item.source_ids),
                       turns=len(records), omitted_turns=0, extra_sessions=0,
                       derived_summary=False, quality_effect='not_measured',
                       original_transcript_identity=bound['raw_transcript_identity'],
                       literal_matches_audit_only=matches)
        return changed, receipt

    def organize(self, items):
        slots = defaultdict(list); events = []; bindings = []; source_links = defaultdict(list)
        for item in items:
            if item.head == 'RS':
                continue
            binding = self.binding(item); bindings.append(dict(key=item.key, head=item.head, **binding))
            body = json.loads(item.content)
            record = dict(key=item.key, reported_at=item.reported_at, binding_status=binding['status'])
            if item.head == 'MP':
                slots[body['profile_slot']].append(record | dict(current_status=body.get('current_status', 'unknown')))
            elif item.head == 'ME':
                events.append(record | dict(stage=body.get('action_stage', 'unknown'),
                    event_time=body.get('event_time'), outcome=body.get('observed_outcome')))
            for claim in binding.get('claims', []):
                for span in claim['spans']:
                    source_links[span['source_key']].append(item.key)
        return dict(version=VERSION, identity=self.identity, audience='construction_only', bindings=bindings,
            profile_report_sequences={k: sorted(v, key=lambda r: (r['reported_at'], r['key'])) for k, v in slots.items()},
            event_reports=sorted(events, key=lambda r: (r['reported_at'], r['key'])),
            shared_source_locations=[dict(source_key=k, resources=sorted(set(v)), relation='shares_source_location',
                same_fact_or_event='unverified') for k, v in sorted(source_links.items()) if len(set(v)) > 1],
            semantic_updates=[], semantic_event_relations=[], new_current_facts=0, training_labels=0)

"""Conservative legacy migration; no new summaries, methods or relation inference.

Historical-only MP stays in the migration ledger, never in runtime candidates.
The three explicitly evidenced repairs have new identities; two change MP→ME.
RS is one complete dialogue case per admitted source, not a proven method.
"""
from __future__ import annotations
from dataclasses import replace
from collections import defaultdict, Counter
from pathlib import Path
import json

from .. import contracts as K
from ..io import canonical_json, decode_contract, file_sha256, object_sha256, write_json_once, write_jsonl_once
from ..sources import source_registry as S
from ..sources.asset_reuse import verify_unit

PROTOCOL='pmrl1v3-bank-v0.1'
INDEX_PROTOCOL='pmrl1v3-index-lexical-static-v0.1'
RENDERER_ID='pmrl1v3-attributed-quotes-full-cases-v0.1'
REPAIR_PATH='project/outputs/pm_rl1/research_preparation_20261115_v1/memory/CANDIDATE_VIEW_REPAIRS_PRIVATE.json'


def _identity(records, registry, inputs):
    return 'bank:'+object_sha256(dict(protocol=PROTOCOL,source_version=registry.version,
        inputs=inputs,records=[replace(r,bank_version='pending') for r in records]))


class Bank:
    def __init__(self,records,registry,inputs,ledger):
        self.records=tuple(records);self.registry=registry;self.inputs=dict(inputs);self.ledger=tuple(ledger)
        self.version=_identity(self.records,registry,inputs)
        if any(r.bank_version!=self.version for r in self.records):raise ValueError('bank version mismatch')
        self.by_id={r.record_id:r for r in self.records}
        if len(self.by_id)!=len(self.records):raise ValueError('duplicate record')
        self.source_ids={}
        for r in self.records:
            if not r.source_refs or r.related_claim_ids or r.relation_index_version:
                raise ValueError('v0 requires source evidence and forbids graph propagation')
            if r.review_status not in ('unverified','development_reviewed') or r.positive_eligible:
                raise ValueError('v0 cannot claim research validation')
            entries=[]
            for ref in r.source_refs:
                e=registry.entry(ref.owner_id,ref.session_id);ref.verify(e.source);entries.append(e)
            ids=tuple(sorted({e.source_id for e in entries}));self.source_ids[r.record_id]=ids
            if len(ids)!=1:raise ValueError('v0 units cannot invent cross-session relations')
            e=entries[0];s=e.source
            if (r.family_id,r.original_raw_identity,r.reported_at,r.ready_at)!=(s.family_id,s.transcript_sha256,e.reported_at,e.ready_at):
                raise ValueError('resource provenance/time mismatch')
            if r.ancestor_family_ids!=(s.family_id,):raise ValueError('family closure mismatch')
            if r.head=='RS':
                if s.dataset!='ESConv' or s.source_split!='train' or s.family_id in registry.excluded_families:
                    raise ValueError('RS train/family violation')
            elif r.owner_id!=s.owner_id or r.source_rank!=s.chronological_rank:
                raise ValueError('memory owner/rank mismatch')
        self.index_version='index:'+object_sha256(dict(protocol=INDEX_PROTOCOL,bank=self.version,
            record_ids=sorted(self.by_id),renderer=RENDERER_ID,query='last_3_visible_turns',packing='one_whole_record'))

    def reason(self,record,prefix):
        for sid in self.source_ids[record.record_id]:
            reason=self.registry.reason(sid,prefix,rs=record.head=='RS')
            if reason:return reason
        if record.review_status in ('rejected','unusable'):return 'review'
        return None

    def candidates(self,head,prefix):
        if head not in K.HEAD_ORDER:raise ValueError('invalid head')
        self.registry.context(prefix)
        return tuple(r for r in self.records if r.head==head and self.reason(r,prefix) is None)


def _base(entry,head,reading,body,refs,*,stage=None,review='unverified',legacy_id):
    s=entry.source
    rid='resource:'+object_sha256(dict(protocol=PROTOCOL,head=head,old_id=legacy_id,
        source_id=entry.source_id,reading=reading,body=body,refs=refs,stage=stage,review=review))
    return K.ResourceRecord(record_id=rid,bank_version='pending',head=head,
        view={'MP':'assertion','ME':'event','MS':'raw','RS':'case'}[head],
        owner_id=None if head=='RS' else s.owner_id,source_refs=tuple(refs),
        reported_at=entry.reported_at,event_time=None,valid_from=None,invalid_at=None,
        stage=stage,body=canonical_json(body),reading_text=reading,index_keys=(),review_status=review,
        writer_identity=PROTOCOL,source_rank=None if head=='RS' else s.chronological_rank,ready_at=entry.ready_at,
        origin_dataset=s.dataset,family_id=s.family_id,original_raw_identity=s.transcript_sha256,
        ancestor_family_ids=(s.family_id,),parent_session_id=s.session_id,
        evidence_status='exact_span_verified',epistemic_status='unknown' if head in ('MS','RS') else 'user_reported',
        raw_view_identity=s.transcript_sha256 if head=='MS' else None,
        license_scope=s.license,risk_tier='unknown',usage_scope='research_only' if head=='RS' else 'engineering_only',
        source_split=s.source_split,positive_eligible=False)


def build(root,registry):
    root=Path(root);pins=S.PinnedInputs(root)
    compiled=pins.read('compiled',lines=True);pool=pins.read('pool',lines=True)
    repairs={r['old_key']:r for r in json.loads(pins.path(REPAIR_PATH).read_text())}
    units=[u for row in compiled for u in row['accepted_units']]
    if len({u['memory_id'] for u in units})!=len(units):raise ValueError('duplicate legacy memory')
    expected_repairs=set(pins.config['known_repair_ids'])
    if {k.split('::')[1] for k in repairs}!=expected_repairs:raise ValueError('repair coverage mismatch')
    sessions={(e.source.owner_id,e.source.session_id):dict(chronological_rank=e.source.chronological_rank,
        timestamp=e.source.date,turns=[dict(idx=idx,role=t.role,content=t.text) for idx,t in zip(e.original_turn_indices,e.source.turns)])
        for e in registry.entries if e.source.dataset==S.DATASET}
    profiles=defaultdict(list)
    for u in units:
        if 'profile_slot_key' in u:profiles[(u['owner_id'],u['profile_slot_key'])].append(u)
    latest={key:tuple(u for u in rows if u['source_session_rank']==max(x['source_session_rank'] for x in rows))
            for key,rows in profiles.items()}
    pool_mp={r['candidate_id'] for r in pool if r['head']=='MP'}
    projected={'mp::'+u['memory_id'] for rows in latest.values() for u in rows}
    if projected!=pool_mp:raise ValueError('old latest-at-full-history projection no longer reproduces MP pool')
    records=[];ledger=[]
    for u in units:
        old_head='MP' if 'profile_slot_key' in u else 'ME';old_id=old_head.lower()+'::'+u['memory_id']
        errors,_=verify_unit(u,sessions)
        if errors:raise ValueError('changed source span '+old_id+':'+','.join(errors))
        e=registry.entry(u['owner_id'],u['source_session_id'])
        refs=tuple(S.span(e.source,e.original_turn_indices.index(s['turn_index']),s['start_char'],s['end_char']) for s in u['supporting_spans'])
        missing=old_head=='MP' and old_id not in pool_mp
        row=dict(old_id=old_id,old_head=old_head,source_verified=True,old_pool_member=not missing,
            source_ids=[e.source_id],source_row_sha256=object_sha256(u),new_record_ids=[],status='migrated',
            reason='exact source quotes; semantics unverified',replacement_ids=[])
        if missing:
            row.update(status='quarantine',reason='old_full_history_latest_rank_projection; no automatic v0 readmission',
                replacement_ids=['mp::'+v['memory_id'] for v in latest[(u['owner_id'],u['profile_slot_key'])]])
        repaired=repairs.get(old_id)
        if missing and repaired is None:ledger.append(row);continue
        head=old_head;stage='unknown' if head=='ME' else None;review='unverified'
        text='Historical self-report; present validity unverified.\n'
        body=dict(legacy_id=old_id,legacy_unit=u,relation_propagation=False,semantic_status='unverified')
        if repaired:
            candidate=repaired['candidate'];binding=repaired['original_quote_and_binding']
            turn=e.source.turns[binding['ordinal_turn']]
            if turn.text!=binding['text'] or not any(ref.exact_quote==binding['text'] for ref in refs):
                raise ValueError('repair quote not bound to original source')
            if candidate['source_owner_id']!=u['owner_id'] or candidate['source_rank']!=u['source_session_rank']:
                raise ValueError('repair owner/rank mismatch')
            head=candidate['proposed_head'];stage=candidate['historical_action']['stage'];review='development_reviewed'
            text=candidate['proposed_past_report']+'\nSource quote (self-report; not independently validated):\n'
            body.update(repair_sha256=object_sha256(repaired),repair_id=repaired['repair_id'],repair_candidate=candidate)
            row.update(status='repaired',reason='evidenced sidecar migration; independent semantic review pending')
        elif head=='ME':text+='Action stage is unknown; do not infer completion or causality.\n'
        text+='\n'.join(f'{ref.speaker}: {ref.exact_quote}' for ref in refs)
        record=_base(e,head,text,body,refs,stage=stage,review=review,legacy_id=old_id)
        records.append(record);row.update(new_record_ids=[record.record_id],new_head=head);ledger.append(row)
    for e in registry.entries:
        if e.source.dataset!=S.DATASET:continue
        s=e.source;old_id=f'ms::{s.owner_id}::{s.session_id}'
        refs=tuple(S.span(s,i) for i,t in enumerate(s.turns) if t.text)
        text='Complete past session (original utterances; not verified world facts):\n'+'\n'.join(f'{t.role}: {t.text}' for t in s.turns)
        record=_base(e,'MS',text,dict(legacy_id=old_id,original_turn_indices=e.original_turn_indices),refs,legacy_id=old_id)
        records.append(record);ledger.append(dict(old_id=old_id,old_head='MS',status='migrated',source_verified=True,
            source_ids=[e.source_id],new_record_ids=[record.record_id],reason='complete immutable RAW; not a summary'))
    strategies=pins.read('rs_strategy',lines=True);treatments=pins.read('rs_treatments',lines=True)
    by_source=defaultdict(list);treatment_by_source=defaultdict(list)
    for strategy in strategies:
        sid=strategy['source_dialogue_id'];e=registry.entry('external:'+sid,sid)
        ordinal=strategy['source_turn_index'];turn=e.source.turns[ordinal]
        # Some historical adapters trim whitespace; retain original bytes in the case.
        if turn.role!='supporter' or ' '.join(turn.text.split())!=' '.join(strategy['example_response'].split()):
            raise ValueError('RS strategy turn not bound to raw dialogue: '+strategy['strategy_id'])
        by_source[sid].append(strategy['strategy_id'])
    for treatment in treatments:
        for sid in treatment['source_dialogue_ids']:
            registry.entry('external:'+sid,sid)  # fail closed if any ancestor is excluded
            treatment_by_source[sid].append(treatment['treatment_id'])
    case_by_source={}
    for sid in sorted(set(by_source)|set(treatment_by_source)):
        e=registry.entry('external:'+sid,sid);s=e.source
        refs=tuple(S.span(s,i) for i,t in enumerate(s.turns) if t.text)
        text=('External research conversation example; unverified and not a professional method. '
              'Do not assume this example happened to the current user or copy promises or self-disclosures.\n'
              +'\n'.join(f'{t.role}: {t.text}' for t in s.turns))
        body=dict(strategy_ids=sorted(by_source[sid]),treatment_ids=sorted(treatment_by_source[sid]),
                  source_dialogue_id=sid,relation_type='derived_from_source_only',no_method_validity_claim=True)
        record=_base(e,'RS',text,body,refs,legacy_id='rs-case::'+sid);records.append(record);case_by_source[sid]=record.record_id
    for r in strategies:
        sid=r['source_dialogue_id'];ledger.append(dict(old_id=r['strategy_id'],old_head='RS_strategy',status='adapted_lineage',
            source_verified=True,source_ids=[registry.entry('external:'+sid,sid).source_id],
            new_record_ids=[case_by_source[sid]],reason='strategy -> complete source case; no guidance validity promotion',
            source_turn_index=r['source_turn_index'],binding='exact' if registry.entry('external:'+sid,sid).source.turns[r['source_turn_index']].text==r['example_response'] else 'legacy_whitespace_normalized; original bytes preserved',
            old_row_sha256=object_sha256(r)))
    for r in treatments:
        ledger.append(dict(old_id=r['treatment_id'],old_head='RS_treatment',status='adapted_lineage',source_verified=False,lineage_verified=True,
            source_ids=[registry.entry('external:'+sid,sid).source_id for sid in r['source_dialogue_ids']],
            new_record_ids=[case_by_source[sid] for sid in r['source_dialogue_ids']],
            source_card_ids=r['source_card_ids'],atomic_card_ids=r['atomic_card_ids'],
            reason='treatment lineage only; not an independent method or outcome',old_row_sha256=object_sha256(r)))
    # Retain existing repair/quarantine status of drafted methods/cases; never import bodies.
    asset_ledger=root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_ITEMS.jsonl'
    audit=pins.audit
    if file_sha256(asset_ledger)!=audit['item_ledger']['sha256']:raise ValueError('asset ledger changed')
    pins.used[str(asset_ledger.relative_to(root))]=file_sha256(asset_ledger)
    for line in asset_ledger.read_text().splitlines():
        r=json.loads(line)
        if r['asset_kind'] in ('RS_case','RS_method'):
            ledger.append(dict(old_id=r['old_id'],old_head=r['asset_kind'],status=r['classification'],source_verified=False,
                new_record_ids=[],reason=r['reason']))
    inputs={**pins.used,'writer_sha256':file_sha256(Path(__file__))}
    records.sort(key=lambda r:r.record_id)
    version=_identity(records,registry,inputs)
    return Bank([replace(r,bank_version=version) for r in records],registry,inputs,ledger)


def save(bank,directory):
    directory=Path(directory);write_jsonl_once(directory/'records.jsonl',bank.records)
    write_jsonl_once(directory/'migration.jsonl',bank.ledger)
    write_json_once(directory/'bank.json',dict(protocol=PROTOCOL,schema_version=K.SCHEMA_VERSION,bank_version=bank.version,
        source_version=bank.registry.version,inputs=bank.inputs,records_sha256=file_sha256(directory/'records.jsonl'),
        migration_sha256=file_sha256(directory/'migration.jsonl'),head_counts=dict(Counter(r.head for r in bank.records))))
    write_json_once(directory/'index.json',index_manifest(bank))


def index_manifest(bank):
    return dict(protocol=INDEX_PROTOCOL,index_version=bank.index_version,
        bank_version=bank.version,source_version=bank.registry.version,renderer_id=RENDERER_ID,
        algorithm='visible_last_3_turn_word_overlap; filter_first; head_specific_tie_break; one_whole_record',
        dense_encoder=None,bm25=None,graph_propagation=False,
        records_content_sha256=object_sha256(bank.records),qualification='engineering_only; recall_quality_not_measured')


def load(directory,registry,*,expected_version=None):
    directory=Path(directory);meta=json.loads((directory/'bank.json').read_text());index=json.loads((directory/'index.json').read_text())
    if meta['protocol']!=PROTOCOL or meta['schema_version']!=K.SCHEMA_VERSION or meta['source_version']!=registry.version:
        raise ValueError('unsupported bank/source/schema version')
    for name,key in [('records.jsonl','records_sha256'),('migration.jsonl','migration_sha256')]:
        if file_sha256(directory/name)!=meta[key]:raise ValueError('bank file integrity: '+name)
    records=[decode_contract(K.ResourceRecord,line) for line in (directory/'records.jsonl').read_text().splitlines()]
    bank=Bank(records,registry,meta['inputs'],[json.loads(line) for line in (directory/'migration.jsonl').read_text().splitlines()])
    if bank.version!=meta['bank_version'] or (expected_version and bank.version!=expected_version):raise ValueError('bank identity mismatch')
    if index!=index_manifest(bank):
        raise ValueError('index identity mismatch')
    return bank

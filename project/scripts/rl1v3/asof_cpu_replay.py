#!/usr/bin/env python3
"""Reproducible P0-P2 CPU delivery. No tokenizer/weights/network/model calls.

Old evidence is read at exact Git commits; never merged, renamed or overwritten.
Requires the pinned PR #12/#13 commits in the local Git object store.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter, defaultdict
from dataclasses import replace
import json
from pathlib import Path
import subprocess

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import canonical_json, decode_contract, file_sha256, object_sha256, sha256_bytes, write_json_once, write_jsonl_once
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.bank import bank_v0
from metacom_pm.rl1v3.retrieve.v0 import search
from metacom_pm.rl1v3.compile import asof as A
from metacom_pm.rl1v3.compile.resource_candidates import MethodCandidate, CaseCandidate, fair_rs_inputs
from metacom_pm.rl1v3.render import asof_candidate as R

BASE = '320a33d1d871199d171f998300ce926b341ca1a8'
PR12 = '8ba20d21da4bdcbb552946241563bd41dbe46c6c'
PR13 = 'ea2f5bde04caba4590b26c80a572d66caa4a2d08'
V3 = 'project/outputs/pm_rl1/v3/'
OWNERS = ('p1','p15','p18')


class Pinned:
    def __init__(self, root): self.root,self.inputs = root,[]
    def text(self, commit, path):
        data = subprocess.check_output(['git','-C',str(self.root),'show',commit+':'+path])
        self.inputs.append(dict(commit=commit,path=path,sha256=sha256_bytes(data),bytes=len(data)))
        return data.decode('utf-8')
    def json(self, commit, path): return json.loads(self.text(commit,path))
    def lines(self, commit, path): return [json.loads(l) for l in self.text(commit,path).splitlines()]
    def local(self, path):
        text = self.text(BASE,path)
        if (self.root/path).read_text() != text: raise ValueError('frozen base input changed: '+path)


def first_prefix(registry, source):
    cut = next(i for i,t in enumerate(source.turns[:-1]) if t.role=='seeker' and source.turns[i+1].role=='supporter')
    return registry.prefix(source.owner_id,source.session_id,cut)


def fixtures(registry):
    # Fixed before outputs; deliberately exposed development examples. These are
    # AI-inspected candidate labels, NOT a human-approved semantic gold set.
    specs = [
        ('p1','p1_conv_9',1,'ME','user',None,'attempted','I started painting.'),
        ('p1','p1_conv_9',1,'ME','therapist',None,'suggested','My therapist suggested taking up a hobby'),
        ('p1','p1_conv_9',3,'ME','user',None,'outcome_reported',None),
        ('p1','p1_conv_12',10,'ME','user',None,'outcome_reported',None),
        ('p1','p1_conv_16',10,'MP','user','work_schedule','unknown',None),
        ('p15','p15_conv_2',8,'ME','user',None,'attempted',None),
        ('p15','p15_conv_2',10,'ME','user',None,'intended',None),
        ('p15','p15_conv_10',15,'ME','user',None,'intended',None),
        ('p18','esc1252',11,'MP','user','relationship','unknown',None),
        ('p18','esc1198',7,'ME','user',None,'intended','I might call my sister and ask her advice.'),
        ('p18','p18_conv_6',9,'MP','user','california_offer','unknown',None),
        ('p18','p18_conv_7',4,'ME','user',None,'rejected',None),
        ('p18','p18_conv_8',6,'MP','user','california_offer','unknown',None),
        ('p18','esc326',4,'MP','user','new_job_report','unknown',None),
    ]
    rows=[]
    for owner,sid,turn,kind,subject,slot,stage,quote in specs:
        e=registry.entry(owner,sid); text=e.source.turns[turn].text
        start=text.index(quote) if quote else 0; end=start+len(quote) if quote else len(text)
        ref=S.span(e.source,turn,start,end)
        rows.append(A.record_from_source(e,kind=kind,refs=(ref,),text=ref.exact_quote,
            subject=subject,slot=slot,stage=stage,review_status='developer_inspected'))
    return rows


def replay(registry, out):
    pending=fixtures(registry); stream=A.Ledger(out/'ledger_rows'); snapshots=[];differences=[]
    for owner in OWNERS:
        entries=sorted((e for e in registry.entries if e.source.owner_id==owner),key=lambda e:e.source.chronological_rank)
        previous=set()
        for entry in entries:
            # Materialize BEFORE committing this session; current prefix is not memory.
            if entry.source.chronological_rank:
                prefix=first_prefix(registry,entry.source)
                snap=A.materialize(registry,prefix,stream)
                ids={r.record_id for r in snap['ledger_prefix']}
                differences.append(dict(owner_id=owner,cutoff_rank=prefix.cutoff_rank,prefix_id=prefix.prefix_id,
                    snapshot_sha=snap['snapshot_sha'],added=sorted(ids-previous),removed=sorted(previous-ids),
                    source_count=len(snap['source_frontier'].sources),
                    disposition_counts=dict(Counter(v['disposition'] for v in snap['views']))))
                previous=ids;snapshots.append((prefix,snap))
                write_json_once(out/'snapshots'/f'{owner}-r{prefix.cutoff_rank:02d}.json',snap)
            raw=A.record_from_source(entry,kind='MS_RAW');stream.append(raw,registry)
            for row in pending:
                if row.owner_id==owner and row.session_id==entry.source.session_id:stream.append(row,registry)
            # SUM structure with exact parent proposition; unreviewed, so fallback.
            chosen=next((r for r in pending if r.owner_id==owner and r.session_id==entry.source.session_id),None)
            if chosen:
                summary=A.record_from_source(entry,kind='MS_SUM',refs=chosen.source_refs,
                    text=chosen.text,raw_parent_id=raw.record_id,subject='session',review_status='unusable')
                stream.append(summary,registry)
    full=A.Ledger()
    for row in stream.rows:full.append(row,registry)
    for prefix,snap in snapshots:
        assert canonical_json(A.materialize(registry,prefix,full))==canonical_json(snap)
    # Restart revalidation and duplicate append are both exercised on persisted data.
    resumed=A.Ledger(out/'ledger_rows')
    for row in stream.rows:assert resumed.append(row,registry) is False
    for prefix,snap in snapshots:assert A.materialize(registry,prefix,resumed)['snapshot_sha']==snap['snapshot_sha']
    write_jsonl_once(out/'LEDGER.jsonl',stream.rows)
    write_jsonl_once(out/'SNAPSHOT_DIFFS.jsonl',differences)
    write_jsonl_once(out/'SEMANTIC_REVIEW_PENDING.jsonl',pending)
    return stream,snapshots


def legacy_risk(units, bank, registry, snapshots):
    units={u['memory_id']:u for row in units for u in row['accepted_units']}
    quarantined=[r for r in bank.ledger if r['old_head']=='MP' and r['status']=='quarantine']
    cases=[]
    for row in quarantined:
        u=units[row['old_id'].split('::')[1]]
        replacements=[units[r.split('::')[1]] for r in row['replacement_ids']]
        assert all(v['source_session_rank']>u['source_session_rank'] for v in replacements)
        e=registry.entry(u['owner_id'],u['source_session_id'])
        refs=[S.span(e.source,e.original_turn_indices.index(s['turn_index']),s['start_char'],s['end_char']) for s in u['supporting_spans']]
        cases.append(dict(old_id=row['old_id'],owner=u['owner_id'],slot=u['profile_slot_key'],
            rank=u['source_session_rank'],source_refs=refs,replacement_ids=row['replacement_ids'],
            replacement_ranks=[v['source_session_rank'] for v in replacements],
            counterexample_cutoff=u['source_session_rank']+1,
            old_full_history_pool_keeps_earlier=False,raw_asof_source_available=True,
            readmitted_to_bank=False,semantic_validity='unknown'))
    by_slot=defaultdict(list)
    for u in units.values():
        if 'profile_slot_key' in u:by_slot[u['owner_id'],u['profile_slot_key']].append(u)
    comparisons=[]
    for p,snap in snapshots:
        before=set();after=set()
        for (owner,slot),group in by_slot.items():
            if owner!=p.owner_id:continue
            past=[u for u in group if u['source_session_rank']<p.cutoff_rank]
            if past:
                m=max(u['source_session_rank'] for u in past)
                before.update(u['memory_id'] for u in past if u['source_session_rank']==m)
            m=max(u['source_session_rank'] for u in group)
            after.update(u['memory_id'] for u in group if u['source_session_rank']==m and m<p.cutoff_rank)
        comparisons.append(dict(owner_id=p.owner_id,cutoff_rank=p.cutoff_rank,
            prefix_only_latest_diagnostic=sorted(before),full_history_latest_then_filter=sorted(after),
            lost_earlier_members=sorted(before-after),
            warning='Both sets are LEGACY_DIAGNOSTIC, not approved facts; new writer consumes RAW only'))
    return dict(quarantined_count=len(cases),all_replacements_later=True,cases=cases,cutoff_comparisons=comparisons,
        conclusion='Full-history pool selection depends on future ranks; not evidence that future text reached G')


def eligibility(record, prefix, bank):
    reason=bank.reason(record,prefix)
    status='BLOCKED' if reason or record.head=='MP' else 'ELIGIBLE' if record.head=='MS' else 'LEGACY_DIAGNOSTIC'
    return dict(record_id=record.record_id,head=record.head,status=status,
        reason=reason or ('full_history_latest_membership_not_asof_writer' if record.head=='MP' else
            'immutable_complete_RAW' if record.head=='MS' else 'legacy_semantics_or_method_applicability_unreviewed'),
        as_of_source_eligible=reason is None,ready_time_basis='logical_r_plus_1' if record.head!='RS' else 'preinstalled_external_version',
        source_rank=record.source_rank,reported_at=record.reported_at,ready_at=record.ready_at,
        source_span_sha256=object_sha256(record.source_refs),source_span_count=len(record.source_refs),
        source_span_locator='bank-v0/records.jsonl#'+record.record_id,
        subject='unknown',event_stage=record.stage,current_validity='unknown',
        worth_reading=None,relevant_but_need_not_mention=None,semantic_review='pending',
        legacy_identity_quarantine=record.head=='MP',research_quality_eligible=False)


def evidence(pins, registry, bank, out, ledger):
    samples=pins.lines(PR12,V3+'relevance_review_20261118/REVIEW_SAMPLES.jsonl')
    catalog=pins.lines(PR12,V3+'relevance_review_20261118/CANDIDATE_RECORDS.jsonl')
    requests=pins.lines(PR12,V3+'G0e_binding_20261118/CPU_REQUESTS_ONLY.jsonl')
    bindings=pins.lines(PR12,V3+'G0e_binding_20261118/KEY_BINDINGS.jsonl')
    proposal=pins.json(PR13,V3+'resource_architecture_review_20261118/cpu/PROPOSED_JOBS.json')
    assert len(samples)==83 and len(catalog)==1876 and len(requests)==len(bindings)==120 and len(proposal['jobs'])==54
    write_json_once(out/'FIXED_54_PROPOSAL_COPY.json',proposal)
    write_json_once(out/'FIXED_83_SELECTION.json',[
        dict(sample_id=r['sample_id'],selected_record_id=r['selected_record_id']) for r in samples])
    for c in catalog:assert decode_contract(K.ResourceRecord,canonical_json(c))==bank.by_id[c['record_id']]
    sample_rows=[];candidate_rows=[]
    for row in samples:
        p=row['prefix'];prefix=registry.prefix(p['owner_id'],p['session_id'],p['cut_turn'])
        ranked=search(bank,row['head'],prefix)
        assert [(r.record_id,r.score) for r in ranked.ranked]==[(r['record_id'],r['score']) for r in row['legal_candidates']]
        details=[eligibility(bank.by_id[r.record_id],prefix,bank) for r in ranked.ranked]
        candidate_rows.extend(dict(d,sample_id=row['sample_id'],rank=i+1) for i,d in enumerate(details))
        top=details[0] if details else dict(status='BLOCKED',reason='no_legal_candidate',record_id=None)
        sample_rows.append(dict(sample_id=row['sample_id'],prefix_id=prefix.prefix_id,owner_id=prefix.owner_id,
            cutoff_rank=prefix.cutoff_rank,head=row['head'],candidate_count=len(details),selected=top,
            old_selection_unchanged=True,status=top['status']))
    # All 3188 old rows retained; span verification is performed by the bank loader.
    inventory=[dict(record_id=r.record_id,head=r.head,source_span_sha256=object_sha256(r.source_refs),
        spans_verified=len(r.source_refs),subject='unknown',event_stage=r.stage,
        current_validity='unknown',worth_reading=None,relevant_but_need_not_mention=None,
        status='BLOCKED' if r.head=='MP' else 'ELIGIBLE' if r.head=='MS' else 'LEGACY_DIAGNOSTIC',
        cutoff_eligibility='requires_prefix; see per-sample/per-job matrix',
        legacy_identity_quarantine=r.head=='MP') for r in bank.records]
    coverage=pins.lines(BASE,V3+'B1/coverage_sample_v1.jsonl')
    prefixes={p['prefix_id']:registry.prefix(p['owner_id'],p['session_id'],p['cut_turn']) for p in coverage}
    by_binding={b['request_sha256']:b for b in bindings};by_request={r['request_id']:r for r in requests}
    job_rows=[];new_requests=[];projection=[]
    renderer_source=pins.text(PR12,'project/src/metacom_pm/rl1v3/render/request_packet.py')
    notes=next(ast.literal_eval(n.value) for n in ast.parse(renderer_source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NOTES' for t in n.targets))
    import html
    for row in requests:
        b=by_binding[row['request_id']];p=prefixes[row['prefix_id']]
        key=decode_contract(K.TerminalKey,canonical_json(b['new_key']))
        trace=decode_contract(K.ExecutionTrace,canonical_json(b['new_trace']));trace.verify_key(key)
        assert key.sha256==row['terminal_key_sha256']==b['new_key_sha256']
        assert len(row['input_ids'])==row['input_tokens']==b['token_ledger']['input_tokens']
        expected=[row['messages'][0]]
        if trace.readings:
            blocks=['<resource head="'+v.head+'">'+html.escape(v.reading_text)+'</resource>' for v in sorted(trace.readings,key=lambda v:K.HEAD_ORDER.index(v.head))]
            expected.append(dict(role='user',content=notes+'<Notes>\n'+'\n'.join(blocks)+'\n</Notes>'))
        expected.extend(dict(role='user' if t.role=='seeker' else 'assistant',content=t.text) for t in p.turns)
        assert expected==row['messages']
        projection.append(dict(request_id=row['request_id'],terminal_key_sha256=key.sha256,
            prefix_id=p.prefix_id,input_ids_sha256=object_sha256(row['input_ids']),
            messages_sha256=object_sha256(row['messages']),stored_native_token_length_verified=True,
            generated=False,retokenized=False))
    for job in proposal['jobs']:
        old=by_request[job['existing_request_id']];b=by_binding[old['request_id']];p=prefixes[job['prefix_id']]
        key=decode_contract(K.TerminalKey,canonical_json(b['new_key']))
        trace=decode_contract(K.ExecutionTrace,canonical_json(b['new_trace']))
        # Snapshot of all legally completed RAW for this exact existing prefix;
        # materializer is independent of full-history legacy MP membership.
        local=A.Ledger()
        for e in sorted(registry.visible(p),key=lambda e:e.source.chronological_rank):
            local.append(A.record_from_source(e,kind='MS_RAW'),registry)
        snapshot=A.materialize(registry,p,local)
        details=[eligibility(bank.by_id[r],p,bank) for g in key.acquired for r in g]
        statuses=[d['status'] for d in details]
        status='BLOCKED' if 'BLOCKED' in statuses else 'LEGACY_DIAGNOSTIC' if 'LEGACY_DIAGNOSTIC' in statuses else 'ELIGIBLE'
        new=R.prepare(p,trace.readings,legacy_key=key,system=old['messages'][0]['content'],snapshot=snapshot,bank=bank)
        new_requests.append(new)
        job_rows.append(dict(plan_job_id=job['plan_job_id'],old_request_id=old['request_id'],subset=job['subset'],
            prefix_id=p.prefix_id,owner_id=p.owner_id,cutoff_rank=p.cutoff_rank,status=status,resources=details,
            new_request_identity=new['new_request_identity'],snapshot_sha=snapshot['snapshot_sha'],
            source_frontier_sha256=snapshot['source_frontier_sha256'],same_evidence=True,
            quality=None,result=None,worth_reading=None,relevant_but_need_not_mention=None,
            status_scope='mechanical_P2_input_only; semantic/native-token/quality qualification pending'))
        write_json_once(out/'request_frontiers'/(p.prefix_id+'.json'),snapshot['source_frontier'])
    for name,rows in [('BANK_INVENTORY',inventory),('SAMPLE_83_ELIGIBILITY',sample_rows),
        ('ALL_SAMPLE_CANDIDATE_ELIGIBILITY',candidate_rows),('INPUT_54_ELIGIBILITY',job_rows),
        ('TYPED_REQUEST_PROPOSALS',new_requests),('OLD_120_REQUEST_PRESERVATION',projection)]:
        write_jsonl_once(out/(name+'.jsonl'),rows)
    return dict(bank_rows=len(inventory),catalog_rows=len(catalog),sample_83=dict(Counter(r['status'] for r in sample_rows)),
        input_54=dict(Counter(r['status'] for r in job_rows)),candidate_contexts=len(candidate_rows),old_requests=len(projection)),prefixes


def rs_package(registry,bank,prefixes,out):
    url='https://library.samhsa.gov/sites/default/files/tip-35-pep19-02-01-003.pdf'
    common=dict(source_url=url,license_scope='SAMHSA public-domain notice except copyrighted material; item review pending',
        external_version='tip35-2019-candidate-20261118',available_from='2026-11-18',
        limits='Source domain is counseling. Everyday support transfer and incremental benefit are untested.')
    methods=[MethodCandidate(name='Invite elaboration',source_section='Chapter 3 / Asking Open Questions',
        source_quote='Use open questions to invite clients to tell their story',
        when_to_use='The person wants to explore an unclear concern.',when_not_to_use='They decline further questions or need a direct factual answer.',
        action_options=('Invite elaboration without suggesting the desired answer.',),
        common_misuse='Interrogating or pressuring disclosure.',**common),
        MethodCandidate(name='Tentative reflection',source_section='Chapter 3 / Reflective Listening',
        source_quote='Be open to being wrong.',when_to_use='Check your understanding of what the person expressed.',
        when_not_to_use='A reflection would invent motives or override a correction.',
        action_options=('Offer a tentative paraphrase and allow correction.',),
        common_misuse='Presenting a guessed feeling as established fact.',**common)]
    p=next(iter(prefixes.values()))
    r=sorted(bank.candidates('RS',p),key=lambda r:r.record_id)[0]
    case=CaseCandidate(r.record_id,r.family_id,r.reading_text,object_sha256(r.source_refs),r.license_scope,r.source_split)
    write_json_once(out/'RS_METHOD_CANDIDATES.json',dict(methods=methods,source_access='official indexed text verified; full PDF fetch returned 403; no redistribution of PDF',
        source_license_evidence='https://www.ncbi.nlm.nih.gov/books/NBK571068/table/ch3.t4/',
        runtime_approved=False,case_method_relation='unverified; candidate CASE chosen by ID, not an asserted demonstration'))
    write_json_once(out/'RS_CASE_CANDIDATE.json',case)
    write_json_once(out/'RS_FOUR_INPUTS.json',fair_rs_inputs(p,methods,case,external_version=common['external_version'],experiment_date='2026-11-18'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();root=args.root;out=args.out
    if out.exists():raise FileExistsError('new output directory required; preserve all prior runs')
    pins=Pinned(root);cfg=json.loads((root/'project/configs/rl1v3/bank_v0_port.json').read_text())
    pins.local('project/configs/rl1v3/bank_v0_port.json')
    for folder,names in [(cfg['registry_dir'],['registry.json','sources.jsonl']),
        (cfg['bank_dir'],['bank.json','index.json','records.jsonl','migration.jsonl'])]:
        for name in names:pins.local(folder+'/'+name)
    for path in ['project/src/metacom_pm/rl1v3/contracts.py',V3+'A0/repair_1/OFF_REQUESTS.jsonl',
                 'project/docs/plans/pm_rl1_v3_20261116/EXECUTION_STATE.json']:
        pins.local(path)
    pins.json(PR12,V3+'G0e_binding_20261118/MANIFEST.json')
    registry=S.load(root/cfg['registry_dir']);bank=bank_v0.load(root/cfg['bank_dir'],registry,expected_version=cfg['expected_bank'])
    assert registry.version==cfg['expected_source'] and bank.index_version==cfg['expected_index']
    ledger,snapshots=replay(registry,out)
    units=pins.lines(BASE,'project/data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl')
    risk=legacy_risk(units,bank,registry,snapshots);write_json_once(out/'LEGACY_LATEST_RISK.json',risk)
    summary,prefixes=evidence(pins,registry,bank,out,ledger);rs_package(registry,bank,prefixes,out)
    summary.update(owners=list(OWNERS),completed_sessions=68,real_cutoffs=len(snapshots),ledger_rows=len(ledger.rows),
        batch_stream_future_extension_equal=True,restart_and_idempotency=True,legacy_quarantined_mp=len(risk['cases']),
        semantic_human_approved=0,model_extraction='pending',gpu_calls=0,model_calls=0,judge_calls=0,paid_calls=0,
        native_retokenization=False,resource_incremental_quality=None,writer_identity=A.writer_identity(),renderer_identity=R.renderer_identity())
    write_json_once(out/'SUMMARY.json',summary)
    from metacom_pm.rl1v3.compile import resource_candidates
    code=[Path(A.__file__),Path(R.__file__),Path(resource_candidates.__file__),Path(__file__)]
    manifest=dict(protocol=A.PROTOCOL,base_sha=BASE,inputs=pins.inputs,
        code={str(p.relative_to(root)):file_sha256(p) for p in code},
        outputs={str(p.relative_to(out)):file_sha256(p) for p in sorted(out.rglob('*')) if p.is_file()},
        evidence_level='engineering_only',human_review_pending=True)
    write_json_once(out/'MANIFEST.json',dict(manifest,manifest_sha256=object_sha256(manifest)))
    print(canonical_json(summary))


if __name__=='__main__':main()

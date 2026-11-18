#!/usr/bin/env python3
"""Exchange verifier: Python standard library only, no WS-A/B package imports.

Useful to reproduce independently; authorship is WS-A, so execution of this
script is NOT a WS-B independent-review receipt or human semantic approval.
"""
import argparse
import hashlib
import json
import html
from pathlib import Path


def unique(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise ValueError('duplicate key: '+k)
        d[k]=v
    return d


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def lines(path):return [json.loads(l,object_pairs_hook=unique) for l in Path(path).read_text().splitlines()]
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()
def file_hash(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check(root,sources):
    registry=[r['source'] for r in lines(sources)]
    bysource={(s['owner_id'],s['session_id']):s for s in registry}
    bindings=lines(root/'BINDINGS.jsonl');manifest=read(root/'MANIFEST.json')
    assert digest({k:v for k,v in manifest.items() if k!='manifest_sha256'})==manifest['manifest_sha256']
    for p,h in manifest['outputs'].items():assert file_hash(root/p)==h,p
    assert len(bindings)==8 and {b['owner_id'] for b in bindings}=={'p2','p3','p5','p8','p11','p13','p15','p16'}
    seen,results=set(),[]
    fields=('owner_id','session_id','dataset','chronological_rank','date','family_id','ancestor_family_ids','license','complete','transcript_sha256')
    context_fields=('schema_version','prefix_id','prefix_protocol','identity_scope','owner_id','session_id','cut_turn','turns','cutoff_rank','timestamp','dataset','family_id','ancestor_family_ids')
    for b in bindings:
        assert b['prefix_id'] not in seen;seen.add(b['prefix_id'])
        p=read(root/b['prefix_path']);current=bysource[p['owner_id'],p['session_id']]
        assert p['turns']==current['turns'][:p['cut_turn']+1]
        assert current['turns'][p['cut_turn']+1]['role']=='supporter'
        assert p['turns'][-1]['role']=='seeker'
        assert p['cutoff_rank']==current['chronological_rank']==b['cutoff_rank']
        assert p['owner_id']==b['owner_id']
        assert digest({k:p[k] for k in context_fields})==b['prefix_context_sha256']
        legal=sorted((s for s in registry if s['owner_id']==p['owner_id'] and s['dataset']==p['dataset'] and s['complete'] and s['chronological_rank']<p['cutoff_rank'] and (not s['date'] or not p['timestamp'] or s['date']<=p['timestamp'])),key=lambda s:s['chronological_rank'])
        assert len(legal)==b['source_count']
        a=read(root/b['snapshot_past']);z=read(root/b['snapshot_future'])
        assert a==z and b['horizon_future_max_rank']>=p['cutoff_rank']>b['horizon_past_max_rank']
        assert b['future_sessions_appended']>0
        for snap in (a,z):
            assert digest({k:v for k,v in snap.items() if k!='snapshot_sha'})==snap['snapshot_sha']==b['snapshot_sha']
            assert digest(snap['source_frontier'])==snap['source_frontier_sha256']==b['source_frontier_sha256']
            assert snap['source_frontier']==read(root/b['frontier_path'])
            assert snap['as_of']['prefix_context_sha256']==b['prefix_context_sha256']
            front=snap['source_frontier']['sources'];assert len(front)==len(legal)
            for f,s in zip(front,legal):
                assert {k:f[k] for k in fields}=={k:s[k] for k in fields}
                assert f['source_sha256']==digest({k:s[k] for k in fields})
                assert f['known_at']['session_rank']==f['ready_at']['session_rank']==s['chronological_rank']+1
            rows={r['record_id']:r for r in snap['ledger_prefix']}
            assert len(rows)==len(snap['ledger_prefix'])==len(snap['views'])
            raw_ids=set()
            for v in snap['views']:
                r=v['record'];assert rows[r['record_id']]==r
                assert r['record_id']=='asof-record:'+digest(dict(r,record_id='pending'))
                assert r['owner_id']==p['owner_id'] and r['session_id'] in {s['session_id'] for s in legal}
                s=bysource[r['owner_id'],r['session_id']]
                assert r['source_sha256']==digest({k:s[k] for k in fields})
                assert r['reported_at']['session_rank']==s['chronological_rank']<r['known_at']['session_rank']<=r['ready_at']['session_rank']<=p['cutoff_rank']
                for ref in r['source_refs']:
                    assert ref['owner_id']==r['owner_id'] and ref['session_id']==r['session_id']
                    t=s['turns'][ref['turn_index']]
                    assert ref['speaker']==t['role'] and ref['source_rank']==s['chronological_rank']
                    assert t['text'][ref['start_char']:ref['end_char']]==ref['exact_quote']
                if r['kind']=='MS_RAW':
                    assert v['disposition']=='raw_available'
                    assert r['text']=='\n'.join(t['role']+': '+t['text'] for t in s['turns'])
                    assert {(r0['turn_index'],r0['exact_quote']) for r0 in r['source_refs']}=={(i,t['text']) for i,t in enumerate(s['turns']) if t['text']}
                    raw_ids.add(r['record_id'])
                else:
                    assert v['disposition']=='quarantine' and r['review_status']=='pending'
            assert raw_ids==set(b['raw_record_ids']) and len(raw_ids)==len(legal)
        past_rows=lines(root/b['ledger_past']);future_rows=lines(root/b['ledger_future'])
        future_byid={r['record_id']:r for r in future_rows}
        assert all(future_byid[r['record_id']]==r for r in past_rows)
        readout=read(root/b['reading_path']);assert readout['MP']['status']==readout['ME']['status']=='unavailable'
        view=readout['MS'];assert digest(view)==b['reading_sha256']
        r=next(r for r in a['ledger_prefix'] if r['record_id']==b['selected_raw_id'])
        expected='Historical complete conversation; reported '+(r['reported_at']['date'] or 'date unknown')+'. Statements are reports by the labelled speakers, not verified world facts.\n'+r['text']
        assert view['reading_text']==expected and view['head']=='MS' and view['view']=='raw'
        results.append(dict(owner_id=b['owner_id'],prefix_id=p['prefix_id'],snapshot_sha=a['snapshot_sha'],passed=True))
    proposals=lines(root/'E1_PROPOSALS.jsonl')
    baseline=read(root/'GENERATOR_BASELINE.json')
    semantic={r['record']['record_id']:r['record'] for r in lines(root/'SEMANTIC_CANDIDATES.jsonl')}
    methods={r['method_id']:r for r in read(root/'RS_METHODS.json')}
    cases={r['case_id']:r for r in lines(root/'RS_CASES.jsonl')}
    def method_text(m):
        return (m['name']+'\nConsider: '+m['when_to_use']+'\nAvoid: '+m['when_not_to_use']+
            '\nOptions: '+' '.join(m['action_options'])+'\nMisuse: '+m['common_misuse']+'\nLimits: '+m['limits'])
    assert len(proposals)==72 and len({r['request_id'] for r in proposals})==72
    for b in bindings:
        rr={r['arm']:r for r in proposals if r['prefix_id']==b['prefix_id']}
        p=read(root/b['prefix_path'])
        assert len(rr)==9
        assert len({(r['g_id'],r['decode_id'],r['step2_id'],r['baseline_sha256'],r['renderer_id']) for r in rr.values()})==1
        assert rr['OFF']['preview_messages']==rr['RS-R0']['preview_messages']
        assert rr['RS-F-resident']['preview_messages']!=rr['RS-R0']['preview_messages']
        assert rr['MS-SUM-direct']['preview_messages'] is None and rr['MS-SUM-direct']['input_ids'] is None
        for r in rr.values():
            identity_keys=('protocol','arm','query_id','selection','prefix_context_sha256',
                'snapshot_sha','source_frontier_sha256','writer_identity','renderer_id','g_id',
                'decode_id','step2_id','candidate_ids','review_records_sha256','messages_sha256','baseline_sha256')
            assert r['request_id']=='E1-proposal:'+digest({k:r[k] for k in identity_keys})
            assert r['decode']==baseline['spec']['decode']
            assert r['g_id']==baseline['identity']['g_id'] and r['decode_id']==baseline['identity']['decode_id']
            assert r['snapshot_sha']==b['snapshot_sha'] and r['source_frontier_sha256']==b['source_frontier_sha256']
            assert r['query_id']=='direct_provision' and not r['runtime_callable'] and not r['research_qualified']
            assert r['reward'] is None and r['terminal_result'] is None and not r['legacy_result_reuse']
            assert digest(r['preview_messages'])==r['messages_sha256']
            if r['preview_messages'] is None:continue
            m=r['preview_messages'];assert digest(m[0]['content'])==r['baseline_sha256']
            assert m[-len(p['turns']):]==[dict(role='user' if t['role']=='seeker' else 'assistant',content=t['text']) for t in p['turns']]
            assert len(r['input_ids'])==r['input_tokens'] and digest(r['input_ids'])==r['input_ids_sha256']
            assert r['native_capacity']==('fits' if r['input_tokens']+320<=16384 else 'over_capacity')
            assert r['native_request_id']=='E1-native-preview:'+digest(dict(proposal_id=r['request_id'],
                input_ids_sha256=r['input_ids_sha256'],tokenizer_identity=manifest['tokenizer_identity'],
                tokenizer_runtime=r['tokenizer_runtime']))
            arm=r['arm'];ids=r['candidate_ids']
            if arm in ('OFF','RS-R0'):
                assert len(m)==1+len(p['turns'])
            else:
                assert len(m)==2+len(p['turns'])
                block=m[1]['content'];opening='<ExternalEvidence type="'+arm+'">\n'
                body=html.unescape(block.split(opening,1)[1].removesuffix('\n</ExternalEvidence>'))
                if arm in ('MP-direct','ME-direct'):
                    source=semantic[ids[0]]
                    expected=('Quoted historical report. Speaker: '+source['source_refs'][0]['speaker']+
                        '; reported: '+(source['reported_at']['date'] or 'date unknown')+'.\n'
                        'Subject, relationship, slot, stage and current validity: unreviewed/unknown. '
                        'Do not attribute third-person experiences to the user. A supporter suggestion '
                        'does not establish user intention, execution or outcome.\n'+source['text'])
                    assert body==expected and source['owner_id']==b['owner_id']
                elif arm=='MS-RAW-direct':assert body==read(root/b['reading_path'])['MS']['reading_text']
                elif arm=='RS-F-resident':assert body=='\n'.join(method_text(methods[i]) for i in ids)
                elif arm=='RS-METHOD':assert body==method_text(methods[ids[0]])
                elif arm=='RS-METHOD+CASE':
                    case=cases[ids[1]]
                    assert case['source_split']=='train'
                    assert not ({case['family_id'],*case['ancestor_family_ids']} & set(p['ancestor_family_ids']))
                    for ref in case['source_refs']:
                        source=bysource[ref['owner_id'],ref['session_id']];t=source['turns'][ref['turn_index']]
                        assert t['text'][ref['start_char']:ref['end_char']]==ref['exact_quote']
                    assert body==method_text(methods[ids[0]])+'\nExternal conversation about other people; not user history.\n'+case['text']
                else:raise AssertionError('unknown arm')
            visible=json.dumps(m,ensure_ascii=False)
            for private in (r['request_id'],r['prefix_id'],r['snapshot_sha'],r['source_frontier_sha256'],*r['candidate_ids']):
                assert private not in visible
            for forbidden in ('NeedCard','Checklist','JudgeIdentity','reward','oracle'):
                # Metadata is never concatenated into evidence blocks.
                assert not any(forbidden in x['content'] for x in m[:-len(p['turns'])])
    return dict(protocol='standalone-e1-export-check-1',passed=True,dual_horizon_pairs=8,
        snapshot_hashes=16,proposals=72,rows=results,semantic_approval=False,
        independent_B_review=False,authors='WS-A; standard-library reference verifier')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--bundle',type=Path,required=True)
    ap.add_argument('--sources',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();result=check(args.bundle,args.sources)
    with args.out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(result,ensure_ascii=False))

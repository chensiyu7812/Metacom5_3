#!/usr/bin/env python3
"""CPU-only, pinned RAW export. Never imports a model, reward, judge or trainer."""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import json
import re
import subprocess
import importlib.metadata

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.compile import asof as A, qualification as Q
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.io import canonical_json, file_sha256, object_sha256, sha256_bytes, write_json_once, write_jsonl_once

BASE='b63635f3621f3a5d252099efcd58ae2d1958dce2'
PR12='8ba20d21da4bdcbb552946241563bd41dbe46c6c'
PR16='a9cf0cca0fecd044a5a4e2a4066355a9a8123dc5'
V3='project/outputs/pm_rl1/v3/'
OWNERS={'p2','p3','p5','p8','p11','p13','p15','p16'}


class Pins:
    def __init__(self,root): self.root,self.inputs=root,[]
    def read(self,commit,path,lines=False):
        data=subprocess.check_output(['git','-C',str(self.root),'show',commit+':'+path])
        self.inputs.append(dict(commit=commit,path=path,sha256=sha256_bytes(data)))
        return [json.loads(l) for l in data.splitlines()] if lines else json.loads(data)


class NativeCounter:
    def __init__(self,path,cfg):
        # Only tokenizer/config/template files. No weight file is opened.
        for name in ('tokenizer.json','tokenizer_config.json','chat_template.jinja','config.json'):
            if file_sha256(path/name)!=cfg['common']['model']['files'][name]['sha256']:
                raise ValueError('pinned tokenizer/config changed: '+name)
        from transformers import AutoTokenizer
        self.tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        self.identity=cfg['common']['tokenizer_identity']
    def count(self,text):return len(self.tokenizer.encode(text,add_special_tokens=False))
    def ids(self,messages):
        from collections.abc import Mapping
        value=self.tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False)
        if isinstance(value,Mapping):value=value['input_ids']
        if value and isinstance(value[0],list):
            if len(value)!=1:raise ValueError('unexpected tokenizer batch')
            value=value[0]
        return list(value)


def methods():
    common=dict(source_url='https://library.samhsa.gov/sites/default/files/tip-35-pep19-02-01-003.pdf',
        source_title='SAMHSA TIP 35 (2019), Chapter 3',
        source_access='official indexed content checked 2026-11-18; NCBI direct access challenge',
        license='public-domain notice with third-party exceptions; item-level exception review pending',
        license_review='pending',applicability_review='pending',candidate_status='pending',
        external_version='rs-method-review-20261118-v2',available_from='2026-11-18',
        limits='Communication candidate only; no clinical intervention or demonstrated support benefit claimed.',
        text_origin='new concise paraphrase for review; not an ESConv strategy label')
    rows=[dict(common,name='Invite elaboration',source_section='Asking Open Questions',
        when_to_use='The person wishes to explore an unclear concern.',
        when_not_to_use='They decline questions, need a direct answer, or have already explained enough.',
        action_options=['Offer one optional, non-leading invitation to elaborate.'],
        common_misuse='Pressure to disclose; repeated questions; postponing acknowledgement.'),
        dict(common,name='Tentative reflection',source_section='Reflective Listening',
        when_to_use='Check understanding of what the person has expressed.',
        when_not_to_use='It would invent motives or override their correction.',
        action_options=['Paraphrase tentatively, leaving room for correction.'],
        common_misuse='Presenting guessed feelings as established truth.')]
    return [dict(r,method_id='method-review:'+object_sha256(r)) for r in rows]


def method_text(m):
    return (m['name']+'\nConsider: '+m['when_to_use']+'\nAvoid: '+m['when_not_to_use']+
        '\nOptions: '+' '.join(m['action_options'])+'\nMisuse: '+m['common_misuse']+
        '\nLimits: '+m['limits'])


def semantic_preview(candidate):
    if candidate is None:return None
    r=candidate['record']
    return ('Quoted historical report. Speaker: '+r.source_refs[0].speaker+
        '; reported: '+(r.reported_at.date or 'date unknown')+'.\n'
        'Subject, relationship, slot, stage and current validity: unreviewed/unknown. '
        'Do not attribute third-person experiences to the user. A supporter suggestion '
        'does not establish user intention, execution or outcome.\n'+r.text)


def audit_coverage(registry):
    """Separate full-corpus coverage audit. Never feeds the writer or E1 choice."""
    patterns={'explicit_correction':r'\b(?:I was wrong|I meant|that is not true|that[’\']s not true|correction|not anymore|no longer)\b',
        'negation_or_refusal':r'\b(?:not|never|don[’\']t|didn[’\']t|won[’\']t|refused)\b',
        'attempt_and_adverse_followup':r'\btried\b.*\b(?:but|fail|not|didn[’\']t)\b',
        'stage_update':r'\b(?:started|finished|completed|decided|applied|attended)\b'}
    hits=[];sessions=0
    for e in registry.entries:
        if e.availability_scope!='personal_history':continue
        sessions+=1
        for i,t in enumerate(e.source.turns):
            if t.role!='seeker':continue
            for cat,pat in patterns.items():
                if re.search(pat,t.text,re.I):
                    hits.append(dict(category=cat,source_ref=S.span(e.source,i),
                        label='lexical_review_candidate_not_verified_chain',known_at=e.ready_at))
    # Fixed directly inspected report sequence, outside E1 and not installed as
    # invalidation. All words/indices are checked against RAW at export time.
    specs=[('p1','p1_conv_9',1,'suggestion_and_start_in_same_report'),
           ('p1','p1_conv_9',3,'reported_response'),
           ('p1','p1_conv_12',10,'later_report_partial_help'),
           ('p2','p2_conv_5',12,'reported_attempt_with_adverse_outcome')]
    sequence=[]
    for owner,sid,i,label in specs:
        e=registry.entry(owner,sid)
        sequence.append(dict(label=label,source_ref=S.span(e.source,i),
            known_at=e.ready_at,semantic_review='pending_human_review',
            relation_installed=False,event_time=None,valid_from=None,valid_to=None))
    return dict(sessions_scanned=sessions,patterns=patterns,
        counts=dict(Counter(r['category'] for r in hits)),hits=hits,
        inspected_report_sequence=sequence,
        verified_human_correction_chains=0,verified_human_negation_links=0,
        verified_human_stage_chains=0,
        conclusion='RAW contains negation and stage/failure reports; lexical hits are not verified linked corrections. No evidence-grounded backdated invalidation chain is approved. Synthetic fixture is mechanism-only.',
        scope='401 source sessions; separate coverage audit, including future; never used for E1 candidate selection')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3]);args=ap.parse_args()
    root,out=args.root,args.out
    if out.exists():raise FileExistsError('new output directory required')
    pins=Pins(root)
    cfg=pins.read(BASE,'project/configs/rl1v3/bank_v0_port.json')
    for name in ('registry.json','sources.jsonl'):
        path=cfg['registry_dir']+'/'+name
        pinned=pins.read(BASE,path,lines=name.endswith('jsonl'))
        actual=([json.loads(l) for l in (root/path).read_text().splitlines()] if name.endswith('jsonl') else json.loads((root/path).read_text()))
        if actual!=pinned:raise ValueError('registry changed')
    registry=S.load(root/cfg['registry_dir'])
    selection=pins.read(PR16,V3+'B6e_plan/v3/SELECTION.json')
    coverage=pins.read(BASE,V3+'B1/coverage_sample_v1.jsonl',lines=True)
    byid={p['prefix_id']:p for p in coverage}
    prefixes=[registry.prefix(byid[i]['owner_id'],byid[i]['session_id'],byid[i]['cut_turn']) for i in selection['selected_ids']]
    assert len(prefixes)==8 and {p.owner_id for p in prefixes}==OWNERS
    gc=pins.read(PR12,'project/configs/rl1v3/G0e.json')
    spec=dict(gc['common'],runtime=gc['runtimes']['hf'])
    binding=dict(g_id='G0e:'+object_sha256({k:spec[k] for k in ('protocol','model','runtime','output_policy')}),
        decode_id='decode:'+object_sha256(spec['decode']),step2_id=spec['step2_id'],decode=spec['decode'])
    counter=NativeCounter(Path(gc['model_path']),gc)
    ms=methods();write_json_once(out/'RS_METHODS.json',ms)
    write_json_once(out/'PINNED_B_SELECTION.json',selection)
    write_json_once(out/'GENERATOR_BASELINE.json',dict(spec=spec,identity=binding,tokenizer_only=True,
        weight_hash_status='historical attestation preserved; no weight load/hash in this run'))
    bindings=[];reviews=[];proposals=[];cases=[];summaries=[];matrices=[]
    for p in prefixes:
        all_entries=[e for e in registry.entries if e.source.owner_id==p.owner_id and e.availability_scope=='personal_history']
        past_entries=list(registry.visible(p))
        past,pc=Q.compile_entries(registry,past_entries)
        full,fc=Q.compile_entries(registry,all_entries)
        a=A.materialize(registry,p,past,writer=Q.writer_identity())
        b=A.materialize(registry,p,full,writer=Q.writer_identity())
        assert canonical_json(a)==canonical_json(b)
        stem=p.owner_id+'-'+p.prefix_id[:12]
        write_json_once(out/'prefixes'/(stem+'.json'),p)
        write_json_once(out/'snapshots'/(stem+'-past.json'),a)
        write_json_once(out/'snapshots'/(stem+'-future.json'),b)
        write_json_once(out/'frontiers'/(stem+'.json'),a['source_frontier'])
        write_jsonl_once(out/'ledgers'/(stem+'-past.jsonl'),past.rows)
        write_jsonl_once(out/'ledgers'/(stem+'-future.jsonl'),full.rows)
        raws=[v['record'] for v in a['views'] if v['record'].kind=='MS_RAW']
        latest=max(raws,key=lambda r:r.reported_at.session_rank)
        view=Q.direct_raw(a,latest.record_id,counter)
        write_json_once(out/'readings'/(stem+'.json'),dict(MP=A.read(a,'MP',ordinal=1,token_counter=counter,context_remaining=16064),
            ME=A.read(a,'ME',ordinal=1,token_counter=counter,context_remaining=16064),MS=view))
        bind=dict(owner_id=p.owner_id,prefix_id=p.prefix_id,session_id=p.session_id,cut_turn=p.cut_turn,
            cutoff_rank=p.cutoff_rank,timestamp=p.timestamp,prefix_context_sha256=p.runtime_sha256,
            snapshot_sha=a['snapshot_sha'],source_frontier_sha256=a['source_frontier_sha256'],writer_identity=Q.writer_identity(),
            snapshot_past='snapshots/'+stem+'-past.json',snapshot_future='snapshots/'+stem+'-future.json',
            ledger_past='ledgers/'+stem+'-past.jsonl',ledger_future='ledgers/'+stem+'-future.jsonl',
            prefix_path='prefixes/'+stem+'.json',frontier_path='frontiers/'+stem+'.json',reading_path='readings/'+stem+'.json',
            horizon_past_max_rank=max(e.source.chronological_rank for e in past_entries),
            horizon_future_max_rank=max(e.source.chronological_rank for e in all_entries),
            future_sessions_appended=sum(e.source.chronological_rank>=p.cutoff_rank for e in all_entries),
            source_count=len(past_entries),raw_record_ids=[r.record_id for r in raws],
            selected_raw_id=latest.record_id,reading_sha256=object_sha256(view),
            same_snapshot_and_readings=True,legal_reading_scope='mechanical_time_owner_span_and_existing_reuse_scope',
            upstream_license='unresolved',semantic_approval_count=0,current_request_suitability=None,
            generator_semantic_use=None,research_qualified=False)
        bindings.append(bind);reviews.extend(dict(c,prefix_id=p.prefix_id) for c in pc)
        e=registry.entry(latest.owner_id,latest.session_id)
        first=next(i for i,t in enumerate(e.source.turns) if t.role=='seeker' and t.text)
        summary=dict(protocol=Q.PROTOCOL,owner_id=p.owner_id,prefix_id=p.prefix_id,
            parent_raw_id=latest.record_id,parent_transcript_sha256=e.source.transcript_sha256,
            source_ref=S.span(e.source,first),candidate_text=e.source.turns[first].text,
            status='unusable',reason='single verbatim proposition is not a complete session summary; coverage/subject/stage not approved',
            semantic_review='pending_human_review',sum_request_available=False,
            fallback_condition='MS-RAW-direct',fallback_request_is_SUM=False)
        summary['summary_candidate_id']='unusable-sum:'+object_sha256(summary);summaries.append(summary)
        # An external train CASE is selected by source-local hash, never similarity
        # or outcome. It remains pending method-link and applicability review.
        ext=sorted(registry.visible(p,rs=True),key=lambda e:A.source_sha(e.source))[0]
        case=dict(source_local_sha256=A.source_sha(ext.source),family_id=ext.source.family_id,
            ancestor_family_ids=ext.source.ancestor_family_ids,source_split=ext.source.source_split,
            license=ext.source.license,source_refs=[S.span(ext.source,i) for i,t in enumerate(ext.source.turns) if t.text],
            text='\n'.join(f'{t.role}: {t.text}' for t in ext.source.turns),
            subject='other_people_not_current_user_or_assistant',candidate_status='pending',
            method_link='unverified',applicability='pending',license_review='pending_research_scope_confirmation')
        case['case_id']='external-case-review:'+object_sha256(case)
        cases.append(dict(case,prefix_id=p.prefix_id))
        picked={h:next((c for c in pc if c['record'].kind==h),None) for h in ('MP','ME')}
        method=method_text(ms[0]);directory='\n'.join(method_text(m) for m in ms)
        arms=[('OFF','',[], 'input_prepared',[]),
            ('MP-direct',semantic_preview(picked['MP']),[picked['MP']['record'].record_id] if picked['MP'] else [],'review_preview_only',['semantic_subject_slot_validity_review','current_request_suitability','upstream_license']),
            ('ME-direct',semantic_preview(picked['ME']),[picked['ME']['record'].record_id] if picked['ME'] else [],'review_preview_only',['semantic_subject_stage_outcome_review','current_request_suitability','upstream_license']),
            ('MS-RAW-direct',view.reading_text,[latest.record_id],'mechanical_reading_prepared',['current_request_suitability','upstream_license']),
            ('MS-SUM-direct',None,[summary['summary_candidate_id']],'unavailable',['no_qualified_summary']),
            ('RS-R0','',[], 'input_prepared',[]),
            ('RS-F-resident',directory,[m['method_id'] for m in ms],'review_preview_only',['method_license_and_applicability']),
            ('RS-METHOD',method,[ms[0]['method_id']],'review_preview_only',['method_license_and_applicability']),
            ('RS-METHOD+CASE',method+'\nExternal conversation about other people; not user history.\n'+case['text'],[ms[0]['method_id'],case['case_id']],'review_preview_only',['method_license_and_applicability','case_method_link_and_license'])]
        for arm,text,ids,status,blocked in arms:
            if text is None and arm in ('MP-direct','ME-direct'):
                status='unavailable';blocked=['no_candidate_under_fixed_rule',*blocked]
            row=Q.proposal(p,a,arm=arm,text=text,candidate_ids=ids,system=spec['system_prompt'],binding=binding,
                material_status=status,blockers=blocked,tokenizer_identity=counter.identity,
                review_records_sha256=object_sha256(dict(semantic=pc,summary=summary,methods=ms,case=case)))
            if row['preview_messages'] is not None:
                ids_native=counter.ids(row['preview_messages'])
                row.update(input_ids=ids_native,input_ids_sha256=object_sha256(ids_native),
                    input_tokens=len(ids_native),output_reserve=320,runtime_context=16384,
                    native_capacity='fits' if len(ids_native)+320<=16384 else 'over_capacity',
                    input_origin='fresh_native_tokenization_of_new_preview; no legacy token reuse')
                row['tokenizer_runtime']={n:importlib.metadata.version(n) for n in ('transformers','tokenizers')}
                row['native_request_id']='E1-native-preview:'+object_sha256(dict(
                    proposal_id=row['request_id'],input_ids_sha256=row['input_ids_sha256'],
                    tokenizer_identity=counter.identity,tokenizer_runtime=row['tokenizer_runtime']))
            else:
                row['native_request_id']=None
            row['qualification_axes']=dict(source_time_owner_span='pass_for_present_material',
                source_permission='pending_upstream_license_or_item_review' if arm not in ('OFF','RS-R0') else 'no_extra_source',
                writer_asof='pass_logical_replay_not_historical_deployment',
                semantic='not_applicable' if arm in ('OFF','RS-R0') else 'pending_or_unusable',
                current_request_suitability=None,generator_correct_use=None)
            proposals.append(row)
            matrices.append({k:row.get(k) for k in ('owner_id','prefix_id','arm','request_id','material_status','blockers','input_tokens','native_capacity','runtime_callable','research_qualified')})
    write_jsonl_once(out/'BINDINGS.jsonl',bindings)
    write_jsonl_once(out/'SEMANTIC_CANDIDATES.jsonl',reviews)
    write_jsonl_once(out/'MS_SUM_CANDIDATES.jsonl',summaries)
    write_jsonl_once(out/'RS_CASES.jsonl',cases)
    write_jsonl_once(out/'E1_PROPOSALS.jsonl',proposals)
    write_jsonl_once(out/'EXECUTABILITY_MATRIX.jsonl',matrices)
    write_json_once(out/'RAW_CHAIN_COVERAGE.json',audit_coverage(registry))
    # RAW background is condition independent; B owns any QH curation/identity.
    write_json_once(out/'QH_SOURCE_HANDOFF.json',dict(status='source_only_not_evaluator_or_frozen_background',
        rule='all legal completed RAW sessions from each binding, identical regardless of resource arm; B independently curates and freezes background before outcomes',
        rows=[dict(prefix_id=b['prefix_id'],snapshot_sha=b['snapshot_sha'],raw_record_ids=b['raw_record_ids']) for b in bindings],
        exposure_policy='prior viewing is not automatic exclusion; record selection/tuning/outcome use; no test-result-driven reselection',
        independent_confirmation='depends on claim, statistical precision and generalization; not a universal prerequisite'))
    summary=dict(protocol=Q.PROTOCOL,owners=len(bindings),dual_horizon_pairs=len(bindings),
        source_counts={b['owner_id']:b['source_count'] for b in bindings},
        semantic_candidates=len(reviews),semantic_approved=0,summary_approved=0,methods_approved=0,
        conditions=len(proposals),tokenized=sum(r['preview_messages'] is not None for r in proposals),
        capacity=dict(Counter(r['native_capacity'] for r in proposals)),
        gpu_calls=0,generator_calls=0,judge_calls=0,training_runs=0,paid_calls=0,
        resource_incremental_quality=None,research_qualified=False)
    write_json_once(out/'SUMMARY.json',summary)
    manifest=dict(protocol=Q.PROTOCOL,inputs=pins.inputs,
        code={str(p.relative_to(root)):file_sha256(p) for p in [Path(__file__),Path(Q.__file__),Path(A.__file__)]},
        outputs={str(p.relative_to(out)):file_sha256(p) for p in sorted(out.rglob('*')) if p.is_file()},
        evidence_level='engineering_only',tokenizer_identity=counter.identity)
    write_json_once(out/'MANIFEST.json',dict(manifest,manifest_sha256=object_sha256(manifest)))
    print(canonical_json(summary))


if __name__=='__main__':main()

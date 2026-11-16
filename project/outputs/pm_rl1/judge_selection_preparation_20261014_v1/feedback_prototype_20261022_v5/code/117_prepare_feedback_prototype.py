#!/usr/bin/env python3
"""Prepare/replay the limited-use feedback prototype, offline only.

No transport, credential read, account query, generation, optimizer or approval
creation. Uses opened train/dev metadata and specifically selected old outputs.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1 import feedback_prototype as f
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1 import task_reference as tr
BASE=PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
PREP=BASE/'task_reference_preparation_20261021_v1'
RESULT=BASE/'task_reference_results_20261021_v1'
OUT=BASE/'feedback_prototype_20261022_v5'


def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(root, name, value):
    p=root/name; p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as h:
        h.write(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    p.chmod(0o600)


def audit_mock_checks(item, paired):
    from copy import deepcopy
    u=paired.response_units(item['reply'])[0];sid,turn=next(iter(paired.evidence_turns(item['evidence']).items()))
    value=dict(check=dict(status='checked',claims=[],coverage='SYNTHETIC TEST ONLY',uncertainty_reasons=[]),
        findings=[dict(response_unit_id=u['id'],response_quote=u['text'],dimension='consequence',
            verdict='unresolved',readings=['SYNTHETIC TEST ONLY'],evidence=[dict(source_id=sid,quote=turn['text'])],
            criterion='SYNTHETIC',consequence='SYNTHETIC',reason='SYNTHETIC')],coverage_limitations='SYNTHETIC FIXTURE')
    def raw(text,finish='stop'):
        return dict(transport='deepseek',choices=[dict(message=dict(content=text,reasoning_content='NOT AN ANSWER'),finish_reason=finish)])
    text=json.dumps(value);cases={}
    for name,body,expected in [('bare',raw(text),True),('fence',raw('```json\n'+text+'\n```'),True),
        ('duplicate_key',raw(text[:-1]+',"findings":[]}'),False),('truncated',raw(text[:-7]),False),
        ('extra_explanation',raw('Here is the answer. '+text),False),('native_length',raw(text,'length'),False),
        ('thinking_only',raw(''),False)]:
        result=f.evaluate_audit(body,item,paired)
        if result['technical_valid']!=expected:raise ValueError('audit fixture failed: '+name)
        cases[name]='passed'
    for name,change in [('illegal_quote',lambda x:x['findings'][0]['evidence'][0].update(quote='NOT_IN_SOURCE_123')),
        ('illegal_source',lambda x:x['findings'][0]['evidence'][0].update(source_id='FUTURE:T001')),
        ('grade_leak',lambda x:x.update(q=4)),('missing_consequence',lambda x:x['findings'][0].pop('consequence'))]:
        bad=deepcopy(value);change(bad)
        if f.evaluate_audit(raw(json.dumps(bad)),item,paired)['technical_valid']:raise ValueError(name)
        cases[name]='passed'
    score=dict(status='scored',q=3)
    msgs,schema=f.repair_payload(item,score,value,'UNCHANGED COMMON PROMPT',paired)
    data=json.loads(msgs[1]['content'])
    if data['legal_evidence']!=item['evidence'] or data['reply']!=item['reply']:raise ValueError('repair drops sources')
    cases['repair_keeps_full_original']='passed'
    good=deepcopy(value);good['findings']=[]
    try:f.repair_payload(item,score,good,'UNCHANGED',paired)
    except ValueError:cases['no_unflagged_resampling']='passed'
    else:raise ValueError('unflagged repair admitted')
    return dict(kind='synthetic_transport_and_schema_fixtures_not_real_scores',cases=cases,count=len(cases),new_model_calls=0)


def validation_materials(out, paired, old_materials):
    """Freeze source/availability-only choice BEFORE reading selected replies.

    Four distinct train owners, one original legal single-head plan each. No
    outcome/score-based selection and no protected test or sealed-label access.
    """
    old=BASE/'four_head_diagnostic_preparation_20261020_v1/inputs_private.json'
    data=read(old)
    poolpath=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2/common_pool/slots_private.json'
    slots=read(poolpath)['rows']
    excluded={x['owner'] for x in old_materials}
    by=defaultdict(dict)
    for s in slots:
        if s['split']=='train' and s['owner'] not in excluded and s['prefix_identity'] in data['specs']:
            by[s['prefix_identity']][tuple(s['counts'])]=s
    selected=[]; owners=set(); missing=[]
    for h,head in enumerate(('RS','MP','MS','ME')):
        plan=tuple(int(i==h) for i in range(4))
        eligible=[pid for pid,p in by.items() if (0,0,0,0) in p and plan in p and p[plan]['owner'] not in owners]
        eligible.sort(key=lambda pid:digest((f.VERSION,head,pid)))
        if not eligible:
            missing.append(dict(head=head,reason='no distinct-owner available OFF/single-head pair'));continue
        pid=eligible[0];on=by[pid][plan];owners.add(on['owner'])
        selected.append(dict(context_id='V'+str(h+1),head=head,owner=on['owner'],prefix_identity=pid,
            source_pool='existing_train_common_pool',selection='fixed hash order, distinct owners, availability only',
            off_slot=by[pid][(0,0,0,0)]['slot_id'],on_slot=on['slot_id'],counts=list(plan),
            resource_tokens=on['resource_tokens'],independent_final_validation=False,
            same_owner_as_task_reference=False,prior_text_exposure='previous generation/preparation; not certified unread',
            prior_label_exposure='no labels read for selection; whole-history label independence not certified',
            fact_family_independence='not certified',history_overlap_with_old_contexts=None))
    write(out,'validation/SELECTION_BEFORE_REPLY_READ.json',dict(items=selected,missing=missing,
          metadata_hashes={str(old):sha(old),str(poolpath):sha(poolpath)}))
    # Index source generation bindings, without reading their output text.
    requests={}
    for rid,b in data['generation_cache'].items():
        req=read(b['request_path'])
        if sha(b['request_path'])!=b['request_sha256']:raise ValueError('cached request changed')
        p=req['provenance'];key=(p['prefix_identity'],tuple(p['canonical_counts']))
        if key in requests:raise ValueError('ambiguous generation identity')
        requests[key]=(rid,b,req)
    items={};bindings=[]; schedule=[]
    old_history={k for m in old_materials for k in m['history_session_identities']}
    prompt=(PREP/'COMMON_PROMPT_EN.txt').read_text()
    for c in selected:
        ev=data['evidence'][c['prefix_identity']]
        history_ids=[digest(x) for x in ev['legal_past_sessions']]
        c['history_overlap_with_old_contexts']=sorted(set(history_ids)&old_history)
        for cond,plan in [('OFF',(0,0,0,0)),('ON',tuple(c['counts']))]:
            rid,b,req=requests[c['prefix_identity'],plan]
            raw=read(b['raw_path'])
            if sha(b['raw_path'])!=b['raw_sha256'] or raw['finish_reason']!='natural_stop' or raw['request_id']!=rid:
                raise ValueError('selected generated reply binding/finish failure')
            if digest({k:v for k,v in req.items() if k!='request_id'})!=rid:raise ValueError('generation request hash mismatch')
            key=c['context_id']+'_'+cond;item=dict(reply=raw['text'],evidence=ev)
            items[key]=item
            bindings.append(dict(material_id=key,context_id=c['context_id'],condition=cond,head=c['head'],owner=c['owner'],
                generation_request=rid,reply_identity=digest(raw['text']),evidence_identity=digest(ev),
                generation_source=b,counts=list(plan),resource_tokens=0 if cond=='OFF' else c['resource_tokens']))
            messages,schema=paired.payload(item,'joint');messages[0]['content']=prompt
            write(out,'validation/joint_payloads/'+key+'.json',dict(messages=messages,schema=schema))
            # Audit body is bound at execution to THIS new first score, not old/manual labels.
            write(out,'validation/audit_schemas/'+key+'.json',f.audit_schema(item,paired))
        order=('OFF','ON') if len(schedule)//4%2==0 else ('ON','OFF')
        for cond in order:
            for component in ('joint','audit'):
                logical=dict(study=f.VERSION,material_id=c['context_id']+'_'+cond,component=component,repetition=1)
                schedule.append(dict(position=len(schedule)+1,slot_id=digest(logical),**logical,
                                     dependency='same endpoint joint must be mechanically complete' if component=='audit' else None))
    write(out,'validation/inputs_private.json',items)
    write(out,'validation/MATERIALS.json',dict(contexts=selected,bindings=bindings,missing=missing,
        complete_pairs=len(selected),unique_replies=len(items),newly_generated=0,
        exposes_text_for_this_preparation=True,independent_validation_certified=0))
    write(out,'validation/SCHEDULE.json',dict(fixed=schedule,
        supplemental_policy='at most first 4 flagged endpoints in fixed joint order, one each; no score/arm-favored selection',
        primary_max_calls=len(schedule),supplemental_max_calls=4,total_max_calls=len(schedule)+4,
        audit_failure='no supplement/retry; technical stage STOP; preserve all missing slots',
        model_unknown='audit may inspect complete uncertain final; never convert unknown to zero'))
    write(out,'validation/JOINT_PROMPT_EN.txt',prompt)
    write(out,'validation/AUDIT_PROMPT_EN.txt',paired.EXTRACT_PROMPT+f.AUDIT_ADDITION)
    write(out,'validation/REPAIR_ADDITION_EN.txt',f.REPAIR_ADDITION)
    return selected,items,schedule,missing


def prepare(out):
    os.umask(0o077)
    if out.exists():raise SystemExit('output exists; use --verify, never overwrite history')
    sys.path.insert(0,str(BASE/'paired_diagnostic_20261019_v1'))
    import paired as p
    source_files=[RESULT/'runtime_summary.json',RESULT/'ANALYST_REVIEWS.json',RESULT/'RESOURCE_COMPARISONS.json',
                  PREP/'protocol.json',PREP/'inputs_private.json',PREP/'materials.json',PREP/'budget.json',
                  PROJECT/'src/metacom_pm/rl1/natural_batch.py',PROJECT/'src/metacom_pm/rl1/diagnostic_session.py',
                  PROJECT/'src/metacom_pm/rl1/e0_learning.py',PROJECT/'docs/pm_rl1_completion_20260930_v2/execution_contract.json']
    ledger=PROJECT/'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    cost=read(RESULT/'COST_AND_EXECUTION.json'); financial=cost['financial_closeout']
    if sha(ledger)!=financial['ledger_sha256']:raise ValueError('ledger changed; reconcile actual state')
    histories=tr.history_snapshot(BASE,BASE/'unused_offline_path')
    if 66+len(histories)!=285:raise ValueError('actual scoring count differs from 285')
    stops={str(x):sha(x) for n in tr.RUN_ROOTS for x in (BASE/n).rglob('STOP.json')}
    pr=read(PREP/'protocol.json'); runtime=read(RESULT/'runtime_summary.json')
    reviews={x['slot_id']:x for x in read(RESULT/'ANALYST_REVIEWS.json')['records']}
    items=read(PREP/'inputs_private.json');materials=read(PREP/'materials.json')
    out.mkdir(parents=True)
    before={str(x):sha(x) for x in source_files+[ledger]} | histories | stops
    write(out,'SOURCE_HASHES_BEFORE.json',before)
    auto={};reviewed={};checked=[]
    for slot in runtime['slots']:
        rawpath=Path(pr['run_dir'])/(slot['slot_id']+'.response.json')
        raw=read(rawpath);actual=p.evaluate(items[slot['material_id']],'joint',raw,pr['identity'],slot['slot_id'])
        for k in ('technical_valid','model_unknown','q','m','U'):
            if actual.get(k)!=slot['result']['evaluation'].get(k):raise ValueError('old raw reparse changed')
        r=reviews[slot['slot_id']]
        if (sha(Path(pr['run_dir'])/(slot['slot_id']+'.result.json'))!=r['result_sha256'] or
            hashlib.sha256(raw['choices'][0]['message']['content'].encode()).hexdigest()!=r['original_final_sha256']):
            raise ValueError('old review/raw hash binding mismatch')
        auto[slot['slot_id']]=f.observation(slot)
        reviewed[slot['slot_id']]=f.observation(slot,review=r)
        checked.append(dict(slot=slot['slot_id'],material=slot['material_id'],arm=slot['arm'],repetition=slot['repetition'],
                            raw_path=str(rawpath),raw_sha256=sha(rawpath),review_identity=digest(r)))
    write(out,'replay/AUTOMATIC_VISIBLE_ONLY.json',auto)
    write(out,'replay/WITH_EXISTING_REVIEW.json',reviewed)
    write(out,'replay/RAW_BINDINGS.json',checked)
    write(out,'replay/REPEAT_SIGNALS.json',f.repeat_signals(runtime['slots']))
    pair_tokens={x['id']:x['resource_tokens'] for x in pr['resource_pairs']}
    comparisons=read(RESULT/'RESOURCE_COMPARISONS.json')
    pairs=[dict(x,resource_tokens=pair_tokens[x['pair_id']]) for x in comparisons]
    ap=[f.pair_feedback(x,auto) for x in pairs];rp=[f.pair_feedback(x,reviewed) for x in pairs]
    write(out,'replay/ALL_PAIRS.json',dict(automatic_visible=ap,with_existing_review=rp))
    grouped=defaultdict(list)
    for x in ap:grouped[x['pair_id']].append(x)
    sensitivity=[]
    for key,rows in grouped.items():
        values=[x['original_net'] for x in rows if x['original_net'] is not None]
        sensitivity.append(dict(pair=key,observations=len(rows),observed_values=values,
            observed_span=max(values)-min(values),observed_directions=sorted(set('positive' if v>0 else 'negative' if v<0 else 'zero' for v in values)),
            true_reward_interval=False,confidence_interval=False,independent_samples=False))
    difficulty=grouped['difficulty_RS'];a=next(x for x in difficulty if x['arm']=='A');b=next(x for x in difficulty if x['arm']=='B')
    sensitivity.append(dict(case='35B different measurement arms, not identical repeats',
        **f.return_sensitivity(a['original_net'],b['original_net'])))
    write(out,'replay/SENSITIVITY.json',sensitivity)
    batch=[]
    for arm in ('A','B'):
        chosen=[x for x in runtime['slots'] if x['arm']==arm]
        # 16 measurement slots are not 16 trajectories. This tests the batch
        # disposition on fixtures with the measured statuses; no natural update.
        fixtures=[dict(trajectory_id=x['slot_id'],status='candidate' if reviewed[x['slot_id']]['status']=='candidate' else 'pending') for x in chosen]
        ids=[x['trajectory_id'] for x in fixtures]
        batch.append(dict(arm=arm,kind='status_replay_fixture_not_real_trajectory_batch',
            initial=f.batch_state(fixtures,expected_ids=ids),exhausted=f.batch_state(fixtures,expected_ids=ids,closed=True)))
    write(out,'replay/BATCH_DISPOSITIONS.json',batch)
    selected,newitems,schedule,missing=validation_materials(out,p,materials)
    write(out,'AUDIT_MOCK_TESTS.json',audit_mock_checks(next(iter(newitems.values())),p))
    mean=Decimal(financial['stage_accounted_usd'])/32
    baseline=Decimal(financial['trial_accounted_usd']);reserve=Decimal('.786432');n=len(schedule)+4
    oldbudget=read(PREP/'budget.json');full=[]
    for s in oldbudget['full_research_scenarios']:
        count=s['slots_with_original_reserves'];core=s['core_J_slots']
        # If every future score needs an audit, request count roughly doubles.
        full.append(dict(episodes_per_seed=s['episodes_per_seed'],selected=False,core_J_slots=core,
            original_slots_with_reserves=count,components=s['components'],
            single_joint_cost=str(count*mean),joint_plus_audit_equal_mean_scenario=str(2*count*mean),
            single_joint_total_with_spent=str(baseline+count*mean),
            equal_mean_two_call_total_with_spent=str(baseline+2*count*mean),
            exact_deduplication_complete=False,human_and_supplements_not_included=True))
    budget=dict(status='PROPOSED_NOT_AUTHORIZED',historical_cost_baseline=str(baseline),known_unsettled=0,
        paid_so_far_this_stage='0',historical_joint_mean=str(mean),max_new_calls=n,
        baseline_calls=285,proposed_cumulative_cap=285+n,active_capacity=349,
        proposed_capacity=285+n+64,reserve_capacity_retained='59+4+1, eligibility applicability still to decide',
        proposed_stage_cost_plus_liability_usd='2',active_trial_usd='3.15',proposed_trial_usd='3.65',shared_usd='20',
        single_native_reserve_usd=str(reserve),all_native_upper_usd=str(n*reserve),
        stage_settled_max_before_next_reserve=str(Decimal(2)-reserve),
        active_trial_headroom=str(Decimal('3.15')-baseline),
        active_trial_settled_max_before_next_reserve=str(Decimal('3.15')-baseline-reserve),
        equal_joint_mean_scenario=str(n*mean),half_to_twice_mean_scenario=[str(n*mean/2),str(n*mean*2)],
        audit_and_repair_usage_not_yet_observed=True,current_prices_not_queried=True,estimate_not_quote_or_guarantee=True,
        management_requests_proposed={'models':1,'user/balance':1},new_generations=0,training_updates=0,
        human_proposed=dict(primary_reply_reviews=8,supplemental_max=4,total_minutes_cap=120,
                            same_researcher_not_independent_gold=True),
        minimal_real_wiring=dict(J=2,G=2,updates=0,authorized=False),
        BC=dict(J=336,checkpoint_available=False,authorized=False),FixedDev=dict(J=250,authorized=False),
        old_random32=dict(J=80,G=44,cap=369,stage_usd='3',trial_usd='4.25',authorized=False,separate_proposal=True),
        full_research=full,shared_budget_fits_not_demonstrated=True)
    write(out,'BUDGET_PROPOSAL.json',budget)
    summary=dict(version=f.VERSION,status='OFFLINE_PROTOTYPE_ONLY',timestamp=datetime.now(timezone.utc).isoformat(),
        historical_score_count=285,active_capacity=349,new_model_requests=0,new_human_reviews=0,natural_updates=0,
        reparsed_existing_outputs=len(checked),plan_slots=len(runtime['slots']),unique_replies=len(items),contexts=5,owners=2,
        automatic_visible_status_counts=dict(Counter(x['status'] for x in auto.values())),
        with_existing_review_counts=dict(Counter(x['status'] for x in reviewed.values())),
        reviewer_issue_types=dict(Counter(t for x in reviewed.values() for t in x['reviewer']['unresolved'])),
        automatic_audits_available=0,prior_manual_relations_present_in_both_arms=True,
        pairs_total=len(pairs),unique_complete_pair_types=len(grouped),
        paired_scenario_candidates_after_review=sum(x['status']=='candidate' for x in rp),
        unique_complete_pair_types_after_review=len({x['pair_id'] for x in rp if x['status']=='candidate'}),
        reward_qualified=False,live_authorized=False,validation_contexts=len(selected),validation_missing=missing,
        interpretation='candidate is a diagnostic numeric candidate, not an assertion of accuracy or train eligibility')
    write(out,'OFFLINE_RESULTS.json',summary)
    write(out,'PROTOTYPE_POLICY.json',f.DEFAULT_POLICY)
    write(out,'IMPLEMENTATION_BINDINGS.json',{str(x):sha(x) for x in
        [Path(__file__),PROJECT/'src/metacom_pm/rl1/feedback_prototype.py',BASE/'paired_diagnostic_20261019_v1/paired.py']})
    if any(sha(path)!=h for path,h in before.items()):raise ValueError('history/source changed during offline work')
    write(out,'HISTORY_PRESERVATION.json',dict(source_files=len(source_files),historical_started=len(histories),
        stop_records=len(stops),all_preserved=True,ledger_sha256=sha(ledger),contract_changed=False))
    manifest={str(x.relative_to(out)):sha(x) for x in out.rglob('*') if x.is_file()}
    write(out,'CORE_MANIFEST.json',manifest)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--verify',action='store_true');args=ap.parse_args()
    if args.verify:
        for name,h in read(args.out/'CORE_MANIFEST.json').items():
            if sha(args.out/name)!=h:raise ValueError('artifact changed: '+name)
        for path,h in read(args.out/'SOURCE_HASHES_BEFORE.json').items():
            if sha(path)!=h:raise ValueError('historical source changed: '+path)
        print('Offline artifacts and immutable historical sources verified; no calls or updates.')
    else:prepare(args.out)


if __name__=='__main__':main()

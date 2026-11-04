#!/usr/bin/env python3
"""Prepare/run/analyze at most eight fixed source/value diagnostic contexts.

Uses the original bounded G executor. No J, quality reward or PM optimization.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import json
from pathlib import Path
import random
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.rl1.calibration_workflow import stamp, verify_identity
from metacom_pm.rl1.online_materials import load_materials, read
from metacom_pm.rl1.resource_organization import OrganizationCatalog
from metacom_pm.rl1.resource_value_probe import match_session, turn_layout, VERSION
from metacom_pm.rl1.resource_comparison_runner import request_for, protocol_for, FixedResourceComparison
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json, file_sha

BASE = PROJECT / 'outputs/pm_rl1'
TRAIN = BASE / 'organized_initial_training_20261103_v2'
OLD = BASE / 'organized_initial_generation_20261103_v2'


def prepare(out, annotations):
    if out.exists():
        raise ValueError('new diagnostic output required')
    notes = read(annotations)
    c, catalogs, renderer = load_materials(TRAIN)
    menu = read(TRAIN / 'MENU_PRIVATE.json')['endpoints']
    old = read(OLD / 'RESPONSES_PRIVATE.json')
    ordered = sorted(catalogs)
    assert len(ordered) == len(notes['inventory']) == 24
    selected = [n for n in notes['inventory'] if n.get('pilot')]
    assert len(selected) <= 8
    inventories = []; cards = []; items = {}; variants = []; relations = []
    requests = []; reused = {}; cache = {}
    source_paths = [annotations, TRAIN / 'CONFIG.json', TRAIN / 'MENU_PRIVATE.json', OLD / 'RESPONSES_PRIVATE.json',
                    BASE / 'contextual_value_reference_20261104_v1/ANSWER_REGISTRY_PRIVATE.json',
                    BASE / 'decision_findings_20261104_v1/FINDINGS_PRIVATE.json']
    for e in menu:
        req = e['requests']['ON']; raw = old[req['request_id']]
        assert raw['finish_reason'] == 'natural_stop' and raw['source_provenance_identity'] == digest(req['provenance'])
        cache.setdefault((req['executor_identity'], digest(req['messages'])), (req, raw))
    runner_file = PROJECT / 'src/metacom_pm/rl1/resource_comparison_runner.py'
    code_id = file_sha(runner_file)
    def add(n, arm, catalog, keys, *, force_fresh=False):
        messages = renderer.messages(catalog, keys); usage = renderer.usage(catalog, keys)
        if not usage['within_native_context'] or usage['truncation']:
            raise ValueError('whole resource exceeds native capacity')
        body = dict(prefix_identity=catalog.prefix.identity, executor_identity=c['runtime']['identity'],
                    renderer_identity=renderer.identity, renderer_route=VERSION, messages=messages,
                    selected_keys=list(keys), selected_resource_identities=[catalog.item(k).identity for k in keys],
                    catalog_identity=catalog.identity, usage=usage)
        row = dict(body, identity=digest(body), reusable_old_requests=[])
        key = row['identity']; items[key] = row
        found = cache.get((c['runtime']['identity'], digest(messages)))
        rid = None
        if found and not force_fresh:
            req, raw = found
            assert req['messages'] == messages and raw['input_tokens'] == usage['input_tokens']
            reused[key] = dict(source_request=req, raw=raw, source_file=str((OLD/'RESPONSES_PRIVATE.json').resolve()))
        elif not any(q['prepared_input_identity'] == key for q in requests) or force_fresh:
            request = request_for(row, runtime=c['runtime'], draw_identity=f'{VERSION}:{n["case"]}:{arm}', code_identity=code_id)
            requests.append(request); rid = request['identity']
        else:
            rid = next(q['identity'] for q in requests if q['prepared_input_identity'] == key)
        card = dict(case=n['case'], prefix=catalog.prefix.identity, arm=arm, input_identity=key,
                    request_identity=rid, reused=bool(found and not force_fresh),
                    input_tokens=usage['input_tokens'], resource_tokens=usage['resource_tokens'],
                    quality=None, reward=None, analyst_hypothesis_only=True)
        cards.append(card)
        return card
    for i, pid in enumerate(ordered, 1):
        n = notes['inventory'][i-1]
        assert n['case'] == f'N{i:02d}'
        catalog = catalogs[pid]; path = TRAIN / 'sources_private' / (pid+'.json')
        source_paths.append(path); source = read(path); source_paths.append(Path(source['stored_source_path']))
        ev = source['evidence']; by_session = {match_session(x, ev)['id']: x for x in catalog._items.values() if x.head == 'MS'}
        ranking = catalog.rank('MS'); key_to_session = {x.key: s for s, x in by_session.items()}
        trial = []; acquired = []
        for _ in range(min(6, len(by_session))):
            acquired.append(catalog.rank('MS', acquired)[0]['key']); trial.append(key_to_session[acquired[-1]])
        inventory = dict(n, prefix_identity=pid, owner=catalog.prefix.owner_id,
            current_prefix=ev['current_prefix'], legal_history_sessions=len(by_session),
            head_inventory=dict(Counter(x.head for x in catalog._items.values())),
            MS_initial_ranking=[key_to_session[r['key']] for r in ranking], MS6_actual_path=trial,
            inferred_need_not_a_human_label=True, qualified_reward=False)
        if n.get('target_session'):
            sid=n['target_session'];target=by_session[sid];session=match_session(target, ev)
            inventory.update(target_resource=asdict(target), target_source=session,
                target_initial_rank=next(j+1 for j,r in enumerate(ranking) if r['key']==target.key),
                target_in_MS6=sid in trial,
                compressed_source_links=[dict(head=x.head, key=x.key, content=x.content, meaning_verified=False)
                    for x in catalog._items.values() if x.head in ('MP','ME') and set(x.source_ids)&set(target.source_ids)])
        inventories.append(inventory)
        if not n.get('pilot'):continue
        add(n,'A_OFF',catalog,[])
        bkey=ranking[0]['key'];add(n,'B_retrieved_MS1',catalog,[bkey])
        if n['case']=='N03':
            finding=read(BASE/'decision_findings_20261104_v1/FINDINGS_PRIVATE.json')[0]
            original=next(x for x in catalog._items.values() if x.head=='ME' and json.loads(x.content)==finding['original_record'])
            assert finding['repair_candidate']|{'past_report':finding['original_record']['past_report']}==finding['original_record']
            add(n,'M0_original_ME',catalog,[original.key])
            fixed=replace(original,content=json.dumps(finding['repair_candidate'],ensure_ascii=False,sort_keys=True,separators=(',',':')),
                source_identity=digest(dict(original=original.identity,repair=finding['repair_candidate'])))
            repaired=OrganizationCatalog(catalog.prefix,[fixed if x.key==fixed.key else x for x in catalog._items.values()],
                provenance_identity=digest(dict(original=catalog.identity,repair=fixed.identity)))
            add(n,'M1_source_supported_ME',repaired,[fixed.key])
            variants.append(dict(case=n['case'],type='ME_statement_repair',original=original.identity,variant=fixed.identity,
                changed_fields=['past_report'],human_quality_label=False,repair_candidate_not_adopted=True))
        if n.get('target_session'):
            target=by_session[n['target_session']];add(n,'C_target_full_MS',catalog,[target.key])
            changed,receipt=turn_layout(target,ev);variants.append(dict(case=n['case'],**receipt))
            variant=OrganizationCatalog(catalog.prefix,[changed if x.key==target.key else x for x in catalog._items.values()],
                                       provenance_identity=digest(dict(original=catalog.identity,intervention=receipt)))
            add(n,'E_same_full_turn_layout',variant,[target.key])
            eligible=[by_session[sid] for sid in n.get('distractor_candidates',[]) if sid!=n['target_session']]
            if eligible:
                tcount=renderer.usage(catalog,[target.key])['resource_tokens']
                distractor=min(eligible,key=lambda x:(abs(renderer.usage(catalog,[x.key])['resource_tokens']-tcount),x.key))
                add(n,'D_other_topic_full_MS',catalog,[distractor.key])
                relations.append(dict(case=n['case'],target=n['target_session'],distractor=match_session(distractor,ev)['id'],
                    resource_token_difference=renderer.usage(catalog,[distractor.key])['resource_tokens']-tcount,
                    distractor_neutrality='not_assumed',perfect_length_match=False))
        if n['case'] in ('N02','N19'):
            add(n,'REPLAY_B_same_input',catalog,[bkey],force_fresh=True)
    # These fixed probes are not automatic GET actions and cannot become PPO labels.
    assert len(requests)<=26 and all(r['provenance']['selected_keys'] for r in requests)
    random.Random(20261104).shuffle(requests)
    runtime=c['runtime'];assets={str(Path(runtime['model_dir'])/name):h for name,h in runtime['model_files'].items()}
    assets.update({str(Path(runtime['adapter']['path'])/name):h for name,h in runtime['adapter']['files'].items()})
    for path in [Path(__file__),runner_file,PROJECT/'src/metacom_pm/rl1/resource_value_probe.py',PROJECT/'scripts/rl1/92_run_p2_common_pool.py',PROJECT/'src/metacom_pm/rl1/generation.py']:
        assets[str(path.resolve())]=file_sha(path)
    out.mkdir(parents=True,mode=0o700)
    protocol=protocol_for(requests,runtime=runtime,assets=assets,packages=runtime['packages']|{'peft':runtime['adapter']['peft_version']},
        gpu_uuid=c['gpu_uuid'],code_identity=code_id,source_package_identity=digest(dict(notes=notes,inputs=items)),run_directory=out/'live_G')
    study=stamp(dict(scope='EXPLORATORY_RESOURCE_VALUE_DIAGNOSTIC',selection=notes['selection'],
        selected_cases=[n['case'] for n in selected],input_identity=digest(items),cards_identity=digest(cards),
        historical_reuse_identity=digest(reused),G_protocol=protocol['identity'],max_new_G_calls=len(requests),
        no_reference_reply_or_candidate_fact_annotations_in_generator=True,
        source_usage_is_not_helpfulness_reward=True,quality_and_latency_separately_pending=True,
        targeted_injection_not_an_available_PM_action=True,quality_gates=None,API_cost_usd=0,
        authorization='研究者：考虑到资源使用和组织问题之后，继续按计划正确推进。'))
    for name,value in [('INVENTORY_PRIVATE.json',inventories),('CARDS_PRIVATE.json',cards),('INPUTS_PRIVATE.json',items),
        ('REUSED_PRIVATE.json',reused),('VARIANTS_PRIVATE.json',variants),('DISTRACTORS_PRIVATE.json',relations),
        ('G_REQUESTS_PRIVATE.json',requests),('G_PROTOCOL.json',protocol),('STUDY.json',study),
        ('SOURCES.json',{str(p.resolve()):file_sha(p) for p in source_paths})]:save_json(out/name,value)
    print(json.dumps(dict(prefixes=len(inventories),pilot_cases=len(selected),cards=len(cards),new_G_calls=len(requests),reused_inputs=len(reused)),ensure_ascii=False),flush=True)


def run(out):
    for path,sha in read(out/'SOURCES.json').items():
        if file_sha(path)!=sha:raise ValueError('source changed: '+path)
    study=read(out/'STUDY.json');verify_identity(study)
    assert digest(read(out/'INPUTS_PRIVATE.json'))==study['input_identity']
    runner=FixedResourceComparison(read(out/'G_PROTOCOL.json'),read(out/'G_REQUESTS_PRIVATE.json'),out/'live_G',approval=read(out/'APPROVAL.json'))
    while True:
        result=runner.step();print(json.dumps(result),flush=True)
        if result['status']=='CLOSED_FIXED_COMPARISON':return
        if result['status']=='RECONCILIATION_REQUIRED' or result.get('finish_reason','natural_stop')!='natural_stop':
            raise RuntimeError('partial run retained; no automatic retry')


def analyze(out):
    protocol=read(out/'G_PROTOCOL.json');cards=read(out/'CARDS_PRIVATE.json');reused=read(out/'REUSED_PRIVATE.json')
    results=[]
    for card in cards:
        r=dict(card);rid=card['request_identity']
        if card['reused']:raw=reused[card['input_identity']]['raw']
        elif (out/'live_G'/(rid+'.raw.json')).exists():
            raw=read(out/'live_G'/(rid+'.raw.json'));seal=read(out/'live_G'/(rid+'.sealed.json'));verify_identity(seal)
            assert seal['raw_identity']==digest(raw) and seal['protocol_identity']==protocol['identity']
        else:results.append(dict(r,status='pending',reply=None));continue
        r.update(status=raw['finish_reason'],reply=raw['text'],reply_identity=digest(raw['text']),
                 output_tokens=raw['output_tokens'],G_component_seconds=raw['generation_seconds'])
        results.append(r)
    comparisons=[]
    for case in sorted({r['case'] for r in results}):
        group={r['arm']:r for r in results if r['case']==case}
        for arm,r in group.items():
            if arm=='A_OFF':continue
            base=group['B_retrieved_MS1' if arm=='REPLAY_B_same_input' else 'C_target_full_MS' if arm=='E_same_full_turn_layout' else 'M0_original_ME' if arm=='M1_source_supported_ME' else 'A_OFF']
            comparisons.append(dict(case=case,left=arm,right=base['arm'],
                identical_reply=(r['reply']==base['reply']) if r['reply'] is not None and base['reply'] is not None else None,
                quality_direction=None,client_latency_effect=None))
    save_json(out/'RESULTS_PRIVATE.json',results);save_json(out/'COMPARISONS.json',comparisons)
    summary=dict(status='GENERATIONS_READY_FOR_CONTENT_REVIEW' if all(r['status']=='natural_stop' for r in results) else 'PARTIAL',
        cards=len(results),new_G_calls=len(list((out/'live_G').glob('*.raw.json'))),
        natural_new_G=sum(read(p)['finish_reason']=='natural_stop' for p in (out/'live_G').glob('*.raw.json')),
        replay_same_text=[x['identical_reply'] for x in comparisons if x['left']=='REPLAY_B_same_input'],
        qualified_rewards=0,policy_updates=0,API_cost_usd=0)
    save_json(out/'SUMMARY.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','run','analyze']);p.add_argument('--output',type=Path,required=True);p.add_argument('--annotations',type=Path)
    a=p.parse_args()
    if a.mode=='prepare':prepare(a.output,a.annotations)
    else:globals()[a.mode](a.output)

#!/usr/bin/env python3
"""Replay existing train retrieval; record hypotheses without quality labels."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.online_materials import load_materials,read
from metacom_pm.rl1.resource_organization import OrganizationSession
from metacom_pm.rl1.resource_value_probe import match_session
from metacom_pm.rl1.schema import HEADS,digest
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.io import sha256_file as sha
BASE=PROJECT/'outputs/pm_rl1';TRAIN=BASE/'organized_initial_training_20261103_v2'
NEW={
 'N06':dict(target='H017',anchors=['H017:T005','H017:T011','H017:T013','H017:T017'],
   hypothesis='已有接近退课的过载经历、珍惜使自己开心的活动；研究导师曾支持。可探讨研究的有限范围或延期，不默认牺牲社团。',
   incremental_information='当前已经说社团是休息和身体不适；新增的是过去过载程度、保留活动的明确意愿及这位导师曾支持。',
   reasonable_OFF='只凭当前身体不适和犹豫，也能建议暂缓承诺或与导师沟通；这些一般建议本身不能证明历史贡献。',
   disconfirmation='ON只重复身体不适、放慢节奏或沟通导师；历史未改变方案，或引用过载反而增加压力。',
   caveats=['考虑与导师谈并不表示已经谈过。','不能把更早物理课老师与当前研究导师当成同一人。','不评估医学诊疗正确性。']),
 'N13':dict(target='H009',anchors=['H009:T007','H009:T009','H009:T010'],
   hypothesis='之前担心老师误解，且反复解释使她疲惫；可降低求助负担，保留不再解释全部的选择，而非再次泛泛建议向多人讲述。',
   incremental_information='当前提到怕给人添负担、和父母争执；没有说曾担心老师误解或已厌倦重复解释。',
   reasonable_OFF='倾听、承认压力、允许暂不行动本来就是合理策略；任何问句都不能自动判坏。',
   disconfirmation='ON只是复述疲惫或另加待办；OFF已同样降低负担；泛泛关怀不能证明特定事实有效。',
   caveats=['过去一次的解释疲惫不是稳定人格或永不求助偏好。','H008计划写信，未证明写过、送过或有效。','研究者偏好不是这位seeker的个人档案。']),
}


def main(out):
    if (out/'OPPORTUNITIES_PRIVATE.json').exists():raise ValueError('audit already sealed')
    c,catalogs,renderer=load_materials(TRAIN)
    inv=read(BASE/'resource_value_probe_20261104_v1/INVENTORY_PRIVATE.json')
    menu=read(TRAIN/'MENU_PRIVATE.json')['endpoints']
    raw=read(BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    inventories=[];targets=[];paths=[Path(__file__),TRAIN/'PACKAGE_MANIFEST.json',TRAIN/'INPUT_HASHES_PRIVATE.json',
        TRAIN/'MENU_PRIVATE.json',BASE/'resource_value_probe_20261104_v1/INVENTORY_PRIVATE.json',
        BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json',
        PROJECT/'src/metacom_pm/rl1/resource_organization.py']
    for old in inv:
        case=old['case'];pid=old['prefix_identity'];cat=catalogs[pid];path=TRAIN/'sources_private'/(pid+'.json')
        src=read(path);ev=src['evidence'];paths += [path,Path(src['stored_source_path'])]
        ms={match_session(x,ev)['id']:x for x in cat._items.values() if x.head=='MS'}
        sid_by_key={v.key:k for k,v in ms.items()};eps=[e for e in menu if e['prefix_identity']==pid]
        full=OrganizationSession(cat,renderer);trace=[];failure=None
        for _ in range(len(ms)):
            try:full.get('MS')
            except ValueError as exc:failure=str(exc);break
            receipt=full.receipt();key=receipt['acquired'][-1]
            trace.append(dict(step=len(trace)+1,session=sid_by_key[key],key=key,input_tokens=receipt['usage']['input_tokens']))
        inventories.append(dict(case=case,prefix_identity=pid,current_date=ev['current_date'],
            current_need_hypothesis=old['need_hypothesis'],old_source_hypothesis=old['source_hypothesis'],
            earlier_generation_probe=old['pilot'],head_inventory=old['head_inventory'],
            original_menu_programs=len(eps),full_dynamic_MS_path=trace,capacity_failure=failure,
            exhaustive_semantic_history_review=False,quality=None,training_reward=None))
        target=NEW.get(case,{}).get('target')
        if target is None and old.get('target_source'):target=old['target_source']['id']
        if target is None:continue
        item=ms[target];session=match_session(item,ev);programs=[]
        for e in eps:
            replay=OrganizationSession(cat,renderer)
            for action in e['actions']:
                if action==0:replay.stop()
                else:replay.get(HEADS[action-1])
            receipt=replay.receipt();req=e['requests']['ON']
            # Terminal G uses canonical presentation; keep acquisition order separately.
            presented=cat.canonical(receipt['acquired'])
            assert [x.key for x in presented]==req['provenance']['selected_keys']
            assert [x.identity for x in presented]==req['provenance']['selected_resource_identities']
            assert renderer.messages(cat,receipt['acquired'])==req['messages']
            assert raw[req['request_id']]['source_provenance_identity']==digest(req['provenance'])
            if item.key in receipt['acquired']:
                programs.append(dict(actions=e['actions'],selected_keys=receipt['acquired'],request_id=req['request_id'],
                    first_target_get=receipt['acquired'].index(item.key)+1,input_tokens=receipt['usage']['input_tokens']))
        # Limited, predeclared route family; these are construction-only oracle inspections.
        routes=[]
        for first in [None,*HEADS]:
            route=OrganizationSession(cat,renderer);actions=[];error=None
            while item.key not in route.receipt()['acquired']:
                head=first if not actions and first else 'MS'
                try:route.get(head)
                except ValueError as exc:error=str(exc);break
                actions.append(HEADS.index(head)+1)
            rec=route.receipt()
            routes.append(dict(initial_head=first,actions=actions+[0],acquired=rec['acquired'],
                target_reached=item.key in rec['acquired'],failure=error,input_tokens=rec['usage']['input_tokens']))
        note=NEW.get(case);anchors=[]
        if note:
            for aid in note['anchors']:
                anchors.append(next(t for t in session['turns'] if t['id']==aid))
        first=cat.rank('MS')[0]['key']
        off=next(e for e in eps if e['actions']==[0]);one=next(e for e in eps if e['actions']==[3,0])
        row=dict(case=case,prefix_identity=pid,new_source_hypothesis=bool(note),hypothesis=note,
            current_prefix=ev['current_prefix'],target_session=session,target_resource_key=item.key,target_resource_identity=item.identity,
            source_anchors=anchors,initial_rank=next(i+1 for i,x in enumerate(cat.rank('MS')) if x['key']==item.key),
            actual_pure_MS_position=next((t['step'] for t in trace if t['key']==item.key),None),
            measured_menu_paths_containing_target=programs,limited_route_family=routes,
            shortest_in_checked_routes=min((r for r in routes if r['target_reached']),key=lambda r:len(r['actions']),default=None),
            global_shortest_path_claim=False,actor_has_target_annotation=False,
            first_MS_session=sid_by_key[first],current_source_file=str(path.resolve()),
            cached_OFF=dict(request=off['requests']['ON'],raw=raw[off['requests']['ON']['request_id']]),
            cached_MS1=dict(request=one['requests']['ON'],raw=raw[one['requests']['ON']['request_id']]),
            related_compressed_records=[dict(key=x.key,head=x.head,content=x.content,entailment_verified=False)
                for x in cat._items.values() if x.head in ('MP','ME') and set(x.source_ids)&set(item.source_ids)],
            help_quality=None,qualified_reward=None)
        targets.append(row)
        print(json.dumps(dict(case=case,target=target,initial=row['initial_rank'],pure_MS=row['actual_pure_MS_position'],
            measured_programs=len(programs),shortest_checked=row['shortest_in_checked_routes']['actions'] if row['shortest_in_checked_routes'] else None)),flush=True)
    for name,obj in [('INVENTORY_AUDIT_PRIVATE.json',inventories),('OPPORTUNITIES_PRIVATE.json',targets),
        ('OPPORTUNITY_SOURCES.json',{str(p.resolve()):sha(p) for p in paths})]:save(out/name,obj)
    save(out/'OPPORTUNITY_SUMMARY.json',dict(prefixes=24,old_target_candidates=len(targets)-len(NEW),new_hypotheses=list(NEW),
        history_review='All current prefixes; selected complete past sources, not exhaustive relevance labels.',
        measured_target_programs=sum(len(t['measured_menu_paths_containing_target']) for t in targets),
        global_shortest_path_search=False,G_calls=0,qualified_rewards=0,training_updates=0,API_cost_usd=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.output.resolve())

#!/usr/bin/env python3
"""Aggregate frozen assistant observations and real GE2 costs; no semantic judge.

Requires actual review files. Cannot create judgments from source coverage,
controller status, format validity or a FINISHED job label.
"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,json
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.journal import ge2_evaluation as E
from metacom_pm.rl1v3.journal.ge2_results import nearest

def read(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(s) for s in Path(p).read_text().splitlines() if s.strip()]

p=argparse.ArgumentParser()
for key in ('root','original','out'):p.add_argument('--'+key,required=True)
a=p.parse_args();root=Path(a.root);old=Path(a.original);out=Path(a.out);out.mkdir(parents=True,exist_ok=False,mode=0o700)
collection=root/'collection-final-v1';paths=rows(collection/'PATHS_PRIVATE.jsonl')
bytask={x['task']['task_id']:x['task'] for x in paths};byeval={x['task']['task_id']:x['evaluation'] for x in paths}
alias={x['task']['task_id']:x['public']['task_alias'] for x in paths}
quality={};review_files=[]
blind=root/'blind8-review-v1';mf=read(blind/'MANIFEST_PRIVATE.json')
for name,h in mf['files_sha256'].items():
    if file_sha256(blind/name)!=h:raise ValueError('sealed blind review changed before unblinding')
key={r['case_id']:r for r in read(old/'evaluation/blind8-v2/BLIND_KEY_PRIVATE.json')['selection']}
for row in rows(blind/'REVIEWS_PRIVATE.jsonl'):
    k=key[row['case_id']];quality[(alias[k['task_id']],k['arm'])]=row
for item in rows(root/'root-common-review-v1/REVIEWS_PRIVATE.jsonl'):
    k=(item['task_alias'],item['method'])
    if k in quality:raise ValueError('replacement review would overwrite blind outcome')
    quality[k]=item['review']
if len(quality)!=37:raise ValueError('exact original 37 reviews required')
supply={(r['task_alias'],r['method']):r for r in rows(root/'actual-supply-v1/ACTUAL_SUPPLY_PRIVATE.jsonl')}
public=[];joined=[];readable=['# GE2 PRIVATE: full original responses and taskwise development observations',
    'RAW/Gold/private review boundary: do not upload this file. No formal reward, no independent human qualification.']
for path in paths:
    pub=path['public'];k=(pub['task_alias'],pub['method']);q=quality[k];output=path['actual_output']
    E.validate_review(q,task=path['task'],evaluation=path['evaluation'],source_packet_sha256=q['source_packet_sha256'],actual_output=output)
    cov=supply[k];facts=[r for r in q['facts'] if r['requirement_role']=='explicit_answer'];ca={r['atom_id']:r for r in cov['strict_atoms']}
    supported=[r for r in facts if r['status']=='supported'];unused=[r for r in facts if ca[r['atom_id']]['covered'] is True and r['status'] in ('omitted','partial')]
    outcomes=dict(complete_interval=q['development_interval'],required_fact_count=len(facts),
        fact_states=dict(Counter(r['status'] for r in facts)),bounded_unknown_answers=sum(r['bounded_unknown'] for r in facts),
        correct_fact_with_supplied_support=sum(ca[r['atom_id']]['covered'] is True for r in supported),
        correct_positive_fact_without_supplied_support=sum(ca[r['atom_id']]['covered'] is not True and not r['bounded_unknown'] for r in supported),
        supplied_required_fact_omitted_or_partial=len(unused),
        support_status=q['requested_support']['status'],natural_quality=q['natural_quality']['status'],
        additional_issue_states=dict(Counter(r['status'] for r in q['additional_claims'])),
        uncertain_issue_ids=[r['id'] for c in ['additional_claims','reference_disputes'] for r in q[c] if r['status']=='uncertain'],
        review_kind=q['reviewer']['kind'],arm_blinded=q['reviewer']['blinded_to_arm'],
        prior_task_authoring=q['reviewer']['prior_task_authoring'],formal_reward=None)
    row=dict(**pub,quality=outcomes,strict_supply=cov['strict'],review_sha256=object_sha256(q))
    row['quality_status']='assistant_development_review_complete_with_uncertainty'
    public.append(row);joined.append(dict(public=row,review=q,source_supply=cov,original_path=path))
    readable.extend(['\n## '+k[0]+' / '+k[1],'\nTechnical: '+pub['technical_status'],
        'Development interval: '+str(q['development_interval']), '\nVisible input:',json.dumps(path['task']['turns'],ensure_ascii=False,indent=2),
        '\nOriginal complete G text:',output['text'],'\nActual actions:',json.dumps([e['action'] for e in path['events'] if e['event']=='TOOL_RETURNED'],ensure_ascii=False,indent=2),
        '\nStrict delivered evidence:',json.dumps(cov,ensure_ascii=False,indent=2),
        '\nBounded review:',json.dumps(q,ensure_ascii=False,indent=2)])
groups=defaultdict(list)
for row in public:groups[row['method']].append(row)
summary={}
for m,ps in groups.items():
    summary[m]=dict(n=len(ps),complete_lower=sum(p['quality']['complete_interval'][0] for p in ps),complete_upper=sum(p['quality']['complete_interval'][1] for p in ps),
        uncertain_endpoints=sum(p['quality']['complete_interval']==[0,1] for p in ps),
        input_tokens=sum(p['input_tokens'] for p in ps),output_tokens=sum(p['output_tokens'] for p in ps),
        all_call_input_tokens=sum(p['all_call_input_tokens'] for p in ps),all_call_output_tokens=sum(p['all_returned_output_tokens'] for p in ps),
        full_p50_s=nearest([p['agent_complete_ns']/1e9 for p in ps],.5),full_p95_s=nearest([p['agent_complete_ns']/1e9 for p in ps],.95),
        first_p50_s=nearest([p['agent_to_G_internal_first_text_ns']/1e9 for p in ps],.5),first_p95_s=nearest([p['agent_to_G_internal_first_text_ns']/1e9 for p in ps],.95),
        pm_p50_s=nearest([p['pm_ns']/1e9 for p in ps],.5),controller_total_s=sum(p['controller_transport_ns'] for p in ps)/1e9,
        actual_tool_total_s=sum(p['tool_wall_ns'] for p in ps)/1e9,guard_total_s=sum(p['experiment_guard_ns'] for p in ps)/1e9)
mapping={(p['task_alias'],p['method']):p for p in public};pairs=[];pair_summaries=[]
for left,right in [('STOP','FixedTop4'),('STOP','LLMOneShot'),('STOP','LLMToolAgent'),('FixedTop4','LLMOneShot'),('FixedTop4','LLMToolAgent'),('LLMOneShot','LLMToolAgent')]:
    these=[]
    for task in sorted({p['task_alias'] for p in public}):
        l,r=mapping[(task,left)],mapping[(task,right)];a1,b1=l['quality']['complete_interval'],r['quality']['complete_interval']
        transition=('definite_repair' if a1==[0,0] and b1==[1,1] else 'definite_regression' if a1==[1,1] and b1==[0,0] else
                    'both_definite_success' if a1==b1==[1,1] else 'both_definite_incomplete' if a1==b1==[0,0] else 'uncertain_comparison')
        q=dict(task_alias=task,left=left,right=right,left_interval=a1,right_interval=b1,transition=transition,
            full_delta_right_minus_left_s=(r['agent_complete_ns']-l['agent_complete_ns'])/1e9,
            first_delta_right_minus_left_s=(r['agent_to_G_internal_first_text_ns']-l['agent_to_G_internal_first_text_ns'])/1e9,
            exact_payload_equal=l['actual_payload_sha256']==r['actual_payload_sha256'],
            common_definite_success=a1==b1==[1,1],deployment_oracle=False,formal_reward=None)
        pairs.append(q);these.append(q)
    common=[q for q in these if q['common_definite_success']]
    pair_summaries.append(dict(left=left,right=right,all_n=len(these),common_success_tasks=[q['task_alias'] for q in common],
        transitions=dict(Counter(q['transition'] for q in these)),
        common_success_full_delta_p50_s=nearest([q['full_delta_right_minus_left_s'] for q in common],.5),
        common_success_first_delta_p50_s=nearest([q['first_delta_right_minus_left_s'] for q in common],.5)))
payloads=defaultdict(list)
for p in public:payloads[(p['task_alias'],p['actual_payload_sha256'])].append(p['method'])
equal=[dict(task_alias=k[0],payload_sha256=k[1],methods=v,quality_observations_not_independent=True,latencies_separately_executed=True) for k,v in payloads.items() if len(v)>1]
calls=rows(collection/'CALLS_PRIVATE.jsonl');controller=[]
for path in paths:
    for e in path['events']:
        if e['event']!='CONTROLLER_ACCEPTED':continue
        c=next(c for c in calls if c['request_id']==e['request_id']);o=c['real_output'];start=c['started'];first=o['passive_output_observer']['events']['first_nonempty_decoded_text']
        controller.append(dict(task_alias=path['public']['task_alias'],method=path['public']['method'],request_id=c['request_id'],
            self_report_status=e['output']['evidence_state']['status'],formal_sufficiency_label=None,
            first_JSON_character_ns=None if first is None else first['monotonic_ns']-start['monotonic_ns'],
            first_accepted_complete_action_ns=e['stamp']['monotonic_ns']-start['monotonic_ns'],
            first_JSON_character_is_usable_action=False,output_tokens=c['output_tokens'],input_tokens=c['input_tokens'],
            control_generation_ns=c['generation_ns'],constraint_measurement=o['constraint_measurement'],formal_reward=None))
write_jsonl_once(out/'ENDPOINTS_REVIEWED_PUBLIC.jsonl',public)
write_jsonl_once(out/'ALL_REVIEWED_PRIVATE.jsonl',joined)
write_json_once(out/'METHOD_SUMMARY_PUBLIC.json',summary)
write_jsonl_once(out/'PAIRED_TASKWISE_PUBLIC.jsonl',pairs)
write_json_once(out/'PAIRED_SUMMARY_PUBLIC.json',pair_summaries)
write_json_once(out/'EXACT_PAYLOAD_GROUPS_PUBLIC.json',equal)
write_jsonl_once(out/'CONTROLLER_TIMING_PUBLIC.jsonl',controller)
(out/'COMPLETE_TASKWISE_REPLIES_PRIVATE.md').write_text('\n'.join(readable)+'\n')
write_json_once(out/'MANIFEST_PRIVATE.json',dict(protocol='ge2-result-analysis-with-explicit-assistant-reviews-v1',
    script_sha256=file_sha256(__file__),blind_review_manifest_sha256=file_sha256(blind/'MANIFEST_PRIVATE.json'),
    root_review_manifest_sha256=file_sha256(root/'root-common-review-v1/MANIFEST_PRIVATE.json'),
    collection_manifest_sha256=file_sha256(collection/'COLLECTION_MANIFEST_PRIVATE.json'),
    actual_supply_manifest_sha256=file_sha256(root/'actual-supply-v1/MANIFEST_PRIVATE.json'),
    files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},formal_reward=None,
    qualification='assistant development only; uncertainty intervals are not confidence intervals; semantic entries not proven by validator'))
print(json.dumps(dict(methods=summary,paired_common_success=pair_summaries,equal_payloads=equal),indent=2))

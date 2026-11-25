#!/usr/bin/env python3
"""Public counts/identities only; raw sources, gold and review text stay private."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from metacom_pm.rl1v3.journal.eval_calibration import metrics
from metacom_pm.rl1v3.io import object_sha256

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);hashes={}


def read(name,lines=False):
    source=a.root/name;hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    return [json.loads(x) for x in source.read_text().splitlines()] if lines else json.loads(source.read_text())


def write(name,value):
    (a.out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n')


def pick(row,keys):return {k:row[k] for k in keys.split()}


measure=read('batch18_results/MEASUREMENTS.json')
write('BATCH18_MEASUREMENTS.json',pick(measure,'job_status physical_calls returned model_load total_wall_seconds total_input_tokens total_output_tokens total_generation_seconds logical_arms exact_reused_arms technical_counts technical_counts_scope pairs reward_qualified'))
rows=read('batch18_results/PAIRED_RESPONSES_PRIVATE.jsonl',True)
write('BATCH18_LOGICAL_MEASUREMENTS.json',[pick(r,'task_id domain arm request_id payload_sha256 response_sha256 input_tokens output_tokens generation_seconds technical_status finish_reason exact_physical_reuse reward') for r in rows])
for source,target in [
    ('memory_retrieval/run-v1/PUBLIC_AGGREGATE.json','RETRIEVAL_AGGREGATE.json'),
    ('memory_retrieval/run-v1/COMMON_SCOPE_COMPARISON_PUBLIC.json','RETRIEVAL_COMMON_SCOPE.json'),
    ('calibration/results-v2/PUBLIC_AGGREGATE.json','CALIBRATION96_AGGREGATE.json'),
    ('calibration/V2_CORRECTION_RECEIPT.json','CALIBRATION_V2_CORRECTION.json'),
    ('ORIGINAL_ALLOCATION_STATUS_V1.json','ORIGINAL_ALLOCATION_STATUS.json'),
    ('memory_packages/final-v2/PACKAGE_REPORT.json','MEMORY_RUN_PACKAGES.json'),
    ('memory_packages/final-v2/INDEPENDENT_INSPECTION.json','MEMORY_PACKAGE_CHECKS.json'),
    ('rs_complex/SUMMARY_PUBLIC.json','RS_COMPLEX_PACKAGE.json')]:
    write(target,read(source))
group_rows=read('calibration/results-v2/SOURCE_GROUP_RESULTS_PRIVATE.json')
for row in group_rows:
    row['source_group_opaque_sha256']=hashlib.sha256(row.pop('source_group').encode()).hexdigest()
write('CALIBRATION96_GROUP_RESULTS.json',group_rows)
memory=read('batch18_memory_review/PUBLIC_AGGREGATE.json')
safe=pick(memory,'protocol tasks physical_responses logical_arm_rows exact_DP_OFF_reused_pairs observed_detail_abstentions_logical observed_detail_abstentions_physical observed_fabricated_specific_target_details_physical observed_additional_personal_context_with_supplied_support_physical hedged_positive_affect_without_supplied_evidence_physical unnecessary_scope_extension_physical temporal_violations_under_original_identity_observed formal_status reward analysis_wide_blinding independent_human_review')
safe['logical_table']=[pick(r,'task_id arm physical_request_id exact_physical_reuse observed_target_detail_abstention observed_target_detail_fabrication supplied_session_count formal_status reward') for r in memory['logical_table']]
write('BATCH18_MEMORY_REVIEW.json',safe)
write('BATCH18_RS_REVIEW.json',read('batch18_rs_review/SUMMARY_PUBLIC.json'))
lineage=read('calibration/source-lineage-v1/SOURCE_LINEAGE_PRIVATE.json')
mapping={r['item_id']:r['component_id'] for r in lineage['item_mapping']}
component_rows=defaultdict(list)
for row in read('calibration/results-v2/CALIBRATION_RESULTS_PRIVATE.jsonl',True):
    component_rows[(mapping[row['item_id']],row['category'],row['method'])].append(row)
write('CALIBRATION_COMPONENT_RESULTS.json',[
    dict(component_id=c,category=k,method=m,**metrics(rows)) for (c,k,m),rows in component_rows.items()])
write('CALIBRATION_LINEAGE.json',dict(items=lineage['items'],original_labels=lineage['original_source_group_labels'],
    known_components=lineage['known_components'],components=[pick(r,'component_id items category_counts cross_construct_score') for r in lineage['components']],
    limitations=lineage['limitations'],semantic_qualification=False))
plan_names=[('M1','memory_packages/final-v2/representation-batch-1/PLAN.json'),
    ('M2','memory_packages/final-v2/representation-batch-2/PLAN.json'),
    ('W1','memory_packages/final-v2/writer8/PLAN.json'),
    ('U1','memory_packages/final-v2/mpme6/PLAN.json')]+[
    ('R'+str(i),'rs_complex/package-v2/batch-'+str(i).zfill(2)+'/PLAN.json') for i in range(1,5)]
catalog=[]
for label,name in plan_names:
    plan=read(name)
    assert plan['authorized'] is False
    request_path=Path(plan['requests_path'])
    assert hashlib.sha256(request_path.read_bytes()).hexdigest()==plan['requests_sha256']
    catalog.append(dict(label=label,plan_relative_path=name,plan_object_sha256=object_sha256(plan),
        plan_file_sha256=hashes[name],**pick(plan,'requests_sha256 max_calls max_model_loads warmup_calls automatic_retry global_seconds load_seconds request_seconds authorized')))
write('RUN_REQUEST_IDENTITIES.json',dict(plans=catalog,recommended_first=['M1','R1','W1'],
    recommended_calls=42,recommended_loads=3,recommended_hard_seconds=3600,
    all_scopes_authorized=False,automatic_continuation=False))
write('SOURCE_HASHES.json',hashes)

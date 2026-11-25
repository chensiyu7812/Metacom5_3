"""Explicit count/identity-only publication for actual T/S and J06 results."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from metacom_pm.rl1v3.io import file_sha256

FILES={
    'CPU_REPLAY_V1/REPLAY_RECEIPT.json':'CPU_REPLAY_RECEIPT.json',
    'joint/V2_ARITHMETIC_CORRECTION_RECEIPT.json':'ARITHMETIC_CORRECTION_RECEIPT.json',
    'TECHNICAL_MEASUREMENTS.json':'TS58_TECHNICAL_MEASUREMENTS.json',
    'JOINT_TECHNICAL_MEASUREMENTS.json':'JOINT96_TECHNICAL_MEASUREMENTS.json',
    'memory/REPRESENTATION_ORACLE_PUBLIC.json':'REPRESENTATION_ORACLE.json',
    'memory/validated-v1/TEMPORAL_AGGREGATE_PUBLIC.json':'TEMPORAL_AGGREGATE.json',
    'memory/validated-v1/TEMPORAL_TASK_TABLE_PUBLIC.json':'TEMPORAL_TASK_TABLE.json',
    'structured/paired_v1/AGGREGATE_PUBLIC.json':'STRUCTURED36_AGGREGATE.json',
    'structured/paired_v1/SOURCE_GROUP_METRICS_PUBLIC.json':'STRUCTURED36_SOURCE_GROUPS.json',
    'structured/format_diagnostic_v1/AGGREGATE_PUBLIC.json':'STRUCTURED_FORMAT_DIAGNOSTIC.json',
    'structured/format_diagnostic_v1/GROUP_DIAGNOSTIC_PUBLIC.json':'STRUCTURED_FORMAT_GROUPS.json',
    'structured/FORMAT_WRAPPER_CATEGORIES_PUBLIC.json':'STRUCTURED_WRAPPERS.json',
    'structured/DIAGNOSTIC_FIELD_DENOMINATORS_PUBLIC.json':'STRUCTURED_FIELD_DENOMINATORS.json',
    'structured/OBSERVABLE_FIELD_DIAGNOSTIC_PUBLIC.json':'STRUCTURED_FIELD_POLICY_DIAGNOSTIC.json',
    'joint/CPU_PATH_COST_PUBLIC.json':'JOINT_CPU_PATH_COST.json',
    'joint/fact-review-v1/FACTS_SUMMARY_PUBLIC.json':'JOINT_FACTS_SUMMARY.json',
    'joint/supply-audit-v1/SUMMARY_PUBLIC.json':'JOINT_SOURCE_SUPPLY.json',
    'joint/supply-audit-v1/OLD_RS12_IDENTITY_PUBLIC.json':'RS12_PRESERVED_IDENTITY.json',
    'joint/analysis-v2/AGGREGATE_PUBLIC.json':'JOINT_AGGREGATE.json',
    'joint/analysis-v2/FIXED_SOURCE_GROUPS_PUBLIC.json':'JOINT_FIXED_SOURCE_GROUPS.json',
    'joint/analysis-v2/FIXED_STRATA_PUBLIC.json':'JOINT_FIXED_STRATA.json',
    'joint/analysis-v2/INTERACTIONS_SOURCE_GROUPS_PUBLIC.json':'JOINT_INTERACTIONS_SOURCE_GROUPS.json',
    'joint/analysis-v2/INTERACTIONS_STRATA_PUBLIC.json':'JOINT_INTERACTIONS_STRATA.json',
    'joint/readback-v2/FOUR_ARM_CELLS_PUBLIC.json':'JOINT_FOUR_ARM_CELLS.json',
    'joint/analysis-v2/PAIR_TRANSITIONS_PUBLIC.json':'JOINT_PAIR_TRANSITIONS.json',
    'joint/analysis-v2/PAIR_TRANSITION_COUNTS_PUBLIC.json':'JOINT_PAIR_TRANSITION_COUNTS.json',
    'joint/analysis-v2/FAILURE_ATTRIBUTION_PUBLIC.json':'JOINT_FAILURE_ATTRIBUTION.json',
}
FORBIDDEN={'text','response','full_response','gold','premise','hypothesis',
    'evidence_quote','exact_quote','question','criterion','model_input','input_ids',
    'source_quotes','output_quotes','query','personal_fact_references','fact_review','support_review'}


def safe(value):
    if isinstance(value,dict):
        if set(value)&FORBIDDEN:raise ValueError('private content key in export: '+str(set(value)&FORBIDDEN))
        for v in value.values():safe(v)
    elif isinstance(value,list):
        for v in value:safe(v)


def write(path,value):
    safe(value)
    with path.open('x') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')


def export(root,out):
    root,out=Path(root),Path(out)
    # Validate the complete selection before making a partial public export.
    values={};hashes={}
    for relative,name in FILES.items():
        source=root/relative;value=json.loads(source.read_text());safe(value)
        values[name]=value;hashes[relative]=file_sha256(source)
    suite=ET.parse(root/'CPU_TESTS_FINAL.xml').find('testsuite')
    counts={k:int(suite.get(k)) for k in ('tests','errors','failures','skipped')}
    assert counts['errors']==counts['failures']==counts['skipped']==0
    catalog=root/'joint/RUN_CATALOG.json'
    assert file_sha256(catalog)=='0194b034edaa369b53d66eddd5318efeccd3f266f8cd4f86a93b09aca5575209'
    receipt=json.loads((root/'JOINT96_USER_AUTHORIZATION.json').read_text())
    assert receipt['approved'] and receipt['physical_calls']==96 and receipt['catalog_file_sha256']==file_sha256(catalog)
    plans=[]
    for p in json.loads(catalog.read_text())['plans']:
        auth=root/(p['label']+'_AUTHORIZED.json');a=json.loads(auth.read_text())
        assert a['authorized'] and a['plan_sha256']==p['plan_object_sha256']
        plans.append(dict(label=p['label'],plan_object_sha256=p['plan_object_sha256'],
            requests_sha256=p['requests_sha256'],authorization_sha256=file_sha256(auth),
            actual_execution_scope='16 calls, one load, zero warmup/retry, 1200 second hard limit'))
    values['JOINT_EXECUTION_IDENTITIES.json']=dict(catalog_sha256=file_sha256(catalog),plans=plans,
        approval_receipt_sha256=file_sha256(root/'JOINT96_USER_AUTHORIZATION.json'),
        authorization='Explicit fixed J06 approval in this conversation, separate from original 58.',
        other_requests_authorized=False,training_authorized=False)
    values['VALIDATION.json']=dict(cpu_tests=counts,test_xml_sha256=file_sha256(root/'CPU_TESTS_FINAL.xml'),
        formal_reward_qualified=False,original_history_preserved=True,
        publication='Counts, identities and code only. RAW/gold/full replies/private reviews remain local.',
        semantic_scope='Assistant development observations with uncertainty, not independent human qualification.')
    values['SOURCE_HASHES.json']=dict(inputs=hashes,export_code_sha256=file_sha256(__file__))
    out.mkdir(parents=True,exist_ok=False)
    for name,value in values.items():write(out/name,value)
    return dict(exported_files=len(values),raw_gold_or_full_reply_export=False)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','out'):p.add_argument('--'+name,required=True)
    print(json.dumps(export(**vars(p.parse_args())),indent=2))

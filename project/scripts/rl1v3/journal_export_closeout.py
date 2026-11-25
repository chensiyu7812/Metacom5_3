"""Export only reviewed counts, identities and CPU receipts from the closeout."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from metacom_pm.rl1v3.io import file_sha256, object_sha256

FILES={
    'TECHNICAL_MEASUREMENTS.json':'TECHNICAL_MEASUREMENTS.json',
    'memory/validated-v2/MEMORY12_AGGREGATE_PUBLIC.json':'MEMORY12_AGGREGATE.json',
    'memory/validated-v2/MEMORY12_PAIRS_PUBLIC.json':'MEMORY12_PAIRS.json',
    'memory/validated-v2/MEMORY12_TASK_TABLE_PUBLIC.json':'MEMORY12_TASK_TABLE.json',
    'memory/validated-v2/U1_AGGREGATE_PUBLIC.json':'U1_AGGREGATE.json',
    'memory/review-v1/U1_CHAIN_AGGREGATE_PUBLIC.json':'U1_CHAIN_IDENTITY.json',
    'memory/NAVIGATION_AGGREGATE_PUBLIC.json':'NAVIGATION_WRAPPERS.json',
    'rs_review/combined-v1/SUMMARY_PUBLIC.json':'RS12_AGGREGATE.json',
    'rs_review/combined-v1/TASK_TABLE_PUBLIC.json':'RS12_TASK_TABLE.json',
    'rs_review/combined-v1/INTERPRETATION_PUBLIC.json':'RS12_INTERPRETATION.json',
    'rs_review/R2/final/SUMMARY_PUBLIC.json':'R2_AGGREGATE.json',
    'rs_review/R3/final/SUMMARY_PUBLIC.json':'R3_AGGREGATE.json',
    'rs_review/R4/final/SUMMARY_PUBLIC.json':'R4_AGGREGATE.json',
    'human_review5/SUMMARY_PUBLIC.json':'FINITE_HUMAN_REVIEW5.json',
    'temporal22-v1/REQUEST_PUBLIC.json':'TEMPORAL22_REQUEST.json',
    'structured/packages-v2/PACKAGE_REPORT.json':'STRUCTURED18_PACKAGE.json',
    'structured/CPU_VALIDATION_RECEIPT.json':'STRUCTURED18_CPU_VALIDATION.json',
    'structured/endpoints-v1/PENDING_RECEIPT.json':'STRUCTURED36_PENDING_ENDPOINTS.json',
}
FORBIDDEN={'text','response','full_response','gold','premise','hypothesis',
    'evidence_quote','exact_quote','question','criterion','model_input','input_ids'}


def safe(value):
    if isinstance(value,dict):
        if set(value)&FORBIDDEN:raise ValueError('private content key in export')
        for v in value.values():safe(v)
    elif isinstance(value,list):
        for v in value:safe(v)


def write(path,value):
    safe(value)
    with path.open('x') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')


def export(root,out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=False);hashes={}
    for relative,name in FILES.items():
        p=root/relative;value=json.loads(p.read_text());write(out/name,value);hashes[relative]=file_sha256(p)
    plans=[]
    for prefix,package in [('T',root/'temporal22-v1'),('S',root/'structured/packages-v2')]:
        for i in (1,2):
            path=package/f'batch-{i:02d}'/'PLAN.json';p=json.loads(path.read_text())
            plans.append(dict(label=prefix+str(i),plan_object_sha256=object_sha256(p),plan_file_sha256=file_sha256(path),
                requests_sha256=p['requests_sha256'],protocol=p['protocol'],job_kind=p['job_kind'],
                physical_calls=p['max_calls'],logical_arms=p['logical_requests'],loads=1,warmup=0,retries=0,
                global_seconds=p['global_seconds'],authorized=False,model_calls=0,
                status='independent CPU admission complete; new explicit authorization required'))
    write(out/'NEW_RUN_REQUEST_IDENTITIES.json',dict(plans=plans,original76_authorization_not_transferable=True))
    xml=root/'CPU_TESTS_ALL.xml';suite=ET.parse(xml).find('testsuite')
    counts={k:int(suite.get(k)) for k in ('tests','errors','failures','skipped')}
    assert counts['errors']==counts['failures']==counts['skipped']==0
    write(out/'VALIDATION.json',dict(cpu_tests=counts,test_xml_sha256=file_sha256(xml),
        original_calibration96_modified=False,original_NLI64_modified=False,
        structured_G_calls=0,structured_reference_fixtures_are_not_G_success=True,
        publication='code and aggregate identities only; raw, gold, full replies and private review retained locally'))
    write(out/'SOURCE_HASHES.json',dict(inputs=hashes,export_code_sha256=file_sha256(__file__)))
    return dict(exported_files=len(list(out.glob('*.json'))),raw_gold_or_reply_export=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('root','out'):parser.add_argument('--'+name,required=True)
    print(json.dumps(export(**vars(parser.parse_args())),indent=2))

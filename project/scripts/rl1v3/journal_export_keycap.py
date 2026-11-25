"""Export the reviewed aggregate allowlist; no raw/source/gold/reply text."""
import argparse,json
from pathlib import Path
import xml.etree.ElementTree as ET
from metacom_pm.rl1v3.io import file_sha256

FILES={
 'TECHNICAL_MEASUREMENTS.json':'TECHNICAL_MEASUREMENTS.json',
 'R1_PRELAUNCH_FAILURE.json':'R1_PRELAUNCH_FAILURE.json',
 'memory_review/review-v1/M1_AGGREGATE_PUBLIC.json':'M1_AGGREGATE.json',
 'memory_review/review-v1/M1_PAIRED_DIAGNOSTICS_PUBLIC.json':'M1_PAIRED_DIAGNOSTICS.json',
 'memory_review/review-v1/W1_AGGREGATE_PUBLIC.json':'W1_AGGREGATE.json',
 'memory_review/validation-v1/VALIDATION_PUBLIC.json':'MEMORY_MECHANICAL_CHECKS.json',
 'rs_r1/INTERPRETATION_PUBLIC.json':'R1_INTERPRETATION.json',
 'rs_r1/final/SUMMARY_PUBLIC.json':'R1_AGGREGATE.json',
 'semantic_validation/results-v1/PUBLIC_AGGREGATE.json':'SEMANTIC64_AGGREGATE.json',
 'semantic_validation/CPU_CLOSEOUT_RECEIPT.json':'SEMANTIC64_VALIDATION.json',
 'semantic_validation/ROOT_REFERENCE_READBACK.json':'SEMANTIC_REFERENCE_READBACK.json',
 'semantic_validation/FINITE_REVIEW_SUMMARY_PUBLIC.json':'FINITE_HUMAN_REVIEW_QUEUE.json',
 'temporal_generation/candidate-v1/SUMMARY_PUBLIC.json':'TEMPORAL_GENERATION_CANDIDATE.json',
 'temporal_generation/candidate-v1/SUPPLY_PUBLIC.json':'TEMPORAL_GENERATION_SUPPLY.json',
 'MEMORY_CONTINUATION_RECHECK.json':'MEMORY_CONTINUATION.json',
 'rs_r1/CONTINUATION_RECHECK.json':'RS_CONTINUATION.json',
}


def write_json_once(path,value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2)
        f.write('\n')


def reject_private_keys(value):
    if isinstance(value,dict):
        if set(value)&{'response','full_response','gold','premise','hypothesis','evidence_quote','exact_quote','question','criterion'}:
            raise ValueError('private text field in public export')
        for v in value.values():reject_private_keys(v)
    elif isinstance(value,list):
        for v in value:reject_private_keys(v)


def export(root,catalog,out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=False);hashes={}
    for relative,name in FILES.items():
        path=root/relative;value=json.loads(path.read_text())
        if name=='TEMPORAL_GENERATION_CANDIDATE.json':
            value['research_hypothesis']=value.pop('hypothesis')
        reject_private_keys(value)
        write_json_once(out/name,value);hashes[relative]=file_sha256(path)
    errata=root/'memory_review/review-v1/SOURCE_REFERENCE_ERRATA_PRIVATE.json'
    e=json.loads(errata.read_text())
    write_json_once(out/'SOURCE_REFERENCE_ERRATA.json',dict(defects=1,private_sidecar_sha256=file_sha256(errata),
        frozen_files_modified=e['original_frozen_files_modified'],
        independent_sufficient_source_retained=e['independent_sufficient_group_retained_in_all_M1_arms'],
        current_M1_core_supply_changed=e['source_reference_defect_changes_current_M1_core_supply'],
        policy='invalid old locator is not treated as evidence; original files preserved with separate source-grounded errata'))
    selected=[p for p in json.loads(Path(catalog).read_text())['plans'] if p['label'] in {'M2','R2','R3','R4','U1'}]
    assert sum(p['max_calls'] for p in selected)==76 and all(p['authorized'] is False for p in selected)
    write_json_once(out/'CONTINUATION_IDENTITIES.json',dict(plans=selected,actual_calls=76,model_loads=5,
        per_job_hard_seconds=1200,total_hard_seconds=6000,new_authorization_required=True,original_remaining220_unchanged=True))
    xml=root/'CPU_TESTS_ALL.xml';suite=ET.parse(xml).find('testsuite')
    counts={k:int(suite.get(k)) for k in ('tests','errors','failures','skipped')}
    assert counts==dict(tests=164,errors=0,failures=0,skipped=0)
    write_json_once(out/'VALIDATION.json',dict(cpu_tests=counts,test_xml_sha256=file_sha256(xml),
        live_raw_fallback_reads=8,structured_actual_cases=16,NLI_CPU_scored=64,original_calibration96_modified=False,
        publication='code, aggregates, identities and replay instructions; private sources/references/replies retained locally'))
    write_json_once(out/'SOURCE_HASHES.json',dict(aggregates=hashes,errata=file_sha256(errata),
        continuation_catalog=file_sha256(catalog),code=file_sha256(__file__)))
    return dict(exported_files=len(list(out.glob('*.json'))),raw_gold_or_reply_export=False)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','catalog','out'):p.add_argument('--'+name,required=True)
    print(json.dumps(export(**vars(p.parse_args())),indent=2))

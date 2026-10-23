#!/usr/bin/env python3
"""Prepare, not execute, the ID-based citation transport on the SAME exam."""
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.judge_indexed import messages_and_schema,INDEXED_RUBRIC,INDEXED_RUBRIC_ID,VERSION
from metacom_pm.rl1.schema import digest
OUT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'


def main():
    exam=json.loads((OUT/'exam_private.json').read_text());dest=OUT/'indexed_citation_candidate_v2';dest.mkdir(exist_ok=True)
    requests=[]
    for j in exam['jobs']:
        messages,schema=messages_and_schema(j['evidence'],j['reply'])
        payload=dict(job_id=j['job_id'],messages=messages,json_schema=schema,draw_id=j['draw_id'],seed=j['seed'],
            rubric_identity=INDEXED_RUBRIC_ID,evidence_identity=digest(j['evidence']),reply_identity=digest(j['reply']))
        requests.append(dict(prepared_request_identity=digest(payload),**payload))
    path=dest/'requests_private.jsonl'
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in requests))
    (dest/'rubric.json').write_text(json.dumps(dict(identity=INDEXED_RUBRIC_ID,text=INDEXED_RUBRIC),ensure_ascii=False,indent=2)+'\n')
    (dest/'manifest.json').write_text(json.dumps(dict(status='PREPARED_NOT_EXECUTED_NOT_QUALIFIED',requests=len(requests),
        source_exam_sha256=sha256_file(OUT/'exam_private.json'),requests_sha256=sha256_file(path),
        rubric_identity=INDEXED_RUBRIC_ID,parser_version=VERSION,
        parser_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/judge_indexed.py'),script_sha256=sha256_file(Path(__file__)),
        proposed_local_transport='vLLM SamplingParams(structured_outputs=StructuredOutputsParams(json=schema)), reasoning_parser=qwen3; validate installed-backend compatibility before scoring',
        changed='output/citation representation only; ordinal q/m definitions retained; citations become whole source turns and response sentences',
        unchanged='same actual replies, evidence, preselected draw seeds and missing conditions; no generation or model-selection grid',
        model_calls=0,api_usd=0,limitations=['format validity does not establish semantic scoring validity',
            'whole-turn citation coarseness must be reviewed', 'full pilot and independent comparison still required before reward freeze']),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(prepared=len(requests),model_calls=0,rubric_identity=INDEXED_RUBRIC_ID)))


if __name__=='__main__':main()

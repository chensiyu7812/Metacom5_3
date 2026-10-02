#!/usr/bin/env python3
"""One explicit format clarification; preserve interrupted V1 and its attempts."""
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'
FORMAT_REQUIREMENT='''
MANDATORY OUTPUT FORMAT: claims MUST contain at least ONE inspected reply fragment.
Never return "claims": []. If the entire reply is general support/advice or an open
question with no factual claim, quote that reply (or a substantial exact fragment)
as verdict "nonfactual", evidence [], and explain why it makes no factual assertion.
Reflections of the user's reported state and factual presuppositions such as "Since
it isn't insomnia" ARE claims to inspect: quote them and cite the exact visible user
statement. Checking a nonfactual fragment is required even when there are zero material
factual claims. Do not invent a factual assertion merely to fill the list.
'''


def read(p):return json.loads(p.read_text())


def main():
    out=OUT/'review_format_v2';out.mkdir(exist_ok=True)
    if (out/'supervision_freeze.json').exists():raise RuntimeError('format repair already frozen')
    original=Path(read(OUT/'review_pointer.json')['run_dir'])
    with sqlite3.connect(original/'attempts.sqlite') as db:
        attempts=db.execute('SELECT request_id,status FROM attempts ORDER BY request_id').fetchall()
    assert len(attempts)<=192,'technical review reserve exceeded'
    # Original interrupted attempts remain untouched. New prompt -> new identities.
    rows=read(OUT/'review_jobs_private.json')
    for row in rows:
        row['messages'][0]['content']+='\n'+FORMAT_REQUIREMENT
        row['renderer_identity']=digest(row['messages'][0]['content'])
    protocol=read(OUT/'supervision_protocol.json')
    protocol['version']='p2-source-bound-weak-supervision-format-v2'
    protocol['review_prompt']+='\n'+FORMAT_REQUIREMENT
    protocol['format_clarifications']=1
    def save(name,obj):
        with (out/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    save('supervision_protocol.json',protocol)
    save('review_jobs_private.json',rows)
    save('format_deviation.json',dict(reason='V1 prompt omitted explicit minItems=1 while parser required a nonempty inspected-fragment list.',
        original_run=str(original),prior_attempts=len(attempts),prior_statuses=dict(Counter(s for _,s in attempts)),
        original_attempts=attempts,interrupted_running_are_unfinished_not_free=True,
        complete_original_summary_sha256=sha256_file(original/'summary.json'),
        new_review_slots=684,maximum_total_initial_review_starts=len(attempts)+684,
        accounting='Additional starts charge the pre-existing extra technical J reserve (192), not the 780 author-attempt cap.',
        author_regenerations=0,semantic_admission_rule_changed=False,
        format_revision_limit=1,no_further_format_prompt_search=True,API_usd=0))
    guards=[OUT/'supervision_freeze.json',OUT/'supervision_protocol.json',OUT/'review_jobs_private.json',
        OUT/'review_jobs_freeze.json',OUT/'source_evidence_private.json',OUT/'coordinator_pre_review_notes_private.json',
        Path(__file__),PROJECT/'scripts/rl1/82b_run_p2_review_format_fix.py']
    save('review_jobs_freeze.json',dict(status='ONE_FORMAT_CLARIFICATION_FROZEN',jobs=684,
        files={str(p.relative_to(PROJECT)):sha256_file(p) for p in guards+[out/'review_jobs_private.json']}))
    inherited=read(OUT/'supervision_freeze.json')
    save('supervision_freeze.json',dict(status='FORMAT_V2_BEFORE_NEW_REVIEWS',
        files={n:sha256_file(out/n) for n in ('supervision_protocol.json','review_jobs_private.json','review_jobs_freeze.json','format_deviation.json')},
        source_files=dict(inherited['source_files'],**{str(p.relative_to(PROJECT)):sha256_file(p) for p in guards})))
    print(json.dumps(dict(out=str(out),new_review_slots=684,prior_starts=len(attempts))))


if __name__=='__main__':main()

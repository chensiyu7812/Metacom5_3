#!/usr/bin/env python3
"""One bounded repair pass; reviewer-only facts never enter author prompts."""
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'
REPAIR_INSTRUCTION='''
Write a fresh supportive reply to the current user from ONLY the original visible
conversation and optional records above. A previous candidate failed source-admission
checks. Do not invent or inherit the historical supporter's words, relatives or life.
Attribute past reports as past; do not turn intention into action or an expected benefit
into an observed result. Do not assert what you cannot establish. You may ignore weak
or irrelevant resources and ask a useful non-presupposing question. Address the user's
current need naturally, without discussing the review, data, or this instruction.
No previous candidate, source-only fact or free-form reviewer feedback is supplied.
'''


def read(p):return json.loads(p.read_text())


def main():
    if (OUT/'repair_jobs_freeze.json').exists():raise RuntimeError('repairs already frozen')
    rows=read(OUT/'provisional_admission_private.json')['rows']
    slots={s['slot_id']:s for s in read(OUT/'authoring_slots_private.json')['slots']}
    audit_path=OUT/'coordinator_audit_decisions_private.json'
    audit=read(audit_path)
    assert audit['status']=='COMPLETE' and audit['independent_human_gold'] is False
    overrides={r['slot_id']:r for r in audit['rows'] if r['override_status'] is not None}
    eligible=[r for r in rows if r['status'] in ('reject','uncertain') and r['parsed'] and r['parsed']['repairable']]
    chosen=[]
    for split,limit in [('train',80),('dev',16)]:
        candidates=[r for r in eligible if r['split']==split and
                    overrides.get(r['slot_id'],{}).get('override_status')!='accept']
        chosen.extend(sorted(candidates,key=lambda r:digest(['pm-rl1-p2-repair-v1',r['slot_id']]))[:limit])
    jobs=[]
    for row in chosen:
        s=slots[row['slot_id']];messages=[dict(m) for m in s['messages']]
        messages[0]['content']+='\n\n'+REPAIR_INSTRUCTION
        jobs.append(dict(slot_id=s['slot_id'],index=s['index'],category=s['category'],split=s['split'],
            prefix_identity=s['prefix_identity'],attempt=1,seed=17,messages=messages,
            renderer_identity=digest([s['messages_identity'],REPAIR_INSTRUCTION]),
            original_messages_identity=s['messages_identity'],initial_author_request_id=row['author_request_id'],
            initial_review_request_id=row['review_request_id']))
    def save(n,v):
        with (OUT/n).open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    save('repair_jobs_private.json',jobs)
    save('repair_selection.json',dict(eligible=len(eligible),selected=len(jobs),by_split=dict(Counter(j['split'] for j in jobs)),
        max_per_slot=1,remaining_unrepaired=len(eligible)-len(jobs),feedback='Fixed generic correction; no SOURCE-only facts or freeform feedback',
        audit_overrides='Preserved separately; audited false accepts are excluded, not silently redrawn outside the frozen repair eligibility rule.'))
    guards=[OUT/'repair_jobs_private.json',OUT/'repair_selection.json',OUT/'provisional_admission_private.json',
            audit_path,OUT/'authoring_slots_private.json',Path(__file__)]
    save('repair_jobs_freeze.json',dict(status='FROZEN_BEFORE_ONE_REPAIR_PASS',jobs=len(jobs),
        files={str(p.relative_to(PROJECT)):sha256_file(p) for p in guards}))
    print(json.dumps(dict(repair_jobs=len(jobs),by_split=dict(Counter(j['split'] for j in jobs)))))


if __name__=='__main__':main()

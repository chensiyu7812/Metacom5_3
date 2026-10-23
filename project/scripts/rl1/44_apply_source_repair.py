#!/usr/bin/env python3
"""Freeze source-bound exclusions; audit their actual materialization effects."""
import json
from collections import defaultdict
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.source_repair import validate_overlay,repaired_as_of_memory

OUT=PROJECT/'outputs/pm_rl1/source_repair_20260929_v2'
RAW=PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
UNITS=PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'
PREV=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v1'

def save(name,obj):
    with (OUT/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def main():
    users=load_sanitized_runtime_users(RAW);um={u.owner_id:u for u in users}
    units=load_accepted_multi_view_units(UNITS,users=users);by=defaultdict(list)
    for u in units:by[u.owner_id].append(u)
    reviews=json.loads((OUT/'profile_reassertion_reviews.json').read_text())
    assert reviews['source_sha256']==sha256_file(UNITS)
    def rule(owner,sid,indices,rationale,slot=None):
        s=um[owner].session_by_id(sid);turns={t.idx:t for t in s.turns}
        return dict(owner=owner,session_id=sid,source_rank=s.chronological_rank,source_time=s.timestamp,
            evidence=[dict(turn_index=i,text=turns[i].content) for i in indices],rationale=rationale,
            **(dict(slot=slot,reviewed_superseding_unit_ids=[]) if slot else {}))
    overlay=dict(version='pm-rl1-source-overlay-v2',source_sha256=sha256_file(UNITS),raw_sha256=sha256_file(RAW),
        review_sha256=sha256_file(OUT/'profile_reassertion_reviews.json'),unit_reviews=reviews['rows'],
        temporal_blocks=[
            rule('p6','p6_conv_1',[4,8,10,12],
                 'Earlier close friendship is not available as current support after explicit loss of contact; esc858 itself was conditional fear of losing it, not a reported loss.',
                 'close_friend_status'),
            rule('p6','esc717',[4,8],
                 'Breakup makes the earlier current-partner slot uncertain; partner identity is unspecified, so quarantine rather than assert a particular relationship ended.',
                 'current_partner_status')],
        session_blocks=[rule('p8','esc995',[26,31],
            'Source explicitly identifies the drinking-workplace narrative as a portrayed scenario and denies abuse. Quarantine compiled claims pending separate scenario/person adjudication; preserve full MS.')],
        policy='Materialize latest strict-past MP first, then exclude; no automatic ancestor fallback. Unexcluded is not semantically approved.',
        reviewer='Codex coordinator AI-assisted development source review',independent_human_gold=False)
    validate_overlay(overlay,units=units,users=um)
    save('source_overlay_private.json',overlay)
    rows=[]
    for raw in json.loads((PREV/'roster_private.json').read_text()):
        p=prefix_from_dict(raw)
        _,receipt=repaired_as_of_memory(p,user=um[p.owner_id],units=by[p.owner_id],
            token_counter=lambda text:len(text),overlay=overlay)
        rows.append(dict(owner=p.owner_id,cutoff=p.cutoff_rank,**receipt))
    save('prior_prefix_projection_audit.json',dict(overlay_identity=digest(overlay),rows=rows,
        removed_occurrences=sum(len(r['removed']) for r in rows),
        removed_unique=len({x['candidate_id'] for r in rows for x in r['removed']}),
        old_experiment_rewritten=False,api_calls=0))
    print(json.dumps(dict(prefixes=len(rows),removed_occurrences=sum(len(r['removed']) for r in rows),overlay_identity=digest(overlay))))
if __name__=='__main__':main()

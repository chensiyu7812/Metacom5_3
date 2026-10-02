#!/usr/bin/env python3
"""Scope a provenance census to legal train/dev history, preserving old files."""
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.source_quarantine import profile_family,quarantine_decision,validate_quarantine_binding
OUT=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v1'
SOURCE=PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'

FINDINGS={
 'mvu_0506ef4aa5498802b8fd7e82':('mvu_cf220d41c423b152554bb558',
    'The July sleep statement was re-emitted with the November greeting as evidence. Greeting does not reaffirm daily sleep problems. Do not turn prior existence into recent/current confirmation.'),
 'mvu_034e83e13ea5e3719d96d5bb':('mvu_45d1b7d87ae9b42ac9766a87',
    'The earlier close friendship was re-emitted using a November statement about how things ended with Lisa. Prior/current conflict requires a slot transition review; restoring the earlier unit alone is unsafe.'),
 'mvu_dcc7e8a90e1350ce2374556f':('mvu_3bf9f1f537ed9d4cf8b551d2',
    'The earlier religious-community interest was copied into a later session about conflict with friends. The new citation does not reaffirm religious involvement or successful community support.'),
}

def save(name,obj):
    with (OUT/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def main():
    keys=json.loads((OUT/'coordinator_only/evidence_source_map.json').read_text())
    legal={(k['prefix']['owner_id'],s['session']) for k in keys for s in k['source_map']}
    compiled=[json.loads(line) for line in SOURCE.read_text().splitlines()]
    sessions=[r for r in compiled if (r['owner_id'],r['session_id']) in legal]
    units=[u for r in sessions for u in r['accepted_units']]
    by_id={u['memory_id']:u for u in units}
    if len(units)!=len(by_id):raise ValueError('duplicate memory IDs')
    parents={};reassertions=[]
    for u in sorted(units,key=lambda u:(u['owner_id'],u['source_session_rank'],u['memory_id'])):
        if 'profile_slot_key' not in u:continue
        family=profile_family(u);prior=parents.get(family)
        if prior and prior['normalized_value']==u['normalized_value']:
            reassertions.append(dict(owner=u['owner_id'],slot=u['profile_slot_key'],prior_id=prior['memory_id'],new_id=u['memory_id'],
                prior_date=prior['timestamp'],new_date=u['timestamp'],same_normalized_value=True,
                semantic_status='UNREVIEWED_REASSERTION_NOT_AUTOMATIC_ERROR'))
        parents[family]=u
    records=[]
    for bad,(prior_id,note) in FINDINGS.items():
        u=by_id[bad];prior=by_id[prior_id]
        record=dict(bad_unit_id=bad,bad_unit_identity=digest(u),family=profile_family(u),
            prior_unit_id=prior_id,prior_unit_identity=digest(prior),rationale=note,
            normalized_value=u['normalized_value'],prior_date=prior['timestamp'],reasserted_date=u['timestamp'],
            evidence=dict(prior_spans=prior['supporting_spans'],new_spans=u['supporting_spans']),
            severity='high for training provenance',confidence='direct source comparison; no causal claim about model internals',
            reviewer='Codex coordinator AI-assisted source review',independent_human_truth=False,
            disposition='quarantine entire MP slot pending source/time repair; preserve raw MS; never silently fall back to prior current-profile value')
        validate_quarantine_binding(record,u);records.append(record)
    contract=json.loads((OUT/'condition_contract_private.json').read_text())
    options=json.loads((OUT/'condition_options_private.json').read_text())
    selected=[]
    for c in contract['conditions']:
        if c['head'] not in ('MP','ME'):continue
        option=next(o for o in options[c['index']-1]['options'] if o['head']==c['head'])
        uid=option['resource']['source_ids'][0];u=by_id[uid]
        selected.append(dict(index=c['index'],condition=c['condition'],head=c['head'],memory_id=uid,
            unit_identity=digest(u),content=option['resource']['content'],supporting_spans=u['supporting_spans'],
            quarantine=quarantine_decision(u,records)))
    exposures=[]
    for spec in json.loads((OUT/'episode_specs_private.json').read_text()):
        for group in spec['inventory']:
            for r in group:
                if r['head']!='MP':continue
                u=by_id[r['source_ids'][0]];decision=quarantine_decision(u,records)
                exposures.append(dict(prefix_identity=digest(spec['prefix']),candidate_id=r['candidate_id'],**decision))
    save('source_quarantine_private.json',dict(status='CONFIRMED_LOCAL_QUARANTINE_NOT_COMPLETE_SOURCE_REPAIR',
        source_sha256=sha256_file(SOURCE),records=records,production_artifact_modified=False,
        compiler_prompt_already_prohibits_repeating_prior_facts_without_current_reaffirmation=True,
        interpretation='Structural span matching passed, while substantive reassertion failed; adding the same sentence to the prompt is not a demonstrated fix.'))
    save('source_census_private.json',dict(grain='accepted MP/ME unit in the union of legal past sessions of the 18 train/dev pilot prefixes',
        scope='No current future turns or test outcome analysis. Not a population error-rate estimate.',
        source_sha256=sha256_file(SOURCE),legal_sessions=len(legal),compiled_sessions=len(sessions),
        accepted_units=len(units),mp_units=sum('profile_slot_key' in u for u in units),me_units=sum('profile_slot_key' not in u for u in units),
        exact_value_reassertions=len(reassertions),reassertion_rows=reassertions,confirmed_bad_reassertions=len(records),
        selected_atomic_resource_exposures=len(selected),selected_unique_atomic_units=len({s['memory_id'] for s in selected}),
        selected_quarantined_exposures=sum(s['quarantine']['blocked'] for s in selected),
        top4_mp_exposures=len(exposures),top4_mp_quarantined_exposures=sum(s['blocked'] for s in exposures),
        selected_rows=selected,mp_exposure_rows=exposures,
        caveats=['Only the three listed failures are semantically adjudicated as source-refresh errors. Other reassertions may be legitimate.',
                 'Some selected atoms also need ontology/time qualifications: willingness to try is not a durable interest; last month anchors to source date; role-play is not a personal diagnosis.',
                 'A response can be acceptable after ignoring a flawed resource; that does not validate the resource.']))
    print(json.dumps(dict(legal_sessions=len(legal),units=len(units),reassertions=len(reassertions),confirmed_bad=len(records),
        selected_quarantined=sum(s['quarantine']['blocked'] for s in selected),top4_blocked=sum(s['blocked'] for s in exposures))))

if __name__=='__main__':main()

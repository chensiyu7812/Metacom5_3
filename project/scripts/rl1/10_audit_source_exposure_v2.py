#!/usr/bin/env python3
"""Verify amended full-history review lineage and quarantine shared descendants.

Construction only. Do not infer absence of semantic contamination from absence
of a literal match, or promote this roster to an untouched final test.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import iter_jsonl,sha256_file
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users,Target
from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.evaluation.human_reference import build_dg_reference
from metacom_pm.rl1.data import build_prefixes,stable_hash
from metacom_pm.rl1.schema import PrefixSpec,PublicTurn,digest
OUT=PROJECT/'outputs/pm_rl1/source_and_capacity_20260928_v1'


def save(name,obj):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name;text=json.dumps(obj,ensure_ascii=False,indent=2)+'\n'
    if p.exists() and p.read_text()!=text:raise RuntimeError('frozen artifact differs: '+str(p))
    p.write_text(text)


def main():
    source=PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    manifest_path=PROJECT/'data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json'
    pairs_path=PROJECT/'data/paper1_authority/paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl'
    users=load_sanitized_runtime_users(source);user_map={u.owner_id:u for u in users}
    manifest=json.loads(manifest_path.read_text());pairs=list(iter_jsonl(pairs_path))
    assert sha256_file(source)==manifest['source_sha256']['sanitized_runtime']
    req_path=PROJECT/manifest['teacher_request_manifest']['path']
    assert sha256_file(req_path)==manifest['teacher_request_manifest']['sha256']
    verified=[]
    for lineage in manifest['DG_reference_lineage']:
        pair=next(p for p in pairs if p['task']=='DG' and p['target_id']==lineage['target_id'])
        target=Target(target_id=lineage['target_id'],task_type=TaskType.DIALOGUE_GENERATION,
            owner_id=lineage['owner_id'],primary_group_key=lineage['target_id'],cutoff_rank=lineage['cutoff_rank'],
            visible_query_text=None)
        view,rebuilt=build_dg_reference(user=user_map[lineage['owner_id']],target=target,excerpt=pair['reference_material'])
        assert rebuilt==lineage
        verified.append(rebuilt)
    source_lineage={r['owner_id']:r for r in verified}
    original,census=build_prefixes(users);splits=census['owner_split']
    branches={}
    for group in census['shared_transcript_groups']:
        if len({r['split'] for r in group})>1:
            for row in group:branches[row['owner']]=min(branches.get(row['owner'],10**9),row['rank'])
    eligible=defaultdict(list);excluded=[]
    for user in users:
        for session in user.sessions:
            if session.chronological_rank<1:continue
            if user.owner_id in branches and session.chronological_rank>=branches[user.owner_id]:
                excluded.append(dict(owner=user.owner_id,session=session.session_id,rank=session.chronological_rank,
                    reason='known shared source session or descendant in full legal history'))
                continue
            cuts=[i for i,t in enumerate(session.turns[:-1]) if t.role=='seeker' and session.turns[i+1].role=='supporter']
            if not cuts:continue
            cut=min(cuts,key=lambda i:stable_hash(f'pm-rl1-census-prefix-v1|{user.owner_id}|{session.session_id}|{i}'))
            p=PrefixSpec(user.owner_id,session.session_id,session.chronological_rank,cut,session.timestamp,
                splits[user.owner_id],tuple(PublicTurn(t.role,t.content) for t in session.turns[:cut+1]))
            eligible[user.owner_id].append(p)
    amounts={split:min(16 if split=='test' else 8,min(len(eligible[o]) for o,s in splits.items() if s==split)) for split in ['train','dev','test']}
    selected=[]
    for owner,group in eligible.items():
        selected.extend(sorted(group,key=lambda p:stable_hash('pm-rl1-census-session-v1|'+p.owner_id+'|'+p.session_id))[:amounts[splits[owner]]])
    exposures=[]
    for p in selected:
        dg=source_lineage.get(p.owner_id)
        exposures.append(dict(prefix=p.identity,owner=p.owner_id,split=p.split,
            current_session_and_suffix_in_verified_old_full_history=bool(dg and p.session_id in dg['source_session_ids']),
            prior_reference_protocol='full-history v2' if dg else 'no verified full-history DG review for this owner',
            prior_full_history_reference_sha256=dg['reference_sha256'] if dg else None,
            old_base_pair_ids=[r['base_pair_id'] for r in pairs if r['owner_or_dialogue_group']==p.owner_id],
            old_QA_Summary_references_require_fact_level_interpretation=any(r['task'] in ('QA','Summary') and r['owner_or_dialogue_group']==p.owner_id for r in pairs)))
    save('prefixes_private.json',[asdict(p) for p in selected])
    save('source_exposure_v2.json',dict(status='SOURCE_GROUPED_DEVELOPMENT_ROSTER_NOT_UNTOUCHED_TEST',
        source_sha256=sha256_file(source),old_manifest_sha256=sha256_file(manifest_path),
        old_teacher_requests_sha256=sha256_file(req_path),verified_old_full_history_lineages=verified,
        distinction='v1 preflight reference_material was an excerpt; amended v2 contained the complete history. Exact v1 substring matches are only a lower bound.',
        shared_source_groups=census['shared_transcript_groups'],quarantined_branches=branches,excluded_sessions=excluded,
        owner_split_unchanged=True,per_owner_amount=amounts,selected_by_split=dict(Counter(p.split for p in selected)),
        rows=exposures,exposure_counts_by_split={s:sum(r['split']==s and r['current_session_and_suffix_in_verified_old_full_history'] for r in exposures) for s in amounts},
        permitted_claim='held out from NEW parameter optimization, with prior research exposure explicitly disclosed',
        prohibited_claim='sealed, researcher-unseen confirmatory test',
        remaining=['semantic paraphrase/fact-family links beyond exact session identity not exhaustively certified',
                   'no newly independent final human review has been returned',
                   'if an untouched confirmation set is required, obtain new source families rather than rename these owners']))
    save('manifest.json',dict(script_sha256=sha256_file(Path(__file__)),
        artifacts={f:sha256_file(OUT/f) for f in ['prefixes_private.json','source_exposure_v2.json']},
        no_outcome_scores_used=True,calls=0,formal_parameter_training_started=False))
    print(json.dumps(dict(selected=dict(Counter(p.split for p in selected)),per_owner=amounts,
        full_history_exposed={s:sum(r['split']==s and r['current_session_and_suffix_in_verified_old_full_history'] for r in exposures) for s in amounts},quarantine=branches),indent=2))


if __name__=='__main__':main()

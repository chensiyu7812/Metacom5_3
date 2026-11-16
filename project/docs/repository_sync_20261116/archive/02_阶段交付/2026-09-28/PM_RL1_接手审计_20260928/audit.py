"""Read-only repository/artifact audit; writes only beside this file.

Run with the existing paper1-py311 Python. No generation, scoring, or paid API.
Census is preliminary: no split/prompt/budget is frozen by this script.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path('/home/tokkio/Metacom5_3').resolve()
PROJECT = REPO / 'project'
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT / 'src'))

from metacom_pm.io import canonical_json, iter_jsonl, read_json, sha256_file, sha256_text
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.memory_source import Target, load_sanitized_runtime_users
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units
from metacom_pm.paper1.multi_view_memory.candidate_adapter import materialize_multi_view_candidates
from metacom_pm.paper1.execution.packing import RankedCandidate, pack_ranked_prefix


def shell(*args):
    return subprocess.check_output(args, cwd=REPO, text=True).strip()


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def dist(values):
    values = sorted(values)
    return dict(n=len(values), min=values[0], median=statistics.median(values),
                p95=values[min(len(values)-1, int(.95 * len(values)))], max=values[-1]) if values else {}


def run():
    status = shell('git', 'status', '--porcelain=v1', '--untracked-files=all')
    dirty_paths = [line[3:] for line in status.splitlines()]
    # Preserve leading spaces stripped by shell() for the first status line.
    raw_status = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=REPO, text=True)
    dirty_paths = [line[3:] for line in raw_status.splitlines()]
    dirty_hashes = {p: sha256_file(REPO / p) for p in dirty_paths if (REPO / p).is_file()}
    remote = shell('git', 'ls-remote', '--heads', 'origin')
    dump('repository_snapshot.json', dict(captured_at=datetime.now(timezone.utc).isoformat(),
         root=str(REPO), head=shell('git', 'rev-parse', 'HEAD'), branch=shell('git', 'branch', '--show-current'),
         status=raw_status, dirty_file_sha256=dirty_hashes, remote_heads=remote,
         new_plan_sha256=sha256_file('/home/tokkio/PM_RL1_单轮资源选择与执行_环境及训练实施方案_20260928.md')))
    cal = PROJECT / 'outputs/paper1_calibration'
    package = cal / 'static_sample_20260917_v1'
    prep = read_json(package / 'preparation_summary.json')
    checks = {p: sha256_file(package / p) == h for p, h in prep['package_artifacts'].items()}
    source_checks = {p: sha256_file(PROJECT / p) == h for p, h in prep['sources'].items()}
    requests = list(iter_jsonl(package / 'generator_requests.jsonl'))
    generation = cal / 'static_generation_20260917_v1'
    manifest = read_json(generation / 'manifest.json')
    responses = {p.stem: read_json(p) for p in (generation / 'responses').glob('*.json')}
    errors = []
    for r in requests:
        digest = sha256_text(canonical_json({k: r[k] for k in ['generator_config_sha256', 'messages']}))
        if digest != r['request_sha256']:
            errors.append([r['request_id'], 'request_hash'])
        saved = responses.get(r['request_id'])
        if not saved:
            errors.append([r['request_id'], 'missing_response'])
            continue
        if any(saved[k] != v for k, v in r.items() if k != 'messages'):
            errors.append([r['request_id'], 'response_binding'])
        if saved['identity_sha256'] != manifest['identity_sha256']:
            errors.append([r['request_id'], 'runtime_identity'])
        if not saved.get('raw_output', '').strip():
            errors.append([r['request_id'], 'empty_output'])
    payloads = list(iter_jsonl(cal / 'static_official_scoring_20260917_v1/requests.jsonl'))
    unique = {r['call_hash']: r for r in payloads}
    payload_errors = []
    for r in payloads:
        p = generation / 'responses' / (r['request_id'] + '.json')
        if sha256_file(p) != r['generator_result_sha256']:
            payload_errors.append([r['request_id'], 'generation_file_hash'])
        if sha256_text(responses[r['request_id']]['raw_output']) != r['prediction_sha256']:
            payload_errors.append([r['request_id'], 'prediction_hash'])
        if sha256_text(canonical_json(r['body'])) != r['call_hash']:
            payload_errors.append([r['request_id'], 'body_hash'])
    ledger_path = PROJECT / 'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    ledger = CumulativePaper1ApiBudgetLedger(ledger_path)
    boundary = read_json(PROJECT / 'outputs/paper1_api_budget/followup_budget_boundary_20260918_v1.json')
    attempts = list(iter_jsonl(generation / 'attempts.jsonl'))
    offs = Counter(r['target_id'] for r in requests if r['head'] is None and r['k'] == 0)
    audit = dict(package_hash_checks=checks, source_hash_checks=source_checks,
        request_count=len(requests), unique_request_ids=len({r['request_id'] for r in requests}),
        response_count=len(responses), binding_errors=errors,
        status=dict(Counter(r['status'] for r in responses.values())),
        finish_reasons=dict(Counter(r['finish_reason'] for r in responses.values())),
        attempts=dict(Counter(r['event'] for r in attempts)),
        natural_ends=sum(r['natural_end'] for r in responses.values()),
        generation_seconds=sum(r['seconds'] for r in responses.values()),
        output_tokens=sum(r['output_tokens'] for r in responses.values()),
        output_length_by_task={task: dist([r['output_tokens'] for r in responses.values() if r['task']==task]) for task in ['qa','summary']},
        shared_off_targets=len(offs), exactly_one_off_per_target=all(v==1 for v in offs.values()),
        payload_count=len(payloads), unique_payloads=len(unique), payload_binding_errors=payload_errors,
        unique_payloads_by_task=dict(Counter(r['task'] for r in unique.values())),
        input_tokens_with_framing_reserve=sum(r['estimated_input_tokens_with_framing_reserve'] for r in unique.values()),
        actual_score_files=sum(1 for d in [cal/'static_official_scores_20260917_v1',cal/'static_official_batch_20260918_v1/scores'] for p in d.glob('**/*.json') if p.name!='preflight.json'),
        generator_runner_hash_matches=sha256_file(PROJECT/'scripts/paper1/79_run_static_amount_generation.py')==manifest['runner_sha256'],
        budget=dict(accounted_usd=str(ledger.accounted_cost_usd), unsettled=len(ledger.unsettled_reservations()),
                    unchanged_since_boundary=sha256_file(ledger_path)==boundary['baseline_ledger_sha256'],
                    baseline=boundary['baseline_accounted_usd'], target=boundary['target_usd'], hard_cap=boundary['hard_cap_usd']))
    dump('legacy_artifact_audit.json', audit)
    print('legacy', json.dumps({k:audit[k] for k in ['request_count','response_count','binding_errors','payload_binding_errors','unique_payloads','budget']}), flush=True)

    source = PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    units_path = PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'
    users = load_sanitized_runtime_users(source)
    units = load_accepted_multi_view_units(units_path, users=users)
    by_owner = defaultdict(list)
    for unit in units:
        by_owner[unit.owner_id].append(unit)
    counter = build_llama_token_counter(Path(manifest['model_dir'])/'tokenizer.json')
    owners = sorted([u.owner_id for u in users], key=lambda o: sha256_text('pmseq-v2-owner|'+o))
    split = {o: 'train' if i<12 else 'dev' if i<15 else 'test' for i,o in enumerate(owners)}
    rows, prefixes, candidates_by_id = [], [], {}
    for user in users:
        legal_sessions, choices = 0, 0
        owner_prefixes = []
        for session in user.sessions:
            if session.chronological_rank == 0:
                continue
            cuts = [i for i,t in enumerate(session.turns[:-1]) if t.role=='seeker' and session.turns[i+1].role=='supporter']
            if not cuts:
                continue
            legal_sessions += 1
            choices += len(cuts)
            # A deterministic preliminary cut, not a final sampling freeze.
            cut = min(cuts,key=lambda i:sha256_text(f'pm-rl1-census-prefix-v1|{user.owner_id}|{session.session_id}|{i}'))
            visible = '\n'.join(f'{t.role}: {t.content}' for t in session.turns[:cut+1])
            target = Target(target_id=f'{user.owner_id}::{session.session_id}::cut{cut}',
                task_type=TaskType.DIALOGUE_GENERATION, owner_id=user.owner_id,
                primary_group_key=session.session_id, cutoff_rank=session.chronological_rank, visible_query_text=visible)
            cands = materialize_multi_view_candidates(tuple(by_owner[user.owner_id]),user=user,target=target,token_counter=counter)
            for head,cs in cands.items():
                for c in cs:
                    if c.candidate_id not in candidates_by_id:
                        packed=pack_ranked_prefix(head=head,ranked=[RankedCandidate(c,0.0)],k=1,
                            target_owner_id=user.owner_id,token_counter=counter)
                        candidates_by_id[c.candidate_id]=dict(head=head.value,raw_tokens=c.token_count,
                            old_single_item_envelope_tokens=packed.rendered_resource_tokens)
            counts={h.value:len(cs) for h,cs in cands.items()}
            collisions=sum(bool(c.raw_descriptors.get('same_rank_slot_collision')) for c in cands[Head.MP])
            owner_prefixes.append(dict(owner=user.owner_id,split=split[user.owner_id],session_id=session.session_id,
                cutoff_rank=session.chronological_rank,cut_after_turn_index=cut,prefix_sha256=sha256_text(visible),
                visible_plain_text_tokens=counter(visible),candidate_counts=counts,same_rank_mp_collision_units=collisions,
                me_action_outcome_count=sum(bool(c.raw_descriptors.get('action_observed_outcome_subtype')) for c in cands[Head.ME])))
        limit=16 if split[user.owner_id]=='test' else 8
        selected=sorted(owner_prefixes,key=lambda p:sha256_text('pm-rl1-census-session-v1|'+p['owner']+'|'+p['session_id']))[:limit]
        for p in owner_prefixes:
            p['preliminary_selected']=p in selected
        prefixes.extend(owner_prefixes)
        rows.append(dict(owner=user.owner_id,split=split[user.owner_id],sessions=len(user.sessions),
            legal_memory_sessions=legal_sessions,all_pre_supporter_cut_choices=choices,preliminary_selected=len(selected),
            selected_prefix_tokens=dist([p['visible_plain_text_tokens'] for p in selected])))
    rs_id_path=PROJECT/'data/paper1_public_rs/esconv_strategy_source_identity_dialogue_only_v2.jsonl'
    rs_ids=list(iter_jsonl(rs_id_path))
    rs_dialogues={r['source_dialogue_id'] for r in rs_ids}
    import re
    seed_overlaps=[]
    source_splits = {r['dialogue_id']: r for r in iter_jsonl(PROJECT/'data/strategy/esconv_split_manifest_v1_5.jsonl')}
    transcript_groups = defaultdict(list)
    for user in users:
        for session in user.sessions:
            transcript_hash = sha256_text(canonical_json([(t.role,t.content) for t in session.turns]))
            transcript_groups[transcript_hash].append(dict(owner=user.owner_id,split=split[user.owner_id],
                session_id=session.session_id,rank=session.chronological_rank))
            match=re.fullmatch(r'esc(\d+)',session.session_id)
            if match:
                mapped=f'esconv_{int(match[1]):04d}'
                seed_overlaps.append(dict(owner=user.owner_id,session_id=session.session_id,
                    mapped_rs_dialogue=mapped,present_in_rs_source_index=mapped in rs_dialogues,
                    explicitly_excluded_in_existing_esconv_split=source_splits.get(mapped,{}).get('excluded_for_evoemo_overlap'),
                    mapping_status='Existing ESConv index linkage; source transcript equivalence not re-audited here'))
    census=dict(status='PRELIMINARY_SOURCE_CENSUS_NOT_FROZEN_DATASET',source_sha256=sha256_file(source),
        unit_artifact_sha256=sha256_file(units_path),compiler_full_source_chain_validation='passed',
        owner_count=len(users),session_count=sum(len(u.sessions) for u in users),accepted_units=len(units),
        accepted_by_head=dict(Counter(u.head.value for u in units)),
        proposed_hash_split=split,existing_compatible_split='not located in current paper1 authority/config/docs searches',
        owner_rows=rows,eligible_sessions=len(prefixes),possible_cuts=sum(r['all_pre_supporter_cut_choices'] for r in rows),
        selected_by_split=dict(Counter(p['split'] for p in prefixes if p['preliminary_selected'])),
        selected_prefix_plain_text_tokens=dist([p['visible_plain_text_tokens'] for p in prefixes if p['preliminary_selected']]),
        old_envelope_capacity_by_head={h:dict(tokens=dist([c['old_single_item_envelope_tokens'] for c in candidates_by_id.values() if c['head']==h]),
            over_cap={str(b):sum(c['old_single_item_envelope_tokens']>b for c in candidates_by_id.values() if c['head']==h) for b in [1024,2048,4096]}) for h in ['MP','MS','ME']},
        seed_overlap_candidates=seed_overlaps,
        cross_owner_exact_transcript_groups=[group for group in transcript_groups.values() if len({r['owner'] for r in group})>1],
        limitations=['No BGE reranking for new prefixes; no RS inventory constructed.',
                    'Capacity uses existing single-item typed envelopes, not frozen RL1 combined renderer/chat context.',
                    'No fact-family/exposure-complete split audit, no measured outcomes, no test generation.',
                    'The future suffix is excluded from prefix text, but all-source construction occurs in offline audit domain.'])
    dump('prefix_census.json',census)
    dump('prefix_manifest_preliminary.json',prefixes)
    dump('candidate_capacity_preliminary.json',candidates_by_id)
    unchanged={p:sha256_file(REPO/p)==h for p,h in dirty_hashes.items()}
    dump('preservation_check.json',dict(all_preexisting_dirty_files_unchanged=all(unchanged.values()),files=len(unchanged)))
    print('census', json.dumps({k:census[k] for k in ['owner_count','session_count','accepted_units','accepted_by_head','eligible_sessions','possible_cuts','selected_by_split','selected_prefix_plain_text_tokens']}),flush=True)


if __name__=='__main__':
    run()

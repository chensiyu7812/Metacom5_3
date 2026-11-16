#!/usr/bin/env python3
"""Offline accounting only. No network, model inference, key or sealed-label access.

Reads frozen train/dev inventories and existing generation receipts. Test prefixes
are counted by split only; the test source text is neither rendered nor selected.
Writes only to a new output directory; rerun with --out to a fresh directory.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

REPO = Path('/home/tokkio/Metacom5_3').resolve()
PROJECT = REPO / 'project'
ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2'
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.rl1.schema import HEADS, PLANS, EpisodeSpec, Resource, digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.judge_completion_candidate import messages_and_schema
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger

SOURCES = {}
CHECKS = Counter()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def record(p):
    p = Path(p).resolve()
    SOURCES[str(p)] = sha(p)
    return p


def read(p):
    return json.loads(record(p).read_text())


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    CHECKS[label] += 1


def write(out, name, value):
    with (out / name).open('x', encoding='utf8') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def csv_write(out, name, rows):
    import csv
    with (out / name).open('x', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                        for k, v in row.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    out = args.out
    baseline = dict(branch=subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip(),
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        status=subprocess.check_output(['git','status','--short'],cwd=REPO,text=True).splitlines())
    baseline['existing_work_hashes'] = {line[3:]: sha(REPO / line[3:]) for line in baseline['status']
                                      if (REPO / line[3:]).is_file()}
    # Check the whole previous delivery, not just its aggregate conclusion.
    prior_manifest_path = PROJECT / 'outputs/pm_rl1/p3_v2_development_audit_20261014/delivery_manifest.json'
    prior_manifest = read(prior_manifest_path)
    for p, item in prior_manifest['files'].items():
        check(sha(record(p)) == item['sha256'], 'previous_development_delivery_preserved')
    original_zip = Path('/home/tokkio/PM_RL1_Chen_Du_标注导出包.zip')
    check(sha(record(original_zip)) == '630d09d7d275febb802e922fab182da9244af36d8388aef26ff6721ba684e7ee',
          'original_annotation_zip_preserved_without_decryption')
    write(out, 'baseline.json', baseline)
    contract = read(PROJECT / 'docs/pm_rl1_completion_20260930_v2/execution_contract.json')
    p1 = ROOT / 'P1'; pool = ROOT / 'P2/common_pool'
    freeze = read(pool / 'input_freeze.json')
    for name, expected in freeze['files'].items():
        check(sha(record(pool / name)) == expected, 'pool_frozen_file_hash')
    for name, expected in freeze['source_files'].items():
        check(sha(record(PROJECT / name)) == expected, 'pool_source_hash')
    executor = read(ROOT / 'P2/executor_freeze.json')
    check(executor['selected'] == 'epoch_3', 'selected_executor_epoch3')
    specs_raw = read(p1 / 'episode_specs_private.json')
    specs = [EpisodeSpec(**dict(s, prefix=prefix_from_dict(s['prefix']),
        inventory=tuple(tuple(Resource(**dict(r, source_ids=tuple(r['source_ids']))) for r in head)
                        for head in s['inventory']))) for s in specs_raw]
    caps = read(p1 / 'capacity_prefix_private.json')
    check(len(caps) == len(specs) == 114, '114_train_dev_specs')
    p1freeze = read(p1 / 'renderer_freeze.json')
    # Tokenization is deterministic CPU preprocessing, never a model forward pass.
    from transformers import AutoTokenizer
    model = Path(executor['primary_runtime']['model_dir'])
    for name in ['tokenizer.json','tokenizer_config.json','config.json']:
        record(model / name)
    tok = AutoTokenizer.from_pretrained(model, local_files_only=True)
    @lru_cache(maxsize=50000)
    def count(text):
        return len(tok.encode(text, add_special_tokens=False))
    renderer = DirectReplyRenderer(count_text=count,
        count_chat=lambda m: len(tok.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=p1freeze['tokenizer_identity'],
        context_limit=read(model / 'config.json')['max_position_embeddings'])
    check(renderer.identity == executor['renderer_identity'] == freeze['renderer_identity'], 'active_renderer_identity')
    coverage = []
    for i, (spec, cap) in enumerate(zip(specs, caps)):
        check(spec.prefix.identity == cap['prefix_identity'] and i == cap['index'], 'capacity_prefix_join')
        actual = ResourceEnv(spec, renderer).observe().initial_plan_mask
        check(list(actual) == cap['initial_plan_mask'], 'recomputed_all70_action_masks')
        for hi, head in enumerate(HEADS):
            ks = [k for k in range(5) if actual[PLANS.index(tuple(k if j == hi else 0 for j in range(4)))]]
            check(ks == list(range(max(ks)+1)), 'single_head_ancestry')
            coverage.append(dict(index=i, prefix_identity=spec.prefix.identity, owner=spec.prefix.owner_id,
                                 split=spec.prefix.split, head=head, legal_doses=ks, terminals=len(ks)))
    totals = {h: sum(r['terminals'] for r in coverage if r['head']==h) for h in HEADS}
    order = ['ME','MP','RS','MS']
    selected = min(HEADS, key=lambda h:(-totals[h], order.index(h)))
    check(selected == 'RS', 'head_selection_by_coverage_only')
    coverage_summary = [dict(head=h, **{s: sum(r['terminals'] for r in coverage if r['head']==h and r['split']==s)
                                     for s in ['train','dev']}, total=totals[h]) for h in HEADS]
    csv_write(out, 'head_coverage.csv', coverage_summary)
    csv_write(out, 'prefix_head_coverage.csv', coverage)

    slots = read(pool / 'slots_private.json')['rows']
    run = Path(read(pool / 'primary_generation_pointer.json')['run_dir'])
    summary = read(run / 'summary.json')
    rows = {r['slot_id']: r for r in summary['rows']}
    check(len(rows) == len(slots) == 586, '586_unique_main_reply_slots')
    frozen_runtime = executor['primary_runtime']['identity']
    raw_by_key = {}; artifact_rows = []
    for slot in slots:
        row = rows[slot['slot_id']]
        rid = row['request_id']
        request = read(run / (rid + '.request.json'))
        raw_path = run / (rid + '.raw.json'); raw = read(raw_path)
        check(sha(raw_path) == row['raw_sha256'], 'raw_response_hash')
        check(digest({k:v for k,v in request.items() if k!='request_id'}) == rid, 'request_identity')
        check(request['executor_identity'] == raw['runtime_identity'] == frozen_runtime, 'executor_runtime_binding')
        check(request['draw_identity'] == executor['terminal_draw_identity'], 'terminal_draw_binding')
        check(request['renderer_identity'] == renderer.identity, 'reply_renderer_binding')
        p = request['provenance']; spec = specs[slot['index']]
        check(p['prefix_identity'] == slot['prefix_identity'] == spec.prefix.identity, 'reply_prefix_binding')
        check(p['inventory_identity'] == digest(specs_raw[slot['index']]['inventory']), 'reply_inventory_binding')
        check(p['retrieval_identity'] == spec.retrieval_identity, 'reply_retrieval_binding')
        check(p['canonical_counts'] == slot['counts'], 'reply_plan_binding')
        check(raw['source_provenance_identity'] == digest(p), 'raw_provenance_binding')
        check(request['messages'] == slot['messages'] == renderer.messages(spec, tuple(slot['counts'])), 'exact_rendered_messages')
        check(raw['finish_reason'] == 'natural_stop' and bool(raw['text'].strip()), 'natural_nonempty_reply')
        key = (slot['prefix_identity'], tuple(slot['counts']))
        check(key not in raw_by_key, 'one_canonical_reply_per_terminal')
        raw_by_key[key] = dict(row=row, raw=raw, path=str(raw_path))
    train_indices = sorted({s['index'] for s in slots if s['split']=='train'})
    check(len(train_indices)==24 and set(Counter(specs[i].prefix.owner_id for i in train_indices).values())=={2}, 'frozen_train24_two_per_owner')
    train_by_owner = defaultdict(list)
    for i,s in enumerate(specs):
        if s.prefix.split == 'train': train_by_owner[s.prefix.owner_id].append(i)
    expected_train = sorted(i for choices in train_by_owner.values() for i in sorted(choices,
        key=lambda j:digest(['p2-common-train-prefix-v1',17,specs[j].prefix.identity]))[:2])
    check(expected_train == train_indices, 'train24_seed17_selection_reproduced')
    dev_indices = [i for i,s in enumerate(specs) if s.prefix.split=='dev']
    b1_rows=[]
    for i in train_indices + dev_indices:
        spec=specs[i]
        for k in range(5):
            plan=(k,0,0,0)
            existing=raw_by_key.get((spec.prefix.identity,plan))
            b1_rows.append(dict(index=i,owner=spec.prefix.owner_id,split=spec.prefix.split,
                selection_status='frozen_train24' if i in train_indices else 'dev6_not_selected_candidate18',
                prefix_identity=spec.prefix.identity,head='RS',dose=k,counts=list(plan),
                resource_tokens=renderer.cost(spec,plan),reusable=bool(existing),
                request_id=existing['row']['request_id'] if existing else None,
                raw_path=existing['path'] if existing else None,
                raw_sha256=existing['row']['raw_sha256'] if existing else None,
                reply_text_identity=digest(existing['raw']['text']) if existing else None,
                missing_reason=None if existing else 'RS3_RS4_not_in_frozen_P2_menu'))
    trainrows=[r for r in b1_rows if r['split']=='train']; devrows=[r for r in b1_rows if r['split']=='dev']
    check(len(trainrows)==120 and sum(r['reusable'] for r in trainrows)==72, 'B1_train120_reuse72_missing48')
    per_dev=Counter(r['index'] for r in devrows if r['reusable'])
    check(len(per_dev)==18 and set(per_dev.values())=={3}, 'any_two_per_owner_dev6_reuse18_missing12')
    # Frozen split metadata only; no test text, labels, rewards, or ranking materialization.
    prefix_path=PROJECT / 'outputs/pm_rl1/source_and_capacity_20260928_v1/prefixes_private.json'
    prefixes=read(prefix_path)
    check(Counter(p['split'] for p in prefixes)==dict(train=96,dev=18,test=48), 'frozen_96_18_48_split')
    check({digest(p) for p in prefixes if p['split']!='test'}=={s.prefix.identity for s in specs}, 'same_frozen_prefix_universe')
    test_count=sum(p['split']=='test' for p in prefixes)
    test_owner_counts=Counter(p['owner_id'] for p in prefixes if p['split']=='test')
    check(len(test_owner_counts)==3 and set(test_owner_counts.values())=={16}, 'test48_three_owners')
    # No claim of exact test reachability without the active inventory/ranking.
    b1_summary=dict(head=selected,selection_basis='all 96 train + 18 dev reachable terminal doses; no label or reply quality',
        train=dict(prefixes=24,terminals=120,reusable_replies=72,missing_replies=48,independent_single_reply_judgments=240),
        dev=dict(prefixes=6,terminals=30,reusable_replies=18,missing_replies=12,independent_single_reply_judgments=60,
            prefix_selection_status='not frozen; all allowed two-per-owner selections have identical counts'),
        test=dict(prefixes=test_count,owners=dict(test_owner_counts),actual_legal_terminals=None,
            range_if_OFF_fits=[48,240],verified_current_executor_replies=0,
            independent_single_reply_judgments_range_if_OFF_fits=[96,480],
            blocking='Active P1 inventory projection/ranking not built for test. No model calls allowed in this accounting.'),
        train_dev=dict(terminals=150,reusable_replies=90,missing_replies=60,independent_single_reply_judgments=300),
        total_conditional=dict(terminals=[198,390],missing_replies=[108,300],two_rater_judgments=[396,780]),
        judgment_unit='one rater assigning q and m to one canonical legal terminal reply; no automatic duplicate-text discount',
        existing_human_complete_independent_qm_judgments=0,
        dev_candidate18_same_prefix_text_unique=len({(r['prefix_identity'],r['reply_text_identity']) for r in devrows if r['reusable']}),
        train24_same_prefix_text_unique=len({(r['prefix_identity'],r['reply_text_identity']) for r in trainrows if r['reusable']}),
        no_other_executor_or_weak_targets_reused=True, adjudication_count=None, human_minutes_observed=None)
    write(out,'b1_summary.json',b1_summary); csv_write(out,'b1_terminal_reuse_private.csv',b1_rows)

    # Input-only sizing of frozen judge jobs: sealed human answers never read.
    jobs=read(ROOT / 'P3/candidate_v1/jobs_private.json')
    groups=Counter(j['group'] for j in jobs)
    check(groups==dict(development=32,validation=47,reserve=16,repeat=12,recheck_probe=1), '108_frozen_jobs_group_counts')
    prim=[j for j in jobs if j['group'] in ['development','validation']]
    check(len({digest([digest(j['evidence']),j['reply']]) for j in prim})==79, '79_exact_evidence_reply_primary_identities')
    sizes=[]
    for job in jobs:
        msgs,schema=messages_and_schema(job['evidence'],job['reply'],recheck=job['recheck'])
        b=sum(len(m['content'].encode('utf8')) for m in msgs)
        sizes.append(dict(job_id=job['job_id'],group=job['group'],utf8_content_bytes=b,
            estimated_input_tokens_low=b/4+256,estimated_input_tokens_high=b/3+256,
            reservation_input_tokens=b+1024,
            schema_identity=digest(schema)))
    csv_write(out,'judge_input_size_only.csv',sizes)
    # These are non-binding planning assumptions, not token counts or new limits.
    stages={
        'development33':[r for r in sizes if r['group'] in ('development','recheck_probe')],
        'validation47':[r for r in sizes if r['group']=='validation'],
        'repeat12':[r for r in sizes if r['group']=='repeat']}
    budget_rows=[]
    for stage, items in stages.items():
        n=len(items);lo=sum(r['estimated_input_tokens_low'] for r in items);hi=sum(r['estimated_input_tokens_high'] for r in items)
        budget_rows.append(dict(stage=stage,calls=n,input_tokens_estimate_low=round(lo),input_tokens_estimate_high=round(hi),
            total_output_tokens_assumed_low=n*2000,total_output_tokens_assumed_high=n*8000,
            peak_usd_estimate_low=round((lo*.3+n*2000*1.2)/1e6,6),
            peak_usd_estimate_high=round((hi*.3+n*8000*1.2)/1e6,6),
            off_peak_usd_estimate_low=round((lo*.15+n*2000*.6)/1e6,6),
            off_peak_usd_estimate_high=round((hi*.15+n*8000*.6)/1e6,6),
            serial_minutes_assuming_30_to_180_seconds=[n*.5,n*3],local_gpu_hours=0))
    maxb=max(r['utf8_content_bytes'] for r in sizes)
    recovery=dict(stage='recovery_reserve4_NOT_AUTHORIZED',calls=4,
        input_tokens_estimate_low=4*(maxb/4+256),input_tokens_estimate_high=4*(maxb/3+256),
        total_output_tokens_assumed_low=8000,total_output_tokens_assumed_high=32000,
        peak_usd_estimate_low=round((4*(maxb/4+256)*.3+8000*1.2)/1e6,6),
        peak_usd_estimate_high=round((4*(maxb/3+256)*.3+32000*1.2)/1e6,6),
        off_peak_usd_estimate_low=round((4*(maxb/4+256)*.15+8000*.6)/1e6,6),
        off_peak_usd_estimate_high=round((4*(maxb/3+256)*.15+32000*.6)/1e6,6),
        serial_minutes_assuming_30_to_180_seconds=[2,12],local_gpu_hours=0)
    budget_rows.append(recovery);csv_write(out,'alternative_trial_budget.csv',budget_rows)
    native_output=393216
    financial=dict(provider='DeepSeek official API',model='deepseek-flash',published_version='DeepSeek-V4.1-Flash',
        reasoning_effort='high',prompt_semantics='exact already-applied candidate rubric; no third prompt',
        estimated_trial_peak_usd=[round(sum(r['peak_usd_estimate_low'] for r in budget_rows),6),round(sum(r['peak_usd_estimate_high'] for r in budget_rows),6)],
        requested_trial_allocation_usd=5,allocation_status='PROPOSAL_NOT_AUTHORIZATION',
        total_followup_hard_cap_usd=20,native_max_output_tokens=native_output,
        conservative_peak_per_request_reservation_usd=round(((maxb+1024)*.3+native_output*1.2)/1e6,6),
        all_96_at_native_ceiling_peak_usd=round(sum(((r['utf8_content_bytes']+1024)*.3+native_output*1.2)/1e6 for r in sizes if r['group']!='reserve')+4*((maxb+1024)*.3+native_output*1.2)/1e6,6),
        estimated_latency_seconds_per_call=[30,180],latency_observed_on_this_provider=False,
        tokenizer_caveat='UTF8 bytes/4 to /3 +256 estimate only; no DeepSeek tokenizer downloaded; reserve bytes+1024 provisionally, verify before dispatch',
        proposed_serial_timeout_seconds=900, native_limit_or_timeout_is_technical_failure_not_score=True)

    oldrun=Path(read(ROOT / 'P3/candidate_v1/development_pointer.json')['run_dir'])
    oldsum=read(oldrun / 'summary.json')
    newroot=PROJECT / 'outputs/pm_rl1/p3_v2_after_confirmation_20261014'
    newsum=read(newroot / 'runs/development/summary.json')
    context=read(newroot / 'context.json'); protocol=read(newroot / 'protocol.json')
    check(protocol['semantic_revisions_after_human_labels']==1,'one_semantic_revision_already_used')
    check(len(oldsum['rows'])==len(newsum['rows'])==33, '33_old_33_new_calls')
    check(newsum['physical_calls_this_invocation']==33,'all_new_attempts_counted_including_failure')
    binding=read(PROJECT/'outputs/pm_rl1/p3_v2_development_audit_20261014/analysis/verified_measurement_bindings.json')
    check(len(binding)==66 and not any(r['cache_hit'] for r in binding),'66_verified_noncache_bindings')
    financial.update(existing_P3_starts=66,unchanged_actual_request_cap=140,remaining_under_cap=74,
        proposed_new_primary_calls=92,proposed_recovery_starts=4,
        proposed_cumulative_without_recovery=158,proposed_cumulative_with_recovery=162,
        additional_cap_needed_without_recovery=18,additional_cap_needed_with_recovery=22,
        reserve8pairs_started=0,semantic_revision_count=1)
    ledger_path=PROJECT/'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl';record(ledger_path)
    ledger=CumulativePaper1ApiBudgetLedger(ledger_path)
    boundary=read(PROJECT/'outputs/paper1_api_budget/followup_budget_boundary_20260918_v1.json')
    financial['local_paid_ledger']=dict(accounted_usd=str(ledger.accounted_cost_usd),
        baseline_usd=boundary['baseline_accounted_usd'],
        new_accounted_usd=str(ledger.accounted_cost_usd-Decimal(boundary['baseline_accounted_usd'])),
        unsettled_reservations=len(ledger.unsettled_reservations()),
        live_provider_balance_checked=False,external_batch_liabilities_reconciled=False,
        paid_dispatch_blocker='Shared atomic reservation path and all external liabilities must be reconciled before paid run; no new namespace budget.')
    batch = read(PROJECT/'outputs/paper1_calibration/static_official_batch_20260918_v1/submit.json')
    check(batch['calls_to_make']==0 and batch['outstanding_batches']==[], 'known_legacy_batch_not_submitted')
    financial['local_paid_ledger']['known_legacy_batch'] = dict(calls_to_make=0, outstanding_batches=[],
        receipt_blocked=batch['blocked'], provider_side_state_checked=False)
    # Downstream warning, not a choice of episodes or a request to run training.
    avglo=sum(r['estimated_input_tokens_low'] for r in sizes if r['group'] in ('development','validation'))/79
    avghi=sum(r['estimated_input_tokens_high'] for r in sizes if r['group'] in ('development','validation'))/79
    downstream=[]
    for episodes in [128,384]:
        n=639+episodes*6+72+216+162+960
        downstream.append(dict(episodes_per_seed=episodes,scheduled_core_J_slots=n,
            optional_RQX_J_slots=288,semantic_check_reserve=96,technical_recovery_reserve=192,
            peak_core_usd_scenario=[round(n*(avglo*.3+2000*1.2)/1e6,2),round(n*(avghi*.3+8000*1.2)/1e6,2)],
            off_peak_core_usd_scenario=[round(n*(avglo*.15+2000*.6)/1e6,2),round(n*(avghi*.15+8000*.6)/1e6,2)],
            caveat='No cache discounts; calibration input mix is a proxy for future train/test, not observed; 639 existing G outputs still need new J labels; no episode choice made.'))
    financial['downstream_not_authorized']=downstream
    write(out,'alternative_budget.json',financial)
    gen_seconds=[r['generation_seconds'] for r in summary['rows']]
    write(out,'observed_local_generation_timing.json',dict(n=len(gen_seconds),mean_seconds=statistics.mean(gen_seconds),median_seconds=statistics.median(gen_seconds),
        missing_train_dev60_projected_minutes=60*statistics.mean(gen_seconds)/60,
        missing_total108_to300_projected_minutes=[108*statistics.mean(gen_seconds)/60,300*statistics.mean(gen_seconds)/60],
        caveat='Same frozen G evidence, but RS3/4/test may differ. Add loading, inventory projection, checks; not measured new runtime.'))
    record(Path(__file__))
    for p in [PROJECT/'src/metacom_pm/rl1/schema.py',PROJECT/'src/metacom_pm/rl1/env.py',PROJECT/'src/metacom_pm/rl1/representation.py',PROJECT/'src/metacom_pm/rl1/representation_direct.py',PROJECT/'src/metacom_pm/rl1/judge_completion.py',PROJECT/'src/metacom_pm/rl1/judge_completion_candidate.py']:
        record(p)
    check(all(sha(Path(p))==h for p,h in SOURCES.items()),'all_read_sources_unchanged')
    check(all(sha(REPO/p)==h for p,h in baseline['existing_work_hashes'].items()),'preexisting_work_unchanged')
    write(out,'source_hashes.json',SOURCES)
    write(out,'verification.json',dict(status='OFFLINE_ACCOUNTING_CHECKS_PASS',checks=dict(CHECKS),
        assertions=sum(CHECKS.values()),read_files=len(SOURCES),model_calls=0,model_downloads=0,
        labels_decrypted=0,training_runs=0,paid_spend_usd=0,repository_core_edits=0,
        sealed_qualification=False,prior_delivery_manifest_identity=sha(prior_manifest_path)))
    print(json.dumps(dict(status='OFFLINE_ACCOUNTING_CHECKS_PASS',head=selected,b1=b1_summary,
        trial=financial,assertions=sum(CHECKS.values())),ensure_ascii=False))


if __name__=='__main__':
    main()

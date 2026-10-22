#!/usr/bin/env python3
"""Offline reconciliation of saved model/token metadata and Claude drafts.

No account query, token-count request, credential read, inference or training.
Input receipts come from separately recorded read-only/free API preparation.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.claude_delivery import prepare_request
from metacom_pm.rl1.schema import digest


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--root', type=Path, default=PROJECT/'outputs/pm_rl1/claude_resource_preparation_20261022')
    parser.add_argument('--source', type=Path, default=PROJECT/'outputs/pm_rl1/completion_preparation_20261022')
    args = parser.parse_args()
    model_receipt = read(args.root/'MODELS_READ.json')
    model = next(m for m in model_receipt['models'] if m['id'] == 'claude-sonnet-5-5')
    old = read(args.source/'primary_requests_private.json')
    saved = read(args.root/'claude_primary_requests_private.json')
    counts = [json.loads(line) for line in (args.root/'TOKEN_COUNTS.jsonl').read_text().splitlines()]
    assert len(old) == len(saved) == len(counts) == 22
    sizes = []
    for source, expected, receipt in zip(old, saved, counts):
        actual = prepare_request(source['wire_body']['messages'], source['local_schema'], model)
        actual.update(source_primary_identity=source['identity'], evidence_identity=source['evidence_identity'],
                      response_identity=source['response_identity'])
        assert actual == expected
        payload = {k:v for k,v in actual['wire_body'].items() if k not in ('max_tokens','stream')}
        assert hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest() == receipt['count_payload_sha256']
        assert receipt['prepared_identity'] == actual['identity'] and receipt['status'] == 'COUNTED'
        assert receipt['model'] == model['id']
        sizes.append(len(json.dumps(source['wire_body']['messages'], ensure_ascii=False).encode()))
    manifest = read(args.source/'SOURCE_HASHES_PRIVATE.json')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p,sha in manifest.items())
    tokens = [r['input_tokens'] for r in counts]
    total = sum(tokens)
    mean = Decimal(total) / 22
    # Retrieved 2026-10-22, standard global uncached pricing. No Batch/cache
    # discount is assumed. Token-count values are provider estimates, not bills.
    rates = {'claude-sonnet-5-5': ['2','10'], 'claude-opus-5-5': ['4','20']}
    scenarios = []
    for model_id, (inp, out) in rates.items():
        for output in (4000, 8000, 16000):
            unit = (mean*Decimal(inp) + Decimal(output)*Decimal(out))/1000000
            scenarios.append(dict(model=model_id, output_tokens_per_call_including_thinking=output,
                assumed_mean_input_tokens=str(mean),
                development22_usd=str(unit*22), complete_single_candidate97_usd=str(unit*97),
                fixed_pool534_usd=str(unit*534),
                warning='Only development22 input is counted for Sonnet; other quantities/model tokenizer are scenarios, not quotes or added costs.'))
    summary = dict(status='CLAUDE_OFFLINE_PREPARATION_READY_NOT_ACTIVATED',
        user_resource_statement='应该是Anthropic API额度，大概几十美元；未给精确余额或到期日',
        account_access_confirmed=True, account_credit_balance_verified=False,
        model_list_requests=1, free_token_count_requests=len(counts),
        new_scoring_or_generation_requests=0, new_natural_updates=0, new_human_tasks=0,
        new_inference_usd='0', historical_research_attempts=307,
        proposed_model=model['id'], proposed_model_semantic_qualification=False,
        input_bytes=dict(min=min(sizes), max=max(sizes), total=sum(sizes)),
        provider_counted_input_tokens=dict(min=min(tokens),max=max(tokens),total=total,mean=str(mean)),
        output_tokens_are_unknown=True, output_native_boundary=model['max_tokens'],
        max_counted_input_plus_native_output_cost_usd=str((Decimal(max(tokens))*2+Decimal(model['max_tokens'])*10)/1000000),
        max_cost_excludes_count_estimation_drift_and_is_not_live_reservation=True,
        candidate_stage_counts=dict(development=22, conditional_qualification=59, shared_technical_recoveries=16,
            maximum=97, hypothetical_cumulative=404, automatic_audits=0),
        stage_counts_exclude_unapproved_semantic_supplements=True,
        stage_activation=False, budget_amendment_applied=False,
        shared_remaining_usd='18.0941768', trial_cap_usd='3.65', active_capacity=374,
        pricing_source='https://platform.claude.com/docs/en/about-claude/pricing',
        price_snapshot_utc_date='2026-10-22', rates_usd_per_million=rates, scenarios=scenarios,
        first_development_inputs_same_as_previous=True, validation_labels_opened=False,
        test_content_read=False, old_source_files_unchanged=len(manifest),
        adapter_limitations=['no paid transport/broker activation', 'no real schema compilation/semantic accuracy evidence',
            'dynamic downstream requests still require bound coordinator integration'],
        source_hashes={name:hashlib.sha256((args.root/name).read_bytes()).hexdigest() for name in
            ('MODELS_READ.json','TOKEN_COUNTS.jsonl','claude_primary_requests_private.json')})
    path = args.root/'PREPARATION_SUMMARY.json'
    if path.exists():
        assert read(path) == summary
    else:
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n');path.chmod(0o600)
    print(json.dumps(dict(status=summary['status'], development22_sonnet_scenarios=[
        r['development22_usd'] for r in scenarios if r['model']==model['id']],
        tokens=summary['provider_counted_input_tokens'], immutable_sources=len(manifest)),ensure_ascii=False))


if __name__ == '__main__':
    main()

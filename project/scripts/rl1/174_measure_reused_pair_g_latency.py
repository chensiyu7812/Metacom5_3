#!/usr/bin/env python3
"""Resident candidate-G timing for the exact already-judged N23 pair.

Two warmups then four pairs with alternating ON/OFF order. Measures G only,
not semantic query encoding, policy, network, ASR, TTS or audible response.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.calibration_workflow import stamp, verify_identity
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.schema import digest
BASE = PROJECT / 'outputs/pm_rl1'
SOURCE = BASE / 'slight_positive_path_20261105_v1'


def read(path):
    return json.loads(path.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prepare(out):
    if out.exists():
        raise ValueError('New timing output directory required')
    replay = read(SOURCE / 'FROZEN_LOCATOR_REPLAY_PRIVATE.json')
    assert replay['old_preference_reusable'] and replay['actual_program'] == [3, 0]
    target = read(SOURCE / 'OLD_HUMAN_REFERENCE_PRIVATE.json')
    card = next(c for c in read(SOURCE / 'CARDS_PRIVATE.json') if c['depth'] == 0)
    off = read(SOURCE / 'REUSED_PRIVATE.json')[card['input_identity']]
    expected = dict(ON=dict(request=target['request'], raw=target['raw']), OFF=off)
    prior = read(SOURCE / 'alternate_G_resume/PROTOCOL.json')
    runtime = prior['runtime']
    for item in expected.values():
        verify_identity(item['request'])
        assert item['request']['runtime_identity'] == runtime['identity']
        assert item['raw']['finish_reason'] == 'natural_stop'
    schedule = [dict(arm='OFF', pair=-1, warmup=True), dict(arm='ON', pair=-1, warmup=True)]
    for pair, order in enumerate([('OFF', 'ON'), ('ON', 'OFF'), ('OFF', 'ON'), ('ON', 'OFF')]):
        schedule.extend(dict(arm=arm, pair=pair, warmup=False) for arm in order)
    requests = []
    for slot, row in enumerate(schedule):
        row['slot'] = slot
        body = {k: v for k, v in expected[row['arm']]['request'].items() if k != 'identity'}
        body['timing_representation'] = dict(slot=slot, pair=row['pair'], warmup=row['warmup'])
        req = stamp(body)
        row['request_identity'] = req['identity']
        requests.append(req)
    out.mkdir(mode=0o700)
    save(out / 'SCHEDULE.json', schedule)
    save(out / 'EXPECTED_PRIVATE.json', expected)
    source_files = [SOURCE / 'FROZEN_LOCATOR_REPLAY_PRIVATE.json', SOURCE / 'OLD_HUMAN_REFERENCE_PRIVATE.json',
                    SOURCE / 'REUSED_PRIVATE.json', SOURCE / 'alternate_G_resume/PROTOCOL.json',
                    out / 'SCHEDULE.json', out / 'EXPECTED_PRIVATE.json']
    code = [Path(__file__), PROJECT / 'scripts/rl1/167_probe_alternate_executor.py',
            PROJECT / 'scripts/rl1/172_resume_slight_path_preload.py',
            PROJECT / 'src/metacom_pm/rl1/local_gpu_guard.py', PROJECT / 'src/metacom_pm/rl1/generation.py',
            PROJECT / 'src/metacom_pm/rl1/durable.py']
    protocol = stamp(dict(scope='EXACT_HUMAN_PAIR_RESIDENT_G_COMPONENT_TIMING_NOT_DEPLOYMENT',
        runtime=runtime, gpu_uuid=prior['gpu_uuid'], requests_identity=digest(requests),
        sources={str(p.resolve()): sha(p) for p in source_files},
        code={str(p.resolve()): sha(p) for p in code}, max_loads=1, max_calls=10,
        stage_seconds=1200, automatic_retries=0, api_cost_usd=0,
        admission_idle_utilization_limit_percent=5, warmups=2, measured_pairs=4,
        expected_output_match_required_for_human_label_reuse=True,
        objective='Quantify only G first-token/completion components for exact already-judged replies; no 3-second deployment decision.',
        omitted_components=['online BGE query/indexing', 'PM encoding and decision', 'network/queue', 'ASR', 'TTS', 'audible response'],
        new_training=False, new_rewards=False, promote=False,
        authorization='2026-11-05 current user 好的 继续推进; follow the accepted latency objective after exact G01 reuse. Free bounded timing; no new human or paid calls.'))
    save(out / 'PROTOCOL.json', protocol)
    save(out / 'REQUESTS_PRIVATE.json', requests)
    print(json.dumps(dict(status='PREPARED', warmups=2, measured_pairs=4, max_calls=10)), flush=True)


def run(out):
    frozen = module('frozen_g', PROJECT / 'scripts/rl1/167_probe_alternate_executor.py')
    admission = module('scoped_admission', PROJECT / 'scripts/rl1/172_resume_slight_path_preload.py')
    frozen.LocalGPUCheck = admission.ScopedIdleCheck
    frozen.run(out)


def analyze(out):
    expected = read(out / 'EXPECTED_PRIVATE.json')
    requests = {r['identity']: r for r in read(out / 'REQUESTS_PRIVATE.json')}
    rows = []
    for item in read(out / 'SCHEDULE.json'):
        raw = read(out / 'raw' / (item['request_identity'] + '.json'))
        req = requests[item['request_identity']]
        assert raw['request_identity'] == req['identity']
        assert req['messages'] == expected[item['arm']]['request']['messages']
        rows.append(dict(**item, finish_reason=raw['finish_reason'],
            first_token_seconds=raw['first_token_seconds'], generation_seconds=raw['generation_seconds'],
            exact_reply_match=raw['text'] == expected[item['arm']]['raw']['text'],
            exact_output_tokens_match=raw['output_token_ids'] == expected[item['arm']]['raw']['output_token_ids'],
            format_failure=any(m in raw['decoded_with_special_tokens'] for m in ('<channel|>', '<|channel', '[channel]', '<think>'))))
    measured = [r for r in rows if not r['warmup']]
    differences = []
    for pair in range(4):
        rs = {r['arm']: r for r in measured if r['pair'] == pair}
        valid = all(r['finish_reason'] == 'natural_stop' and r['exact_reply_match'] and not r['format_failure'] for r in rs.values())
        differences.append(dict(pair=pair, exact_pair_reproduced=valid,
            ON_minus_OFF_first_token_seconds=rs['ON']['first_token_seconds'] - rs['OFF']['first_token_seconds'] if valid else None,
            ON_minus_OFF_completion_seconds=rs['ON']['generation_seconds'] - rs['OFF']['generation_seconds'] if valid else None))
    summary = dict(warmups=2, measured_pairs=4, exact_reproduced_pairs=sum(d['exact_pair_reproduced'] for d in differences),
        all_replies_exact=sum(r['exact_reply_match'] for r in rows), component_only=True,
        Tokkio_extra_wait_seconds=None, online_retrieval_seconds=None, net_utility=None,
        api_cost_usd=0, training_updates=0, human_answers_added=0)
    if all(d['exact_pair_reproduced'] for d in differences):
        for key in ['ON_minus_OFF_first_token_seconds', 'ON_minus_OFF_completion_seconds']:
            values = [d[key] for d in differences]
            summary[key] = dict(median=statistics.median(values), min=min(values), max=max(values), n=4)
    save(out / 'TIMING_ROWS.json', rows)
    save(out / 'PAIRED_DIFFERENCES.json', differences)
    save(out / 'SUMMARY.json', summary)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'run', 'analyze'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    globals()[args.mode](args.output.resolve())

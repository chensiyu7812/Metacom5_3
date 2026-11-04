#!/usr/bin/env python3
"""Audit actual P2 targets and run one 8-context OFF/ON instruction comparison."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.rl1.calibration_workflow import stamp, verify_identity
from metacom_pm.rl1.executor_use_probe import INSTRUCTION, VERSION, intervene, request_for
from metacom_pm.rl1.resource_comparison_runner import FixedResourceComparison, protocol_for
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import file_sha, save_json

BASE = PROJECT / 'outputs/pm_rl1'
PRIOR = BASE / 'resource_value_probe_20261104_v1'
P2 = BASE / 'completion_20260930_v2/P2'


def read(path):
    return json.loads(path.read_text())


def prepare(output):
    from transformers import AutoTokenizer
    if output.exists():
        raise ValueError('new output directory required')
    for name, expected in read(PRIOR / 'OUTPUT_MANIFEST.json').items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert file_sha(PRIOR / name) == expected
    freeze = read(P2 / 'dataset_freeze.json')
    for name, expected in freeze['files'].items():
        assert file_sha(PROJECT / name) == expected
    dataset = read(P2 / 'accepted_dataset_private.json')
    assert digest(dataset['rows']) == dataset['dataset_identity'] == freeze['dataset_identity']
    slots = {s['slot_id']:s for s in read(P2 / 'authoring_slots_private.json')['slots']}
    inventories = read(PRIOR / 'INVENTORY_PRIVATE.json')
    selected = [x for x in inventories if x['pilot']]
    assert len(selected) == 8
    train = [r for r in dataset['rows'] if r['split'] == 'train']
    target_cards = []; source_coverage = []
    for row in dataset['rows']:
        slot = slots[row['slot_id']]
        assert row['messages'] == slot['messages'] and row['messages_identity'] == digest(row['messages'])
        assert digest(row['response']) == row['response_identity']
    for case in selected:
        rows = [r for r in train if r['prefix_identity'] == case['prefix_identity']]
        hits = []
        for row in rows:
            target_cards.append(dict(case=case['case'], **row))
            system = row['messages'][0]['content']
            resources = json.loads(system.split('<resources>\n', 1)[1].split('\n</resources>', 1)[0]) if '<resources>' in system else []
            if case.get('target_resource'):
                target = json.loads(case['target_resource']['content'])['full_source_conversation']
                if any(json.loads(r['content']).get('full_source_conversation') == target for r in resources):
                    hits.append(row['slot_id'])
        source_coverage.append(dict(case=case['case'], accepted_targets=len(rows),
            target_session=case.get('target_session'), full_target_MS_slots=hits,
            only_explicit_full_MS_delivery_checked=True, compressed_fact_equivalence_not_assumed=True))
    groups = {p:[r for r in train if r['prefix_identity'] == p] for p in {r['prefix_identity'] for r in train}}
    audit = dict(actual_dataset_rows=len(dataset['rows']), train_rows=len(train), dev_rows=len(dataset['rows']) - len(train),
        train_prefixes=len(groups), train_ON=sum(bool(sum(r['counts'])) for r in train),
        train_OFF=sum(not sum(r['counts']) for r in train),
        train_prefixes_with_OFF_and_ON=sum(any(not sum(r['counts']) for r in g) and any(sum(r['counts']) for r in g) for g in groups.values()),
        ON_model_reported_behavior=dict(Counter(r['resource_behavior_model_reported'] for r in train if sum(r['counts']))),
        behavior_counts_not_semantically_validated=True, inspected_panel_targets=len(target_cards),
        panel_source_coverage=source_coverage,
        objective='response-plus-EOT supervised NLL; no pairwise incremental-benefit term',
        admission='same-model author/source review; accepted does not establish benefit',
        selection='severe-error exclusion then dev weak-target NLL, not measured resource benefit',
        paired_relative_quality_labels_added=0, new_training_updates=0)
    previous_items = read(PRIOR / 'INPUTS_PRIVATE.json')
    previous_cards = read(PRIOR / 'CARDS_PRIVATE.json')
    previous_results = read(PRIOR / 'RESULTS_PRIVATE.json')
    previous_protocol = read(PRIOR / 'G_PROTOCOL.json')
    runtime = previous_protocol['runtime']
    tokenizer = AutoTokenizer.from_pretrained(runtime['model_dir'], local_files_only=True)
    count_chat = lambda messages: len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    runner_path = PROJECT / 'src/metacom_pm/rl1/resource_comparison_runner.py'
    code_id = file_sha(runner_path)
    rows = []; items = {}; requests = []; originals = []
    for case in selected:
        arms = [('OFF', 'A_OFF'), ('ON', 'B_retrieved_MS1' if case['case'] == 'N03' else 'C_target_full_MS')]
        for condition, arm in arms:
            card = next(c for c in previous_cards if c['case'] == case['case'] and c['arm'] == arm)
            original = previous_items[card['input_identity']]
            assert count_chat(original['messages']) == original['usage']['input_tokens']
            prior_result = next(r for r in previous_results if r['case'] == case['case'] and r['arm'] == arm)
            changed = intervene(original, count_chat)
            request = request_for(changed, runtime=runtime, draw_identity=f'{VERSION}:{case["case"]}:{condition}', code_identity=code_id)
            items[changed['identity']] = changed; requests.append(request)
            originals.append(dict(case=case['case'], condition=condition, item=original, result=prior_result))
            rows.append(dict(case=case['case'], condition=condition, changed=True,
                original_input_identity=original['identity'], input_identity=changed['identity'], request_identity=request['identity'],
                extra_prompt_tokens=changed['usage']['input_tokens'] - original['usage']['input_tokens'], quality=None, reward=None))
        if case['case'] in ('N02', 'N19'):
            original = originals[-1]['item']
            request = request_for(original, runtime=runtime, draw_identity=f'{VERSION}:{case["case"]}:REPLAY', code_identity=code_id)
            items[original['identity']] = original; requests.append(request)
            rows.append(dict(case=case['case'], condition='REPLAY_ON', changed=False,
                original_input_identity=original['identity'], input_identity=original['identity'], request_identity=request['identity'],
                extra_prompt_tokens=0, quality=None, reward=None))
    assert len(requests) == 18
    random.Random(202611041).shuffle(requests)
    sources = {str(PRIOR / name):file_sha(PRIOR / name) for name in
               ('OUTPUT_MANIFEST.json', 'INPUTS_PRIVATE.json', 'CARDS_PRIVATE.json', 'RESULTS_PRIVATE.json',
                'INVENTORY_PRIVATE.json', 'ANSWER_REGISTRY_PRIVATE.json', 'G_PROTOCOL.json')}
    sources.update({str(P2 / name):file_sha(P2 / name) for name in
                    ('dataset_freeze.json', 'accepted_dataset_private.json', 'authoring_slots_private.json',
                     'supervision_protocol.json', 'executor_selection.json', 'admission_duplicate_disposition.json')})
    sources[str(Path(__file__).resolve())] = file_sha(Path(__file__))
    assets = deepcopy(previous_protocol['assets'])
    assets.update({str(path.resolve()):file_sha(path) for path in
                   (Path(__file__), PROJECT / 'src/metacom_pm/rl1/executor_use_probe.py')})
    protocol = protocol_for(requests, runtime=runtime, assets=assets, packages=previous_protocol['packages'],
        gpu_uuid=previous_protocol['gpu_uuid'], code_identity=code_id,
        source_package_identity=digest(dict(sources=sources, inputs=items)), run_directory=output / 'live_G')
    study = stamp(dict(scope='EXPLORATORY_CURRENT_NEED_INSTRUCTION_ABLATION', selection='Same fixed 8 exposed train contexts as prior resource probe; no winner selection.',
        intervention=INSTRUCTION, instruction_version=VERSION, hypotheses=['More current-need relevance may help use or ignore resources appropriately.',
        'Prompt may improve OFF alone, do nothing, or harm; changed text is not benefit.'],
        paired_design='original versus one revised instruction, each OFF and full ON; original replies cached',
        source_organization_unchanged=True, adapter_unchanged=True, no_private_fact_or_target_answer_in_prompt=True,
        input_identity=digest(items), cards_identity=digest(rows), originals_identity=digest(originals),
        G_protocol=protocol['identity'], max_new_G_calls=18, max_loads=1, API_calls=0, training_updates=0,
        offline_targeted_ON_not_PM_action=True, scalar_rewards=0, repeat_tolerance='report exact text/token equality; do not discard original or retry differences',
        next_step='Inspect all outputs with sources before any adoption; do not rewrite weak targets from unvalidated new generations.'))
    output.mkdir(parents=True, mode=0o700)
    authorization = output / 'USER_AUTHORIZATION_ZH.txt'
    authorization.write_text('2026-11-04 研究者：好的，按计划推进。\n接续已说明的执行器训练材料核查及必要有界对照；本阶段18次免费本地G、1次加载、无API/训练，不改原冻结执行器。\n')
    approval = dict(status='APPROVED', protocol_identity=protocol['identity'], operations=['resource_comparison_generation'],
        user_authorization_reference='Current conversation: 好的，按计划推进。', researcher_authorization_record=str(authorization.resolve()),
        researcher_record_sha256=file_sha(authorization))
    for name, value in [('P2_AUDIT.json', audit), ('TARGET_CARDS_PRIVATE.json', target_cards),
        ('ORIGINALS_PRIVATE.json', originals), ('INPUTS_PRIVATE.json', items), ('CARDS_PRIVATE.json', rows),
        ('G_REQUESTS_PRIVATE.json', requests), ('G_PROTOCOL.json', protocol), ('STUDY.json', study),
        ('SOURCES.json', sources), ('APPROVAL.json', approval)]:
        save_json(output / name, value)
    print(json.dumps(dict(status='PREPARED', train_targets=len(train), panel_targets=len(target_cards),
        contexts=len(selected), fresh_G_calls=len(requests), instruction_variants=1)), flush=True)


def run(output):
    for path, expected in read(output / 'SOURCES.json').items():
        assert file_sha(path) == expected
    study = read(output / 'STUDY.json'); verify_identity(study)
    assert digest(read(output / 'INPUTS_PRIVATE.json')) == study['input_identity']
    runner = FixedResourceComparison(read(output / 'G_PROTOCOL.json'), read(output / 'G_REQUESTS_PRIVATE.json'),
        output / 'live_G', approval=read(output / 'APPROVAL.json'))
    while True:
        result = runner.step(); print(json.dumps(result), flush=True)
        if result['status'] == 'CLOSED_FIXED_COMPARISON':
            return
        if result['status'] == 'RECONCILIATION_REQUIRED' or result.get('finish_reason', 'natural_stop') != 'natural_stop':
            raise RuntimeError('partial result retained; no automatic retry')


def analyze(output):
    protocol = read(output / 'G_PROTOCOL.json')
    results = []
    for card in read(output / 'CARDS_PRIVATE.json'):
        rid = card['request_identity']; raw = read(output / 'live_G' / (rid + '.raw.json'))
        seal = read(output / 'live_G' / (rid + '.sealed.json')); verify_identity(seal)
        assert seal['raw_identity'] == digest(raw) and seal['protocol_identity'] == protocol['identity']
        results.append(dict(card, reply=raw['text'], reply_identity=digest(raw['text']),
            output_tokens=raw['output_tokens'], input_tokens=raw['input_tokens'], finish_reason=raw['finish_reason'],
            G_component_seconds=raw['generation_seconds']))
    replays = []
    originals = read(output / 'ORIGINALS_PRIVATE.json')
    for r in results:
        if r['condition'] != 'REPLAY_ON':
            continue
        prior = next(x for x in originals if x['case'] == r['case'] and x['condition'] == 'ON')['result']
        raw = read(output / 'live_G' / (r['request_identity'] + '.raw.json'))
        old_raw = read(PRIOR / 'REUSED_PRIVATE.json')[prior['input_identity']]['raw'] if prior['reused'] else read(PRIOR / 'live_G' / (prior['request_identity'] + '.raw.json'))
        replays.append(dict(case=r['case'], text_equal=r['reply'] == prior['reply'], token_ids_equal=raw['output_token_ids'] == old_raw['output_token_ids']))
    summary = dict(status='GENERATIONS_READY_FOR_SOURCE_AND_CONTENT_REVIEW', new_G_calls=len(results),
        natural_stops=sum(r['finish_reason'] == 'natural_stop' for r in results), replays=replays,
        quality_labels_added=0, scalar_rewards_added=0, API_cost_usd=0, training_updates=0)
    save_json(output / 'RESULTS_PRIVATE.json', results); save_json(output / 'SUMMARY.json', summary)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'run', 'analyze'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    globals()[args.mode](args.output)

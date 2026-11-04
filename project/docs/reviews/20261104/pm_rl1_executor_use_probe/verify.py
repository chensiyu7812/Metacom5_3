"""Reconcile this fixed instruction comparison without loading a model."""
import hashlib
import json
from pathlib import Path
import statistics

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT / 'outputs/pm_rl1'
ROOT = BASE / 'executor_use_probe_20261104_v1'
PRIOR = BASE / 'resource_value_probe_20261104_v1'
P2 = BASE / 'completion_20260930_v2/P2'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def stamped(value):
    assert value['identity'] == digest({k:v for k,v in value.items() if k != 'identity'})


def main():
    for name, expected in read(ROOT / 'OUTPUT_MANIFEST.json').items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert sha(ROOT / name) == expected
    for name, expected in read(PRIOR / 'OUTPUT_MANIFEST.json').items():
        assert sha(PRIOR / name) == expected
    for name, expected in read(ROOT / 'SOURCES.json').items():
        assert sha(Path(name)) == expected
    dataset_freeze = read(P2 / 'dataset_freeze.json')
    for name, expected in dataset_freeze['files'].items():
        assert sha(PROJECT / name) == expected
    dataset = read(P2 / 'accepted_dataset_private.json')['rows']
    assert digest(dataset) == dataset_freeze['dataset_identity']
    targets = read(ROOT / 'TARGET_CARDS_PRIVATE.json')
    assert len(targets) == 26 and all(t['split'] == 'train' for t in targets)
    assert all({k:v for k,v in t.items() if k != 'case'} in dataset for t in targets)
    for anchor in read(ROOT / 'P2_CONTENT_REVIEW_PRIVATE.json')['anchors']:
        row = next(t for t in targets if t['slot_id'] == anchor['slot_id'])
        assert row['response'][anchor['start']:anchor['end']] == anchor['quote']
        assert digest(row['response']) == anchor['response_identity']
    drafts = read(ROOT / 'REVISION_CANDIDATES_PRIVATE.json')
    assert len(drafts['candidates']) == 5 and not drafts['original_dataset_replaced']
    inventory = read(PRIOR / 'INVENTORY_PRIVATE.json')
    for candidate in drafts['candidates']:
        original = next(t for t in targets if t['slot_id'] == candidate['original_slot_id'])
        assert candidate['messages'] == original['messages'] and candidate['original_response'] == original['response']
        assert digest(candidate['messages']) == candidate['messages_identity']
        assert digest(candidate['proposed_response']) == candidate['proposed_response_identity']
        assert candidate['q'] is candidate['m'] is candidate['reward'] is candidate['human_quality_label'] is None
        assert not candidate['accepted_for_training']
        for anchor in candidate['source_anchors']:
            source = next(n['target_source'] for n in inventory if n['case'] == candidate['case'])
            assert anchor['turn'] in source['turns'] and anchor['turn']['role'] == 'seeker'
            resources = json.loads(candidate['messages'][0]['content'].split('<resources>\n', 1)[1].split('\n</resources>', 1)[0])
            full_text = '\n'.join(t['role'] + ': ' + t['text'] for t in source['turns'])
            assert any(json.loads(r['content']).get('full_source_conversation') == full_text for r in resources)
    items = read(ROOT / 'INPUTS_PRIVATE.json'); cards = read(ROOT / 'CARDS_PRIVATE.json')
    originals = read(ROOT / 'ORIGINALS_PRIVATE.json'); study = read(ROOT / 'STUDY.json'); stamped(study)
    assert digest(items) == study['input_identity'] and digest(cards) == study['cards_identity']
    assert digest(originals) == study['originals_identity']
    prior_items = read(PRIOR / 'INPUTS_PRIVATE.json'); prior_results = read(PRIOR / 'RESULTS_PRIVATE.json')
    assert len(originals) == 16 and all(o['item'] == prior_items[o['item']['identity']] and o['result'] in prior_results for o in originals)
    for card in cards:
        item = items[card['input_identity']]; original = prior_items[card['original_input_identity']]
        assert item['messages'][1:] == original['messages'][1:]
        assert item['selected_keys'] == original['selected_keys']
        assert item['selected_resource_identities'] == original['selected_resource_identities']
        assert item['catalog_identity'] == original['catalog_identity']
        if card['changed']:
            changed_text = item['messages'][0]['content']
            assert changed_text.count(study['intervention']) == 1
            assert changed_text.replace('\n' + study['intervention'], '', 1) == original['messages'][0]['content']
            assert item['renderer_identity'] != original['renderer_identity']
            assert card['extra_prompt_tokens'] == 137
        else:
            assert item == original
        if card['condition'] == 'OFF':
            assert not item['selected_keys'] and '<resources>' not in item['messages'][0]['content']
    assert sum(c['condition'] == 'OFF' for c in cards) == 8
    protocol = read(ROOT / 'G_PROTOCOL.json'); stamped(protocol)
    assert protocol['identity'] == study['G_protocol'] and protocol == read(ROOT / 'live_G/PROTOCOL.json')
    assert protocol['runtime'] == read(PRIOR / 'G_PROTOCOL.json')['runtime']
    assert protocol['max_G_loads'] == 1 and protocol['max_G_calls'] == 18
    assert read(ROOT / 'live_G/load.observed.json')['runtime'] == protocol['runtime']
    for name, expected in protocol['assets'].items():
        if name.endswith('.py'):
            assert sha(Path(name)) == expected
    requests = read(ROOT / 'G_REQUESTS_PRIVATE.json'); results = read(ROOT / 'RESULTS_PRIVATE.json')
    assert len(requests) == len(results) == 18 and [r['identity'] for r in requests] == protocol['request_ids']
    assert len(list((ROOT / 'live_G').glob('*.raw.json'))) == 18
    raw_by_request = {}
    for request in requests:
        stamped(request); rid = request['identity']
        item = items[request['prepared_input_identity']]
        assert request['messages'] == item['messages'] and request['provenance']['selected_keys'] == item['selected_keys']
        start = read(ROOT / 'live_G' / (rid + '.started.json')); assert start['request'] == request
        raw = read(ROOT / 'live_G' / (rid + '.raw.json'))
        seal = read(ROOT / 'live_G' / (rid + '.sealed.json')); stamped(seal)
        assert seal['raw_identity'] == digest(raw) and seal['request_identity'] == rid
        assert seal['protocol_identity'] == protocol['identity'] and seal['reward'] is None
        visible = dict(messages=request['messages'], executor_identity=protocol['runtime']['identity'],
                       draw_identity=request['draw_identity'], renderer_identity=request['renderer_identity'])
        assert raw['request_id'] == digest(visible) and raw['runtime_identity'] == protocol['runtime']['identity']
        assert raw['finish_reason'] == 'natural_stop' and raw['api_cost_usd'] == 0
        assert raw['input_tokens'] == request['expected_input_tokens'] == item['usage']['input_tokens']
        assert len(raw['output_token_ids']) == raw['output_tokens']
        assert raw['output_token_ids'][-1] in protocol['runtime']['policy']['eos_token_ids']
        raw_by_request[rid] = raw
    for row in results:
        raw = raw_by_request[row['request_identity']]
        assert row['reply'] == raw['text'] and row['reply_identity'] == digest(raw['text'])
        assert row['quality'] is row['reward'] is None
    replay = []
    reused = read(PRIOR / 'REUSED_PRIVATE.json')
    for case in ('N02', 'N19'):
        row = next(r for r in results if r['case'] == case and r['condition'] == 'REPLAY_ON')
        prior = next(o['result'] for o in originals if o['case'] == case and o['condition'] == 'ON')
        old = reused[prior['input_identity']]['raw'] if prior['reused'] else read(PRIOR / 'live_G' / (prior['request_identity'] + '.raw.json'))
        raw = raw_by_request[row['request_identity']]
        replay.append(dict(case=case, text_equal=raw['text'] == old['text'], tokens_equal=raw['output_token_ids'] == old['output_token_ids']))
    cfg = read(BASE / 'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for name, expected in cfg['policy']['historical_files'].items():
        assert sha(Path(name)) == expected
    ledger_sha = sha(Path(cfg['ledger']))
    assert ledger_sha == 'e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417'
    closed = read(ROOT / 'live_G/CLOSED.json'); stamped(closed)
    assert closed['completed'] == closed['natural_stops'] == 18
    assert closed['API_calls'] == closed['training_updates'] == closed['non_natural'] == 0
    checks = dict(status='VERIFIED', P2_frozen_files=len(dataset_freeze['files']), actual_P2_rows=len(dataset),
        train_rows=sum(r['split'] == 'train' for r in dataset), inspected_target_rows=26,
        contexts=8, unchanged_cached_baselines=16, new_G_calls=18, natural_stops=18,
        prompt_only_pairs=16, source_content_and_current_context_preserved=True, instruction_variants=1,
        extra_input_tokens_each=137, original_prompt_replays=replay,
        frozen_history_files=len(cfg['policy']['historical_files']), ledger_sha256=ledger_sha,
        G_component_seconds_sum=sum(x['generation_seconds'] for x in raw_by_request.values()),
        G_component_seconds_median=statistics.median(x['generation_seconds'] for x in raw_by_request.values()),
        weak_revision_candidates=5, candidate_inputs_preserved=True, drafts_accepted_for_training=0,
        new_client_latency_measurements=0, new_quality_labels=0, new_scalar_rewards=0,
        new_training_updates=0, new_human_questions=0, API_cost_usd=0)
    (Path(__file__).parent / 'CHECKS.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    main()

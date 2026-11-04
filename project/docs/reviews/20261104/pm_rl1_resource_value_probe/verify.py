"""Independent, CPU-only reconciliation of source, generation and answer artifacts."""
import hashlib
import json
from pathlib import Path
import statistics

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT / 'outputs/pm_rl1'
ROOT = BASE / 'resource_value_probe_20261104_v1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def stamped(value):
    assert value['identity'] == digest({k:v for k,v in value.items() if k != 'identity'})


def resource(item):
    text = item['messages'][0]['content']
    rows = json.loads(text.split('<resources>\n', 1)[1].split('\n</resources>', 1)[0])
    assert len(rows) == 1
    return rows[0], json.loads(rows[0]['content'])


def main():
    manifest = read(ROOT / 'OUTPUT_MANIFEST.json')
    for name, value in manifest.items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert sha(ROOT / name) == value, name
    sources = read(ROOT / 'SOURCES.json')
    for path, value in sources.items():
        assert sha(Path(path)) == value, path
    study = read(ROOT / 'STUDY.json'); stamped(study)
    items = read(ROOT / 'INPUTS_PRIVATE.json')
    cards = read(ROOT / 'CARDS_PRIVATE.json')
    reused = read(ROOT / 'REUSED_PRIVATE.json')
    assert digest(items) == study['input_identity']
    assert digest(cards) == study['cards_identity']
    assert digest(reused) == study['historical_reuse_identity']
    assert len(cards) == 41 and len(items) == 36 and len(reused) == 17
    for key, item in items.items():
        body = {k:v for k,v in item.items() if k not in ('identity', 'reusable_old_requests')}
        assert digest(body) == key == item['identity']
        assert item['usage']['within_native_context'] and not item['usage']['truncation']
    protocol = read(ROOT / 'G_PROTOCOL.json'); stamped(protocol)
    assert protocol == read(ROOT / 'live_G/PROTOCOL.json')
    assert protocol['identity'] == study['G_protocol']
    runtime = protocol['runtime']; stamped(runtime)
    assert read(ROOT / 'live_G/load.observed.json')['runtime'] == runtime
    assert read(ROOT / 'live_G/load.done.json')['runtime_identity'] == runtime['identity']
    # The executor checked all model assets before loading; independently rehash source code here.
    code_assets = {p:h for p,h in protocol['assets'].items() if p.endswith('.py')}
    for path, value in code_assets.items():
        assert sha(Path(path)) == value, path
    requests = read(ROOT / 'G_REQUESTS_PRIVATE.json')
    assert [r['identity'] for r in requests] == protocol['request_ids']
    assert len(requests) == protocol['max_G_calls'] == 21 and protocol['max_G_loads'] == 1
    assert len(list((ROOT / 'live_G').glob('*.raw.json'))) == 21
    fresh = {}
    for request in requests:
        stamped(request); key = request['identity']
        item = items[request['prepared_input_identity']]
        assert request['messages'] == item['messages']
        assert request['base_runtime_identity'] == item['executor_identity'] == runtime['identity']
        start = read(ROOT / 'live_G' / (key + '.started.json'))
        assert start['request'] == request and start['protocol_identity'] == protocol['identity']
        raw = read(ROOT / 'live_G' / (key + '.raw.json'))
        seal = read(ROOT / 'live_G' / (key + '.sealed.json')); stamped(seal)
        assert seal['raw_identity'] == digest(raw) and seal['request_identity'] == key
        assert seal['protocol_identity'] == protocol['identity'] and seal['reward'] is None
        assert not seal['measurement_qualified']
        visible = dict(messages=request['messages'], executor_identity=runtime['identity'],
                       draw_identity=request['draw_identity'], renderer_identity=request['renderer_identity'])
        assert raw['request_id'] == digest(visible)
        assert raw['runtime_identity'] == runtime['identity']
        assert raw['input_tokens'] == request['expected_input_tokens'] == item['usage']['input_tokens']
        assert raw['finish_reason'] == 'natural_stop' and raw['api_cost_usd'] == 0
        assert len(raw['output_token_ids']) == raw['output_tokens']
        assert raw['output_token_ids'][-1] in runtime['policy']['eos_token_ids']
        fresh[key] = raw
    old = read(BASE / 'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    for key, entry in reused.items():
        request = entry['source_request']; raw = entry['raw']; item = items[key]
        assert old[request['request_id']] == raw
        assert request['messages'] == item['messages']
        assert request['executor_identity'] == raw['runtime_identity'] == runtime['identity']
        assert raw['source_provenance_identity'] == digest(request['provenance'])
        assert raw['input_tokens'] == item['usage']['input_tokens']
    results = read(ROOT / 'RESULTS_PRIVATE.json')
    assert len(results) == len(cards)
    all_raw = {}
    for card, row in zip(cards, results):
        assert all(row[k] == v for k,v in card.items())
        raw = reused[card['input_identity']]['raw'] if card['reused'] else fresh[card['request_identity']]
        assert row['reply'] == raw['text'] and row['reply_identity'] == digest(raw['text'])
        assert row['status'] == raw['finish_reason'] == 'natural_stop'
        assert row['quality'] is row['reward'] is None
        all_raw[(card['case'], card['arm'])] = raw
    for case in ('N02', 'N19'):
        assert all_raw[case, 'B_retrieved_MS1']['output_token_ids'] == all_raw[case, 'REPLAY_B_same_input']['output_token_ids']
    inventories = read(ROOT / 'INVENTORY_PRIVATE.json')
    assert len(inventories) == 24 and sum(x['pilot'] for x in inventories) == 8
    target_rows = []; layout_deltas = []; by_case = {}
    for entry in inventories:
        source = read(BASE / 'organized_initial_training_20261103_v2/sources_private' / (entry['prefix_identity'] + '.json'))
        assert source['prefix']['split'] == 'train'
        assert entry['current_prefix'] == source['evidence']['current_prefix']
        if not entry.get('target_session'):
            continue
        group = {r['arm']:r for r in cards if r['case'] == entry['case']}; by_case[entry['case']] = group
        c = items[group['C_target_full_MS']['input_identity']]
        e = items[group['E_same_full_turn_layout']['input_identity']]
        c_resource, c_body = resource(c); e_resource, e_body = resource(e)
        source_session = next(s for s in source['evidence']['legal_past_sessions'] if s['id'] == entry['target_session'])
        assert source_session == entry['target_source'] and source_session['date'] <= source['evidence']['current_date']
        assert c_body == json.loads(entry['target_resource']['content'])
        expected = [[i, t['role'], t['text']] for i,t in enumerate(source_session['turns'])]
        assert e_body['turns'] == expected and e_body['omitted_turns'] == 0 and e_body['summary'] is None
        assert '\n'.join(role + ': ' + text for _,role,text in expected) == c_body['full_source_conversation']
        assert {k:v for k,v in c_resource.items() if k != 'content'} == {k:v for k,v in e_resource.items() if k != 'content'}
        assert c['messages'][1:] == e['messages'][1:]
        assert c['messages'][0]['content'].split('<resources>')[0] == e['messages'][0]['content'].split('<resources>')[0]
        target_rows.append(entry); layout_deltas.append(e['usage']['input_tokens'] - c['usage']['input_tokens'])
    n03 = {r['arm']:items[r['input_identity']] for r in cards if r['case'] == 'N03'}
    _, before = resource(n03['M0_original_ME']); _, after = resource(n03['M1_source_supported_ME'])
    assert before['past_report'] != after['past_report']
    assert {k:v for k,v in before.items() if k != 'past_report'} == {k:v for k,v in after.items() if k != 'past_report'}
    for anchor in read(ROOT / 'CONTENT_REVIEW_PRIVATE.json')['anchors']:
        row = next(r for r in results if r['case'] == anchor['case'] and r['arm'] == anchor['arm'])
        assert row['reply'][anchor['start']:anchor['end']] == anchor['quote']
        assert row['reply_identity'] == anchor['reply_identity'] and anchor['helpfulness'] is None
    intake = read(ROOT / 'INTAKE_PRIVATE.json')
    received = read(ROOT / 'RECEIVED_ANSWER_PRIVATE.json')
    registry = read(ROOT / 'ANSWER_REGISTRY_PRIVATE.json')
    previous = read(BASE / 'contextual_value_reference_20261104_v1/ANSWER_REGISTRY_PRIVATE.json')
    assert registry[:-1] == previous and len(registry) == 36
    assert registry[-1]['raw_label']['original_answer'] == intake['original_answer'] == received['original_answer']
    assert '我让GPT网页版' in intake['original_answer'] and 'A略有提升，但收益有限' in intake['original_answer']
    assert intake['exact_qm'] is intake['numeric_reward'] is None and not intake['qualified_reward']
    assert registry[-1]['intake_identity'] == digest(intake)
    assert intake['human_respondents'] == 1 and intake['web_analysis_is_not_second_human_rater']
    cfg = read(BASE / 'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for path, value in cfg['policy']['historical_files'].items():
        assert sha(Path(path)) == value
    ledger_sha = sha(Path(cfg['ledger']))
    assert ledger_sha == 'e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417'
    closed = read(ROOT / 'live_G/CLOSED.json'); stamped(closed)
    assert closed['completed'] == closed['natural_stops'] == 21
    assert closed['API_calls'] == closed['training_updates'] == closed['non_natural'] == 0
    checks = dict(status='VERIFIED', source_files=len(sources), code_assets_rehashed=len(code_assets),
                  frozen_history_files=len(cfg['policy']['historical_files']), ledger_sha256=ledger_sha,
                  train_prefixes=24, pilot_cases=8, pilot_owners=len({x['owner'] for x in inventories if x['pilot']}),
                  cards=41, unique_inputs=36, reused_unique_inputs=17, new_G_calls=21, natural_new_G=21,
                  replay_text_and_token_ids_equal=2, complete_source_preserving_layout_pairs=7,
                  initial_MS1_candidate_hits=sum(x['target_initial_rank'] == 1 for x in target_rows),
                  MS6_candidate_hits=sum(x['target_in_MS6'] for x in target_rows),
                  candidate_denominator=7, layout_added_input_tokens=layout_deltas,
                  ME_repair_changed_fields=['past_report'], old_references_preserved=35, reference_records=36,
                  new_human_answer_events=1, human_answer_AI_assisted=True, scalar_rewards_added=0,
                  G_component_seconds_sum=sum(r['generation_seconds'] for r in fresh.values()),
                  G_component_seconds_median=statistics.median(r['generation_seconds'] for r in fresh.values()),
                  new_client_latency_measurements=0, API_cost_usd=0, new_policy_updates=0)
    (Path(__file__).parent / 'CHECKS.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    main()

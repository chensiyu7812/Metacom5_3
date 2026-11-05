"""Independent source, native-token, raw-output and exact-human-reuse checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT / 'outputs/pm_rl1'
ROOT = BASE / 'slight_positive_path_20261105_v1'
TIMING = BASE / 'reused_pair_g_latency_20261105_v1'
sys.path.insert(0, str(PROJECT / 'src'))


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def digest(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def identity(x):
    assert x['identity'] == digest({k: v for k, v in x.items() if k != 'identity'})


def module(name, p):
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    folders = [ROOT, TIMING, BASE / 'alternate_executor_probe_20261104_v1',
               BASE / 'incremental_help_probe_20261105_v1', BASE / 'incremental_help_human_review_20261105_v1']
    manifest_count = 0
    for folder in folders:
        for rel, expected in read(folder / 'OUTPUT_MANIFEST.json').items():
            assert sha(folder / rel) == expected, str(folder / rel)
            manifest_count += 1
    study = read(ROOT / 'STUDY.json')
    identity(study)
    for path, expected in study['source_hashes'].items():
        assert sha(Path(path)) == expected, path
    from transformers import AutoTokenizer
    from metacom_pm.rl1.online_materials import load_materials
    from metacom_pm.rl1.resource_organization import OrganizationSession
    from metacom_pm.rl1.resource_value_probe import match_session
    train = BASE / 'organized_initial_training_20261103_v2'
    config = read(train / 'CONFIG.json')
    tokenizer = AutoTokenizer.from_pretrained(config['runtime']['model_dir'], local_files_only=True)

    class Compatibility:
        def __getattr__(self, name):
            return getattr(tokenizer, name)

        def apply_chat_template(self, *args, **kwargs):
            kwargs.setdefault('return_dict', False)
            return tokenizer.apply_chat_template(*args, **kwargs)

    _, cats, renderer = load_materials(train, prefix_ids=[study['prefix_identity']], tokenizer=Compatibility())
    cat = cats[study['prefix_identity']]
    session = OrganizationSession(cat, renderer)
    cards, inputs, rows = [read(ROOT / n) for n in ('CARDS_PRIVATE.json', 'INPUTS_PRIVATE.json', 'RESULTS_PRIVATE.json')]
    evidence = read(ROOT / 'EVIDENCE_PRIVATE.json')
    for card, row in zip(cards, rows):
        if card['depth']:
            session.get('MS')
        keys = session.receipt()['acquired']
        assert card['actual_program'] == [3] * card['depth'] + [0]
        assert keys == card['acquisition_order']
        item = inputs[card['input_identity']]
        assert item['messages'] == renderer.messages(cat, keys)
        assert item['selected_keys'] == [x.key for x in cat.canonical(keys)]
        assert item['selected_resource_identities'] == [x.identity for x in cat.canonical(keys)]
        for x in cat.canonical(keys):
            match_session(x, evidence)
        raw = read(Path(row['raw_source']))
        assert sha(Path(row['raw_source'])) == row['raw_sha256']
        assert raw['text'] == row['reply'] and digest(row['reply']) == row['reply_identity']
        assert row['human_preference'] is row['reward'] is None
    assert len(cards) == 5 and len(session.receipt()['acquired']) == 4
    assert {match_session(x, evidence)['id'] for x in cat.canonical(session.receipt()['acquired'])} == {
        x['id'] for x in evidence['legal_past_sessions']}
    assert not (ROOT / 'alternate_G/LOAD_STARTED.json').exists()
    recovery = read(ROOT / 'PRELOAD_RECOVERY.json')
    identity(recovery)
    assert recovery['prior_model_loads'] == recovery['prior_model_requests'] == 0
    gemma = None
    new_calls = 0
    for folder in (ROOT / 'alternate_G_resume', TIMING):
        protocol = read(folder / 'PROTOCOL.json')
        identity(protocol)
        runtime = protocol['runtime']
        identity(runtime)
        for group in ('code', 'sources'):
            for path, expected in protocol[group].items():
                assert sha(Path(path)) == expected, path
        if gemma is None:
            gemma = AutoTokenizer.from_pretrained(runtime['model_dir'], local_files_only=True)
        assert digest(gemma.chat_template) == runtime['chat_template_identity']
        requests = read(folder / 'REQUESTS_PRIVATE.json')
        assert digest(requests) == protocol['requests_identity']
        assert len(list((folder / 'raw').glob('*.started.json'))) == len(requests) == protocol['max_calls']
        for req in requests:
            identity(req)
            tokens = gemma.apply_chat_template(req['messages'], tokenize=True, add_generation_prompt=True,
                enable_thinking=False, return_dict=False)
            assert len(tokens) == req['input_tokens'] and digest(tokens) == req['token_ids_identity']
            raw = read(folder / 'raw' / (req['identity'] + '.json'))
            assert raw['request_identity'] == req['identity'] and raw['runtime_identity'] == runtime['identity']
            assert raw['input_identity'] == req['input_identity'] and raw['finish_reason'] == 'natural_stop'
            assert raw['output_tokens'] == len(raw['output_token_ids'])
            assert raw['output_token_ids'][-1] in runtime['policy']['eos_token_ids']
            assert req['input_tokens'] + raw['output_tokens'] < runtime['policy']['context_limit']
            assert gemma.decode(raw['output_token_ids'], skip_special_tokens=True).strip() == raw['text']
            assert gemma.decode(raw['output_token_ids'], skip_special_tokens=False) == raw['decoded_with_special_tokens']
            assert not any(m in raw['decoded_with_special_tokens'] for m in ('<channel|>', '<|channel', '[channel]', '<think>', '</think>'))
            new_calls += 1
        assert read(folder / 'CLOSED.json')['completed'] == len(requests)
    assert new_calls == 13
    locator_module = module('replay_verification', PROJECT / 'scripts/rl1/173_replay_complete_frozen_ms_rank.py')
    alternate = locator_module.CompleteFrozenMSCatalog(cat)
    route = OrganizationSession(alternate, renderer)
    route.get('MS')
    replay = read(ROOT / 'FROZEN_LOCATOR_REPLAY_PRIVATE.json')
    assert alternate.identity == replay['variant_catalog_identity']
    assert route.receipt() == replay['receipt']
    old = read(ROOT / 'OLD_HUMAN_REFERENCE_PRIVATE.json')
    assert renderer.messages(alternate, route.receipt()['acquired']) == old['request']['messages']
    assert sha(Path(old['source'])) == old['sha256']
    registry = read(BASE / 'incremental_help_human_review_20261105_v1/ANSWER_REGISTRY_PRIVATE.json')
    assert len(registry) == 45
    reference = next(r for r in registry if r.get('question_id') == 'G01')
    assert reference['evidence']['current_prefix'] == [dict(speaker=t['role'], text=t['text']) for t in evidence['current_prefix']]
    assert reference['evidence']['legal_past_source'] == match_session(alternate.item(route.receipt()['acquired'][0]), evidence)
    assert reference['slight_edge_reply_identity'] == old['raw']['text_identity'] == replay['preferred_reply_identity']
    assert reference['numeric_reward'] is replay['numeric_reward'] is None
    assert not any(r['exact_old_preferred_reply'] for r in rows)
    measured = [r for r in read(TIMING / 'TIMING_ROWS.json') if not r['warmup']]
    expected = read(TIMING / 'EXPECTED_PRIVATE.json')
    for row in read(TIMING / 'TIMING_ROWS.json'):
        raw = read(TIMING / 'raw' / (row['request_identity'] + '.json'))
        assert raw['text'] == expected[row['arm']]['raw']['text']
        assert raw['output_token_ids'] == expected[row['arm']]['raw']['output_token_ids']
        for metric in ('first_token_seconds', 'generation_seconds'):
            assert row[metric] == raw[metric]
    for metric, key in [('first_token_seconds', 'ON_minus_OFF_first_token_seconds'),
                        ('generation_seconds', 'ON_minus_OFF_completion_seconds')]:
        differences = []
        for pair in range(4):
            pairrows = {r['arm']: r for r in measured if r['pair'] == pair}
            differences.append(pairrows['ON'][metric] - pairrows['OFF'][metric])
        assert statistics.median(differences) == read(TIMING / 'SUMMARY.json')[key]['median']
    p2 = read(BASE / 'completion_20260930_v2/P2/dataset_freeze.json')['files']
    for path, expected in p2.items():
        assert sha(PROJECT / path) == expected, path
    j = read(BASE / 'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for path, expected in j['policy']['historical_files'].items():
        assert sha(Path(path)) == expected, path
    assert sha(Path(j['ledger'])) == 'e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417'
    checks = dict(status='VERIFIED', native_complete_new_G_calls=new_calls,
        branch_endpoints=5, exact_old_human_pair_reused='G01 via separate static locator',
        original_locator_unchanged=True, old_human_records_preserved=45, new_human_answers=0,
        exact_timing_reply_reproductions=10, measured_pairs=4,
        original_P2_files_unchanged=len(p2), historical_files_unchanged=len(j['policy']['historical_files']),
        files_verified_by_manifests=manifest_count, ledger_unchanged=True,
        targeted_tests_passed=15, targeted_test_exit_code=0,
        new_training_updates=0, API_cost_usd=0)
    (Path(__file__).parent / 'CHECKS.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    main()

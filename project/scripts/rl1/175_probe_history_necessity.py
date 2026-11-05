#!/usr/bin/env python3
"""Bounded source-first diagnostic. No retrieval changes, judge or RL rewards."""
import argparse
from collections import defaultdict
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.calibration_workflow import stamp, verify_identity
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.schema import digest

BASE = PROJECT / 'outputs/pm_rl1'
PRIOR = BASE / 'alternate_executor_probe_20261104_v1'
ORG = BASE / 'resource_organization_20261029_v1'
MODEL = Path('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3')


def read(path):
    return json.loads(path.read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def freeze(out):
    from transformers import AutoTokenizer
    from metacom_pm.rl1.evidence import prefix_from_dict
    from metacom_pm.rl1.resource_organization import OrganizedItem
    protocol = read(out / 'SCREENING_PROTOCOL.json')
    verify_identity(protocol)
    assert sha(ORG / 'OUTPUT_MANIFEST.json') == protocol['source_manifest_sha256']
    assert sha(ORG / 'CATALOG_MANIFEST.json') == read(ORG / 'OUTPUT_MANIFEST.json')['CATALOG_MANIFEST.json']
    source = read(out / 'SOURCE_SCREEN_PRIVATE.json')
    notes = read(out / 'SOURCE_ANNOTATIONS_PRIVATE.json')
    assert len(source) == len(notes) == 96
    assert len({r['case'] for r in notes}) == 96
    src = {r['case']: r for r in source}
    expected = {r['prefix_identity'] for r in read(ORG / 'CATALOG_MANIFEST.json') if r['split'] == 'train'}
    assert {r['prefix_identity'] for r in notes} == expected
    tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    count = lambda m: len(tok.encode(m['content'], add_special_tokens=False))
    owners = defaultdict(list)
    for row in notes:
        r = src[row['case']]
        assert sha(Path(r['path'])) == r['source_sha256'] == row['source_sha256']
        assert prefix_from_dict(r['prefix']).identity == row['prefix_identity']
        assert r['prefix']['split'] == 'train' and row['current_prefix_reviewed']
        if row['decision'] != 'candidate_with_controls':
            continue
        by_sid = {m['source_ids'][0]: m for m in r['MS']}
        c = by_sid[row['target_session']]
        ds = [by_sid[s] for s in row['distractor_eligible_sessions']]
        assert ds and row['source_seeker_quote'] in c['search_text']
        assert ('seeker: ' + row['source_seeker_quote']) in c['search_text']
        assert row['current_anchor']['content'] == r['prefix']['turns'][row['current_anchor']['index']]['content']
        for m in [c, *ds]:
            assert m['source_check'] in ('complete_raw_session_roles_and_text_verified',
                'full_session_from_frozen_legal_evidence_not_new_raw_corpus_read')
            assert m['owner_id'] == r['prefix']['owner_id']
            assert m['source_rank'] < r['prefix']['cutoff_rank'] and m['reported_at'] < r['prefix']['timestamp']
            assert json.loads(m['content'])['full_source_conversation'] == m['search_text']
        d = min(ds, key=lambda m: (abs(count(m) - count(c)), m['key']))
        assert c['key'] != d['key'] and row['source_seeker_quote'] not in d['search_text']
        owners[row['owner']].append(dict(**row, prefix=r['prefix'], C=c, D=d,
            C_identity=OrganizedItem(**c).identity, D_identity=OrganizedItem(**d).identity,
            C_tokens=count(c), D_tokens=count(d), length_mismatch=count(d)-count(c)))
    for rows in owners.values():
        rows.sort(key=lambda r: hashlib.sha256(r['prefix_identity'].encode()).hexdigest())
    selected = []
    for round_number in range(2):
        for owner in sorted(owners):
            if len(owners[owner]) > round_number:
                selected.append(owners[owner][round_number])
    selected = selected[:protocol['maximum_cases']]
    assert len({(r['owner'], r['session']) for r in selected}) == len(selected)
    result = stamp(dict(screening_protocol=protocol['identity'], cases=selected,
        status='READY' if len(selected) >= protocol['minimum_cases_for_full_probe'] else 'INSUFFICIENT_CANDIDATES',
        source_hashes={str((out / n).resolve()): sha(out / n) for n in
            ('SCREENING_PROTOCOL.json', 'SOURCE_SCREEN_PRIVATE.json', 'SOURCE_ANNOTATIONS_PRIVATE.json')},
        actual_review_order='Complete currents reviewed in exported owner/prefix order, then targeted source inspection; differs from stated owner/session order. No new replies or outcome-based selection.',
        control_scope='Analyst judged other-topic controls, not proven inert resources. Whole sessions and incidental generic content preserved; length mismatch explicit.',
        exposure='Exposed train development; not independent pristine evaluation.',
        new_generation_before_freeze=0, qualified_rewards=0))
    save(out / 'SELECTION_PRIVATE.json', result)
    print(json.dumps(dict(status=result['status'], cases=len(selected), owners=len(owners), identity=result['identity'])), flush=True)


def prepare(out):
    from transformers import AutoTokenizer
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    from metacom_pm.rl1.evidence import prefix_from_dict
    from metacom_pm.rl1.resource_organization import OrganizationCatalog, OrganizedItem, OrganizedRenderer
    selected = read(out / 'SELECTION_PRIVATE.json'); verify_identity(selected)
    assert selected['status'] == 'READY'
    for path, expected in selected['source_hashes'].items():
        assert sha(Path(path)) == expected
    config = read(BASE / 'organized_initial_training_20261103_v2/CONFIG.json')
    llama_dir = Path(config['runtime']['model_dir'])
    assert sha(llama_dir / 'tokenizer.json') == LLAMA_TOKENIZER_JSON_SHA256
    tok = AutoTokenizer.from_pretrained(llama_dir, local_files_only=True)
    renderer = OrganizedRenderer(count_text=lambda s: len(tok.encode(s, add_special_tokens=False)),
        count_chat=lambda ms: len(tok.apply_chat_template(ms, tokenize=True, add_generation_prompt=True, return_dict=False)),
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256, template=tok.chat_template)),
        context_limit=config['runtime']['policy']['context_limit'])
    assert renderer.identity == config['renderer_identity']
    runtime = read(PRIOR / 'PROTOCOL.json')['runtime']; verify_identity(runtime)
    assert runtime['identity'] == 'cf84d46eccfb00133963f0b31e80eb323c0fa3c58ba64455b215c1a7dbcf0b3e'
    gemma = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    # Only inspect old generated outputs after the source selection is frozen.
    cache = {}
    cache_sources = [PRIOR, BASE / 'incremental_help_probe_20261105_v1/alternate_G']
    for root in cache_sources:
        p = read(root / 'PROTOCOL.json'); verify_identity(p)
        reqs = read(root / 'REQUESTS_PRIVATE.json')
        assert digest(reqs) == p['requests_identity'] and p['runtime']['identity'] == runtime['identity']
        for req in reqs:
            verify_identity(req)
            assert digest(req['messages']) == req['messages_identity']
            path = root / 'raw' / (req['identity'] + '.json')
            raw = read(path)
            assert raw['request_identity'] == req['identity'] and raw['runtime_identity'] == runtime['identity']
            assert raw['text_identity'] == digest(raw['text'])
            if raw['finish_reason'] == 'natural_stop' and raw['completed_assistant_turn']:
                cache.setdefault(req['messages_identity'], dict(request=req, raw=raw, source=str(path.resolve()), sha256=sha(path)))
    cards, inputs, requests, reused = [], {}, [], {}
    for row in selected['cases']:
        cat = OrganizationCatalog(prefix_from_dict(row['prefix']), [OrganizedItem(**row[x]) for x in ('C', 'D')],
            provenance_identity=selected['identity'])
        # Diagnostic subset, not a production action-domain or retrieval change.
        for arm in ('OFF', 'C', 'D'):
            keys = [] if arm == 'OFF' else [row[arm]['key']]
            item = dict(prefix_identity=cat.prefix.identity, renderer_identity=renderer.identity,
                diagnostic_catalog_identity=cat.identity, messages=renderer.messages(cat, keys),
                selected_keys=keys, selected_resource_identities=[cat.item(k).identity for k in keys], usage=renderer.usage(cat, keys))
            assert item['usage']['within_native_context'] and not item['usage']['truncation']
            key = digest(item); inputs[key] = dict(item, identity=key)
            native = gemma.apply_chat_template(item['messages'], tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False)
            assert 0 < len(native) < runtime['policy']['context_limit']
            req = stamp(dict(input_identity=key, messages=item['messages'], messages_identity=digest(item['messages']),
                selected_keys=keys, selected_resource_identities=item['selected_resource_identities'],
                runtime_identity=runtime['identity'], input_tokens=len(native), token_ids_identity=digest(native)))
            old = cache.get(req['messages_identity'])
            if old:
                assert old['request']['messages'] == req['messages']
                assert old['request']['token_ids_identity'] == req['token_ids_identity']
                reused[key] = old
            else:
                requests.append(req)
            cards.append(dict(case=row['case'], owner=row['owner'], arm=arm, input_identity=key,
                reused=old is not None, quality=None, reward=None))
    assert len(cards) == 3 * len(selected['cases']) and len(requests) <= 36
    random.Random(20261105).shuffle(requests)
    for name, obj in [('INPUTS_PRIVATE.json', inputs), ('CARDS_PRIVATE.json', cards), ('REUSED_PRIVATE.json', reused)]:
        save(out / name, obj)
    sources = [out / x for x in ('SCREENING_PROTOCOL.json', 'SELECTION_PRIVATE.json', 'SOURCE_ANNOTATIONS_PRIVATE.json',
        'INPUTS_PRIVATE.json', 'CARDS_PRIVATE.json', 'REUSED_PRIVATE.json')]
    sources += [Path(r['source_path']) for r in selected['cases']]
    code = [Path(__file__), PROJECT / 'scripts/rl1/167_probe_alternate_executor.py',
        PROJECT / 'scripts/rl1/172_resume_slight_path_preload.py', PROJECT / 'src/metacom_pm/rl1/resource_organization.py',
        PROJECT / 'src/metacom_pm/rl1/generation.py', PROJECT / 'src/metacom_pm/rl1/local_gpu_guard.py', PROJECT / 'src/metacom_pm/rl1/durable.py']
    protocol = stamp(dict(scope='SOURCE_FIRST_HISTORY_VALUE_THREE_ARM_DIAGNOSTIC', runtime=runtime,
        sources={str(p.resolve()): sha(p) for p in sources}, code={str(p.resolve()): sha(p) for p in code},
        requests_identity=digest(requests), gpu_uuid='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4',
        max_loads=1, max_calls=len(requests), automatic_retries=0, stage_seconds=1800, api_cost_usd=0,
        admission='ScopedIdleCheck: latest XML <=5% and >=45000MiB, no other visible processes, query errors reject.',
        screening_identity=read(out / 'SCREENING_PROTOCOL.json')['identity'], selection_identity=selected['identity'],
        new_training=False, new_rewards=False, promote=False))
    run_dir = out / 'alternate_G'; run_dir.mkdir(mode=0o700)
    save(run_dir / 'PROTOCOL.json', protocol); save(run_dir / 'REQUESTS_PRIVATE.json', requests)
    print(json.dumps(dict(cards=len(cards), cached=len(reused), new_calls=len(requests))), flush=True)


def run(out):
    runner = module('history_runner', PROJECT / 'scripts/rl1/167_probe_alternate_executor.py')
    guard = module('history_guard', PROJECT / 'scripts/rl1/172_resume_slight_path_preload.py')
    runner.LocalGPUCheck = guard.ScopedIdleCheck
    runner.run(out / 'alternate_G')


def collect(out):
    mapping = {r['input_identity']: r for r in read(out / 'alternate_G/REQUESTS_PRIVATE.json')}
    reused = read(out / 'REUSED_PRIVATE.json')
    rows = []
    for card in read(out / 'CARDS_PRIVATE.json'):
        key = card['input_identity']
        if key in reused:
            raw = reused[key]['raw']; origin = reused[key]['source']
            assert sha(Path(origin)) == reused[key]['sha256']
        else:
            origin = str((out / 'alternate_G/raw' / (mapping[key]['identity'] + '.json')).resolve())
            raw = read(Path(origin)) if Path(origin).exists() else None
        if raw:
            assert digest(raw['text']) == raw['text_identity']
        rows.append(dict(**card, raw=raw, source=origin, valid=bool(raw and raw['finish_reason'] == 'natural_stop' and raw['completed_assistant_turn'])))
    save(out / 'RESULTS_PRIVATE.json', rows)
    print(json.dumps(dict(total=len(rows), natural=sum(r['valid'] for r in rows), missing_or_failed=sum(not r['valid'] for r in rows))), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['freeze', 'prepare', 'run', 'collect'])
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); globals()[a.mode](a.output.resolve())

#!/usr/bin/env python3
"""Complete the N23 MS branch with the frozen candidate G; no inferred reward."""
import argparse
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
TRAIN = BASE / 'organized_initial_training_20261103_v2'
PRIOR = BASE / 'alternate_executor_probe_20261104_v1'
REVIEW = BASE / 'incremental_help_human_review_20261105_v1'
AUDIT = BASE / 'feedback_and_opportunity_20261105_v1'


def read(path):
    return json.loads(path.read_text())


def prepare(out):
    from metacom_pm.rl1.online_materials import load_materials
    from metacom_pm.rl1.resource_organization import OrganizationSession
    if out.exists():
        raise ValueError('A new, immutable output directory is required')
    for name, expected in read(PRIOR / 'OUTPUT_MANIFEST.json').items():
        assert sha(PRIOR / name) == expected, name
    audit = next(r for r in read(REVIEW / 'SLIGHT_POSITIVE_PATH_AUDIT_PRIVATE.json')['rows']
                 if r['case'] == 'N23')
    opportunity = next(r for r in read(AUDIT / 'OPPORTUNITIES_PRIVATE.json') if r['case'] == 'N23')
    _, catalogs, renderer = load_materials(TRAIN, prefix_ids=[opportunity['prefix_identity']])
    cat = catalogs[opportunity['prefix_identity']]
    session = OrganizationSession(cat, renderer)
    prior_protocol = read(PRIOR / 'PROTOCOL.json')
    verify_identity(prior_protocol)
    runtime = prior_protocol['runtime']
    verify_identity(runtime)
    prior_requests = read(PRIOR / 'REQUESTS_PRIVATE.json')
    assert digest(prior_requests) == prior_protocol['requests_identity']
    cache = {}
    for req in prior_requests:
        verify_identity(req)
        assert digest(req['messages']) == req['messages_identity']
        assert req['runtime_identity'] == runtime['identity']
        cache[(runtime['identity'], req['messages_identity'])] = req
    cards, inputs, reused = [], {}, {}
    # This is a selected branch for a diagnostic, not a new global action limit.
    for depth in range(len(audit['actual_keys']) + 1):
        if depth:
            session.get('MS')
        acquired = session.receipt()['acquired']
        assert acquired == audit['actual_keys'][:depth]
        presented = cat.canonical(acquired)
        usage = renderer.usage(cat, acquired)
        assert usage['within_native_context'] and not usage['truncation']
        messages = renderer.messages(cat, acquired)
        body = dict(prefix_identity=cat.prefix.identity, catalog_identity=cat.identity,
                    renderer_identity=renderer.identity, messages=messages,
                    selected_keys=[x.key for x in presented],
                    selected_resource_identities=[x.identity for x in presented], usage=usage)
        key = digest(body)
        inputs[key] = dict(body, identity=key)
        old = cache.get((runtime['identity'], digest(messages)))
        if old:
            path = PRIOR / 'raw' / (old['identity'] + '.json')
            raw = read(path)
            assert old['messages'] == messages and old['selected_keys'] == body['selected_keys']
            assert old['selected_resource_identities'] == body['selected_resource_identities']
            assert raw['request_identity'] == old['identity']
            assert raw['runtime_identity'] == runtime['identity']
            assert raw['input_identity'] == old['input_identity']
            assert raw['text_identity'] == digest(raw['text'])
            assert raw['finish_reason'] == 'natural_stop' and raw['completed_assistant_turn']
            reused[key] = dict(request=old, raw=raw, source=str(path.resolve()), sha256=sha(path))
        cards.append(dict(case='N23', arm=f'MS{depth}_STOP', depth=depth,
                          actual_program=[3] * depth + [0], acquisition_order=list(acquired),
                          input_identity=key, reused=old is not None, human_preference=None, reward=None))
    assert len(cards) == 5 and len(reused) == 2
    assert digest(inputs[cards[-1]['input_identity']]['messages']) == audit['actual_messages_identity']
    target_req = next(r for r in prior_requests if r['identity'] == audit['exact_judged_input'])
    target_path = PRIOR / 'raw' / (target_req['identity'] + '.json')
    target_raw = read(target_path)
    assert target_raw['text_identity'] == audit['preferred_reply_identity']
    assert reused[cards[0]['input_identity']]['raw']['text_identity'] == audit['OFF_reply_identity']
    sources = [REVIEW / 'SLIGHT_POSITIVE_PATH_AUDIT_PRIVATE.json', REVIEW / 'ANSWER_REGISTRY_PRIVATE.json',
               REVIEW / 'CLOSEOUT_MANIFEST.json', AUDIT / 'OPPORTUNITIES_PRIVATE.json',
               PRIOR / 'OUTPUT_MANIFEST.json', PRIOR / 'PROTOCOL.json',
               PRIOR / 'REQUESTS_PRIVATE.json', TRAIN / 'PACKAGE_MANIFEST.json',
               TRAIN / 'sources_private' / f"{cat.prefix.identity}.json"]
    source = read(sources[-1])
    sources.append(Path(source['stored_source_path']))
    study = stamp(dict(scope='N23_EXISTING_SLIGHT_PREFERENCE_ACTUAL_MS_BRANCH_DIAGNOSTIC',
        case='N23', prefix_identity=cat.prefix.identity, runtime_identity=runtime['identity'],
        cards_identity=digest(cards), inputs_identity=digest(inputs), reused_identity=digest(reused),
        source_hashes={str(p.resolve()): sha(p) for p in sources},
        new_calls=3, cached_replies=2, max_loads=1, automatic_retries=0,
        selection='Previously judged slight positive G01; shorter of two audited MS routes, not latency or globally shortest route.',
        interpretation=[
            'Acquire each MS using unchanged dynamic rank; render all acquired complete sources in canonical order.',
            'All five STOP depths included before generation; no choosing only the winning depth afterward.',
            'Human G01 preference applies to the old exact target-only pair; do not transfer by semantic similarity.',
            'Naturalness and support timing can be benefits; source mention alone is not benefit.',
            'One greedy reply per input, local G seconds are not deployment latency; failures remain missing.',
            'No actor sees analyst target annotations; this diagnostic does not promote the candidate G.',
            'No new human questionnaire or scalar reward automatically created.'],
        api_cost_usd=0, new_training_updates=0, new_qualified_rewards=0))
    out.mkdir(mode=0o700)
    for name, obj in [('STUDY.json', study), ('INPUTS_PRIVATE.json', inputs), ('CARDS_PRIVATE.json', cards),
                      ('REUSED_PRIVATE.json', reused), ('EVIDENCE_PRIVATE.json', source['evidence']),
                      ('OLD_HUMAN_REFERENCE_PRIVATE.json', dict(audit=audit, request=target_req, raw=target_raw,
                            source=str(target_path.resolve()), sha256=sha(target_path))),
                      ('USER_AUTHORIZATION.json', dict(date='2026-11-05 Asia/Tokyo',
                            actual_user_message='好的 继续推进',
                            inherited_plan='补齐N23实际读取路径，先复用旧结果及判断，再决定延迟与受限学习。',
                            scope='3条新的本地候选G回复，保持旧G与人评；无付费、训练、自动重试。'))]:
        save(out / name, obj)
    print(json.dumps(dict(status='PREPARED', branch_endpoints=5, reused=2, new_calls=3)), flush=True)


def prepare_runtime(out):
    from transformers import AutoTokenizer
    study = read(out / 'STUDY.json')
    verify_identity(study)
    for path, expected in study['source_hashes'].items():
        assert sha(Path(path)) == expected, path
    old = read(PRIOR / 'PROTOCOL.json')
    runtime = old['runtime']
    tokenizer = AutoTokenizer.from_pretrained(runtime['model_dir'], local_files_only=True)
    assert digest(tokenizer.chat_template) == runtime['chat_template_identity']
    inputs, cards, reused = [read(out / name) for name in
                             ('INPUTS_PRIVATE.json', 'CARDS_PRIVATE.json', 'REUSED_PRIVATE.json')]
    for name, obj in [('inputs', inputs), ('cards', cards), ('reused', reused)]:
        assert digest(obj) == study[name + '_identity']
    requests = []
    for card in cards:
        key = card['input_identity']
        item = inputs[key]
        ids = tokenizer.apply_chat_template(item['messages'], tokenize=True, add_generation_prompt=True,
                                            enable_thinking=False, return_dict=False)
        assert 0 < len(ids) < runtime['policy']['context_limit']
        if card['reused']:
            assert reused[key]['request']['token_ids_identity'] == digest(ids)
            assert reused[key]['request']['input_tokens'] == len(ids)
            continue
        requests.append(stamp(dict(input_identity=key, messages=item['messages'], messages_identity=digest(item['messages']),
            selected_keys=item['selected_keys'], selected_resource_identities=item['selected_resource_identities'],
            runtime_identity=runtime['identity'], input_tokens=len(ids), token_ids_identity=digest(ids))))
    assert len(requests) == study['new_calls'] == 3
    random.Random(20261105).shuffle(requests)
    code = [Path(__file__), PROJECT / 'scripts/rl1/167_probe_alternate_executor.py',
            PROJECT / 'src/metacom_pm/rl1/generation.py', PROJECT / 'src/metacom_pm/rl1/local_gpu_guard.py',
            PROJECT / 'src/metacom_pm/rl1/durable.py']
    protocol = stamp(dict(scope=study['scope'], runtime=runtime, gpu_uuid=old['gpu_uuid'],
        requests_identity=digest(requests), sources={str(p.resolve()): sha(p) for p in out.glob('*.json')},
        code={str(p.resolve()): sha(p) for p in code}, stage_seconds=1200,
        max_loads=1, max_calls=3, automatic_retries=0, api_cost_usd=0,
        new_training=False, new_rewards=False, promote=False, authorization=read(out / 'USER_AUTHORIZATION.json')))
    run_dir = out / 'alternate_G'
    run_dir.mkdir(mode=0o700)
    save(run_dir / 'PROTOCOL.json', protocol)
    save(run_dir / 'REQUESTS_PRIVATE.json', requests)
    print(json.dumps(dict(status='RUNTIME_PREPARED', new_calls=3, runtime=runtime['identity'])), flush=True)


def run(out):
    spec = importlib.util.spec_from_file_location('frozen_alternate', PROJECT / 'scripts/rl1/167_probe_alternate_executor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run(out / 'alternate_G')


def analyze(out):
    reused = read(out / 'REUSED_PRIVATE.json')
    requests = read(out / 'alternate_G/REQUESTS_PRIVATE.json')
    reference = read(out / 'OLD_HUMAN_REFERENCE_PRIVATE.json')
    registry = read(REVIEW / 'ANSWER_REGISTRY_PRIVATE.json')
    rows = []
    for card in read(out / 'CARDS_PRIVATE.json'):
        key = card['input_identity']
        if card['reused']:
            record = reused[key]
            raw, source = record['raw'], record['source']
            assert sha(Path(source)) == record['sha256']
        else:
            req = next(r for r in requests if r['input_identity'] == key)
            source = str(out / 'alternate_G/raw' / (req['identity'] + '.json'))
            raw = read(Path(source)) if Path(source).exists() else None
        text = raw['text'] if raw else None
        format_failure = None if raw is None else any(marker in raw['decoded_with_special_tokens'] for marker in
                     ('[channel]', '<|channel', '<channel|>', '<think>', '</think>'))
        rows.append(dict(**card, reply=text, reply_identity=digest(text) if text is not None else None,
            raw_source=source, finish_reason=raw['finish_reason'] if raw else 'pending',
            format_failure=format_failure, output_tokens=raw['output_tokens'] if raw else None,
            G_seconds=raw['generation_seconds'] if raw else None,
            G_first_token_seconds=raw['first_token_seconds'] if raw else None,
            exact_old_preferred_reply=text == reference['raw']['text'],
            old_human_preference_transferred=False))
    # Registry inspection/rebinding is a separate evidence review, never text-only auto-labeling.
    save(out / 'RESULTS_PRIVATE.json', rows)
    save(out / 'SUMMARY.json', dict(branch_endpoints=len(rows), reused=2, new_calls=len(requests),
         natural=sum(r['finish_reason'] == 'natural_stop' for r in rows),
         format_failures=sum(r['format_failure'] is True for r in rows),
         exact_old_preferred_replies=sum(r['exact_old_preferred_reply'] for r in rows),
         source_registry_identity=digest(registry), human_preferences_pending=True,
         new_qualified_rewards=0, new_training_updates=0, api_cost_usd=0))
    print(json.dumps(read(out / 'SUMMARY.json')), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'prepare_runtime', 'run', 'analyze'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    globals()[args.mode](args.output.resolve())

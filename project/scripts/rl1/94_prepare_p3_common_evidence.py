#!/usr/bin/env python3
"""Prepare method-independent legal evidence for the frozen common prefixes.

No response contents, scores, human labels, test targets, or model inference are
read. This binds source material only, not a calibrated measurement protocol.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.rl1.evidence import evidence_turns, legal_evidence, prefix_from_dict
from metacom_pm.rl1.representation import ROLE_INSTRUCTION
from metacom_pm.rl1.schema import digest

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2'
OUT = ROOT / 'P3/common_evidence'
MODEL = Path('/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b')


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    if (OUT / 'input_freeze.json').exists():
        raise RuntimeError('evidence input already frozen')
    freeze_path = ROOT / 'P2/common_pool/input_freeze.json'
    pool = freeze_path.parent
    freeze = read(freeze_path)
    for name, expected in freeze['files'].items():
        assert sha256_file(pool / name) == expected, name
    for name, expected in freeze['source_files'].items():
        assert sha256_file(PROJECT / name) == expected, name
    slots = read(pool / 'slots_private.json')['rows']
    indexes = sorted({slot['index'] for slot in slots})
    assert len(indexes) == 42
    source = PROJECT / 'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    users = {user.owner_id: user for user in load_sanitized_runtime_users(source)}
    specs_path = ROOT / 'P1/episode_specs_private.json'
    specs = read(specs_path)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    evidence_pool = {}; mappings = []; stats = []
    for index in indexes:
        prefix = prefix_from_dict(specs[index]['prefix'])
        assert prefix.split in ('train', 'dev'), 'test evidence is outside this preparation'
        evidence, mapping = legal_evidence(prefix, users[prefix.owner_id])
        # This is the evaluator-only full legal history, independent of the
        # resources a particular candidate plan selected or ignored.
        assert set(evidence) == {'current_date', 'current_prefix', 'legal_past_sessions'}
        turns = evidence_turns(evidence)
        assert len(evidence['current_prefix']) == prefix.cut_after_turn_index + 1
        assert evidence['current_prefix'][-1]['role'] == 'seeker'
        assert all(row['rank'] < prefix.cutoff_rank for row in mapping['source_map'])
        assert len(mapping['source_map']) == len(evidence['legal_past_sessions'])
        for slot in slots:
            if slot['index'] == index:
                assert slot['prefix_identity'] == prefix.identity
        # Token count of evidence alone, not a promise that a future whole
        # scoring request fits. Prompt/schema/reply overhead is still pending.
        serialized = json.dumps(evidence, ensure_ascii=False)
        token_count = len(tokenizer.encode(serialized, add_special_tokens=False))
        evidence_pool[prefix.identity] = evidence
        mappings.append(dict(index=index, split=prefix.split, owner=prefix.owner_id, **mapping))
        stats.append(dict(index=index, split=prefix.split, owner=prefix.owner_id,
            prefix_identity=prefix.identity, evidence_identity=digest(evidence),
            current_turns=len(evidence['current_prefix']), past_sessions=len(evidence['legal_past_sessions']),
            source_turns=len(turns), evidence_only_tokens=token_count,
            full_source_turn_hashes=sorted({digest([turn['role'], turn['text']]) for turn in turns.values()})))
    assert len(evidence_pool) == 42
    speaker_contract = dict(status='TASK_CONTEXT_NOT_AN_ANSWER_OR_SCORE',
        current_reply_speaker='Current AI assistant, distinct from every historical supporter.',
        executor_role_instruction=ROLE_INSTRUCTION,
        evaluation_scope='All methods receive identical complete as-of source evidence for a prefix. '
            'Do not reveal resource plans, executor, cost, seed, method names, or preferred answers to scorers/humans.',
        note='Speaker contract is task context, never fabricated dialogue evidence or an actor observation.')
    summary = dict(status='COMMON_SOURCE_INPUTS_PREPARED_NOT_SCORER_OR_HUMAN_PACKAGE',
        prefixes=len(indexes), by_split=dict(Counter(row['split'] for row in stats)),
        owners_by_split={split: len({row['owner'] for row in stats if row['split'] == split})
            for split in ('train', 'dev')}, common_primary_slots=len(slots),
        source_turns_across_prefixes=sum(row['source_turns'] for row in stats),
        source_turn_count_note='Repeated historical turns across prefixes are counted repeatedly, not independent facts.',
        evidence_only_tokens={key: value for key, value in zip(('min', 'median', 'max'),
            (min(row['evidence_only_tokens'] for row in stats),
             statistics.median(row['evidence_only_tokens'] for row in stats),
             max(row['evidence_only_tokens'] for row in stats)))},
        token_scope='Qwen tokenizer, serialized legal evidence alone; whole future scorer request is not yet checked.',
        response_contents_read=0, scorer_calls=0, human_tasks=0, test_prefixes=0,
        API_usd=0, reward_qualified=False,
        remaining=['Freeze one scorer role/scope/schema identity after development preparation.',
            'Partition finite human pairs by prefix and actual fact family, preserving shared-history dependencies.',
            'Build blinded source-linked human forms and sealed-label ingestion; obtain real human judgments.',
            'Measure actual complete-request context/throughput and bounded calibration before PPO.'])
    OUT.mkdir(parents=True, exist_ok=True)
    save(OUT / 'evidence_pool_private.json', evidence_pool)
    save(OUT / 'source_map_private.json', mappings)
    save(OUT / 'source_statistics_private.json', stats)
    save(OUT / 'speaker_contract.json', speaker_contract)
    save(OUT / 'summary.json', summary)
    guards = [freeze_path, specs_path, source, Path(__file__),
        PROJECT / 'src/metacom_pm/rl1/evidence.py', PROJECT / 'src/metacom_pm/rl1/representation.py',
        PROJECT / 'src/metacom_pm/paper1/data/memory_source.py']
    manifest = dict(status=summary['status'],
        files={p.name: sha256_file(p) for p in sorted(OUT.glob('*.json'))},
        source_files={str(p.relative_to(PROJECT)): sha256_file(p) for p in guards},
        tokenizer_files={p.name: sha256_file(p) for p in sorted(MODEL.iterdir())
            if p.is_file() and p.suffix in ('.json', '.jinja', '.txt')},
        tokenizer_class=type(tokenizer).__name__, task_context_identity=digest(speaker_contract))
    save(OUT / 'input_freeze.json', manifest)
    save(PROJECT / 'docs/pm_rl1_completion_20260930_v2/p3_evidence_preparation.json',
        dict(summary, input_freeze_sha256=sha256_file(OUT / 'input_freeze.json')))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    main()

"""CPU-only feasibility audit of frozen train/dev QA and existing human evidence.

No model calls, answer scoring, repairs, dataset admissions or runtime changes.
"""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT / 'outputs/pm_rl1'
OLD = BASE / 'dataset_diagnostics_20260930_v1'
HUMAN = BASE / 'history_necessity_human_review_20261105_v1'
OUT = BASE / 'value_and_novelty_audit_20261105_v1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return row['owner'], row['group'], int(row['idx'])


def form(row):
    if row['unknown_answer']:
        return 'unknown'
    if re.match(r'^(no\b|false\b)', row['answer'].strip(), re.I):
        return 'negative_prefix'
    if re.match(r'^(yes\b|true\b)', row['answer'].strip(), re.I):
        return 'positive_prefix'
    return 'open_other'


def main():
    checked = {}
    for rel, expected in read(OLD / 'closeout.json')['artifacts'].items():
        path = PROJECT / rel
        assert sha(path) == expected, rel
        checked[str(path.resolve())] = expected
    for rel, expected in read(HUMAN / 'OUTPUT_MANIFEST.json').items():
        path = HUMAN / rel
        assert sha(path) == expected, rel
        checked[str(path.resolve())] = expected
    q = read(OLD / 'qa_train_dev_review_private.json')
    census = read(OLD / 'census.json')
    with (OLD / 'qa_audit_registry.csv').open() as f:
        registry = {key(r): r for r in csv.DictReader(f)}
    with (OLD / 'qa_train_dev_features.csv').open() as f:
        features = {key(r): r for r in csv.DictReader(f)}
    assert len(q) == len(registry) == len(features) == len({key(r) for r in q}) == 1261
    assert all(r['split'] in ('train', 'dev') for r in q)
    assert all(census['owner_splits'][r['owner']] == r['split'] for r in q)
    for r in q:
        assert registry[key(r)]['capability'] == r['capability']
        assert all(str(r[k]) == features[key(r)][k] for k in features[key(r)])
        sessions = {x['session'] for x in r['reference_resolution']
                    if x['kind'] in ('visible_turn', 'visible_session')}
        assert len(sessions) == r['visible_evidence_sessions']
    dimensions = {}
    for split in ('train', 'dev', 'combined'):
        rows = [r for r in q if split == 'combined' or r['split'] == split]
        dimensions[split] = dict(rows=len(rows), owners=len({r['owner'] for r in rows}),
            capabilities=dict(Counter(r['capability'] for r in rows)),
            strata=dict(Counter(registry[key(r)]['structural_stratum'] for r in rows)),
            visible_sessions=dict(Counter(str(min(2, r['visible_evidence_sessions'])) for r in rows)),
            visible_sessions_key='0 / 1 / 2 means no cited visible session / one / at least two; not minimal necessary reads.',
            solely_visible_resolved=sum(bool(r['visible_evidence_sessions']) and not r['private_event_refs'] and not r['unresolved_refs'] for r in rows),
            multisession_solely_visible_resolved=sum(r['visible_evidence_sessions'] >= 2 and not r['private_event_refs'] and not r['unresolved_refs'] for r in rows),
            short_extractive_candidates=sum(r['capability'] == 'information extraction' and r['answer_words'] <= 5
                and bool(r['literal_seeker_answer_hits']) and not r['unresolved_refs'] for r in rows),
            answer_form_by_capability={cap: dict(Counter(form(r) for r in rows if r['capability'] == cap))
                for cap in sorted({r['capability'] for r in rows})})
    assert dimensions['train']['rows'] == census['tasks']['train']['qa'] == 1003
    assert dimensions['dev']['rows'] == census['tasks']['dev']['qa'] == 258
    assert dimensions['combined']['visible_sessions']['2'] == 219
    sample = []
    for cap in sorted(dimensions['train']['capabilities']):
        eligible = [r for r in q if r['split'] == 'train' and r['capability'] == cap]
        sample.extend(sorted(eligible, key=lambda r: hashlib.sha256('|'.join(map(str, key(r))).encode()).hexdigest())[:3])
    assert len(sample) == 15
    old_semantic = read(OLD / 'semantic_review_findings_private.json')
    natural = read(HUMAN / 'SUMMARY.json')
    findings = dict(scope='EXISTING_TRAIN_DEV_DATA_AND_LITERATURE_FEASIBILITY_ONLY',
        local_dataset_version='ES-MemEval-Public-v1.0.0-1427',
        task_counts_metadata_only=census['tasks'], qa=dimensions,
        old_qa_inventory_already_existed=True, old_semantic_examples=len(old_semantic['rows']),
        new_citation_review_examples=15, new_example_selection='SHA256(owner|group|idx), first three train rows per capability; illustrative, not prevalence.',
        natural_history_value=natural['primary_ordinal_analysis'],
        three_questions=dict(response_quality='SPECIFIC_INTERACTION_PROBLEMS_OBSERVED; improvement magnitude not established',
            incremental_resource_value='NATURAL_PROBE_GATE_NOT_MET; QA_HAS_SOURCE_GROUNDED_CANDIDATES_NOT_MEASURED_GAIN',
            sequential_policy_value='NOT_ESTABLISHED; multi-session citations do not prove adaptive value'),
        evidence_type_note='A citation or literal answer hit is not semantic certification, a usable reward, or a deployable retrieval path.',
        shortcut_note='Answer-prefix counts are dataset diagnostics, not predictions or measured classifier accuracy; task capability labels remain evaluator-only.',
        new_qualified_rewards=0, model_calls=0, new_training_updates=0, API_cost_usd=0,
        test_gold_content_read=False, old_protocol_reopened=False,
        research_decision='BOUNDED_GAIN_VALIDATION_WORTH_PREPARING; FULL_RL_AND_NOVELTY_CLAIM_NOT_JUSTIFIED_YET')
    outputs = {'SOURCE_MANIFEST.json': checked, 'QA_SUMMARY.json': findings,
        'CITATION_SAMPLE_PRIVATE.json': sample}
    for name, value in outputs.items():
        with (OUT / name).open('x') as f:
            f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        (OUT / name).chmod(0o600)
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

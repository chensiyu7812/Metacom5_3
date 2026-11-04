"""Append the received N21 answer; preserve AI assistance and non-cardinal wording."""
import hashlib
import json
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT / 'outputs/pm_rl1'
ROOT = BASE / 'resource_value_probe_20261104_v1'


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def main():
    question = read(ROOT / 'ONE_COMPARISON_PRIVATE.json')
    received = read(ROOT / 'RECEIVED_ANSWER_PRIVATE.json')
    original = read(BASE / 'contextual_value_reference_20261104_v1/ANSWER_REGISTRY_PRIVATE.json')
    results = read(ROOT / 'RESULTS_PRIVATE.json')
    assert question['case'] == 'N21' and question['human_answer'] is None
    evidence_id = digest(question['evidence'])
    bindings = {}
    for alias, binding in zip(('A', 'B'), question['response_binding']):
        row = next(r for r in results if r['case'] == 'N21' and r['arm'] == question['arm_' + alias])
        assert row['input_identity'] == binding['input_identity']
        assert digest(question['reply_' + alias]) == row['reply_identity'] == binding['reply_identity']
        bindings[alias] = dict(binding, arm=row['arm'], reply=row['reply'])
    pair_id = digest(dict(evidence=evidence_id, replies=sorted(x['reply_identity'] for x in bindings.values())))
    assert not any(r.get('pair_identity') == pair_id for r in original)
    intake = dict(**received, question_artifact='ONE_COMPARISON_PRIVATE.json',
                  question_artifact_sha256=hashlib.sha256((ROOT / 'ONE_COMPARISON_PRIVATE.json').read_bytes()).hexdigest(),
                  evidence_identity=evidence_id, pair_identity=pair_id, alias_bindings=bindings,
                  observation_origin='researcher judgment after consulting web ChatGPT translation/analysis',
                  human_respondents=1, independent_validation=False, web_analysis_is_not_second_human_rater=True,
                  practical_comparison='A_slightly_better_limited_gain_possible_premature_self_care',
                  illustrative_values=dict(A=95, B=90), values_are_cardinal_utilities=False,
                  preference_dependence='researcher hypothesis; no recipient preference observation',
                  exact_qm=None, numeric_reward=None, qualified_reward=False,
                  decision_use='No automatic material-benefit reward for correct memory use or layout change; retain slight gain and uncertainty.',
                  reask_same_question=False)
    record_id = 'pmrl1-n21-layout-limited-benefit-20261104-v1'
    ref = dict(direction='near_equivalent_with_small_A_edge', evidence_identity=evidence_id,
               independent_frozen_validation=False, kind='pair_preference_with_illustrative_magnitude',
               observation_origin=intake['observation_origin'], pair_identity=pair_id,
               preferred_reply_identity=None, slight_edge_reply_identity=bindings['A']['reply_identity'],
               purpose='exposed exploratory diagnostic; not a scalar reward or independent rater agreement',
               qualified_reward=False, raw_label=dict(original_answer=received['original_answer']),
               record_id=record_id, reply_identities=sorted(x['reply_identity'] for x in bindings.values()),
               source='20261104_current_conversation', asset_id='pairs:20261104_current_conversation:' + record_id,
               evidence=question['evidence'], replies={x['reply_identity']:x['reply'] for x in bindings.values()},
               task_family='pairs', independent_new_observation=False, new_answer_event=True,
               independence_note='One researcher answer after AI assistance; neither independent validation nor two human ratings.',
               original_question_number=None, intake_identity=digest(intake))
    merged = original + [ref]
    assert len(merged) == 36 and len({r['asset_id'] for r in merged}) == len(merged)
    for row in merged:
        assert digest(row['evidence']) == row['evidence_identity']
        assert all(digest(text) == key for key, text in row['replies'].items())
    outputs = {'INTAKE_PRIVATE.json':intake, 'ANSWER_REGISTRY_PRIVATE.json':merged,
               'REFERENCE_INDEX.json':dict(active_registry=str(ROOT / 'ANSWER_REGISTRY_PRIVATE.json'),
                   base_registry=str(BASE / 'contextual_value_reference_20261104_v1/ANSWER_REGISTRY_PRIVATE.json'),
                   old_records_preserved=35, new_answer_events=1, registry_records=len(merged),
                   registry_task_families=dict(Counter(r['task_family'] for r in merged)),
                   new_scalar_rewards=0, scoring_or_training_automatically_reconfigured=False)}
    for name, value in outputs.items():
        path = ROOT / name
        if path.exists():
            assert read(path) == value, 'existing intake differs; do not overwrite'
        else:
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            path.chmod(0o600)
    print(json.dumps(outputs['REFERENCE_INDEX.json'], ensure_ascii=False))


if __name__ == '__main__':
    main()

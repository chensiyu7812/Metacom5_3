"""One-time ordinal intake; no model, reward conversion, or original-file writes."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT / 'outputs/pm_rl1'
SOURCE = BASE / 'history_necessity_probe_20261105_v1'
PRIOR = BASE / 'incremental_help_human_review_20261105_v1/ANSWER_REGISTRY_PRIVATE.json'
OUT = BASE / 'history_necessity_human_review_20261105_v1'
STUDY = 'c52a56fd81d55d112ce227063bbdbcff0d0fb3325df03c03c2adde5a298e4e78'


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_keys)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def parse_order(order, labels):
    if not re.fullmatch(r'[ABC](?:[>=][ABC])*', order):
        raise ValueError('invalid ordinal expression')
    groups = [group.split('=') for group in order.split('>')]
    seen = [label for group in groups for label in group]
    if len(seen) != len(set(seen)) or set(seen) != set(labels):
        raise ValueError('missing, duplicate or unexpected display label')
    return {label: rank for rank, group in enumerate(groups) for label in group}


def validate_submission(answer, packet):
    if answer['study'] != packet['identity'] or answer['study'] != STUDY:
        raise ValueError('wrong study identity')
    if set(answer['answers']) != {m['question'] for m in packet['mapping']}:
        raise ValueError('question coverage mismatch')
    for mapping in packet['mapping']:
        a = answer['answers'][mapping['question']]
        parse_order(a['order'], mapping['display'])
        if a['degree'] not in ('', '略好', '有实质改善', '不确定') or not isinstance(a['reason'], str):
            raise ValueError('invalid degree/reason')


def summarize(rows):
    joint = [r for r in rows if r['relations']['C/OFF'] == r['relations']['C/D'] == 'preferred']
    return dict(cases=len(rows), joint_wins=len(joint), joint_questions=[r['question'] for r in joint],
        joint_owners=sorted({r['owner'] for r in joint}),
        comparisons={pair: {state: sum(r['relations'][pair] == state for r in rows)
            for state in ('preferred', 'equivalent', 'worse', 'not_directly_judged')}
            for pair in ('C/OFF', 'C/D', 'D/OFF')})


def main():
    for name, expected in read(SOURCE / 'OUTPUT_MANIFEST.json').items():
        assert sha(SOURCE / name) == expected, name
    packet = read(SOURCE / 'HUMAN_PACKET_PRIVATE.json')
    protocol = read(SOURCE / 'SCREENING_PROTOCOL.json')
    selection = read(SOURCE / 'SELECTION_PRIVATE.json')
    for obj in (packet, protocol, selection):
        assert obj['identity'] == digest({k: v for k, v in obj.items() if k != 'identity'})
    for path, expected in packet['source_hashes'].items():
        assert sha(Path(path)) == expected, path
    assert packet['selection_identity'] == selection['identity']
    assert selection['screening_protocol'] == protocol['identity']
    submitted = read(OUT / 'RECEIVED_ANSWER_PRIVATE.json')
    validate_submission(submitted, packet)
    results = {(r['case'], r['arm']): r for r in read(SOURCE / 'RESULTS_PRIVATE.json')}
    reused = read(SOURCE / 'REUSED_HUMAN_PRIVATE.json')
    assert digest(reused) == packet['reused_human_identity']
    cases = {r['case']: r for r in selection['cases']}
    old = read(PRIOR)
    assert len(old) == 45
    rows, records = [], []
    for mapping in packet['mapping']:
        question, case = mapping['question'], mapping['case']
        a = submitted['answers'][question]
        display_ranks = parse_order(a['order'], mapping['display'])
        ranks = {binding['arm']: display_ranks[label] for label, binding in mapping['display'].items()}
        relations, origins, replies = {}, {}, {}
        for label, binding in mapping['display'].items():
            r = results[case, binding['arm']]
            assert r['valid'] and digest(r['raw']['text']) == binding['reply_identity']
            assert read(Path(r['source'])) == r['raw']
            replies[binding['reply_identity']] = r['raw']['text']
        for pair in ('C/OFF', 'C/D', 'D/OFF'):
            left, right = pair.split('/')
            if left in ranks and right in ranks:
                relations[pair] = ('preferred' if ranks[left] < ranks[right] else
                                   'worse' if ranks[left] > ranks[right] else 'equivalent')
                origins[pair] = 'current_question_order'
            else:
                relations[pair], origins[pair] = 'not_directly_judged', None
        if mapping['reused_record']:
            item = reused[case]
            assert item['record'] in old and item['record']['record_id'] == mapping['reused_record']
            assert sha(Path(item['registry'])) == item['registry_sha256']
            for arm in ('C', 'OFF'):
                raw = results[case, arm]['raw']
                assert item['record']['replies'][raw['text_identity']] == raw['text']
            relations['C/OFF'] = {1: 'preferred', 0: 'equivalent', -1: 'worse'}[item['C_over_OFF']]
            origins['C/OFF'] = dict(record_id=mapping['reused_record'], evidence_scope=item['evidence_scope'])
        evidence = dict(current=cases[case]['prefix'], C=cases[case]['C'], D=cases[case]['D'])
        row = dict(question=question, case=case, owner=mapping['owner'], original_answer=a,
            alias_bindings=mapping['display'], relations=relations, relation_origins=origins,
            degree_uncertain=a['degree'] == '不确定', evidence_identity=digest(evidence))
        rows.append(row)
        rid = 'pmrl1-history-necessity-human-20261105-' + question
        record = dict(record_id=rid, asset_id='history-necessity:' + rid,
            task_family='rankings' if mapping['mode'] == 'rank' else 'pairs',
            kind='triplet_ordinal_preference' if mapping['mode'] == 'rank' else 'pair_preference',
            study=STUDY, question_id=question, raw_label=a, alias_bindings=mapping['display'],
            evidence=evidence, evidence_identity=digest(evidence), replies=replies,
            reply_identities=sorted(replies), degree=a['degree'], degree_uncertain=row['degree_uncertain'],
            ordinal_scope='One question-level ranking; degree is not a separately measured pairwise magnitude.',
            source='20261105_current_conversation', human_respondents=1, new_answer_event=True,
            independent_frozen_validation=False, independent_new_observation=False,
            independence_note='Same researcher; development cases, shared owners and replies; derived pairs are not independent answers.',
            translation_exposure=packet['translation'], assistance_status='not_reported',
            qualified_reward=False, numeric_reward=None, exact_qm=None, intake_identity=digest(row))
        if mapping['mode'] == 'pair':
            record.update(pair_identity=digest(dict(evidence=digest(evidence), replies=sorted(replies))),
                          direction=relations['C/D'])
        records.append(record)
    merged = old + records
    assert len(merged) == len({r['asset_id'] for r in merged}) == 55
    for r in merged:
        assert digest(r['evidence']) == r['evidence_identity']
        assert all(digest(text) == key for key, text in r['replies'].items())
    primary = summarize(rows)
    gate = protocol['decision_gate']
    checks = dict(coverage=primary['cases'] >= gate['required_valid_triplets'],
        joint_wins=primary['joint_wins'] >= gate['required_joint_wins'],
        owners=len(primary['joint_owners']) >= gate['required_joint_win_owners'],
        loss_check=primary['joint_wins'] > primary['comparisons']['C/OFF']['worse'])
    summary = dict(study=STUDY, primary_ordinal_analysis=primary, protocol_gate=gate,
        gate_checks=checks, continuation_gate_passed=all(checks.values()),
        decision='STOP_POSITIVE_EXPANSION_UNDER_THIS_PROTOCOL',
        uncertain_degree_questions=[r['question'] for r in rows if r['degree_uncertain']],
        sensitivity_excluding_uncertain_degree=summarize([r for r in rows if not r['degree_uncertain']]),
        sensitivity_note='8 cases are coverage-incomplete, not a new study. No imputation, substitution or additional questions.',
        source_error_rule='No source-confirmed error supplying either observed joint advantage in the pre-answer content audit; no positive case excluded.',
        human_submission_units=10, new_derived_pair_relations=26, reused_pair_relations=2,
        new_material_improvement_labels=sum(a['degree'] == '有实质改善' for a in submitted['answers'].values()),
        qualified_scalar_rewards=0, new_questions=0, new_model_calls=0, API_cost_usd=0,
        training_updates=0, existing_cost_negative_control_PPO_updates=24)
    # This is a closeout, not a generic evaluator that silently follows an unexpected branch.
    assert not summary['continuation_gate_passed']
    outputs = {
        'INTAKE_PRIVATE.json': dict(study=STUDY, rows=rows,
            serialization_note='Submitted JSON indentation normalized to ordinary spaces; all answer strings retained verbatim. Not a byte-level transport capture.',
            sources={str(p.resolve()): sha(p) for p in [SOURCE / 'OUTPUT_MANIFEST.json',
                SOURCE / 'HUMAN_PACKET_PRIVATE.json', SOURCE / 'CONTENT_AUDIT_PRIVATE.json',
                PRIOR, OUT / 'RECEIVED_ANSWER_PRIVATE.json']}),
        'ANSWER_REGISTRY_PRIVATE.json': merged,
        'REFERENCE_INDEX.json': dict(active_registry=str(OUT / 'ANSWER_REGISTRY_PRIVATE.json'),
            base_registry=str(PRIOR), old_records_preserved=45, new_answer_events=10, registry_records=55,
            registry_task_families=dict(Counter(r['task_family'] for r in merged)),
            grain='36 pair records, 8 triplet records, 8 single q/m records, 3 supplements; not 55 independent pair labels.',
            scoring_or_training_automatically_reconfigured=False),
        'SUMMARY.json': summary,
    }
    for name, value in outputs.items():
        with (OUT / name).open('x') as f:
            f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    for p in OUT.iterdir():
        if p.is_file():
            p.chmod(0o600)
    with (OUT / 'OUTPUT_MANIFEST.json').open('x') as f:
        json.dump({p.name: sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'OUTPUT_MANIFEST.json'}, f, indent=2)
        f.write('\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

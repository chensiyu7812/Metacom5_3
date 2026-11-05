"""Read-only independent unblinding expectations and intake rejection checks."""
import copy
import json
from collections import Counter
from ingest import OUT, PRIOR, SOURCE, digest, parse_order, read, sha, unique_keys, validate_submission


def main():
    checked = {}
    for name, folder in [('frozen_probe', SOURCE), ('new_intake', OUT)]:
        manifest = read(folder / 'OUTPUT_MANIFEST.json')
        for path, expected in manifest.items():
            assert sha(folder / path) == expected, path
        checked[name + '_files_unchanged'] = len(manifest)
    intake = read(OUT / 'INTAKE_PRIVATE.json')
    for path, expected in intake['sources'].items():
        from pathlib import Path
        assert sha(Path(path)) == expected, path
    packet = read(SOURCE / 'HUMAN_PACKET_PRIVATE.json')
    answer = read(OUT / 'RECEIVED_ANSWER_PRIVATE.json')
    validate_submission(answer, packet)
    expected = [
        ('Q01', 'H63', 'p3', 'preferred', 'preferred', 'equivalent'),
        ('Q02', 'H07', 'p10', 'preferred', 'equivalent', 'preferred'),
        ('Q03', 'H74', 'p6', 'equivalent', 'worse', 'preferred'),
        ('Q04', 'H95', 'p9', 'equivalent', 'equivalent', 'equivalent'),
        ('Q05', 'H34', 'p16', 'preferred', 'equivalent', 'not_directly_judged'),
        ('Q06', 'H59', 'p3', 'worse', 'worse', 'worse'),
        ('Q07', 'H36', 'p16', 'equivalent', 'equivalent', 'equivalent'),
        ('Q08', 'H16', 'p11', 'preferred', 'preferred', 'equivalent'),
        ('Q09', 'H79', 'p6', 'equivalent', 'equivalent', 'not_directly_judged'),
        ('Q10', 'H27', 'p13', 'equivalent', 'preferred', 'worse'),
    ]
    for row, (q, case, owner, *relations) in zip(intake['rows'], expected, strict=True):
        assert (row['question'], row['case'], row['owner']) == (q, case, owner)
        assert row['original_answer'] == answer['answers'][q]
        assert [row['relations'][key] for key in ('C/OFF', 'C/D', 'D/OFF')] == relations
        assert row['degree_uncertain'] == (q in ('Q03', 'Q06'))
    old, merged = read(PRIOR), read(OUT / 'ANSWER_REGISTRY_PRIVATE.json')
    assert merged[:45] == old and len(merged) == 55
    assert Counter(r['task_family'] for r in merged) == dict(pairs=36, rankings=8, singles=8, supplements=3)
    for record in merged:
        assert record['evidence_identity'] == digest(record['evidence'])
        assert all(digest(text) == identity for identity, text in record['replies'].items())
    for record, row in zip(merged[45:], intake['rows'], strict=True):
        assert record['raw_label'] == row['original_answer']
        assert record['intake_identity'] == digest(row)
        assert record['numeric_reward'] is record['exact_qm'] is None
        assert record['qualified_reward'] is False
    summary = read(OUT / 'SUMMARY.json')
    primary = summary['primary_ordinal_analysis']
    assert primary['joint_questions'] == ['Q01', 'Q08'] and primary['joint_owners'] == ['p11', 'p3']
    assert primary['joint_wins'] == 2 and primary['cases'] == 10
    assert summary['gate_checks'] == dict(coverage=True, joint_wins=False, owners=False, loss_check=True)
    assert summary['continuation_gate_passed'] is False
    assert summary['sensitivity_excluding_uncertain_degree']['cases'] == 8
    assert summary['sensitivity_excluding_uncertain_degree']['joint_wins'] == 2
    for pair in ('C/OFF', 'C/D', 'D/OFF'):
        counted = Counter(row['relations'][pair] for row in intake['rows'])
        assert {k: counted[k] for k in primary['comparisons'][pair]} == primary['comparisons'][pair]
    derived = sum(len(m['display']) * (len(m['display']) - 1) // 2 for m in packet['mapping'])
    assert derived == summary['new_derived_pair_relations'] == 26
    assert summary['human_submission_units'] == 10 and summary['reused_pair_relations'] == 2
    rejected = 0
    for order, labels in [('A>A=B', 'ABC'), ('A>B', 'ABC'), ('A>B>D', 'ABC'), ('A>>B=C', 'ABC'), ('A=B=C', 'AB')]:
        try:
            parse_order(order, labels)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError('invalid rank accepted')
    bad = copy.deepcopy(answer); bad['study'] = 'wrong'
    bad_coverage = copy.deepcopy(answer); del bad_coverage['answers']['Q10']
    for bad_answer in (bad, bad_coverage):
        try:
            validate_submission(bad_answer, packet)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError('invalid submission accepted')
    try:
        json.loads('{"Q01": 1, "Q01": 2}', object_pairs_hook=unique_keys)
    except ValueError:
        rejected += 1
    assert rejected == 8
    checked.update(question_bindings=10, expected_relations_checked=30, original_records_preserved=45,
        registry_records=55, rejection_cases=8, uncertain_degrees_retained=['Q03', 'Q06'],
        inferred_D_OFF_for_reused_pairs=0, scalar_rewards_created=0, gate='NOT_MET', status='PASS')
    print(json.dumps(checked, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

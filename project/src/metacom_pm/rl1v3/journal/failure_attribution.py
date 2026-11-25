"""Trace existing observations to evidence, without inferring hidden mechanisms.

Inputs and all semantic decisions are private. This module does not rescore a
response. It preserves the original labels and separates observable supply or
output properties from unidentifiable internal causes.
"""
from collections import defaultdict
from ..io import object_sha256

CATEGORIES = {'evidence_insufficient', 'representation_insufficient',
              'fact_understanding_unresolved', 'application_decision_failure',
              'expression_failure', 'evaluation_uncertain'}


def verify_case(case):
    if case['output_sha256'] != object_sha256(case['actual_output']):
        raise ValueError('original output identity mismatch')
    if case['original_review_sha256'] != object_sha256(case['original_review']):
        raise ValueError('original observation identity mismatch')
    if case['actual_output']['text'] != case['response']:
        raise ValueError('response changed')
    if len({a['id'] for a in case['atoms']}) != len(case['atoms']):
        raise ValueError('duplicate original atom')
    original = case['original_review']
    original_atoms = original.get('fact_review', original).get('fact_atoms', original.get('atoms', []))
    if original_atoms:
        old = {a.get('id', a.get('atom_id')): a.get('status', a.get('observed')) for a in original_atoms}
        if set(old) != {a['id'] for a in case['atoms']}:
            raise ValueError('original atom membership changed')
        if any(a['original_status'] != old[a['id']] for a in case['atoms']):
            raise ValueError('original atom status changed')
    for atom in case['atoms']:
        for quote in atom['source_quotes']:
            if not quote or quote not in case['delivered_text']:
                raise ValueError('source quote was not actually supplied')
        for quote in atom['output_quotes']:
            if not quote or quote not in case['response']:
                raise ValueError('output quotation changed')
        if atom['supply'] == 'full' and not atom['source_quotes']:
            raise ValueError('complete supply requires delivered evidence')
        for quote in atom.get('removed_representation_quotes', []):
            if not quote or quote in case['delivered_text']:
                raise ValueError('representation omission is not absent from delivered input')
            if quote not in case['raw_counterpart_text']:
                raise ValueError('representation omission lacks same-task RAW counterpart')
    for diagnostic in case['diagnostics']:
        if diagnostic['category'] not in CATEGORIES:
            raise ValueError('unrecognized diagnostic category')
        for quote in diagnostic.get('output_quotes', []):
            if not quote or quote not in case['response']:
                raise ValueError('diagnostic output quote changed')
        for quote in diagnostic.get('source_quotes', []):
            if not quote or quote not in case['delivered_text']:
                raise ValueError('diagnostic source quote not delivered')
    return True


def attribute(case):
    verify_case(case)
    events = []
    for atom in case['atoms']:
        base = dict(atom_id=atom['id'], original_status=atom['original_status'],
                    source_quotes=atom['source_quotes'], output_quotes=atom['output_quotes'])
        if atom['reference_uncertain'] or atom['interpretation_uncertain']:
            events.append(dict(base, category='evaluation_uncertain',
                kind='unresolved_original_reference_or_interpretation',
                epistemic_status='recorded_measurement_uncertainty',
                internal_cause_identified=False))
            continue
        if atom['supply'] in {'absent', 'partial'} and atom['original_status'] not in {'complete', 'supported'}:
            events.append(dict(base, category='evidence_insufficient',
                kind='necessary_evidence_not_fully_delivered',
                epistemic_status='direct_input_observation',
                internal_cause_identified=False))
            if atom.get('removed_representation_quotes'):
                events.append(dict(base, category='representation_insufficient',
                    kind='same_source_content_missing_from_transformed_view',
                    removed_quotes=atom['removed_representation_quotes'],
                    epistemic_status='direct_input_comparison',
                    internal_cause_identified=False))
        elif atom['supply'] == 'full' and atom['original_status'] in {'omitted', 'partial'}:
            events.append(dict(base, category='expression_failure',
                kind='fully_supplied_atom_not_fully_expressed',
                epistemic_status='observed_output_manifestation_only',
                internal_cause_identified=False,
                competing_mechanism_hypotheses=['fact interpretation', 'content selection',
                    'request interpretation', 'verbal expression'],
                mechanism_identifiability='The answer alone cannot distinguish these hypotheses.'))
    for diagnostic in case['diagnostics']:
        events.append(dict(diagnostic, internal_cause_identified=False))
    return dict(protocol='existing-evidence-attribution-sidecar-v1', cohort=case['cohort'],
        logical_id=case['logical_id'], task_id=case['task_id'], arm=case['arm'],
        request_id=case['request_id'], source_group=case['source_group'],
        output_sha256=case['output_sha256'], original_review_sha256=case['original_review_sha256'],
        original_atom_count=len(case['atoms']), events=events,
        scope_limitations=case['scope_limitations'], original_labels_changed=False,
        new_semantic_judge_calls=0, formal_reward=None,
        fact_understanding_failure='not_identifiable_from_existing_outputs',
        application_decision_mechanism='not_identifiable_from_existing_outputs',
        expression_mechanism='not_identifiable_from_existing_outputs')


def aggregate(rows):
    if len({r['logical_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate logical endpoint')
    cohorts = defaultdict(lambda: dict(rows=0, tasks=set(), requests=set(), groups=set(), atom_presentations=0))
    counts = defaultdict(lambda: dict(events=0, rows=set(), tasks=set(), requests=set(), groups=set(), atoms=set()))
    limitations = defaultdict(set)
    for row in rows:
        c=cohorts[row['cohort']];c['rows']+=1;c['tasks'].add(row['task_id']);c['requests'].add(row['request_id']);c['groups'].add(row['source_group']);c['atom_presentations']+=row['original_atom_count']
        for limitation in row['scope_limitations']:
            limitations[limitation].add(row['logical_id'])
        for event in row['events']:
            key=(row['cohort'],event['category'],event['kind']);s=counts[key]
            s['events']+=1;s['rows'].add(row['logical_id']);s['tasks'].add(row['task_id']);s['requests'].add(row['request_id']);s['groups'].add(row['source_group'])
            if event.get('atom_id'):s['atoms'].add((row['task_id'],event['atom_id']))
    def plain(c):return {k:len(v) if isinstance(v,set) else v for k,v in c.items()}
    return dict(protocol='failure-attribution-anonymous-counts-v1',
        cohorts={k:plain(v) for k,v in cohorts.items()},
        event_counts=[dict(cohort=k[0],category=k[1],kind=k[2],**plain(v)) for k,v in sorted(counts.items())],
        scope_limitation_rows={k:len(v) for k,v in limitations.items()},
        internal_causal_mechanisms_identified=0,
        category_counts_are_nonadditive=True,
        category_names_are_analysis_buckets_not_causal_diagnoses=True,
        evidence_insufficiency_is_not_a_generator_failure=True,
        output_omission_is_not_proof_of_failed_understanding=True,
        original_labels_changed=False, new_judge_calls=0,
        pending_real_human_items_unchanged=5,formal_reward=None,
        scope='Existing assistant development observations; no causal or formal-reward qualification.')

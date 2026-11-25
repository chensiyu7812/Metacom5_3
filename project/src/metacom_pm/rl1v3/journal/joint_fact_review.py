"""Validate privately authored joint-task fact observations, never infer a reward.

Semantic observations are supplied in private review files. Public code checks
identity, quote provenance and completeness only; exact quotations are not a
semantic correctness metric.
"""
from collections import Counter, defaultdict
from ..io import object_sha256

STATUSES = {'supported', 'partial', 'omitted', 'unsupported', 'unresolved'}
DELIVERIES = {'current', 'MS', 'current_and_MS', 'absent'}


def validate_review(review, actual, evaluation, supply):
    for key in ('logical_id', 'task_id', 'arm', 'request_id', 'output_sha256'):
        if review[key] != actual[key]:
            raise ValueError('actual identity mismatch: ' + key)
    if actual['output_sha256'] != object_sha256(actual['output']):
        raise ValueError('output hash mismatch')
    if review['evalspec_sha256'] != object_sha256(evaluation):
        raise ValueError('evaluation identity mismatch')
    if review['logical_id'] != supply['logical_id']:
        raise ValueError('supply identity mismatch')
    expected = {a['id'] for a in evaluation['personal_fact_references']}
    atoms = review['fact_atoms']
    if len(atoms) != len(expected) or {a['id'] for a in atoms} != expected:
        raise ValueError('every original atom must appear exactly once')
    output = actual['output']['text']
    for atom in atoms:
        if atom['status'] not in STATUSES or atom['delivery'] not in DELIVERIES:
            raise ValueError('invalid observation status')
        if atom['delivery'] != supply['delivery'] or atom['required'] is not True:
            raise ValueError('original supply or required status changed')
        if atom['status'] in {'supported', 'partial', 'unsupported'} and not atom['output_quotes']:
            raise ValueError('asserted answer requires exact output evidence')
        if any(not q or q not in output for q in atom['output_quotes']):
            raise ValueError('non-exact output quote')
        if atom['status'] == 'supported' and atom['delivery'] == 'absent':
            raise ValueError('unsupported delivered context cannot become completion')
        if atom['delivery'] == 'absent' and atom['source_quotes']:
            raise ValueError('absent evidence cannot be supplied')
        if atom['delivery'] != 'absent' and not atom['source_quotes']:
            raise ValueError('supplied atom needs evidence')
        for source in atom['source_quotes']:
            if source['quote'] != supply['source_binding']['exact_quote']:
                raise ValueError('source quote differs from frozen supply receipt')
            if source['location'] not in {'current', 'MS'}:
                raise ValueError('unknown delivery location')
            if source['location'] not in atom['delivery']:
                raise ValueError('source location not delivered')
    for finding in review['additional_claims']:
        if finding['status'] not in {'supported', 'unsupported', 'unresolved'}:
            raise ValueError('invalid additional claim status')
        if not finding['output_quotes'] or any(not q or q not in output for q in finding['output_quotes']):
            raise ValueError('additional claim needs exact output quote')
    if review['technical_status'] != actual['technical_status']:
        raise ValueError('technical status changed')
    if review['formal_semantic_status'] != 'uncertain' or review['formal_reward'] is not None:
        raise ValueError('development review cannot qualify formal reward')
    return True


def aggregate(reviews):
    """Export counts and opaque identifiers only, without private observations."""
    seen = set()
    by_arm = defaultdict(lambda: dict(outputs=0, required_atoms=0, statuses=Counter(),
        all_atoms_supported=0, safe_nonrecall=0, unsupported_additional_claims=0,
        unresolved_additional_claims=0))
    table = []
    for row in reviews:
        if row['logical_id'] in seen:
            raise ValueError('duplicate logical review')
        seen.add(row['logical_id'])
        counts = Counter(a['status'] for a in row['fact_atoms'])
        full = bool(row['fact_atoms']) and counts['supported'] == len(row['fact_atoms'])
        group = by_arm[row['arm']]
        group['outputs'] += 1
        group['required_atoms'] += len(row['fact_atoms'])
        group['statuses'].update(counts)
        group['all_atoms_supported'] += full
        group['safe_nonrecall'] += row['abstention']['safe_nonrecall']
        group['unsupported_additional_claims'] += sum(x['status'] == 'unsupported' for x in row['additional_claims'])
        group['unresolved_additional_claims'] += sum(x['status'] == 'unresolved' for x in row['additional_claims'])
        table.append(dict(logical_id=row['logical_id'],task_id=row['task_id'],arm=row['arm'],
            request_id=row['request_id'],output_sha256=row['output_sha256'],
            required_atoms=len(row['fact_atoms']),statuses=dict(counts),all_atoms_supported=full,
            supplied_atoms=sum(a['delivery']!='absent' for a in row['fact_atoms']),
            safe_nonrecall=row['abstention']['safe_nonrecall'],formal_reward=None))
    return dict(protocol='joint-fact-development-review-v1',outputs=len(reviews),
        by_arm=dict(by_arm),table=table,formal_semantic_status='uncertain',formal_reward=None,
        independent_human_qualification=False,semantic_reference='assistant-authored development observation')


def completion_intervals(reviews, disputes):
    """Keep original observations and expose separately identified uncertainty."""
    by_key = {(r['logical_id'], a['id']): a for r in reviews for a in r['fact_atoms']}
    uncertain = set()
    for dispute in disputes:
        key = (dispute['logical_id'], dispute['atom_id'])
        if key not in by_key or key in uncertain:
            raise ValueError('unknown or duplicate interpretation dispute')
        if dispute['original_status'] != by_key[key]['status'] or dispute['interpretation_status'] != 'unresolved':
            raise ValueError('dispute does not preserve the original observation')
        if dispute['completion_interval'] != [0, 1]:
            raise ValueError('uncertainty must remain an interval')
        uncertain.add(key)
    counts = defaultdict(lambda: dict(required_atoms=0, completed_atom_lower=0,
        completed_atom_upper=0, complete_task_lower=0, complete_task_upper=0,
        interpretation_disputes=0))
    for row in reviews:
        bounds = []
        group = counts[row['arm']]
        for atom in row['fact_atoms']:
            key = (row['logical_id'], atom['id'])
            value = ([0, 1] if key in uncertain or atom['status']=='unresolved'
                else [1, 1] if atom['status']=='supported' else [0, 0])
            bounds.append(value)
            group['required_atoms'] += 1
            group['completed_atom_lower'] += value[0]
            group['completed_atom_upper'] += value[1]
            group['interpretation_disputes'] += key in uncertain
        group['complete_task_lower'] += bool(bounds) and all(v[0] for v in bounds)
        group['complete_task_upper'] += bool(bounds) and all(v[1] for v in bounds)
    return dict(counts)

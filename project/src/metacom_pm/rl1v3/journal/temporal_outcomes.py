"""CPU diagnostics for frozen Memory representations and strict-date outputs.

Post-hoc representation selection is not a PM oracle or a qualified reward.
Semantic observations are private manual inputs; no matching rule invents them.
"""
from collections import Counter, defaultdict
import html

from ..io import object_sha256

REPRESENTATIONS = ('SPAN', 'RAW', 'TYPED_OR_SUM')
TEMPORAL_ARMS = ('RET-v1-filtered', 'Time-Lexical', 'Hybrid')


def representation_oracle(reviews, audits):
    """Choose one whole representation per task; never splice individual atoms."""
    grouped = defaultdict(dict)
    for row in reviews:
        if row['arm'] in grouped[row['task_id']]:
            raise ValueError('duplicate task representation')
        grouped[row['task_id']][row['arm']] = row
    tasks = []
    for task, arms in sorted(grouped.items()):
        if set(arms) != set(REPRESENTATIONS):
            raise ValueError('incomplete fixed representation set')
        eligible = {a['atom_id'] for a in audits[task]['atoms'] if a['required'] and a['status_end_history'] in {'supported', 'calendar_derived'}}
        scores = {}
        for arm, row in arms.items():
            atoms = {a['atom_id']: a for a in row['atoms'] if a['atom_id'] in eligible}
            if set(atoms) != eligible:
                raise ValueError('required supported atom set changed')
            scores[arm] = sum(a['observed']=='complete' for a in atoms.values())
        best = max(REPRESENTATIONS, key=lambda arm: scores[arm])
        tasks.append(dict(task_id=task,supported_atoms=len(eligible),complete_counts=scores,
            selected_whole_representation=best,selected_complete=scores[best],
            selected_task_complete=bool(eligible) and scores[best]==len(eligible)))
    fixed = {arm:dict(complete_atoms=sum(t['complete_counts'][arm] for t in tasks),
        complete_tasks=sum(bool(t['supported_atoms']) and t['complete_counts'][arm]==t['supported_atoms'] for t in tasks)) for arm in REPRESENTATIONS}
    return dict(protocol='journal-memory-representation-upper-bound-v1',tasks=len(tasks),
        supported_atoms=sum(t['supported_atoms'] for t in tasks),fixed=fixed,
        taskwise=dict(complete_atoms=sum(t['selected_complete'] for t in tasks),complete_tasks=sum(t['selected_task_complete'] for t in tasks)),
        rows=tasks,tie_order=REPRESENTATIONS,scope='retrospective whole-representation development diagnostic; not PM oracle, policy result, independent confirmation or qualified reward',
        atom_splicing=False,semantic_approved=0,reward=None)


def join_temporal_outputs(logical_requests, physical_rows):
    by_id={r['request_id']:r for r in physical_rows}
    if len(by_id)!=len(physical_rows):
        raise ValueError('physical calls repeated')
    if {r['request_id'] for r in logical_requests}!=set(by_id):
        raise ValueError('logical/physical denominator differs')
    seen=set();result=[]
    for request in logical_requests:
        physical=by_id[request['request_id']]
        if object_sha256(request['model_input'])!=request['payload_sha256'] or request['payload_sha256']!=physical['request']['payload_sha256']:
            raise ValueError('logical reuse requires identical actual payload')
        if request['logical_id'] in seen:
            raise ValueError('duplicate logical arm')
        seen.add(request['logical_id'])
        result.append(dict(logical_id=request['logical_id'],request_id=request['request_id'],request=request,
            output=physical['output'],output_sha256=physical['output_sha256'],
            physical_reuse_count=sum(r['request_id']==request['request_id'] for r in logical_requests)))
    return result


def validate_temporal_review(review, joined, audit, delivery):
    if review['logical_id']!=joined['logical_id'] or review['original_task_id']!=audit['task_id'] or review['request_id']!=joined['request_id']:
        raise ValueError('review identity mismatch')
    if review['original_task_id']!=joined['request']['original_task_id'] or review['arm']!=joined['request']['arm']:
        raise ValueError('review task/arm differs from actual request')
    if review['source_sessions_count']!=len(delivery['source_sessions']) or review['future_sources']!=0:
        raise ValueError('reported supply counts differ from frozen delivery')
    expected={a['atom_id'] for a in audit['atoms'] if a['required']}
    if len(review['atoms'])!=len(expected) or {a['atom_id'] for a in review['atoms']}!=expected:
        raise ValueError('every original required atom must remain visible')
    supplied=html.unescape('\n'.join(m['content'] for m in joined['request']['model_input']['messages'][:-1]))
    output=joined['output']['text']
    if review['output_sha256']!=joined['output_sha256']:
        raise ValueError('response binding changed')
    if any(d>delivery['cutoff'] for d in delivery['source_reports']):
        raise ValueError('future source in actual delivery')
    for atom in review['atoms']:
        if atom['reference_status']!=next(a['status_explicit_date'] for a in audit['atoms'] if a['atom_id']==atom['atom_id']):
            raise ValueError('original strict-date reference status changed')
        if atom['observed'] not in {'complete','partial','omitted','contradicted','uncertain'}:
            raise ValueError('invalid development observation')
        if atom['observed'] in {'complete','partial','contradicted'} and not atom['output_quotes']:
            raise ValueError('observed answer needs exact output quotation')
        if any(not q or q not in output for q in atom['output_quotes']):
            raise ValueError('nonexact response evidence')
        if any(not q['quote'] or q['quote'] not in supplied for q in atom['source_quotes']):
            raise ValueError('cited evidence not actually supplied')
    for finding in review['additional_findings']:
        if any(not q or q not in output for q in finding['output_quotes']):
            raise ValueError('additional observation response quote mismatch')
        if any(not q or q not in supplied for q in finding.get('source_quotes',[])):
            raise ValueError('additional observation source quote mismatch')
    if review['formal_semantic_status']!='uncertain' or review['reward'] is not None:
        raise ValueError('development review cannot yield formal reward')
    return True


def temporal_aggregate(reviews):
    groups=defaultdict(list)
    for row in reviews:groups[row['arm']].append(row)
    result={}
    for arm,rows in groups.items():
        atoms=[a for r in rows for a in r['atoms'] if a['reference_status'] in {'supported','calendar_derived'}]
        count=Counter(a['observed'] for a in atoms)
        result[arm]=dict(tasks=len(rows),supported_atom_presentations=len(atoms),completion_counts=dict(count),
            complete_on_supported_atoms_tasks=sum(bool([a for a in r['atoms'] if a['reference_status'] in {'supported','calendar_derived'}]) and all(a['observed']=='complete' for a in r['atoms'] if a['reference_status'] in {'supported','calendar_derived'}) for r in rows),
            unresolved_reference_presentations=sum(a['reference_status'] not in {'supported','calendar_derived'} for r in rows for a in r['atoms']),
            frozen_group_covered=sum(a['frozen_group_covered'] for a in atoms),
            complete_from_frozen_group=sum(a['observed']=='complete' and a['frozen_group_covered'] for a in atoms),
            complete_from_other_actual_source=sum(a['observed']=='complete' and not a['frozen_group_covered'] and bool(a['source_quotes']) for a in atoms),
            source_sessions_delivered=sum(r['source_sessions_count'] for r in rows),
            future_sources=sum(r['future_sources'] for r in rows),
            abstention_observations=dict(Counter(r['abstention_status'] for r in rows)),
            additional_finding_counts=dict(Counter(f['kind'] for r in rows for f in r.get('additional_findings',[]))),
            input_tokens=sum(r['technical']['input_tokens'] for r in rows),
            output_tokens=sum(r['technical']['output_tokens'] for r in rows),
            logical_attributed_seconds=sum(r['technical']['seconds'] for r in rows))
    physical={r['request_id']:r for r in reviews}
    return dict(protocol='journal-temporal-outcomes-development-v1',by_arm=result,
        logical_outputs=len(reviews),physical_outputs=len(physical),exact_payload_reuses=len(reviews)-len(physical),
        physical_seconds=sum(r['technical']['seconds'] for r in physical.values()),
        physical_input_tokens=sum(r['technical']['input_tokens'] for r in physical.values()),
        physical_output_tokens=sum(r['technical']['output_tokens'] for r in physical.values()),
        attribution_limit='filtered legacy Top4 is not refilled; the new rankings supply more legal sessions. Output effects cannot all be attributed to ordering.',
        semantic_approved=0,rewards=0,independent_human_review=False)

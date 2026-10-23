"""Private source admission and real GET witnesses for multi-resource inputs.

Evidence integrity is mechanical; semantic admission is the separately recorded
reviewer's judgment. Neither this receipt nor the review enters model messages.
"""
from dataclasses import asdict

from .env import ResourceEnv
from .schema import PLANS, digest
from .source_quarantine import require_pre_generation_source_reviews


def acquisition_witness(spec, counts, renderer):
    if (len(counts) != 4 or any(type(n) is not int or n < 0 for n in counts)
            or sum(counts) > 4
            or any(n > len(rows) for n, rows in zip(counts, spec.inventory))):
        raise ValueError('invalid resource counts')
    counts = tuple(counts)
    env = ResourceEnv(spec, renderer)
    if not env.observe().initial_plan_mask[PLANS.index(counts)]:
        raise ValueError('requested resource plan is not sequentially reachable')
    # Tokenizer costs need not be monotone. Find a legal path rather than assume
    # canonical rendering order is a legal acquisition order.
    paths = {(0, 0, 0, 0): ()}
    for plan in PLANS[1:]:
        if any(a > b for a, b in zip(plan, counts)) or not renderer.fits(spec, plan):
            continue
        for i, n in enumerate(plan):
            previous = tuple(v - (j == i) for j, v in enumerate(plan))
            if n and previous in paths:
                paths[plan] = paths[previous] + (i + 1,)
                break
    for action in paths[counts] + (0,):
        env.step(action, expected_state_hash=env.state_hash)
    assert env.observe().counts == counts and env.phase == 'pending_generation'
    return env.generation_request(), env.snapshot()


def _check_refs(review, resource, evidence):
    refs = review.get('evidence_refs', [])
    if not refs:
        raise ValueError('source review lacks concrete evidence references')
    sessions = {s['id']: s for s in evidence['legal_past_sessions']}
    for ref in refs:
        if resource['head'] == 'RS':
            if (ref.get('kind') != 'strategy' or ref.get('candidate_id') != resource['candidate_id']
                    or tuple(ref.get('source_ids', ())) != tuple(resource['source_ids'])
                    or ref.get('content_identity') != digest(resource['content'])):
                raise ValueError('strategy provenance reference changed')
            continue
        session = sessions.get(ref.get('session_id'))
        if session is None or ref.get('session_identity') != digest(session):
            raise ValueError('reference is not bound to a complete legal past session')
        if ref.get('kind') == 'complete_session' and resource['head'] == 'MS':
            continue
        if ref.get('kind') != 'turn' or resource['head'] not in ('MP', 'ME'):
            raise ValueError('invalid memory evidence reference kind')
        turns = {t['id']: t for t in session['turns']}
        turn = turns.get(ref.get('turn_id'))
        if (turn is None or not ref.get('quote') or ref['quote'] not in turn['text']
                or ref.get('role') != turn['role']):
            raise ValueError('reference quote/role does not match legal evidence')


def validate_resource_plans(contract, *, specs, evidence, reviews, renderer):
    if len(specs) != len(evidence) or renderer.identity != contract['renderer_identity']:
        raise ValueError('roster or renderer identity changed')
    review_map = {}
    for review in reviews:
        key = (review['prefix_identity'], review['candidate_id'])
        if key in review_map:
            raise ValueError('duplicate source review')
        review_map[key] = review
    seen, receipts = set(), []
    for condition in contract['conditions']:
        index, label = condition['index'], condition['condition']
        if type(index) is not int or not 1 <= index <= len(specs):
            raise ValueError('condition index outside frozen roster')
        key = (index, label)
        if key in seen or label not in ('OFF', 'R', 'L'):
            raise ValueError('duplicate or unknown condition')
        seen.add(key)
        spec, row = specs[index - 1], evidence[index - 1]
        e = row['evidence']
        current = [dict(id=f'C:T{i:03d}', role=t.role, text=t.content)
                   for i, t in enumerate(spec.prefix.turns)]
        if (condition['prefix_identity'] != spec.prefix.identity
                or condition['owner'] != spec.prefix.owner_id
                or condition['split'] != spec.prefix.split or spec.prefix.split not in ('train', 'dev')
                or row['prefix_identity'] != spec.prefix.identity
                or row['evidence_identity'] != digest(e)
                or e['current_prefix'] != current or e['current_date'] != spec.prefix.timestamp):
            raise ValueError('prefix/evidence identity changed')
        counts = tuple(condition['counts'])
        if (label == 'OFF') != (counts == (0, 0, 0, 0)):
            raise ValueError('OFF must be empty; R/L must contain resources')
        request, snapshot = acquisition_witness(spec, counts, renderer)
        actual = request['messages']
        if actual != condition['messages'] or digest(actual) != condition['messages_identity']:
            raise ValueError('rendered input changed or contains private annotations')
        selected = [asdict(r) for rows, n in zip(spec.inventory, counts) for r in rows[:n]]
        bound = {cid: review for (pid, cid), review in review_map.items() if pid == spec.prefix.identity}
        require_pre_generation_source_reviews(selected, prefix_identity=spec.prefix.identity,
            evidence_identity=row['evidence_identity'], reviews=bound)
        for resource in selected:
            _check_refs(bound[resource['candidate_id']], resource, e)
        receipts.append(dict(index=index, condition=label, counts=counts,
            messages_identity=digest(actual), request_identity=request['request_id'],
            actions=snapshot['actions'], acquisition_receipts=snapshot['receipts'],
            resource_identities=[digest(r) for r in selected],
            review_identities=[digest(bound[r['candidate_id']]) for r in selected]))
    if seen != {(i, c) for i in range(1, len(specs) + 1) for c in ('OFF', 'R', 'L')}:
        raise ValueError('incomplete condition roster')
    return dict(status='ALL_SELECTED_SOURCES_AND_GET_PATHS_ADMITTED', conditions=receipts,
        contract_identity=digest(contract), review_identity=digest(reviews),
        semantic_authority='Bound AI-assisted source review; not independent human truth')

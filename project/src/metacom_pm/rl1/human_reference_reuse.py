"""Exact-input reuse of existing human development references, not new labels."""
from collections import Counter
from .schema import digest


def pair_reference(*, source, record_id, evidence_id, left, right, direction, raw_label,
                   observation_origin, purpose):
    if direction not in ('left','right','tie','uncertain') or not all((source,record_id,evidence_id,left,right,observation_origin)):
        raise ValueError('complete historical pair binding required')
    winner = left if direction=='left' else right if direction=='right' else None
    endpoints=sorted((left,right))
    return dict(kind='pair_preference',source=source,record_id=record_id,evidence_identity=evidence_id,
        reply_identities=endpoints,pair_identity=digest(dict(evidence=evidence_id,replies=endpoints)),
        direction='tie' if direction=='tie' else 'uncertain' if direction=='uncertain' else 'preferred_reply',
        preferred_reply_identity=winner,raw_label=raw_label,observation_origin=observation_origin,
        purpose=purpose,independent_frozen_validation=False,qualified_reward=False)


def reuse_map(materials, pairs, singles, supplements=()):
    """No fuzzy joins: matching prefix/topic or one reply is not a pair label."""
    if len({m['key'] for m in materials})!=len(materials):raise ValueError('duplicate material key')
    rows=[]
    for m in materials:
        reply,evidence=digest(m['reply']),digest(m['evidence'])
        exact=lambda r:r['evidence_identity']==evidence and r['reply_identity']==reply
        rows.append(dict(key=m['key'],purpose=m['purpose'],reply_identity=reply,evidence_identity=evidence,
            single_references=[s for s in singles if exact(s)],
            pair_endpoint_references=[dict(source=p['source'],record_id=p['record_id'],
                pair_identity=p['pair_identity']) for p in pairs if p['evidence_identity']==evidence and reply in p['reply_identities']],
            prior_clarifications=[s for s in supplements if exact(s)],
            q=None,m=None,qualified_reward=False))
    proposed_pairs=[]
    groups={}
    for m in materials:
        if m['key'].startswith('newdev_'):
            group,side=m['key'].rsplit('_',1);groups.setdefault(group,{})[side]=m
    for name,g in sorted(groups.items()):
        if set(g)!={'0','1'} or digest(g['0']['evidence'])!=digest(g['1']['evidence']):
            raise ValueError('newdev pair/source mismatch')
        key=digest(dict(evidence=digest(g['0']['evidence']),replies=sorted(digest(g[s]['reply']) for s in ('0','1'))))
        matches=[p for p in pairs if p['pair_identity']==key]
        proposed_pairs.append(dict(pair=name,exact_pair_references=matches,
            disposition='reuse_existing_development_reference' if matches else 'no_previous_pair_judgment_found'))
    summary=dict(materials=len(materials),old_preference_records=len(pairs),
        old_distinct_pair_inputs=len({p['pair_identity'] for p in pairs}),old_single_reply_records=len(singles),
        old_singleton_q=sum(s.get('q_status')=='single' for s in singles),
        old_interval_q=sum(s.get('q_status')=='range' for s in singles),
        current_reply_slots_with_old_single_judgment=sum(bool(r['single_references']) for r in rows),
        current_reply_slots_with_old_pair_endpoint=sum(bool(r['pair_endpoint_references']) for r in rows),
        newdev_pairs=len(proposed_pairs),newdev_pairs_with_exact_old_preference=sum(bool(p['exact_pair_references']) for p in proposed_pairs),
        newdev_reply_slots_with_old_single_judgment=sum(r['purpose']=='new_development_not_independent_validation' and bool(r['single_references']) for r in rows),
        prior_clarifications_matched=sum(len(r['prior_clarifications']) for r in rows),
        preferences_by_origin=dict(Counter(p['observation_origin'] for p in pairs)),
        new_human_labels=0,qualified_reward=False,independent_validation_created=False,
        interpretation='Historical developmental references retained; holistic ties do not imply exact equal U; ranges never averaged.')
    return dict(summary=summary,reply_rows=rows,pair_rows=proposed_pairs)

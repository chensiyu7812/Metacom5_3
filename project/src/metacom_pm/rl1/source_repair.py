"""Versioned, private source exclusions applied AFTER latest-slot selection.

This is a conservative development overlay, not a semantic verifier. Raw data
and historical evidence remain intact. No decision is exposed to the actor.
"""
from .data import as_of_memory
from .schema import digest
from metacom_pm.paper1.contracts import Head


def validate_overlay(overlay, *, units, users):
    by_id = {u.memory_id: u.model_dump(mode='json') for u in units}
    for row in overlay['unit_reviews']:
        unit = by_id[row['unit_id']]
        if (digest(unit) != row['unit_identity'] or unit['owner_id'] != row['owner']
                or unit['source_session_rank'] != row['source_rank']):
            raise ValueError('source review binding changed')
    if len({r['unit_id'] for r in overlay['unit_reviews']}) != len(overlay['unit_reviews']):
        raise ValueError('duplicate unit review')
    for rule in overlay['temporal_blocks'] + overlay['session_blocks']:
        user = users[rule['owner']]
        session = user.session_by_id(rule['session_id'])
        if session.chronological_rank != rule['source_rank'] or session.timestamp != rule['source_time']:
            raise ValueError('source transition time changed')
        turns = {t.idx: t for t in session.turns}
        if not rule['evidence'] or not rule['rationale']:
            raise ValueError('source decision lacks evidence')
        for ev in rule['evidence']:
            t = turns[ev['turn_index']]
            if t.role != 'seeker' or t.content != ev['text']:
                raise ValueError('source transition evidence changed')
    return True


def exclusion(unit, *, prefix, overlay):
    """Only evidence strictly preceding this prefix may affect materialization."""
    if unit['owner_id'] != prefix.owner_id or unit['source_session_rank'] >= prefix.cutoff_rank:
        raise ValueError('source must be same-owner strict past')
    for row in overlay['unit_reviews']:
        if row['unit_id'] == unit['memory_id']:
            if digest(unit) != row['unit_identity']:
                raise ValueError('reviewed unit changed')
            if row['citation_status'] != 'citation_sufficient':
                return dict(reason='new_citation_not_sufficient', decision_identity=digest(row))
    for rule in overlay['session_blocks']:
        if (rule['owner'] == prefix.owner_id and rule['source_rank'] < prefix.cutoff_rank
                and rule['session_id'] == unit['source_session_id']):
            return dict(reason='ambiguous_scenario_source', decision_identity=digest(rule))
    for rule in overlay['temporal_blocks']:
        if (rule['owner'] == prefix.owner_id and rule['source_rank'] < prefix.cutoff_rank
                and rule['slot'] == unit.get('profile_slot_key')):
            # Reopening requires a separately source-reviewed superseding unit,
            # never merely a new extractor timestamp or unsupported reassertion.
            if unit['memory_id'] not in rule.get('reviewed_superseding_unit_ids', []):
                return dict(reason='current_relationship_unresolved', decision_identity=digest(rule))
    return None


def repaired_as_of_memory(prefix, *, user, units, token_counter, overlay):
    candidates = as_of_memory(prefix, user=user, units=units, token_counter=token_counter)
    unit_map = {u.memory_id: u.model_dump(mode='json') for u in units}
    result, removed = {}, []
    for head, rows in candidates.items():
        kept = []
        for c in rows:
            decision = None if head == Head.MS else exclusion(
                unit_map[c.lineage.source_record_ids[0]], prefix=prefix, overlay=overlay)
            if decision:
                removed.append(dict(candidate_id=c.candidate_id, head=head.value, **decision))
            else:
                kept.append(c)
        result[head] = tuple(kept)
    return result, dict(prefix_identity=prefix.identity, overlay_identity=digest(overlay),
        before={h.value: len(v) for h, v in candidates.items()},
        after={h.value: len(v) for h, v in result.items()}, removed=removed,
        semantic_approval=False, old_slot_fallback=False)

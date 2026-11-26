"""Read-only, evaluation-side source coordinates; no model or retrieval imports.

Supply is not task success. A matching question/quotation is not automatically
a user fact. Current-context semantic observations are separately bound inputs.
"""
import hashlib
import json

PROTOCOL = 'pmrl1-j-ge2-source-coordinate-audit-v1'


def object_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def reference_location(ref, records):
    """Verify the one named source turn, never search other turns for a quote."""
    if ref.get('record_id') is None:
        return dict(status='current_only_no_historical_coordinate', valid=None)
    record = records.get(ref['record_id'])
    if record is None:
        return dict(status='record_absent', valid=False)
    for key, rkey in (('owner_id', 'owner_id'), ('session_id', 'parent_session_id')):
        if ref.get(key) != record.get(rkey):
            return dict(status=key+'_mismatch', valid=False)
    idx = ref.get('turn_index')
    if type(idx) is not int:
        return dict(status='turn_index_missing_or_invalid', valid=False)
    found = [s for s in record['source_refs'] if s['turn_index'] == idx]
    if len(found) != 1:
        return dict(status='named_turn_not_unique', valid=False)
    original = found[0]
    if ref.get('speaker') != original['speaker']:
        return dict(status='speaker_mismatch', valid=False)
    start, end = ref.get('start_char'), ref.get('end_char')
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(original['exact_quote']):
        return dict(status='unicode_offset_invalid', valid=False)
    if original.get('start_char') != 0 or original.get('end_char') != len(original['exact_quote']):
        return dict(status='pool_turn_not_full_original', valid=False)
    if original['exact_quote'][start:end] != ref.get('exact_quote'):
        return dict(status='named_turn_quote_mismatch', valid=False)
    if text_sha(original['exact_quote']) != original.get('raw_turn_sha256'):
        return dict(status='original_turn_hash_mismatch', valid=False)
    return dict(status='exact_original_turn_verified', valid=True,
        original_turn_sha256=original['raw_turn_sha256'], reference_sha256=object_sha(ref))


def validate_intervals(intervals, records):
    """Accept the executed intervals as-is. No re-ranking or interval repair."""
    for rid, spans in intervals.items():
        if rid not in records:
            raise ValueError('delivered record outside legal pool')
        known = {s['turn_index'] for s in records[rid]['source_refs']}
        for pair in spans:
            if (not isinstance(pair, list) or len(pair) != 2 or
                any(type(x) is not int for x in pair) or pair[0] > pair[1] or
                pair[0] not in known or pair[1] not in known):
                raise ValueError('delivered original turn interval invalid')


def history_delivered(ref, records, intervals):
    location = reference_location(ref, records)
    if location['valid'] is not True:
        return False
    return any(lo <= ref['turn_index'] <= hi for lo, hi in intervals.get(ref['record_id'], []))


def occurrences(ref, task):
    result = []
    quote = ref['exact_quote']
    if not quote:
        raise ValueError('empty reference quote')
    for index, turn in enumerate(task['turns']):
        at = 0
        while True:
            start = turn['text'].find(quote, at)
            if start < 0:
                break
            result.append(dict(visible_turn_index=index, speaker=turn['role'],
                start_char=start, end_char=start+len(quote), exact_quote=quote,
                turn_text_sha256=text_sha(turn['text'])))
            at = start + len(quote)
    return result


def current_semantic_delivery(ref, task, review):
    """Tri-state source-for-this-task observation, not a generated-answer score."""
    hits = occurrences(ref, task) if ref.get('current_visible') else []
    if not hits:
        return False
    if review is None:
        return None
    if review.get('task_sha256') != object_sha(task) or not review.get('reviewer_identity'):
        raise ValueError('current observation identity')
    states=[]
    for hit in hits:
        if hit['speaker'] != ref.get('speaker'):
            states.append(False); continue
        matches=[o for o in review['reference_occurrences']
                 if o['reference_sha256']==object_sha(ref) and o['occurrence']==hit]
        if len(matches) != 1:
            states.append(None); continue
        observed=matches[0]
        if not observed.get('rationale') or observed['classification'] not in (
            'user_self_report', 'explicit_recollection_quote', 'quoted_note',
            'question', 'hypothesis', 'other_or_uncertain'):
            raise ValueError('current observation schema')
        status=observed['admissible_for_original_task']
        if status not in ('yes_bounded', 'no', 'uncertain'):
            raise ValueError('current observation judgement')
        states.append(True if status=='yes_bounded' else False if status=='no' else None)
    return True if True in states else None if None in states else False


def _and(values):
    return False if False in values else None if None in values else True


def _or(values):
    return True if True in values else None if None in values else False


def strict_supply(atoms, records, intervals, task, current_review=None):
    """Reusable for CPU variants or actual read_intervals / Direct recipes.

    Caller must bind receipt, legal pool and real payload identities. This pure
    function cannot prove that a claimed receipt was rendered into model input.
    """
    records={r['record_id']: r for r in records} if isinstance(records,list) else records
    validate_intervals(intervals, records)
    rows=[]
    for atom in atoms:
        groups=atom.get('sufficient_groups', [])
        history_groups=[]; current_groups=[]; combined_groups=[]
        for group in groups:
            hs=[history_delivered(ref, records, intervals) for ref in group]
            cs=[current_semantic_delivery(ref, task, current_review) for ref in group]
            history_groups.append(_and(hs)); current_groups.append(_and(cs))
            combined_groups.append(_and([_or([h,c]) for h,c in zip(hs,cs)]))
        rows.append(dict(atom_id=atom['id'],requirement_role=atom['requirement_role'],
            historical_coordinate_covered=_or(history_groups) if groups else None,
            current_task_scope_covered=_or(current_groups) if groups else None,
            covered=_or(combined_groups) if groups else None))
    required=[r for r in rows if r['requirement_role']=='explicit_answer']
    return dict(atoms=rows,required_slots=len(required),
        covered_slots=sum(r['covered'] is True for r in required),
        unknown_slots=sum(r['covered'] is None for r in required),
        uncovered_slots=sum(r['covered'] is False for r in required),
        all_atom_covered=sum(r['covered'] is True for r in rows),
        all_atom_unknown=sum(r['covered'] is None for r in rows),
        historical_required_covered=sum(r['historical_coordinate_covered'] is True for r in required),
        current_task_scope_required_covered=sum(r['current_task_scope_covered'] is True for r in required),
        complete_all_required=bool(required) and all(r['covered'] is True for r in required),
        source_only=True,task_success=None,formal_reward=None)


def legacy_supply(atoms, delivered, visible_text):
    """Frozen old predicate reproduced for comparison; never change old files."""
    def seen(ref):
        if ref.get('current_visible') and ref['exact_quote'] in visible_text:
            return True
        return any(d.get('record_id') == ref.get('record_id') and ref['exact_quote'] in d.get('text','') for d in delivered)
    rows=[]
    for a in atoms:
        groups=a.get('sufficient_groups',[])
        rows.append(dict(atom_id=a['id'],requirement_role=a['requirement_role'],
            covered=any(all(seen(r) for r in g) for g in groups) if groups else None))
    required=[r for r in rows if r['requirement_role']=='explicit_answer']
    return dict(atoms=rows,required_slots=len(required),covered_slots=sum(r['covered'] is True for r in required),
        unknown_slots=sum(r['covered'] is None for r in required),all_atom_covered=sum(r['covered'] is True for r in rows))


def direct_intervals(recipe):
    """Exact source coordinates only; do not infer missing ranges or expand them."""
    result={}
    for unit in recipe['source_units']:
        result.setdefault(unit['record_id'], []).append([unit['start_turn'],unit['end_turn']])
    return result

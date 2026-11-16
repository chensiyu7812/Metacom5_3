"""Context-task reference adapter over the existing paired diagnostic engine.

No provider, credentials, model loading or contract activation on import.
The old relation-reference study and training caches remain immutable.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from . import relation_reference as rr
from .schema import digest
from .evidence import evidence_turns

VERSION = 'pmrl1-context-task-reference-v1-20261021'
INTERFACE = 'context-task-data-v1-20261021'
MARKER = '\n\nCONTEXT_TASK_REFERENCE_V1_DATA\n'
CARD_FIELDS = {'interface_version', 'evidence_identity', 'current_date', 'source_facts',
               'request_elements', 'role_application', 'acceptable_options',
               'unresolved_importance', 'provenance', 'independent_gold'}
USE = ('This is a shared context-level task reference, not a rating of this reply. '
       'It was prepared by an analyst from the current dialogue and stated role rules, '
       'after exposure to development results; it is not independent human gold. '
       'The same context reference is used for every candidate reply in this context. '
       'Check it against the complete original sources. Explain a source-grounded '
       'correction rather than silently redefining the user request. Distinguish '
       'what this reply actually contributes from what it omits; a shared omission '
       'does not prescribe equal scores. Importance and severity not established '
       'by the sources remain unresolved, not automatically a defect or zero risk. '
       'Do not infer a preferred reply, q/m, or resource plan. Use the unchanged '
       'final schema and original source IDs only.')
RUN_ROOTS = ('live_runs', 'paired_diagnostic_runs', 'action_stage_runs', 'reward_noise_runs',
             'anchor_calibration_runs', 'four_head_diagnostic_runs', 'relation_reference_runs',
             'task_reference_runs')


def validate_card(item, card):
    if set(card) != CARD_FIELDS or card['interface_version'] != INTERFACE:
        raise ValueError('task card allowlist/version mismatch')
    if (card['evidence_identity'] != digest(item['evidence']) or card['independent_gold'] is not False
            or card['current_date'] != item['evidence']['current_date']):
        raise ValueError('task card context/gold binding mismatch')
    turns = evidence_turns(item['evidence'])
    if not card['source_facts']:
        raise ValueError('task card requires source anchors')
    for fact in card['source_facts']:
        if set(fact) != {'source_id', 'speaker', 'quote'} or not fact['source_id'].startswith('C:'):
            raise ValueError('task source allowlist')
        source = turns.get(fact['source_id'])
        if not source or fact['speaker'] != source['role'] or fact['quote'] != source['text']:
            raise ValueError('task source exact full-turn binding failed')
    for field in ('request_elements', 'acceptable_options', 'unresolved_importance'):
        if not isinstance(card[field], list) or not card[field] or any(not isinstance(v, str) or not v for v in card[field]):
            raise ValueError('task card requires explicit request/options/uncertainty')
    if not isinstance(card['role_application'], str) or not card['role_application']:
        raise ValueError('role application missing')
    if card['provenance'] != 'analyst_prepared_after_development_exposure_not_independent_gold':
        raise ValueError('task semantics cannot self-certify as gold')


def make_payload(item, ref, card, arm, prompt, paired):
    if arm not in ('A', 'B'):
        raise ValueError('unknown task diagnostic arm')
    validate_card(item, card)
    # Both arms receive exactly the same existing reply-level relation information.
    data = rr.make_payload(item, ref, 'B', prompt, paired)
    if arm == 'B':
        data['messages'][0]['content'] += MARKER + json.dumps(
            {'task_reference_use_contract': USE, 'context_task_reference': card}, ensure_ascii=False)
    return data


def validate_payload(item, ref, card, arm, prompt, payload, paired):
    if payload != make_payload(item, ref, card, arm, prompt, paired):
        raise ValueError('outbound payload differs from frozen full source/reference/schema')
    return paired.input_guard(payload['messages'])


def schedule(items, order, repeats):
    rows = []
    for key, repetition in [(k, 1) for k in order]+[(k, 2) for k in repeats]:
        arms = ('A', 'B') if order.index(key) % 2 == 0 else ('B', 'A')
        if repetition == 2:
            arms = arms[::-1]
        for arm in arms:
            logical = dict(study=VERSION, item=key, arm=arm, repetition=repetition)
            rows.append(dict(position=len(rows)+1, slot_id=digest(logical), logical_slot=logical,
                item_key=key+'__'+arm, material_id=key, arm=arm, repetition=repetition,
                component='joint', reply_identity=digest(items[key]['reply']),
                evidence_identity=digest(items[key]['evidence'])))
    return rows


def history_snapshot(base, run_dir):
    base, run_dir = Path(base), Path(run_dir)
    return {str(p): rr.sha(p) for name in RUN_ROOTS for p in (base/name).rglob('*.started.json')
            if 'management' not in p.parts and not p.is_relative_to(run_dir)}


def historical_guard(protocol, base):
    actual = history_snapshot(base, protocol['run_dir'])
    if actual != protocol['historical_started_hashes']:
        raise ValueError('historical/cross-version started set changed; reconcile without redispatch')
    for path, sha in protocol['old_stop_hashes'].items():
        if rr.sha(path) != sha:
            raise ValueError('historical STOP changed')
    count = 66+len(actual)
    if count != protocol['baseline_cumulative']:
        raise ValueError('cumulative baseline mismatch')
    return count


def require_approval(protocol, approval):
    if (approval.get('status') != 'APPROVED' or approval.get('protocol_identity') != protocol['identity']
            or any(approval.get(k) != v for k, v in protocol['approval_required'].items())):
        raise ValueError('explicit new study/outbound/budget approval missing')
    record = approval.get('researcher_authorization_record')
    if not record or not Path(record).is_file() or rr.sha(record) != approval.get('researcher_record_sha256'):
        raise ValueError('actual researcher authorization record binding missing')
    amendment_path = Path(protocol['activation_file'])
    if not amendment_path.is_file():
        raise ValueError('approved capacity/execution amendment not activated')
    a = rr.read(amendment_path)
    if (a.get('applied') is not True or a.get('protocol_identity') != protocol['identity']
            or a.get('capacity') != protocol['limits']['proposed_capacity']
            or a.get('approval_identity') != digest(approval)):
        raise ValueError('active amendment mismatch')


def summarize(protocol, root, baseline, paired):
    starts, results = paired.replay(root, protocol)
    stop_path = Path(root)/'STOP.json'
    stop = rr.read(stop_path) if stop_path.exists() else None
    slots = []
    for slot in protocol['schedule']:
        result = results.get(slot['slot_id'])
        state = ('model_unknown' if result and result['technical_valid'] and result['evaluation'].get('model_unknown')
                 else 'completed' if result and result['technical_valid'] else 'failed' if result
                 else 'started_unresolved' if slot['slot_id'] in starts else 'not_dispatched')
        slots.append(dict(**slot, state=state, result=result,
            not_dispatched_reason=(stop['reason'] if stop else 'not authorized/not dispatched') if state=='not_dispatched' else None))
    comparisons = []
    for pair in protocol['resource_pairs']:
        for arm in ('A', 'B'):
            off_slots = [s for s in slots if s['material_id']==pair['off'] and s['arm']==arm]
            on_slots = [s for s in slots if s['material_id']==pair['on'] and s['arm']==arm]
            for off in off_slots:
                same = next((s for s in on_slots if s['repetition']==off['repetition']), None)
                on = same or next(s for s in on_slots if s['repetition']==1)
                valid = off['state']==on['state']=='completed'
                delta = on['result']['evaluation']['U']-off['result']['evaluation']['U'] if valid else None
                comparisons.append(dict(pair_id=pair['id'], arm=arm, off_draw=off['repetition'],
                    on_draw=on['repetition'], off_slot=off['slot_id'], on_slot=on['slot_id'],
                    shared_on=same is None, comparable=valid, delta_U=delta,
                    net_reward=delta-pair['resource_tokens']/40960 if valid else None,
                    direction_correctness=None, independent_new_cases=0,
                    missing_reason=None if valid else 'missing/failed/model unknown endpoint'))
    usage = [r['usage'] for r in results.values() if isinstance(r.get('usage'), dict)]
    return dict(study=VERSION, planned=len(slots), started=len(starts), cumulative=baseline+len(starts),
        slots=slots, resource_comparisons=comparisons, stop=stop, statistics=protocol['statistics'],
        technical_delivered=sum(r['technical_valid'] for r in results.values()),
        model_unknown=sum(r['evaluation'].get('model_unknown') is True for r in results.values()),
        numerical_scored=sum(s['state']=='completed' for s in slots),
        prompt_tokens=sum(u.get('prompt_tokens') or 0 for u in usage),
        output_tokens_including_thinking=sum(u.get('completion_tokens') or 0 for u in usage),
        elapsed_seconds=sum(r['elapsed_seconds'] for r in results.values()),
        accounted_usd=str(sum((Decimal(r['financial']['accounted_upper_usd'] or '0') for r in results.values()), Decimal(0))),
        result_liability_usd=str(sum((Decimal(r['financial']['unsettled_reservation_usd']) for r in results.values()),Decimal(0))
                                +Decimal('.786432')*(len(starts)-len(results))),
        authoritative_liability_source='shared ledger, including reserved-before-start orphan',
        semantic_status='requires_bound_offline_review_not_inferred_from_numerical_agreement',
        independent_human_reviews=0, reward_eligible=False, natural_updates=0)


def runtime(protocol, payloads, items, refs, cards, prompt, paired, authorize):
    def payload(item, component, first=None):
        if component != 'joint' or first is not None:
            raise ValueError('one joint call per diagnostic slot')
        key = item['material_id']
        card = cards[digest(item['evidence'])]
        data = payloads[key+'__'+item['arm']]
        validate_payload(item, refs[key], card, item['arm'], prompt, data, paired)
        return deepcopy(data['messages']), deepcopy(data['schema'])
    return dict(max_calls=protocol['limits']['max_calls'], cap=protocol['limits']['cumulative_cap'],
        study=VERSION, version=VERSION, approve=authorize, payload=payload, streaks=rr.check_stop,
        summarize=lambda p, root, b:summarize(p, root, b, paired), review=None,
        semantic_revisions_applied=protocol['proposed_semantic_revision_count'], joint_prompt_unchanged=False)

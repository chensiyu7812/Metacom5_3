"""CPU-only closeout checks for fixed representation and update experiments.

Mechanical source matching never establishes semantic correctness or a reward.
Private inputs hold all observed dialogue, reference answers and review claims.
"""
from collections import Counter, defaultdict
import json
import re

from ..io import object_sha256, parse_json, sha256_text
from .keycap_memory_review import INCOMPLETE

FIELDS = {'kind', 'source_session', 'turn', 'speaker', 'exact_quote',
          'reported_date', 'slot_or_event', 'stage', 'relation'}
STAGES = {'unknown', 'suggested', 'intended', 'attempted', 'completed', 'outcome_reported', 'rejected'}
RELATIONS = {'append', 'uncertain_same_event', 'explicit_correction'}


def parse_update(text):
    """Strict full-response JSON first; code fences are a named sensitivity."""
    error = None
    try:
        value = parse_json(text)
    except (ValueError, TypeError) as exc:
        error = type(exc).__name__
        match = re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*', text, flags=re.S)
        if not match:
            return dict(strict_parse_status='fail', strict_error=error, value=None,
                        sensitivity='none', sensitivity_parse_status='unavailable')
        try:
            value = parse_json(match.group(1))
        except (ValueError, TypeError):
            return dict(strict_parse_status='fail', strict_error=error, value=None,
                        sensitivity='outer_fence_only', sensitivity_parse_status='fail')
    return dict(strict_parse_status='fail' if error else 'pass', strict_error=error,
                value=value, sensitivity='outer_fence_only' if error else 'none',
                sensitivity_parse_status='pass' if error else 'not_used')


def check_update(text, inventory):
    parsed = parse_update(text)
    value = parsed['value']
    errors, records = [], []
    if not isinstance(value, dict):
        errors.append('not_object')
    elif not isinstance(value.get('records'), list):
        errors.append('records_not_list')
    else:
        if value.get('coverage') != 'partial':
            errors.append('coverage_not_partial')
        counts = Counter()
        for index, record in enumerate(value['records']):
            local, locations = [], []
            if not isinstance(record, dict) or not FIELDS.issubset(record):
                records.append(dict(record_index=index, errors=['missing_required_fields'], source_locations=[]))
                continue
            kind = record['kind']
            if not isinstance(kind, str) or kind not in {'MP', 'ME'}:
                local.append('kind')
            else:
                counts[kind] += 1
            if kind == 'ME' and (not isinstance(record['stage'], str) or record['stage'] not in STAGES):
                local.append('ME_stage_enum')
            if not isinstance(record['relation'], str) or record['relation'] not in RELATIONS:
                local.append('relation_enum')
            sessions = [s for s in inventory['sessions'] if s['session_id'] == record['source_session']]
            if len(sessions) != 1:
                local.append('source_session_not_supplied')
            else:
                source = sessions[0]
                if record['reported_date'] != source['reported_date']:
                    local.append('reported_date')
                turn = next((t for t in source['turns'] if type(record['turn']) is int and t['turn'] == record['turn']), None)
                if turn is None:
                    local.append('source_turn_not_supplied')
                else:
                    if record['speaker'] != turn['speaker']:
                        local.append('speaker')
                    quote = record['exact_quote']
                    if not isinstance(quote, str) or not quote or quote not in turn['text']:
                        local.append('non_exact_quote_at_specified_turn')
                    else:
                        start = turn['text'].index(quote)
                        locations.append(dict(session_id=source['session_id'], turn=turn['turn'],
                            speaker=turn['speaker'], start_char=start, end_char=start+len(quote),
                            source_turn_sha256=sha256_text(turn['text'])))
            records.append(dict(record_index=index, errors=local, source_locations=locations,
                                stage_enum_is_not_stage_semantics=True))
        if any(n > 1 for n in counts.values()):
            errors.append('more_than_one_per_kind')
    all_errors = errors + [e for row in records for e in row['errors']]
    content_status = 'fail' if all_errors else 'pass'
    return dict(parse=parsed, schema_and_source_status=content_status,
                primary_mechanical_status='pass' if content_status == 'pass' and parsed['strict_parse_status'] == 'pass' else 'fail',
                errors=errors, records=records, semantic_approved=False,
                formal_semantic_status='uncertain', reward=None)


def validate_update_review(review, checked, output):
    if review['formal_semantic_status'] != 'uncertain' or review['reward'] is not None:
        raise ValueError('development review cannot award a formal reward')
    value = checked['parse']['value']
    records = value.get('records', []) if isinstance(value, dict) else []
    if not isinstance(records, list):
        records = []
    if len(review['records']) != len(records) or {r['record_index'] for r in review['records']} != set(range(len(records))):
        raise ValueError('every returned record must be reviewed')
    for row in review['records']:
        record = records[row['record_index']]
        for evidence in row['output_field_evidence']:
            if not isinstance(record, dict) or record.get(evidence['field']) != evidence['value']:
                raise ValueError('review field evidence differs from actual JSON')
    for quote in review.get('output_quotes', []):
        if not quote or quote not in output:
            raise ValueError('review output quote not exact')
    return True


def combined_representation_aggregate(reviews, audits):
    """Keep unknown/conflicting gold separate from supported completion counts."""
    by_arm = defaultdict(list)
    for review in reviews:
        by_arm[review['arm']].append(review)
    groups = {}
    for arm, rows in by_arm.items():
        refs, supported, unresolved = Counter(), Counter(), Counter()
        complete_tasks = 0
        for row in rows:
            atom_map = {a['atom_id']: a for a in audits[row['task_id']]['atoms']}
            eligible = []
            for atom in row['atoms']:
                reference = atom_map[atom['atom_id']]['status_end_history']
                refs[reference] += 1
                if reference in {'supported', 'calendar_derived'}:
                    supported[atom['observed']] += 1
                    eligible.append(atom)
                else:
                    unresolved[atom['observed']] += 1
            complete_tasks += bool(eligible) and all(a['observed'] == 'complete' for a in eligible)
        groups[arm] = dict(tasks=len(rows), original_required_atom_presentations=sum(refs.values()),
            reference_status_counts=dict(refs), supported_or_calendar_atom_presentations=sum(supported.values()),
            supported_atom_observations=dict(supported), unresolved_gold_observations=dict(unresolved),
            complete_on_supported_atoms_tasks=complete_tasks,
            input_tokens=sum(r['technical']['input_tokens'] for r in rows),
            output_tokens=sum(r['technical']['output_tokens'] for r in rows),
            local_seconds=sum(r['technical']['seconds'] for r in rows))
    return dict(protocol='journal-memory12-direct-development-v1', by_arm=groups,
        original_eval_rules_preserved=True, unknown_gold_is_not_a_generator_failure=True,
        semantic_approved=0, rewards=0, scope='same-source exposed Direct diagnostic; assistant development interpretation, not production retrieval or Writer quality')


def paired_representation_changes(reviews, audits):
    grouped = defaultdict(dict)
    for row in reviews:
        grouped[row['task_id']][row['arm']] = row
    result = []
    for task, rows in sorted(grouped.items()):
        if set(rows) != {'RAW', 'SPAN', 'TYPED_OR_SUM'}:
            raise ValueError('fixed three-arm task incomplete')
        allowed = {a['atom_id'] for a in audits[task]['atoms'] if a['required'] and a['status_end_history'] in {'supported', 'calendar_derived'}}
        baseline = {a['atom_id']: a for a in rows['RAW']['atoms'] if a['atom_id'] in allowed}
        for arm in ('SPAN', 'TYPED_OR_SUM'):
            atoms = {a['atom_id']: a for a in rows[arm]['atoms'] if a['atom_id'] in allowed}
            if set(atoms) != set(baseline):
                raise ValueError('paired atoms differ')
            repaired = [i for i in atoms if atoms[i]['observed']=='complete' and baseline[i]['observed']!='complete']
            lost = [i for i in atoms if atoms[i]['observed']!='complete' and baseline[i]['observed']=='complete']
            result.append(dict(task_id=task, arm=arm, repaired_atom_ids=repaired, newly_incomplete_atom_ids=lost,
                incomplete_in_both_atom_ids=[i for i in atoms if atoms[i]['observed']!='complete' and baseline[i]['observed']!='complete'],
                newly_incomplete_with_absent_supply=[i for i in lost if atoms[i]['delivery']=='absent'],
                newly_incomplete_with_insufficient_supply=[i for i in lost if atoms[i]['delivery'] in {'absent','partial'}],
                newly_incomplete_with_full_supply=[i for i in lost if atoms[i]['delivery']=='full'],
                formal_semantic_status='uncertain', reward=None))
    return result


def per_task_representation_table(reviews, audits):
    """Public-safe counts and cost fields; never export question or evidence."""
    grouped = defaultdict(dict)
    for review in reviews:
        grouped[review['task_id']][review['arm']] = review
    result = []
    for task, by_arm in sorted(grouped.items()):
        required = {a['atom_id']: a for a in audits[task]['atoms'] if a['required']}
        eligible = {i for i, a in required.items() if a['status_end_history'] in {'supported', 'calendar_derived'}}
        unresolved = Counter(a['status_end_history'] for i, a in required.items() if i not in eligible)
        arms = {}
        for arm, review in by_arm.items():
            atoms = [a for a in review['atoms'] if a['atom_id'] in eligible]
            if {a['atom_id'] for a in atoms} != eligible:
                raise ValueError('per-task eligible atom set differs')
            arms[arm] = dict(supply_counts=dict(Counter(a['delivery'] for a in atoms)),
                completion_counts=dict(Counter(a['observed'] for a in atoms)),
                complete_on_supported_atoms=bool(atoms) and all(a['observed']=='complete' for a in atoms),
                input_tokens=review['technical']['input_tokens'], output_tokens=review['technical']['output_tokens'],
                local_seconds=review['technical']['seconds'])
        result.append(dict(task_id=task,original_required_atoms=len(required),supported_or_calendar_atoms=len(eligible),
            unresolved_reference_atoms=sum(unresolved.values()),unresolved_reference_statuses=dict(unresolved),arms=arms,
            formal_semantic_status='uncertain',reward=None))
    return result


def navigation_digest(original, *, raw_pointer):
    """Conservative contract repair only; original text and identity preserved."""
    if not raw_pointer:
        raise ValueError('actual source-bound RAW pointer required')
    text = original if INCOMPLETE in original.splitlines() else original + ('\n' if original.endswith('\n') else '\n\n') + INCOMPLETE
    identity = object_sha256(dict(original_sha256=sha256_text(original), navigation_text=text, raw_pointer=raw_pointer))
    return dict(identity='navigation-digest:' + identity, original_sha256=sha256_text(original),
        text=text, raw_pointer=raw_pointer, original_text_is_exact_prefix=text.startswith(original),
        incomplete_marker_added=text != original, semantic_content_improved=False,
        semantic_approved=False, scope='navigation-only derived wrapper; no Writer rerun or old result modification')

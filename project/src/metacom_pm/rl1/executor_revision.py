"""Validation of a small, explicitly weak, source-conditional SFT experiment."""
import json
from .schema import digest


def visible_text(messages):
    """Decode resource JSON so source quotes match text, not JSON escapes."""
    system = messages[0]['content']
    texts = [m['content'] for m in messages]
    if '<resources>\n' in system:
        rows = json.loads(system.split('<resources>\n', 1)[1].split('\n</resources>', 1)[0])
        def walk(value):
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, dict):
                for x in value.values(): walk(x)
            elif isinstance(value, list):
                for x in value: walk(x)
        for row in rows: walk(json.loads(row['content']))
    return texts


def validate_dataset(rows, inputs):
    if not rows or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('nonempty unique training rows required')
    used = set(); groups = {}
    for row in rows:
        item = inputs[row['input_identity']]
        if row['split'] != 'train' or not row['weak_supervision'] or row['reward'] is not None:
            raise ValueError('train-only weak targets, never rewards')
        if digest(row['response']) != row['response_identity'] or not row['response'].strip():
            raise ValueError('target response binding changed')
        if row['input_identity'] in used:
            raise ValueError('duplicate/conflicting training input')
        used.add(row['input_identity']); groups.setdefault(row['case'], []).append(row)
        texts = visible_text(item['messages'])
        for claim in row['historical_claims']:
            if not item['selected_keys'] or not claim['source_quote'] or not any(claim['source_quote'] in t for t in texts):
                raise ValueError('historical target claim absent from acquired input')
            if claim['modality'] != 'past_report_not_current_success':
                raise ValueError('historical status strengthened')
    for case, group in groups.items():
        off = [r for r in group if not inputs[r['input_identity']]['selected_keys']]
        on = [r for r in group if inputs[r['input_identity']]['selected_keys']]
        if len(off) != 1 or not on or off[0]['historical_claims']:
            raise ValueError('every context needs actual OFF and resource conditions')
        if any(r['historical_claims'] for r in group):
            controls = [r for r in on if r['role'] == 'other_topic_control']
            if not controls or any(r['historical_claims'] for r in controls):
                raise ValueError('memory-bearing target requires no-claim other-topic control')
    return dict(rows=len(rows), contexts=len(groups), historical_target_rows=sum(bool(r['historical_claims']) for r in rows),
                source_quote_binding_only_not_helpfulness=True)

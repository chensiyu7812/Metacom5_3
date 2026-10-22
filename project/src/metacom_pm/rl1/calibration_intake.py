"""Lossless, field-wise human intake. This layer does not manufacture gold.

Annotations are reviewed, quoted interpretations, not a free-text classifier.
Their authorship remains distinct from the original human's structured values.
"""
from copy import deepcopy

from .evidence import evidence_turns
from .human_calibration import LABEL_KEYS, validate_label
from .schema import digest


def accept_label(label, item, mapping, evidence, *, reviewer, provenance,
                 annotations=(), raw_source=None, reason_frame=None):
    if set(label) != LABEL_KEYS or label['item_id'] != item['item_id']:
        raise ValueError('label/item schema or identity mismatch')
    if type(mapping.get('swapped')) is not bool:
        raise ValueError('explicit A/B mapping required')
    if not isinstance(label['source_ids'], list):
        raise ValueError('source_ids must remain a list')
    allowed = set(evidence_turns(evidence)) | {'ROLE', 'FULL_SOURCE'}
    references_valid = (all(isinstance(s, str) for s in label['source_ids'])
        and len(set(label['source_ids'])) == len(label['source_ids'])
        and set(label['source_ids']) <= allowed)
    accepted_notes = []
    for a in annotations:
        if a['field'] not in LABEL_KEYS or not isinstance(label[a['field']], str):
            raise ValueError('annotation must refer to an original text field')
        if not a['span'] or a['span'] not in label[a['field']]:
            raise ValueError('annotation span is not verbatim')
        if a.get('source_confirmed') or a.get('severity') is not None:
            raise ValueError('analyst notes cannot add human confirmation or severity')
        if a.get('reply_span') and a['reply_span'] not in item[a['side']]:
            raise ValueError('aligned reply quote is not exact')
        for ref in a.get('sources', []):
            turn = evidence_turns(evidence).get(ref['id'])
            if not turn or ref['text'] != turn['text']:
                raise ValueError('aligned source quote does not match')
        accepted_notes.append(deepcopy(a))
    pref = label['preference'] if label['preference'] in ('A', 'B', 'tie', 'uncertain') else None
    pref_origin = 'structured' if pref is not None else 'unknown'
    recovered = [a for a in accepted_notes if a.get('recover_preference') is not None]
    # Only explicit inability to judge is currently supported. No A/B extraction
    # from prose, sentiment, another rater or the automatic judge.
    if recovered:
        if len(recovered) != 1 or recovered[0]['recover_preference'] != 'uncertain':
            raise ValueError('unsupported preference recovery')
        if pref not in (None, 'uncertain'):
            raise ValueError('structured preference conflicts with narrative recovery')
        pref, pref_origin = 'uncertain', 'quoted_narrative_uncertainty'
    sides = {'A': 1 if mapping['swapped'] else 0, 'B': 0 if mapping['swapped'] else 1}
    canonical = ('left', 'right')[sides[pref]] if pref in sides else pref
    risks = {}
    for side in ('A', 'B'):
        raw = label['risk_' + side]
        level = raw if raw in ('none_detected', 'local', 'severe', 'uncertain') else None
        quote = label['quote_' + side]
        exact = isinstance(quote, str) and bool(quote.strip()) and quote in item[side]
        risks[side] = dict(raw=raw, level=level, canonical_side=sides[side],
            quote_exact=exact,
            source_anchored=bool(exact and references_valid and label['source_ids']),
            evidence_complete=(level == 'none_detected' or bool(
                level in ('local', 'severe') and exact and references_valid and label['source_ids'])),
            # A valid "none detected" is a human report, not verified absence.
            source_confirmed=False)
    try:
        validate_label(label, item, evidence)
        strict_error = None
    except ValueError as exc:
        strict_error = str(exc)
    result = dict(item_id=item['item_id'], pair_id=mapping['pair_id'], group=mapping['group'],
        reviewer=reviewer, provenance=deepcopy(provenance), raw_source=raw_source,
        raw_label=deepcopy(label), raw_label_identity=digest(label),
        original_strict_error=strict_error, mapping=deepcopy(mapping),
        reply_identities={s:digest(item[s]) for s in ('A', 'B')},
        evidence_identity=digest(evidence), reason_frame=reason_frame or reviewer,
        preference=dict(value=pref, canonical=canonical, origin=pref_origin,
                        comparable=canonical in ('left', 'right', 'tie')),
        risks=risks, annotations=accepted_notes, source_ids_valid=references_valid,
        human_factual_confirmation=False, reward_qualified=False)
    return dict(result, identity=digest(result))


def independent_reviewers(records, requested):
    """A copied second file does not constitute a second observation."""
    if len(requested) not in (1, 2) or len(set(requested)) != len(requested):
        raise ValueError('one or two unique reviewers required')
    origins = []
    for name in requested:
        rows = [r for r in records if r['reviewer'] == name]
        if not rows:
            raise ValueError('missing reviewer')
        provenance = rows[0]['provenance']
        if any(r['provenance'] != provenance for r in rows):
            raise ValueError('conflicting reviewer provenance')
        if provenance.get('kind') not in ('saved_browser_record', 'independent_human_export'):
            raise ValueError('derived reviewer cannot be counted as independent')
        origin = provenance.get('observation_origin')
        if not origin or origin in origins:
            raise ValueError('missing or repeated observation origin')
        origins.append(origin)
    return list(requested)

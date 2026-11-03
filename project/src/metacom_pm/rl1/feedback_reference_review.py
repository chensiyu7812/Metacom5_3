"""Prepare existing score-aware audits, with human references kept LOCAL.

No new scorer, prompt, qualification threshold, provider, reward or human task.
Numeric disagreements are review evidence, not automatic relabeling rules.
"""
from copy import deepcopy

from .schema import digest


def compare_reference(score, reference):
    """Compare components separately; equal utility can hide a missed error."""
    if reference['q_status'] == 'single':
        low = high = reference['q_value']
    elif reference['q_status'] == 'range':
        low, high = reference['q_min'], reference['q_max']
    else:
        raise ValueError('explicit single value or retained interval required')
    m = reference['m_value']
    if (type(low) is not int or type(high) is not int or not 0 <= low <= high <= 4
            or type(m) not in (int, float) or m not in (0, .25, 1)):
        raise ValueError('invalid human numeric reference')
    result = dict(reference_id=reference['asset_id'], q_interval=[low, high], m=m,
        U_interval=[low/4-m, high/4-m], q_agrees=None, m_agrees=None,
        U_in_interval=None, utility_hides_component_disagreement=None,
        disposition='missing_numeric_candidate', replacement_score=None)
    if score is None:
        return result
    q, candidate_m = score['q'], score['m']
    if (type(q) is not int or q not in range(5) or type(candidate_m) not in (int, float)
            or candidate_m not in (0, .25, 1)):
        raise ValueError('invalid candidate score')
    u = q/4-candidate_m
    q_ok, m_ok = low <= q <= high, m == candidate_m
    u_ok = low/4-m <= u <= high/4-m
    return result | dict(q_agrees=q_ok, m_agrees=m_ok, U_in_interval=u_ok,
        utility_hides_component_disagreement=u_ok and not (q_ok and m_ok),
        disposition=('components_match' if q_ok and m_ok else
                     'quality_disagreement' if m_ok else 'misuse_disagreement'))


def prepare_bound_review(adapter, item, request, raw, references):
    """Reparse original S and prepare its existing A; never infer a missing S.

    References must bind this entire evidence/reply input. They are returned in
    a separate local card and must not enter the audit's wire body or identity.
    The caller retains the original journal/raw/protocol provenance as well.
    """
    if request != adapter.prepare(item, 'S'):
        raise ValueError('primary request does not match exact current input')
    evaluated = adapter.evaluate(request, item, raw)
    if not evaluated['technical_valid']:
        raise ValueError('invalid primary cannot be repaired into an audit input')
    eid, rid = digest(item['evidence']), digest(item['reply'])
    for ref in references:
        if (ref['evidence_identity'] != eid or ref['reply_identity'] != rid
                or ref['task_family'] not in ('singles', 'supplements')):
            raise ValueError('reference is not for this exact complete input')
    numeric = None if evaluated.get('model_unknown') else {
        k:evaluated[k] for k in ('q', 'm', 'U')}
    comparisons = [compare_reference(numeric, ref) for ref in references
                   if ref['task_family'] == 'singles']
    prepared = adapter.prepare(item, 'A', score=evaluated['value'])
    return dict(request=prepared, primary_evaluation=evaluated,
        local_review=dict(evidence_identity=eid, reply_identity=rid,
            primary_request_identity=request['identity'],
            preliminary_score_identity=digest(evaluated['value']),
            audit_request_identity=prepared['identity'], candidate=numeric,
            comparisons=comparisons, original_references=deepcopy(references),
            new_human_question=None, replacement_score=None,
            interpretation='Exposed development diagnostics; numeric agreement is not qualification.',
            qualified_reward=False, training_authorized=False))

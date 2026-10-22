"""Offline candidate: distinguish a reply defect from a preliminary-score defect.

This module has no dispatch, credentials, ledger writes or optimizer entry point.
The source_evidence interface and original numeric scorer are reused unchanged.
Explicit score links are a new measurement contract, NOT a reinterpretation of
historical audit outputs. Even a valid, internally consistent audit is fallible.
"""
from copy import deepcopy
import json

from . import feedback_source_evidence as source
from .schema import digest

VERSION = 'pmrl1-score-aware-audit-offline-v1-20261022'
INTERFACE = 'source-evidence-score-links-v1-20261022'
POLICY = dict(enabled=False, live_dispatch=False, old_stops_released=False,
              reward_eligible=False, training_authorized=False,
              historical_scores_mutable=False)

ADDITION = '''
SCORE-AWARE AUDIT CANDIDATE (new interface, unchanged q/m definitions)
An error in the reply is not by itself an error in the preliminary_score.
Keep the original reply/source audit, then explicitly examine the preliminary
measurement. Return score_review in addition to check, findings and
coverage_limitations. This replaces only the earlier list of top-level keys.
Bind score_review to the supplied preliminary_score_sha256. For EVERY finding
provide its zero-based finding_index, score_links with exact JSON paths and
nonempty quotations from the preliminary score, disposition and reason.
Disposition: already_accounted means this SAME claim/reading and its treatment
are adequately represented; no_score_issue means a no_issue_identified finding
reveals no score defect; score_issue means a specific omission or inconsistency;
unresolved means the score implication lacks sufficient justification.
For an omission, cite the relevant existing assessment, coverage or q rationale
and explain what is absent; do not invent a quote for the missing judgment.
Shared unit IDs or sources do not prove that the same claim was assessed.
Do not let already_accounted certify q or severity: check quality, severity and
coverage separately. Each check must cite the relevant preliminary reasoning,
state the applicable unchanged criterion and the concrete grounds for supported,
score_issue or unresolved. An unsupported claim alone does not determine severity.
q and m may overlap when their respective task consequences justify it. A minor
alternative reading is not automatically blocking; a genuine unresolved numeric
basis remains unresolved. Empty findings do not establish complete coverage.
Do not supply replacement q/m/U, a preferred resource or a target numeric outcome.
Read the full original reply and legal sources; the preliminary score is fallible,
not evidence or gold. A check remains a machine claim, not independent validation.
'''


def _obj(properties):
    return dict(type='object', properties=properties, required=list(properties),
                additionalProperties=False)


def score_texts(score):
    """Only readable preliminary reasoning can be cited, never arbitrary paths."""
    texts = {'/coverage': score['coverage']}
    for key in ('current_need', 'reason'):
        texts['/q_rationale/' + key] = score['q_rationale'][key]
    for i, assessment in enumerate(score['assessments']):
        texts[f'/assessments/{i}/reason'] = assessment['reason']
    return texts


def review_schema(score):
    text = dict(type='string', minLength=1)
    links = dict(type='array', minItems=1, items=_obj(dict(
        path=dict(enum=list(score_texts(score))), quote=text)))
    check = _obj(dict(status=dict(enum=['supported', 'score_issue', 'unresolved']),
                      score_links=links, criterion=text, reason=text))
    finding = _obj(dict(finding_index=dict(type='integer', minimum=0),
        disposition=dict(enum=['no_score_issue', 'already_accounted', 'score_issue', 'unresolved']),
        score_links=links, reason=text))
    return _obj(dict(preliminary_score_sha256=dict(const=digest(score)),
        findings=dict(type='array', items=finding),
        checks=_obj({key: deepcopy(check) for key in ('quality', 'severity', 'coverage')})))


def audit_schema(item, score, paired):
    schema = source.audit_schema(item, paired)
    schema['properties']['score_review'] = review_schema(score)
    schema['required'].append('score_review')
    return schema


def audit_payload(item, score, paired):
    # Reuse the original source audit BEFORE its old exact-schema suffix, so the
    # model receives one complete schema, not competing old/new definitions.
    messages, _ = source.old.audit_payload(item, score, paired)
    data = json.loads(messages[1]['content'])
    data['preliminary_score_sha256'] = digest(score)
    schema = audit_schema(item, score, paired)
    messages[0]['content'] += '\n' + ADDITION + '\nOUTPUT INTERFACE ' + INTERFACE
    messages[0]['content'] += (': findings uses source_evidence; check.claims keeps evidence. '
        'Return one JSON object matching this complete schema exactly:\n') + json.dumps(schema, ensure_ascii=False)
    messages[1]['content'] = json.dumps(data, ensure_ascii=False)
    return messages, schema


def validate_review(audit, score):
    """Mechanical binding only; this cannot certify the semantic dispositions."""
    from jsonschema import Draft202012Validator
    review = audit['score_review']
    Draft202012Validator(review_schema(score)).validate(review)
    indices = [f['finding_index'] for f in review['findings']]
    if sorted(indices) != list(range(len(audit['findings']))):
        raise ValueError('every finding must be linked exactly once')
    texts = score_texts(score)
    for entry in [*review['findings'], *review['checks'].values()]:
        for link in entry['score_links']:
            if link['quote'] not in texts[link['path']]:
                raise ValueError('score quote not in bound preliminary reasoning')
    for link in review['findings']:
        finding = audit['findings'][link['finding_index']]
        disposition, verdict = link['disposition'], finding['verdict']
        if verdict == 'unresolved' and disposition != 'unresolved':
            raise ValueError('unresolved numeric finding cannot be marked accounted')
        if verdict == 'identified_error' and disposition == 'no_score_issue':
            raise ValueError('reply error requires explicit accounting or score issue')
        if verdict == 'no_issue_identified' and disposition == 'already_accounted':
            raise ValueError('already_accounted is reserved for an identified reply defect')
        if disposition == 'already_accounted':
            paths = [x['path'] for x in link['score_links']]
            if finding['dimension'] == 'relation' and not any(p.startswith('/assessments/') for p in paths):
                raise ValueError('accounted relation must cite an actual assessment')
    paths = [x['path'] for x in review['checks']['quality']['score_links']]
    if not any(p.startswith('/q_rationale/') for p in paths):
        raise ValueError('quality check must inspect q rationale')
    paths = [x['path'] for x in review['checks']['severity']['score_links']]
    if not any(p.startswith('/assessments/') for p in paths):
        raise ValueError('severity check must inspect assessments')
    return deepcopy(review)


def validate_audit(audit, item, score, paired):
    from jsonschema import Draft202012Validator
    Draft202012Validator(audit_schema(item, score, paired)).validate(audit)
    base = {k: deepcopy(v) for k, v in audit.items() if k != 'score_review'}
    source.validate_audit(base, item, paired)
    validate_review(audit, score)
    return deepcopy(audit)


def evaluate_audit(raw, item, score, paired):
    try:
        final, finish = paired.final_content(raw)
        if finish != 'natural_stop':
            raise ValueError('audit final incomplete')
        _, value, adaptation = paired.envelope.unwrap(final)
        validate_audit(value, item, score, paired)
        return dict(technical_valid=True, value=value, outer_adaptation=adaptation,
                    interface_version=INTERFACE, reward_eligible=False, semantic_gold=False)
    except Exception as exc:
        return dict(technical_valid=False, value=None, error_type=type(exc).__name__,
                    error=str(exc), interface_version=INTERFACE, reward_eligible=False)


def decision(joint, audit):
    """Pure offline proposal on already source/schema-validated evaluations.

    No decision authorizes execution or changes a score. Caller must use
    evaluate_audit before passing new evaluations. Legacy valid audits cannot be
    upgraded by this function; their missing score links remain missing.
    """
    from jsonschema.exceptions import ValidationError
    result = dict(version=VERSION, execute=False, reward_eligible=False,
                  training_ready=False, proposed_U=None, semantic_gold=False)
    if not joint or not audit:
        return result | dict(action='pending_dependency', reasons=['missing_result'])
    if joint.get('hard_stop') or audit.get('hard_stop') or not all(
            r.get('technical_valid') and r.get('evaluation', {}).get('technical_valid') for r in (joint, audit)):
        return result | dict(action='hard_stop', reasons=['technical_or_execution_failure'])
    je, ae = joint['evaluation'], audit['evaluation']
    if je.get('model_unknown') or je['value']['status'] == 'uncertain':
        return result | dict(action='supplement_candidate', reasons=['model_score_unknown'])
    if ae['value']['check']['status'] == 'uncertain':
        return result | dict(action='supplement_candidate', reasons=['model_check_unknown'])
    if 'score_review' not in ae['value']:
        return result | dict(action='legacy_link_missing', reasons=['not_retroactively_inferred'])
    try:
        if ae.get('interface_version') != INTERFACE:
            raise ValueError('new review requires its own validated interface identity')
        review = validate_review(ae['value'], je['value'])
    except (ValueError, KeyError, TypeError, ValidationError) as exc:
        return result | dict(action='hard_stop', reasons=['score_binding_failure', str(exc)])
    reasons = [f'finding:{x["finding_index"]}:{x["disposition"]}' for x in review['findings']
               if x['disposition'] in ('score_issue', 'unresolved')]
    reasons += [f'{key}:{value["status"]}' for key, value in review['checks'].items()
                if value['status'] != 'supported']
    if reasons:
        return result | dict(action='supplement_candidate', reasons=reasons)
    return result | dict(action='retain_numeric_candidate', reasons=['explicit_machine_score_review_only'],
                         proposed_U=je['U'])


def association_candidates(score, audit):
    """Inspect old records without pretending they contain new model decisions.

    A unit can contain multiple claims, so overlap retrieves possible links only.
    It NEVER sets already_accounted, q/m correctness or qualification.
    """
    output = []
    for i, finding in enumerate(audit['findings']):
        sources = {e['source_id'] for e in finding['source_evidence']}
        matches = []
        for j, assessment in enumerate(score['assessments']):
            if assessment['response_unit_id'] == finding['response_unit_id']:
                matches.append(dict(path=f'/assessments/{j}/reason',
                    quote=assessment['reason'], relation=assessment['relation'],
                    severity=assessment['severity'],
                    shared_source_ids=sorted(sources & set(assessment['source_turn_ids']))))
        output.append(dict(finding_index=i, verdict=finding['verdict'],
            response_quote=finding['response_quote'], candidate_assessments=matches,
            disposition=None, proves_same_claim=False, proves_correct_score=False))
    return output

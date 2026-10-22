"""Offline feedback-resolution prototype; no provider or optimizer entry point.

The existing scorer, extraction validator, cache and PendingBatch are reused by
adapters. This module never qualifies a reward or overrides an historical STOP.
Machine declarations are signals, not certified entailment or human gold.
"""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import json
import math

from .schema import digest
from .evidence import evidence_turns
from .judge_indexed import response_units

VERSION = "pmrl1-feedback-resolution-prototype-20261022-v1"
ISSUES = ("interpretation", "relation", "consequence", "quality_basis")
VERDICTS = ("no_issue_identified", "unresolved", "identified_error")
DEFAULT_POLICY = dict(version=VERSION, enabled=False, max_supplements_per_endpoint=1,
                      max_supplements_per_batch=4, batch_size=16,
                      max_review_minutes=120, training_authorized=False)

# A substantive, proposed post-score audit interface, NOT an enabled prompt fix.
AUDIT_ADDITION = """
POST-SCORE EVIDENCE AUDIT (development prototype, not an independent judge)
The preliminary_score is a fallible measurement, not evidence. Independently
read the entire original reply and complete legal sources. First supply the
unchanged claim-check object under check. Then return findings (possibly empty).
Each finding identifies one specific response unit and exact response quote,
dimension (interpretation, relation, consequence, quality_basis), verdict
(no_issue_identified, unresolved, identified_error), readings (one or more
plausible readings; do not manufacture alternatives), exact source evidence,
criterion, consequence and reason. For a missing source, name the searched scope
in reason; unsupported is not proof of real-world nonoccurrence. For consequence,
state what core understanding/advice changes or remains intact; a second reading
is NOT itself a severity justification. For quality_basis, identify the current
request and the concrete contribution/omission; do not prescribe one style.
Different readings, source relations, and consequences are separate questions.
Not every possible alternative reading prevents scoring. Mark unresolved only
when the supplied evidence and anchors do not support the numeric justification;
report a nonblocking caveat as no_issue_identified with its limitation instead.
Do not give q, m, U, a resource preference, or a replacement numeric score. Do not
force agreement with preliminary_score. Source quotes/IDs must bind originals.
Return exactly check, findings, coverage_limitations. coverage_limitations is a
nonempty string identifying any coverage limits, not a claim of perfect recall.
"""

REPAIR_ADDITION = """
BOUNDED EVIDENCE RESOLUTION (new measurement, not a retry)
The supplied preliminary_score and machine_audit are fallible model outputs,
not evidence or gold. Check them against the full original reply and sources.
Use the unchanged q/m anchors and final schema. You may retain a score with a
source-grounded reason or correct it; do not seek a preferred score, direction,
or agreement with the audit. Distinguish plausible readings, evidence relation,
and consequences to core understanding/advice. If the numeric judgment remains
underdetermined under these rules, return the existing uncertain status. No
averaging, worst-case selection, imputation, or invented source is permitted.
This is the only supplemental measurement allowed for this endpoint. Its result
does not erase the first result or resolve itself by another request.
"""


def audit_schema(item, paired):
    text = dict(type="string", minLength=1)
    obj = paired.obj
    finding = obj(dict(response_unit_id=dict(enum=[u['id'] for u in response_units(item['reply'])]),
        response_quote=text, dimension=dict(enum=list(ISSUES)), verdict=dict(enum=list(VERDICTS)),
        readings=dict(type="array", minItems=1, items=text),
        evidence=dict(type="array", items=obj(dict(source_id=dict(enum=list(evidence_turns(item['evidence']))), quote=text))),
        criterion=text, consequence=text, reason=text))
    return obj(dict(check=paired.extraction_schema(item), findings=dict(type="array", items=finding),
                    coverage_limitations=text))


def audit_payload(item, score, paired):
    """No manual reference, score from another arm, resource winner, or label."""
    messages, _ = paired.payload(item, "extract")
    data = json.loads(messages[1]['content'])
    data['preliminary_score'] = deepcopy(score)
    return [dict(role="system", content=messages[0]['content'] + AUDIT_ADDITION),
            dict(role="user", content=json.dumps(data, ensure_ascii=False))], audit_schema(item, paired)


def validate_audit(value, item, paired):
    from jsonschema import Draft202012Validator
    Draft202012Validator(audit_schema(item, paired)).validate(value)
    paired.validate_extract(value['check'], item)
    units = {u['id']:u['text'] for u in response_units(item['reply'])}
    turns = evidence_turns(item['evidence'])
    for f in value['findings']:
        if f['response_quote'] not in units[f['response_unit_id']]:
            raise ValueError("audit quote not in original reply unit")
        for e in f['evidence']:
            if e['quote'] not in turns[e['source_id']]['text']:
                raise ValueError("audit quote not in original source")
    return deepcopy(value)


def evaluate_audit(raw, item, paired):
    """Same final-only envelope and duplicate-key rules as existing requests."""
    try:
        final, finish=paired.final_content(raw)
        if finish!='natural_stop':raise ValueError('audit final incomplete')
        _,value,adaptation=paired.envelope.unwrap(final)
        validate_audit(value,item,paired)
        return dict(technical_valid=True,value=value,outer_adaptation=adaptation,
                    reward_eligible=False,semantic_gold=False)
    except Exception as exc:
        return dict(technical_valid=False,value=None,error_type=type(exc).__name__,
                    error=str(exc),reward_eligible=False)


def repair_payload(item, score, audit, common_prompt, paired):
    validate_audit(audit,item,paired)
    flagged=(score['status']=='uncertain' or audit['check']['status']=='uncertain'
             or any(x['verdict']!='no_issue_identified' for x in audit['findings']))
    if not flagged:raise ValueError('unflagged endpoints cannot receive extra sampling')
    messages,schema=paired.payload(item,'joint')
    data=json.loads(messages[1]['content'])
    data.update(preliminary_score=deepcopy(score),machine_audit=deepcopy(audit))
    return [dict(role='system',content=common_prompt+REPAIR_ADDITION),
            dict(role='user',content=json.dumps(data,ensure_ascii=False))],schema


def scalar(q, m):
    if type(q) is not int or q not in range(5) or type(m) not in (int, float) or m not in (0, .25, 1):
        raise ValueError("original q/m scale required; missing is not zero")
    return float(Decimal(q) / 4 - Decimal(str(m)))


def observation(slot, *, review=None, audit=None):
    """Keep source provenance and issues separate; never infer new semantic labels.

    `slot` is an existing, validated paired-engine result. An audit must already
    pass validate_audit. Returned candidates are NOT permission for training.
    """
    result = slot.get('result')
    ev = (result or {}).get('evaluation') or {}
    binding = dict(slot_id=slot['slot_id'], request_identity=(result or {}).get('request_identity'),
                   reply_identity=slot['reply_identity'], evidence_identity=slot['evidence_identity'],
                   pipeline_identity=ev.get('pipeline_identity'), arm=slot['arm'], result_identity=digest(result))
    raw = dict(q=ev.get('q'), m=ev.get('m'), U=ev.get('U'))
    technical = ('not_started' if result is None and slot.get('state')=='not_dispatched'
                 else 'unresolved_request' if result is None
                 else 'valid' if result.get('technical_valid') and ev.get('technical_valid')
                 else 'failed')
    unknown = ev.get('model_unknown') is True
    signal = []
    if (ev.get('value') or {}).get('uncertainty_reasons') and not unknown:
        signal.append('scored_with_explicit_uncertainty')
    reviewer = dict(unresolved=[], confirmed_errors=[], basis_issue=None, watch=[])
    if review is not None:
        if (review.get('slot_id') != slot['slot_id'] or review.get('request_identity') != binding['request_identity']
                or review.get('evidence_identity') != slot['evidence_identity'] or review.get('raw_scores') != raw):
            raise ValueError("review bound to different request/evidence/scores")
        reviewer = dict(unresolved=review.get('reviewer_unresolved_types', []),
            confirmed_errors=review.get('confirmed_source_proven_checking_errors', []),
            basis_issue=review.get('scoring_basis_issue'), watch=review.get('additional_boundary_watch', []))
    machine_findings = deepcopy(audit['findings']) if audit is not None else []
    if audit and audit['check']['status']=='uncertain':
        signal.append('audit_relation_uncertain')
    if any(f['verdict']!='no_issue_identified' for f in machine_findings):
        signal.append('audit_requires_resolution')
    if technical == 'valid' and not unknown:
        if scalar(raw['q'], raw['m']) != raw['U']:
            raise ValueError("stored utility mismatch")
    if unknown and any(raw[k] is not None for k in raw):
        raise ValueError("model unknown must retain nulls")
    status = ('not_started' if technical=='not_started' else 'hard_stop' if technical!='valid'
              else 'model_unknown' if unknown else 'confirmed_error' if reviewer['confirmed_errors']
              else 'review_unresolved' if reviewer['unresolved'] or reviewer['basis_issue']
              else 'machine_flagged' if signal else 'candidate')
    out = dict(version=VERSION, binding=binding, status=status, technical=technical,
        model_unknown=unknown, machine_signals=signal, machine_findings=machine_findings,
        automatic_audit_available=audit is not None, reviewer=deepcopy(reviewer),
        original=raw, candidate_U=raw['U'] if status=='candidate' else None,
        reward_eligible=False, training_authorized=False,
        known_manual_assistance=slot.get('manual_assistance', True))
    return out | dict(identity=digest(out))


def repeat_signals(slots):
    """Same measurement condition only; A vs B is never a stochastic repeat."""
    groups = defaultdict(list)
    for s in slots:
        r = s.get('result') or {}; e = r.get('evaluation') or {}
        if r.get('technical_valid') and not e.get('model_unknown'):
            groups[(s['reply_identity'], s['evidence_identity'], s['arm'], e.get('pipeline_identity'))].append(s)
    flags = {}
    for group in groups.values():
        if len({(x['result']['evaluation']['q'], x['result']['evaluation']['m']) for x in group})>1:
            ids = [x['slot_id'] for x in group]
            for x in group:
                flags[x['slot_id']] = dict(kind='observed_same_condition_repeat_difference',
                    related_slots=ids, proves_correct_interval=False, proves_error=False,
                    available_only_when_repeats_measured=True)
    return flags


def pair_feedback(pair, records):
    off, on = records[pair['off_slot']], records[pair['on_slot']]
    if off['binding']['evidence_identity'] != on['binding']['evidence_identity']:
        raise ValueError("OFF/ON evidence mismatch")
    if (off['binding']['pipeline_identity'],off['binding']['arm']) != (on['binding']['pipeline_identity'],on['binding']['arm']):
        raise ValueError("OFF/ON measurement version mismatch")
    tokens = pair['resource_tokens']
    if type(tokens) is not int or not 0 <= tokens <= 2048:
        raise ValueError("invalid complete resource token count")
    valid = all(x['status']=='candidate' for x in (off, on))
    raw_valid = all(x['technical']=='valid' and not x['model_unknown'] for x in (off,on))
    raw_net = on['original']['U']-off['original']['U']-tokens/40960 if raw_valid else None
    return dict(pair_id=pair['pair_id'], arm=pair['arm'], off_slot=pair['off_slot'], on_slot=pair['on_slot'],
        off_draw=pair['off_draw'], on_draw=pair['on_draw'], shared_on=pair['shared_on'],
        resource_tokens=tokens, original_net=raw_net, candidate_net=raw_net if valid else None,
        status='candidate' if valid else 'pending',
        reasons=[dict(slot=x['binding']['slot_id'], status=x['status']) for x in (off,on) if x['status']!='candidate'],
        direction_correctness=None, reward_eligible=False, independent_cases=0)


def batch_state(trajectory_feedback, *, expected_ids, supplements_started=0,
                review_minutes=0, closed=False, policy=None):
    """A proposed orchestration decision; never calls PendingBatch.update_once."""
    policy = policy or DEFAULT_POLICY
    if (len(expected_ids)!=policy['batch_size'] or len(set(expected_ids))!=len(expected_ids)
            or len(trajectory_feedback)!=len(expected_ids)
            or {x['trajectory_id'] for x in trajectory_feedback}!=set(expected_ids)):
        raise ValueError("retain every original trajectory exactly once")
    statuses = {x['status'] for x in trajectory_feedback}
    if not statuses <= {'candidate','pending','hard_stop'}:
        raise ValueError("unknown batch feedback state")
    pending = [x['trajectory_id'] for x in trajectory_feedback if x['status']!='candidate']
    if 'hard_stop' in statuses: state='STOP_EXECUTION_FAILURE'
    elif not pending: state='COMPLETE_CANDIDATE_BATCH_NOT_AUTHORIZED'
    elif closed or supplements_started >= policy['max_supplements_per_batch'] or review_minutes >= policy['max_review_minutes']:
        state='END_BATCH_UNRESOLVED_NO_UPDATE'
    else: state='WAIT_BOUNDED_RESOLUTION_BEHAVIOR_FROZEN'
    return dict(state=state, pending=pending, retained=len(trajectory_feedback),
        all_original_trajectories_retained=True, update_allowed=False,
        new_batch_sampling_allowed=False, parameter_update_count=0)


class ResolutionLog:
    """Append-only local supplement identities; NOT a request dispatcher.

    All claims consume a bounded slot, including interrupted/unknown attempts.
    On restart a claim is retained. A second claim for that endpoint is refused.
    """
    def __init__(self, root, study, policy=None):
        self.root, self.study = Path(root), study
        self.policy = deepcopy(policy or DEFAULT_POLICY)
        if self.policy['max_supplements_per_endpoint']!=1:
            raise ValueError('prototype supports exactly one supplement, not repeated polling for a score')
        self.root.mkdir(parents=True, exist_ok=True)
        self._once(self.root/'identity.json', dict(study=study, policy=self.policy))

    @staticmethod
    def _once(path, value):
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n'
        if path.exists():
            if path.read_text()!=data: raise ValueError("immutable resolution identity changed")
            return
        with path.open('x') as f:
            f.write(data); f.flush()
            import os
            os.fsync(f.fileno())
        path.chmod(0o600)

    def claim(self, record):
        if digest({k:v for k,v in record.items() if k!='identity'})!=record['identity']:
            raise ValueError('feedback record changed before resolution')
        if record['status'] not in ('model_unknown','confirmed_error','review_unresolved','machine_flagged'):
            raise ValueError("supplement is not a retry for technical failure or an unflagged score")
        # flock covers admission across concurrent local callers; no provider here.
        import fcntl
        with (self.root/'admission.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            key=digest(dict(study=self.study, endpoint=record['binding']['slot_id'], purpose='one_evidence_resolution'))
            path=self.root/(key+'.claim.json')
            if path.exists(): raise ValueError("already claimed; no retry or cross-version re-claim")
            if len(list(self.root.glob('*.claim.json'))) >= self.policy['max_supplements_per_batch']:
                raise ValueError("bounded resolution budget exhausted")
            spent=sum(json.loads(p.read_text())['review_minutes'] for p in self.root.glob('*.resolution.json'))
            if spent >= self.policy['max_review_minutes']:
                raise ValueError('bounded human review time exhausted')
            self._once(path, dict(key=key, record_identity=record['identity'], binding=record['binding'],
                original=record['original'], original_status=record['status'], scope='OFFLINE_PROTOTYPE'))
            return key

    def finish(self, key, decision, item):
        claim=json.loads((self.root/(key+'.claim.json')).read_text())
        if set(decision) != {'claim_identity','outcome','q','m','basis','source_bindings','provenance','review_minutes'}:
            raise ValueError("explicit resolution fields required")
        if decision['claim_identity'] != digest(claim) or not decision['basis'] or not decision['source_bindings']:
            raise ValueError("resolution requires bound evidence and basis")
        if (digest(item['reply'])!=claim['binding']['reply_identity'] or
                digest(item['evidence'])!=claim['binding']['evidence_identity']):
            raise ValueError("supplement bound to a different endpoint")
        turns=evidence_turns(item['evidence'])
        for entry in decision['source_bindings']:
            if (set(entry)!={'source_id','quote'} or entry['source_id'] not in turns
                    or not entry['quote'] or entry['quote'] not in turns[entry['source_id']]['text']):
                raise ValueError("supplement lacks exact legal source binding")
        if decision['provenance'] not in ('machine_proposal_not_gold','researcher_adjudication','synthetic_test_fixture'):
            raise ValueError("do not manufacture independent gold")
        if type(decision['review_minutes']) not in (int,float) or not math.isfinite(decision['review_minutes']) or decision['review_minutes']<0:
            raise ValueError("review time must be explicit")
        if decision['outcome']=='still_unresolved':
            if decision['q'] is not None or decision['m'] is not None: raise ValueError("unresolved is not a number")
            u=None
        elif decision['outcome'] in ('retain_with_evidence','correct_under_original_scale'):
            if claim['original_status'] in ('confirmed_error','model_unknown') and decision['outcome']=='retain_with_evidence':
                raise ValueError("a known error or missing value cannot be retained as usable")
            u=scalar(decision['q'],decision['m'])
            if decision['outcome']=='retain_with_evidence' and (decision['q'],decision['m'])!=(claim['original']['q'],claim['original']['m']):
                raise ValueError("retain must preserve actual score")
        else: raise ValueError("unrecognized resolution; never choose until favored")
        derived=dict(**decision, derived_U=u, parent_claim=key, reward_eligible=False,
                     training_authorized=False, requires_source_validation_and_approved_policy=True)
        self._once(self.root/(key+'.resolution.json'), derived)
        return derived


def return_sensitivity(before, after, old_value=0.):
    """Terminal-return/value-target analysis only, not a simulated PPO outcome."""
    delta=after-before
    return dict(original_return=before, alternate_return=after, delta_return=delta,
        delta_each_preceding_return_gamma1=delta, delta_raw_advantage=delta,
        value_squared_error_before=(before-old_value)**2,
        value_squared_error_after=(after-old_value)**2,
        illustrative_old_value=old_value, actual_value_prediction_available=False,
        ppo_uses_batch_normalized_nonforced_advantages=True,
        actual_optimizer_or_policy_change_inferred=False)

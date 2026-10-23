"""P3 binding and fail-closed adapters around the existing decision arithmetic.

No models, training, filesystem writes or implicit label decryption. Callers
supply immutable inputs and, only after a real freeze, a decryption callback.
"""
from collections import Counter
from copy import deepcopy

from .calibration_decision import decide, utility
from .calibration_intake import accept_label, independent_reviewers
from .human_calibration import PROTOCOL
from .evidence import evidence_turns
from .schema import digest

FROZEN = 'FROZEN_BEFORE_VALIDATION_LABEL_ACCESS'
DRAFT = 'DRAFT_NOT_AUTHORIZATION_TO_UNSEAL'
BINDINGS = {'packet', 'forms', 'maps', 'pairs', 'jobs', 'pair_score_map',
            'development_intake', 'development_score_review', 'contract', 'protocol', 'runtime', 'code'}


def stamp(value):
    return dict(value, identity=digest(value))


def verify_identity(value):
    if value.get('identity') != digest({k:v for k,v in value.items() if k != 'identity'}):
        raise ValueError('artifact identity mismatch')


def make_freeze(inputs, *, raters, revision_events, final=False):
    if set(inputs) != BINDINGS:
        raise ValueError('incomplete freeze inputs')
    independent_reviewers(inputs['development_intake'], raters)
    hp = inputs['contract']['measurement']['human_pairs']
    dev_pairs = {p['pair_id'] for p in inputs['pairs']['pairs'] if p['group'] == 'development'}
    if len(dev_pairs) != hp['development_natural'] + hp['development_control']:
        raise ValueError('fixed development partition incomplete')
    for name in raters:
        rows = [r for r in inputs['development_intake'] if r['reviewer'] == name]
        for row in rows: verify_identity(row)
        if (len(rows) != len(dev_pairs) or {r['pair_id'] for r in rows} != dev_pairs
                or any(r['group'] != 'development' for r in rows)):
            raise ValueError('development intake coverage/partition mismatch')
    revisions = [r for r in revision_events if r['state'] == 'applied']
    if any(r['state'] not in ('proposed', 'applied', 'recheck_probe') for r in revision_events):
        raise ValueError('unknown revision event')
    if len(revisions) > inputs['contract']['measurement']['semantic_revisions_max']:
        raise ValueError('semantic revision allowance exceeded')
    protocol = inputs['protocol']
    verify_identity(protocol)
    verify_identity(inputs['runtime'])
    if inputs['runtime']['protocol_identity'] != protocol['identity']:
        raise ValueError('runtime/protocol mismatch')
    if protocol['semantic_revisions_after_human_labels'] != len(revisions):
        raise ValueError('revision counter/history mismatch')
    if revisions and revisions[-1]['to_protocol_identity'] != protocol['identity']:
        raise ValueError('revision event does not bind selected protocol')
    if protocol['packet_identity'] != inputs['packet']['packet_identity']:
        raise ValueError('packet/protocol mismatch')
    if final:
        review = inputs['development_score_review']
        verify_identity(review)
        expected = {j['job_id'] for j in inputs['jobs'] if j['group'] in ('development','recheck_probe')}
        if (review.get('status') != 'DEVELOPMENT_REVIEW_CLOSED'
                or review.get('protocol_identity') != protocol['identity']
                or review.get('runtime_identity') != inputs['runtime']['identity']
                or set(review.get('job_ids', [])) != expected
                or review.get('unresolved_measurements') != []):
            raise ValueError('selected runtime development review must close before final freeze')
    by_pair = {p['pair_id']:p for p in inputs['pairs']['pairs']}
    by_job = {j['job_id']:j for j in inputs['jobs']}
    if len(by_pair) != len(inputs['pairs']['pairs']) or len(by_job) != len(inputs['jobs']):
        raise ValueError('duplicate pair/job identity')
    refs = inputs['pair_score_map']
    if (len(refs) != 2*len(by_pair)
            or {(r['pair_id'],r['side']) for r in refs} != {(p,s) for p in by_pair for s in (0,1)}):
        raise ValueError('pair-to-score mapping incomplete')
    for ref in refs:
        pair, job = by_pair[ref['pair_id']], by_job[ref['job_id']]
        if (job['reply'] != pair['replies'][ref['side']] or job['group'] != pair['group']
                or job['prefix_identity'] != pair['prefix_identity']):
            raise ValueError('pair-to-score content/partition mismatch')
    return stamp(dict(version='pm-rl1-calibration-workflow-v1', status=FROZEN if final else DRAFT,
        bindings={k:digest(v) for k,v in inputs.items()}, raters=list(raters),
        packet_identity=protocol['packet_identity'],
        form_identities=[f['form_identity'] for f in inputs['forms'].values()],
        scorer_protocol_identity=protocol['identity'], runtime_identity=inputs['runtime']['identity'],
        rubric_identity=protocol['rubric_identity'], parser_version=protocol['version'],
        development_intake_sha256=digest(inputs['development_intake']),
        qualification_contract_identity=digest(inputs['contract']),
        semantic_revisions=len(revisions), revision_events=deepcopy(revision_events),
        automatic_training_authorization=False))


def require_freeze(freeze, inputs):
    verify_identity(freeze)
    if freeze['status'] != FROZEN:
        raise ValueError('final measurement freeze required before validation access')
    rebuilt = make_freeze(inputs, raters=freeze['raters'],
                          revision_events=freeze['revision_events'], final=True)
    if rebuilt != freeze:
        raise ValueError('freeze inputs or runtime have changed')


def receive_sealed(submission, *, slot, reviewer, provenance, freeze, inputs, decrypt):
    # This MUST precede even obtaining a key or invoking the callback.
    require_freeze(freeze, inputs)
    form, mapping = inputs['forms'][slot], inputs['maps'][slot]
    if set(submission) != {'protocol', 'packet_identity', 'form_identity', 'reviewer_kind',
                           'reviewer_identity', 'reviewer_details', 'items'}:
        raise ValueError('submission schema mismatch')
    if submission['protocol'] != PROTOCOL or submission['reviewer_kind'] != 'individual_human':
        raise ValueError('instrument/reviewer kind mismatch')
    if any(submission[k] != form[k] for k in ('packet_identity', 'form_identity')):
        raise ValueError('submission/form mismatch')
    if (not isinstance(submission['reviewer_identity'], str) or not submission['reviewer_identity'].strip()
            or not isinstance(submission['reviewer_details'], str)):
        raise ValueError('reviewer identity/details missing')
    visible = {i['item_id']:i for i in form['items']}
    envelopes = submission['items']
    if len(envelopes) != len(visible) or {e['item_id'] for e in envelopes} != set(visible):
        raise ValueError('missing, duplicated or replaced encrypted items')
    if any(set(e) != {'item_id', 'wrapped_key', 'nonce', 'ciphertext'} for e in envelopes):
        raise ValueError('invalid encrypted envelope')
    jobs = {j['job_id']:j for j in inputs['jobs']}
    refs = {r['pair_id']:jobs[r['job_id']]['evidence'] for r in inputs['pair_score_map']}
    pairs = {p['pair_id']:p for p in inputs['pairs']['pairs']}
    # Validate every selected mapping before opening the first selected label.
    for item_id, item in visible.items():
        meta = mapping[item_id]
        if meta['group'] != 'validation': continue
        pair = pairs[meta['pair_id']]
        if (type(meta['swapped']) is not bool or pair['group'] != 'validation'
                or item['A'] != pair['replies'][int(meta['swapped'])]
                or item['B'] != pair['replies'][1-int(meta['swapped'])]):
            raise ValueError('sealed form A/B or partition mismatch')
    records = []
    for envelope in envelopes:
        item_id = envelope['item_id']; meta = mapping[item_id]
        if meta['group'] != 'validation':
            continue
        label = decrypt(envelope, packet_identity=form['packet_identity'], form_identity=form['form_identity'])
        records.append(accept_label(label, visible[item_id], meta, refs[meta['pair_id']],
            reviewer=reviewer, provenance=provenance,
            raw_source=dict(submission_identity=digest(submission), envelope_identity=digest(envelope)),
            reason_frame=provenance.get('reason_frame', reviewer)))
    hp = inputs['contract']['measurement']['human_pairs']
    if len(records) != hp['sealed_natural'] + hp['sealed_control']:
        raise ValueError('sealed partition count mismatch')
    return stamp(dict(freeze_identity=freeze['identity'], phase='validation', records=records,
        other_phase_decrypted=False, reward_qualified=False))


def bind_measurement(job, request, raw, measurement, *, runtime, protocol, scorer, cache_hit=False):
    """Reparse raw bytes and verify the exact request, job and runtime, not q/U alone."""
    verify_identity(runtime); verify_identity(protocol)
    if runtime['protocol_identity'] != protocol['identity'] or scorer.RUBRIC_ID != protocol['rubric_identity']:
        raise ValueError('scorer/protocol/runtime mismatch')
    if request['request_id'] != digest({k:v for k,v in request.items() if k != 'request_id'}):
        raise ValueError('request digest mismatch')
    messages, schema = scorer.messages_and_schema(job['evidence'], job['reply'], recheck=job['recheck'])
    if request['messages'] != messages or request['json_schema'] != schema:
        raise ValueError('job/prompt mismatch')
    score_id = digest(dict(evidence=job['evidence'],reply=job['reply'],rubric=scorer.RUBRIC_ID,
        runtime=runtime['identity'],recheck=job['recheck'],
        repeat_draw=job['draw_id'] if job.get('repeat') else None))
    if request.get('score_identity') != score_id:
        raise ValueError('score cache identity mismatch')
    if (request['executor_identity'] != runtime['identity'] or raw['runtime_identity'] != runtime['identity']
            or raw['request_id'] != request['request_id'] or request['draw_identity'] != job['draw_id']
            or request['seed'] != job['seed'] or request['attempt'] not in (0, 1)):
        raise ValueError('run/draw/attempt binding mismatch')
    expected = scorer.parse_completion(raw['text'], evidence=job['evidence'], reply=job['reply'],
        runtime_identity=runtime['identity'], draw_id=job['draw_id'], finish_reason=raw['finish_reason'])
    if measurement != expected:
        raise ValueError('stored measurement differs from reparsed raw output')
    measured = measurement['measurement_status'] == 'measured_candidate'
    return stamp(dict(job_id=job['job_id'], request_id=request['request_id'],
        runtime_identity=runtime['identity'], protocol_identity=protocol['identity'],
        reply_identity=digest(job['reply']), evidence_identity=digest(job['evidence']),
        draw_id=job['draw_id'], seed=job['seed'], attempt=request['attempt'], cache_hit=cache_hit,
        measurement_status=measurement['measurement_status'],
        q=measurement['q'] if measured else None, m=measurement['m'] if measured else None,
        format_valid=measurement['measurement_status'] in ('measured_candidate', 'semantic_uncertainty'),
        raw_identity=digest(raw), measurement_identity=digest(measurement)))


def _supported_contract(contract):
    # Arithmetic lives in the already reviewed implementation. Refuse drift
    # rather than pretending a changed JSON threshold has been implemented.
    fixed = dict(repeat_single_replies=12, repeat_same_utility_min=11,
        severe_risk_repeat_flips_allowed=0, first_format_valid_fraction_min=.95,
        clear_human_pairs_min=8, direction_agreement_min=.75,
        human_ties_min_for_tie_gate=5, tie_agreement_min=.8,
        low_contrast_requires_all_available_clear_directions_correct=True)
    if any(contract['measurement'][k] != v for k,v in fixed.items()):
        raise ValueError('contract changed: existing qualification arithmetic must be reviewed')


def _fact_confirmation(fact, pair, inputs, raters):
    if not fact:
        return {}
    verify_identity(fact)
    if (fact.get('confirmation_kind') not in ('human_fact_adjudication', 'independent_human')
            or fact.get('reviewer') not in raters or fact.get('source_confirmed') is not True
            or fact.get('pair_id') != pair['pair_id'] or not fact.get('verbatim_confirmation')):
        raise ValueError('explicit human factual confirmation required; coordinator intention is not gold')
    if fact.get('replies_identity') != digest(pair['replies']):
        raise ValueError('fact/reply mismatch')
    job = next(j for j in inputs['jobs'] if j['prefix_identity'] == pair['prefix_identity'])
    if fact.get('evidence_identity') != digest(job['evidence']):
        raise ValueError('fact/source version mismatch')
    if not fact.get('source_ids') or not set(fact['source_ids']) <= set(evidence_turns(job['evidence'])) | {'ROLE', 'FULL_SOURCE'}:
        raise ValueError('factual confirmation lacks legal source references')
    # Confirming that a subject/time attribution is wrong does not also confirm
    # the severe-risk anchor. Keep such a control unresolved, not failed gold.
    if pair['kind'] == 'control':
        severe = pair['control_type'] in ('identity','subject','currentness','intent_to_result')
        if fact.get('severity') != ('severe' if severe else 'none_detected'):
            return {}
    return {k:fact[k] for k in ('source_confirmed', 'confirmation_kind', 'source_ids',
            'good_side', 'bad_side', 'side', 'severity') if k in fact} | dict(human_review_identity=fact['identity'])


def qualify(*, freeze, inputs, intakes, scores, confirmations=()):
    require_freeze(freeze, inputs); _supported_contract(inputs['contract'])
    labels = []
    for intake in intakes:
        verify_identity(intake)
        if intake['freeze_identity'] != freeze['identity'] or intake['phase'] != 'validation':
            raise ValueError('intake/freeze/partition mismatch')
        labels.extend(intake['records'])
    raters = independent_reviewers(labels, freeze['raters'])
    pairs = [p for p in inputs['pairs']['pairs'] if p['group'] == 'validation']
    expected_counts = inputs['contract']['measurement']['human_pairs']
    if Counter(p['kind'] for p in pairs) != dict(natural=expected_counts['sealed_natural'], control=expected_counts['sealed_control']):
        raise ValueError('fixed 24-pair partition drift')
    pair_ids = {p['pair_id'] for p in pairs}
    by_label = {}
    forms = inputs['forms']; maps = inputs['maps']
    evidence_by_pair = {r['pair_id']:next(j['evidence'] for j in inputs['jobs'] if j['job_id']==r['job_id'])
                       for r in inputs['pair_score_map']}
    for r in labels:
        verify_identity(r)
        if r['group'] != 'validation' or r['pair_id'] not in pair_ids:
            raise ValueError('development or unknown label in qualification')
        if r['reviewer'] not in raters:
            continue  # explicitly derived copies may be archived, never count
        slots = [s for s,m in maps.items() if r['item_id'] in m]
        if len(slots) != 1: raise ValueError('label item must bind one frozen form')
        slot = slots[0]; meta = maps[slot][r['item_id']]
        item = next(i for i in forms[slot]['items'] if i['item_id']==r['item_id'])
        rebuilt = accept_label(r['raw_label'],item,meta,evidence_by_pair[r['pair_id']],
            reviewer=r['reviewer'],provenance=r['provenance'],annotations=r['annotations'],
            raw_source=r['raw_source'],reason_frame=r['reason_frame'])
        if rebuilt != r: raise ValueError('derived label content or A/B mapping has drifted')
        key = (r['pair_id'], r['reviewer'])
        if key in by_label:
            raise ValueError('duplicate reviewer/pair')
        by_label[key] = r
    if set(by_label) != {(p,r) for p in pair_ids for r in raters}:
        raise ValueError('fixed human pair coverage incomplete')
    jobs = {j['job_id']:j for j in inputs['jobs']}
    planned = {j['job_id'] for j in jobs.values() if j['group'] in ('development', 'validation', 'repeat')}
    attempts = {}
    for score in scores:
        verify_identity(score)
        jid = score['job_id']
        attempt_key = (jid, score['attempt'])
        if jid not in planned or attempt_key in attempts:
            raise ValueError('unexpected/duplicate scored job')
        j = jobs[jid]
        if (score['runtime_identity'] != freeze['runtime_identity']
                or score['protocol_identity'] != freeze['scorer_protocol_identity']
                or score['reply_identity'] != digest(j['reply'])
                or score['evidence_identity'] != digest(j['evidence'])
                or score['draw_id'] != j['draw_id'] or score['seed'] != j['seed']):
            raise ValueError('score bound to wrong reply/evidence/run/draw')
        if type(score['attempt']) is not int or score['attempt'] not in (0, 1):
            raise ValueError('P3 permits one fixed technical recovery')
        if score['measurement_status'] != 'measured_candidate' and (score['q'] is not None or score['m'] is not None):
            raise ValueError('technical/uncertain result cannot carry normal reward')
        utility(score)
        attempts[attempt_key] = score
    by_score = {}
    for jid in {k[0] for k in attempts}:
        first = attempts.get((jid, 0)); recovered = attempts.get((jid, 1))
        if first is None:
            raise ValueError('first-attempt accounting required before recovery')
        if recovered and (first['format_valid'] or jobs[jid]['group'] == 'repeat'):
            raise ValueError('no score selection or substitution of independent repeats')
        if recovered and recovered['request_id'] == first['request_id']:
            raise ValueError('recovery must have distinct attempt identity')
        by_score[jid] = recovered or first
    missing = sorted(planned - by_score.keys())
    if missing:
        return stamp(dict(status='PENDING_MEASUREMENTS', missing_jobs=missing,
            freeze_identity=freeze['identity'], automatic_training_authorization=False))
    refs = {(r['pair_id'],r['side']):r['job_id'] for r in inputs['pair_score_map']}
    facts = {f['pair_id']:f for f in confirmations}
    if len(facts) != len(confirmations) or not set(facts) <= pair_ids:
        raise ValueError('duplicate/foreign fact confirmation')
    natural, controls, unresolved = [], [], []
    for pair in pairs:
        human = {r:by_label[pair['pair_id'],r]['preference']['canonical'] for r in raters}
        if any(v is None for v in human.values()):
            unresolved.append(pair['pair_id'])
        row = dict(pair_id=pair['pair_id'], owner=pair['owner'], prefix_identity=pair['prefix_identity'],
                   human=human, scores=[by_score[refs[pair['pair_id'],s]] for s in (0,1)])
        fact = _fact_confirmation(facts.get(pair['pair_id']), pair, inputs, raters)
        if pair['kind'] == 'natural':
            if fact:
                row['severe_facts'] = [fact] if fact.get('severity') == 'severe' else []
            natural.append(row)
        else:
            # Do not copy expected good/bad labels out of the authored control.
            controls.append(row | fact | dict(control_type=pair['control_type']))
    repeats = []
    for job in jobs.values():
        if job['group'] != 'repeat':
            continue
        primary, repeat = by_score[job['primary_job_id']], by_score[job['job_id']]
        if (primary['reply_identity'], primary['evidence_identity']) != (repeat['reply_identity'],repeat['evidence_identity']):
            raise ValueError('repeat uses different input')
        if primary['request_id'] == repeat['request_id'] or primary['seed'] == repeat['seed']:
            raise ValueError('repeat must be a new independent draw')
        repeats.append(dict(primary=primary, repeat=repeat, cache_hit=repeat['cache_hit'],
            primary_draw=primary['draw_id'], repeat_draw=repeat['draw_id']))
    if unresolved:
        return stamp(dict(status='INSUFFICIENT_HUMAN_INFORMATION', unknown_preferences=unresolved,
            freeze_identity=freeze['identity'], automatic_training_authorization=False))
    primary = [s for j,s in by_score.items() if jobs[j]['group'] != 'repeat']
    first_primary = [attempts[j,0] for j in by_score if jobs[j]['group'] != 'repeat']
    technical = dict(planned=len(primary), first_valid=sum(s['format_valid'] for s in first_primary),
        processable_after_recovery=sum(s['measurement_status']=='measured_candidate' for s in primary))
    result = decide(natural=natural, controls=controls, repeats=repeats, technical=technical, raters=raters)
    return stamp(result | dict(freeze_identity=freeze['identity'], runtime_identity=freeze['runtime_identity'],
        rubric_identity=freeze['rubric_identity'], technical=technical,
        input_identity=digest(dict(intakes=intakes, scores=scores, confirmations=confirmations))))

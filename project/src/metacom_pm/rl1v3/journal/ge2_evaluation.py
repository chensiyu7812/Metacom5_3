"""GE2 evidence-bound review records, never a natural-language reward oracle.

The runtime must not import or receive this module's private task references.
Mechanical validation does not validate the semantics of a reviewer's judgement.
"""
from __future__ import annotations
import hashlib
import json

PROTOCOL='pmrl1-j-ge2-evaluation-v1'
NORMAL_ARMS=('STOP','FixedTop4','LLMOneShot','LLMToolAgent')
FACT_STATES={'unreviewed','supported','partial','omitted','unsupported','contradicted','uncertain'}
RULE_STATES={'unreviewed','pass','fail','uncertain','not_applicable'}
ROLES={'explicit_answer','correct_if_used','optional_background'}


def sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def contract():
    return dict(protocol=PROTOCOL,output_mode='unchanged_natural_language_G',formal_reward=None,
        tiers=['mechanical_identity_and_delivery','substantive_requested_fact','bounded_semantic_operation','natural_support_quality'],
        mechanical=['request/output/source/asof/hash binding','technical EOS vs length/failure/unexecuted','exact quote offset'],
        mechanical_does_not_imply=['substantive_answer','entailment','goal_completion','natural_support_quality'],
        substantive_answer_rule='A cited or supplied passage is not an answer by itself: review the proposition answering the actual question, actor, report/event time, stage, polarity, uncertainty and relevant alternatives.',
        fact_states=sorted(FACT_STATES),rule_states=sorted(RULE_STATES),requirement_roles=sorted(ROLES),
        natural_no_mandatory_recall=True,natural_empty_atom_list_is_not_success=True,
        missing_output_semantics=None,unresolved_semantics='unknown, never zero or equivalent',
        structured_branch=dict(reusable_evaluator='structured_learning.evaluate',
            scorer_sha256='a83cc1b5960cb419bc893768f190da0664630cdc18c3ee4e9e63ae0a9374d87d',
            scope='only original finite JSON fields, explicit source reference, exact original contract',
            can_supply_bounded_development_supervision=True,GE2_natural_output_scoring=False,
            natural_reward_qualification=False,training_authorized=False),
        nli=dict(role='optional existing auxiliary source/claim diagnostic only',
            new_calls=0,automatic_pass=False,automatic_fail=False,judge_vote=False),
        blind_review=dict(selected_task_rule='first fact and first natural_support in frozen task order',
            arms=list(NORMAL_ARMS),max_outputs=8,minimum_complete_groups=0,
            no_replacement_for_missing=True,DirectEvidence_excluded=True,
            reviewer_identity='unassigned; actual provenance recorded before review',
            qualification='limited audit; assistant blind reading is not independent human qualification',
            historical_human_pending=5,old_human_answers='development only, no new independent labels'),
        direct_failure_review='additional development explanation only; not substituted into fixed blind eight',
        interpretation='program checks identities and entered observations, not their semantic truth')


def select_blind(task_order,channels):
    chosen=[]
    for channel in ('fact','natural_support'):
        task=next((t for t in task_order if channels[t]==channel),None)
        if task is None:raise ValueError('fixed blind stratum unavailable; no outcome-based replacement')
        chosen.append(task)
    return [(task,arm) for task in chosen for arm in NORMAL_ARMS]


def normalized_atoms(evaluation,channel):
    atoms=[];seen=set()
    for atom in evaluation.get('required_atoms',[]):
        if atom['id'] in seen:raise ValueError('duplicate atom')
        seen.add(atom['id'])
        role=atom.get('requirement_role','optional_background' if channel=='natural_support' else 'explicit_answer')
        if role not in ROLES:raise ValueError('requirement role')
        if channel=='natural_support' and role=='explicit_answer':
            raise ValueError('natural tasks cannot inherit constructed mandatory recall')
        atoms.append(dict(atom_id=atom['id'],requirement_role=role,status='unreviewed',
            answers_requested_proposition=None,bounded_unknown=False,
            reference_assumption_disposition='unresolved' if atom.get('reference_status')=='calendar_derived' else 'not_applicable',
            output_spans=[],source_evidence_ids=[],rationale=''))
    return atoms


def review_template(*,case_id,task,evaluation,channel,source_packet_sha256):
    return dict(protocol=PROTOCOL,case_id=case_id,task_sha256=sha(task),evaluation_sha256=sha(evaluation),
        source_packet_sha256=source_packet_sha256,channel=channel,
        actual_output_sha256=None,output_text=None,technical_status='not_run',
        reviewer=dict(identity=None,kind='unassigned',blinded_to_arm=True,prior_task_authoring=None,
            prior_output_exposure=None,identity_evidence_sha256=None),
        facts=normalized_atoms(evaluation,channel),
        requested_support=dict(status='not_applicable' if channel=='fact' else 'unreviewed',output_spans=[],rationale=''),
        constraints=[dict(id=c['id'],status='unreviewed',output_spans=[],rationale='') for c in evaluation.get('constraints',[])],
        additional_claims=[],reference_disputes=[],
        constraints_reviewed=False,additional_claims_reviewed=False,reference_disputes_reviewed=False,
        natural_quality=dict(status='not_applicable' if channel=='fact' else 'unreviewed',rationale='',
            standardized_score=None,clinical_or_longitudinal_effect=None),
        development_interval=None,formal_reward=None,semantic_qualification=False)


def validate_spans(spans,text):
    for span in spans:
        if set(span)!={'start','end','text'} or type(span['start']) is not int or type(span['end']) is not int:
            raise ValueError('exact span schema')
        if not 0<=span['start']<span['end']<=len(text) or text[span['start']:span['end']]!=span['text']:
            raise ValueError('output span mismatch')


def validate_review(row,*,task,evaluation,source_packet_sha256,actual_output=None):
    if (row.get('protocol')!=PROTOCOL or row['task_sha256']!=sha(task) or row['evaluation_sha256']!=sha(evaluation)
            or row['source_packet_sha256']!=source_packet_sha256):raise ValueError('review identity binding')
    if row['formal_reward'] is not None or row['semantic_qualification'] is not False:raise ValueError('reward/qualification not authorized')
    expected_channel=evaluation.get('channel')
    if expected_channel=='natural':expected_channel='natural_support'
    if expected_channel not in ('fact','natural_support','joint') or row['channel']!=expected_channel:
        raise ValueError('original evaluation channel changed')
    quality=row['natural_quality']
    if quality['standardized_score'] is not None or quality['clinical_or_longitudinal_effect'] is not None:
        raise ValueError('no unmeasured general quality/clinical effect')
    if row['channel']=='fact' and quality['status']!='not_applicable':raise ValueError('fact natural quality scope')
    expected=normalized_atoms(evaluation,row['channel'])
    if [(a['atom_id'],a['requirement_role']) for a in row['facts']]!=[(a['atom_id'],a['requirement_role']) for a in expected]:
        raise ValueError('original atom requirement inventory changed')
    if [c['id'] for c in row['constraints']]!=[c['id'] for c in evaluation.get('constraints',[])]:
        raise ValueError('original visible constraint inventory changed')
    if actual_output is None:
        if row['technical_status'] not in ('not_run','unexecuted','technical_incomplete'):
            raise ValueError('missing output technical status')
        if row['actual_output_sha256'] is not None or row['output_text'] is not None or row['development_interval'] is not None:
            raise ValueError('unrun outcome')
        if any(a['status']!='unreviewed' for a in row['facts']):raise ValueError('unrun semantic judgement')
        if row['requested_support']['status'] not in ('unreviewed','not_applicable'):raise ValueError('unrun support judgement')
        if row['natural_quality']['status'] not in ('unreviewed','not_applicable'):raise ValueError('unrun quality judgement')
        if any(c['status']!='unreviewed' for c in row['constraints']) or row['additional_claims'] or row['reference_disputes']:
            raise ValueError('unrun additional judgement')
        if any(row[k] for k in ('constraints_reviewed','additional_claims_reviewed','reference_disputes_reviewed')):
            raise ValueError('unrun completed review')
        return dict(status='UNRUN_TEMPLATE_VALID',formal_reward=None)
    if row['actual_output_sha256']!=sha(actual_output) or row['output_text']!=actual_output['text']:
        raise ValueError('complete worker output/text binding')
    if row['technical_status']!='eos':
        if row['development_interval'] is not None:raise ValueError('technical missing is not semantic failure')
        return dict(status='TECHNICAL_NONCOMPLETION',development_interval=None,formal_reward=None)
    if actual_output.get('finish_reason')!='eos':raise ValueError('non-EOS output cannot have semantic completion')
    reviewer=row['reviewer']
    if not reviewer['identity'] or reviewer['kind'] not in ('assistant_development','human_development','human_independent'):
        raise ValueError('actual reviewer identity required')
    if reviewer['kind']=='human_independent' and (not reviewer['identity_evidence_sha256']
            or reviewer['prior_task_authoring'] is not False or reviewer['prior_output_exposure'] is not False):
        raise ValueError('independence cannot be self-certified from a label')
    if not all(row[x] is True for x in ('constraints_reviewed','additional_claims_reviewed','reference_disputes_reviewed')):
        raise ValueError('required response and dispute review incomplete')
    text=actual_output['text'];mandatory=[]
    for atom in row['facts']:
        if atom['status'] not in FACT_STATES or atom['status']=='unreviewed':raise ValueError('fact status')
        if not atom['rationale'].strip():raise ValueError('substantive observation explanation')
        validate_spans(atom['output_spans'],text)
        if atom['status'] in ('partial','unsupported','contradicted') and not atom['output_spans']:
            raise ValueError('located asserted or partial proposition required')
        original=next(a for a in evaluation.get('required_atoms',[]) if a['id']==atom['atom_id'])
        groups=original.get('evidence_groups',original.get('sufficient_groups',[]))
        evidence_ids={g.get('id',atom['atom_id']+'/g'+str(i)) if isinstance(g,dict) else atom['atom_id']+'/g'+str(i)
                      for i,g in enumerate(groups,1)}
        if not set(atom['source_evidence_ids'])<=evidence_ids:raise ValueError('invented reference evidence identifier')
        if atom['status']=='supported' and atom['requirement_role']=='explicit_answer':
            absence=original.get('reference_status')=='absence_supported' and atom['bounded_unknown'] is True
            if atom['answers_requested_proposition'] is not True or not atom['output_spans'] or (not atom['source_evidence_ids'] and not absence):
                raise ValueError('citation or source presence is not a substantive answer')
        if original.get('reference_status')=='calendar_derived':
            if atom['reference_assumption_disposition'] not in ('accepted_development_assumption','unresolved'):
                raise ValueError('calendar assumption disposition')
            if atom['reference_assumption_disposition']=='unresolved':mandatory.append('uncertain')
        elif atom['reference_assumption_disposition']!='not_applicable':raise ValueError('undeclared reference assumption')
        if atom['requirement_role']=='explicit_answer' or atom['status'] in ('unsupported','contradicted'):
            mandatory.append(atom['status'])
        elif atom['status']=='uncertain' and atom['output_spans']:mandatory.append('uncertain')
    for collection in ('constraints','additional_claims','reference_disputes'):
        ids=set()
        for item in row[collection]:
            if not item.get('id') or item['id'] in ids:raise ValueError('review item identity')
            ids.add(item['id'])
            if item['status'] not in ('pass','fail','uncertain') or not item.get('rationale','').strip():raise ValueError('item judgement')
            if collection=='additional_claims' and not item.get('output_spans'):raise ValueError('additional assertion needs located output')
            validate_spans(item.get('output_spans',[]),text);mandatory.append(item['status'])
    support=row['requested_support']
    if row['channel']=='fact':
        if support['status']!='not_applicable':raise ValueError('fact support scope')
    else:
        if support['status'] not in ('pass','fail','uncertain') or not support['rationale'].strip():raise ValueError('support judgement missing')
        validate_spans(support['output_spans'],text);mandatory.append(support['status'])
        if support['status']=='pass' and not support['output_spans']:raise ValueError('support operation evidence required')
        if row['natural_quality']['status'] not in ('pass','fail','uncertain') or not row['natural_quality']['rationale'].strip():
            raise ValueError('bounded natural quality observation missing')
        if row['natural_quality']['standardized_score'] is not None or row['natural_quality']['clinical_or_longitudinal_effect'] is not None:
            raise ValueError('no unmeasured general quality/clinical effect')
        mandatory.append(row['natural_quality']['status'])
    fail=any(s in ('partial','omitted','unsupported','contradicted','fail') for s in mandatory)
    uncertain='uncertain' in mandatory
    expected_interval=[0,0] if fail else [0,1] if uncertain else [1,1]
    if row['development_interval']!=expected_interval:raise ValueError('interval differs from explicit entered observations')
    return dict(status='DEVELOPMENT_RECORD_MECHANICALLY_VALID',development_interval=expected_interval,
        semantic_qualification=False,formal_reward=None)

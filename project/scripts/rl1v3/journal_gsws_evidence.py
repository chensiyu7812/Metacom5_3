#!/usr/bin/env python3
"""Evaluation-only coordinate audit. Never imported by the normal runtime."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.ge2_sources import rows,write_once
from metacom_pm.rl1v3.journal.ge2_source_coordinate_audit import strict_supply,occurrences,object_sha

FOCI={
 'Q01': ['Resolve source-scoped user versus named person without assuming names establish identity.',
         'Distinguish planned retreat from attendance; upcoming weekend from report date.',
         'Inherited exact-calendar atom is disputed: retain original reference and mark uncertain unless source/calendar relation is independently established.'],
 'Q02': ['Current user says another person offered help; do not turn offer into completed assistance.',
         'Respond to current feeling of relief; no compulsory history recital or diagnosis.'],
 'Q03': ['Current quotation establishes a reported decision, not its later implementation.',
         'Find the requested family relationship only if supplied; otherwise explicitly leave it unresolved.',
         'Provide the requested kind sentence without prescribing a career choice.'],
 'Q04': ['A booked ticket is an arrangement, not a completed trip or positive outcome.',
         'Current quotation is sufficient for stated timing, without invented calendar date.',
         'Include the requested reassuring draft; no guarantee of clarity or relief.'],
 'Q05': ['Separate user, manager and named third party.',
         'Answer the requested identity and role when actually supported; no invented identity from a question.'],
 'Q06': ['A question presupposition does not establish that activities happened.',
         'No retrieved supporting report permits a scoped unknown, not a universal assertion of absence.',
         'Inherited archive-absence reference remains evaluation-only; legitimate unknown and full answerability are separate.'],
 'Q07': ['Current desire to talk does not explicitly request discussion of retrieved relationship history.',
         'A welcoming response can succeed with no historical recital; old relationship status is not automatically current.'],
 'Q08': ['Speaker greeting/name is not the assistant identity.',
         'Mixed feelings invite support without inferring an unconfirmed hidden goal.',
         'Historical criticism or praise must keep actor, time and applicability if used.'],
}


def audit(bundle,output):
    b=Path(bundle);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    tasks={r['task_id']:r for r in rows(b/'TASKS.runtime.jsonl')}
    es={r['task_id']:r for r in rows(b/'EVALSPEC.private.jsonl')}
    details=[];summary=[];contracts=[]
    for state in rows(b/'CPU_STATES_PRIVATE.jsonl'):
        tid=state['task_id'];e=es[tid];task=tasks[tid];alias=e['goal_alias']
        review=dict(task_sha256=object_sha(task),reviewer_identity='assistant_development_pre_generation',reference_occurrences=[])
        for a in e['required_atoms']:
            for group in a.get('sufficient_groups',[]):
                for ref in group:
                    for hit in occurrences(ref,task):
                        # Explicit bounded quotations are relevant to what these tasks ask.
                        kind='explicit_recollection_quote' if alias=='Q03' else 'quoted_note' if alias=='Q04' else 'other_or_uncertain'
                        review['reference_occurrences'].append(dict(reference_sha256=object_sha(ref),occurrence=hit,
                            classification=kind,admissible_for_original_task='yes_bounded' if alias in ('Q03','Q04') else 'uncertain',
                            rationale='The task requests the content of this visible quotation; this is not proof of execution/current validity or an independently verified event.'))
        # Same reference may occur in multiple equivalent sufficient groups.
        review['reference_occurrences']=list({object_sha(x):x for x in review['reference_occurrences']}.values())
        intervals=state['source_receipt']['read_intervals']
        supply=strict_supply(e['required_atoms'],state['source_records'],intervals,task,review)
        obs=state['observation'];verified=0
        byid={r['record_id']:r for r in state['source_records']}
        for item in obs['evidence']:
            if item['kind']=='current_visible':
                turn=task['turns'][item['turn_index']];assert (item['speaker'],item['text'])==(turn['role'],turn['text'])
            else:
                rec=byid[item['record_id']];assert object_sha256(rec)==item['record_sha256']
                ref=next(r for r in rec['source_refs'] if r['turn_index']==item['turn_index'])
                assert item['text']==ref['exact_quote'] and item['speaker']==ref['speaker']
                assert item['start_char']==0 and item['end_char']==len(item['text'])
                assert item['report_time']==rec['reported_at']['date']
                assert any(lo<=item['turn_index']<=hi for lo,hi in intervals[item['record_id']])
            verified+=1
        details.append(dict(goal_alias=alias,stage=state['stage'],current_review=review,supply=supply,verified_turns=verified))
        summary.append(dict(goal=alias,stage=state['stage'],channel=e['channel'],verified_turns=verified,
            required_atoms=supply['required_slots'],covered=supply['covered_slots'],unknown=supply['unknown_slots'],
            uncovered=supply['uncovered_slots'],task_success=None))
        contracts.append(dict(task_id=tid,goal_alias=alias,stage=state['stage'],
            task_sha256=object_sha256(task),observation_sha256=obs['snapshot_sha256'],
            semantic_checks=FOCI[alias],mechanical_checks=['same-source coordinates','actual provenance','strict JSON and enum',
                 'no future/foreign evidence','version parent','call and token caps','EOS vs length'],
            semantic_checks_are_not_regex_rewards=True,
            labels=['pass','fail','unknown','equivalent','not_applicable','technical_failure'],
            review_scope='assistant development reference; no independent human qualification',
            fact_goal=e['channel'] in ('fact','joint'),support_goal=e['channel'] in ('natural','joint'),
            historical_facts_must_be_recited=e['channel'] in ('fact','joint'),
            evidence_coverage_not_success=True,natural_support_reward_qualified=False,formal_reward=None))
    write_once(out/'COORDINATES_PRIVATE.json',details)
    write_once(out/'STATE_EVAL_CONTRACT_PRIVATE.jsonl',contracts,jsonl=True)
    write_once(out/'COORDINATES_PUBLIC.json',summary)
    print(json.dumps(dict(states=len(summary),verified_visible_turns=sum(x['verified_turns'] for x in summary),model_calls=0,formal_reward=None)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--output',required=True);a=p.parse_args();audit(a.bundle,a.output)

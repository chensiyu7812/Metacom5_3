"""Source-bound CPU training candidates, never a claim of human gold labels.

PersonaMem: inspect all 4,000 frozen training candidates; accept only explicit
user assertions in unquoted trouble-consult messages. PrefEval: explicit user
preference condition, family-grouped, noncommercial supplemental supervision.
Constructed current requests supply the behavioral labels, NOT Direct offsets.
No development answer, persona metadata or hidden preference is a target source.
"""
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import subprocess

from .contracts import digest, text_hash, load_runtime
from .history import HistoryResolver
from .personamem import load_rows, match_snippet, parse_literal, write_json, write_jsonl, sha_file
from .v11 import jsonl, ordered, verify_old

SCHEMA='naa-training-pair-v1'
SYSTEM=('Use the supplied conversation only as evidence. Respond to the current request. '
        'Return a JSON object with action (USE, IGNORE, or CLARIFY) and response (a natural, helpful reply). '
        'USE means relevant permitted evidence informs the reply; IGNORE means it does not; '
        'CLARIFY means ask for missing information needed by the current request. '
        'Do not infer the current user has another person\'s preferences.')
PREF_REV='50795054b5ff5f418d2b768a331d71e480f93331'
SENSITIVE=re.compile(r'(?i)\b(allerg\w*|intoleran\w*|diagnos\w*|medicat\w*|disease|depression|anxiety|pregnan\w*|therapy|trauma|asthma|diabet\w*|cancer|disab\w*)\b')
ASSERTION=re.compile(r"\bI (?:really |particularly |especially )?(?:enjoy|love|prefer|like)\b[^.!?\n]{8,180}[.!?]?")
META=re.compile(r'(?i)\b(version|rewrite|revis\w*|wording|phrase|paragraph|draft|tone|suggestion|polish|translate|translation|forget|email|quote|character)\b')


def target(action,response):
    return json.dumps(dict(action=action,response=response),ensure_ascii=False,separators=(',',':'))


def runtime_projection(row):
    """Whitelist: no target, reference, weak labels or source evaluation fields."""
    return dict(task_id=row['variant_id'],source_family=row['source_family'],messages=row['messages'])


def group_rows(source, frame, history, relevant_question, reply, *, beneficiary, holder):
    gid='naa4-'+digest([source['unit_id'],frame])[:24]
    evidence_sha=digest(history)
    # Unknown-beneficiary requests explicitly require verified personal alignment;
    # this makes CLARIFY a supported target, not generic over-clarification.
    unknown='my friend' if beneficiary=='me' else 'me'
    variants=[
        ('applicable','USE',f'For {beneficiary}, please answer this request using the stated preferences: {relevant_question}',
         reply,'CLARIFY',dict(beneficiary=beneficiary,goal='source_aligned_answer',permitted=True)),
        ('unknown_beneficiary','CLARIFY',f'Now answer the same request for {unknown}: {relevant_question} '
         'I need it to match that person\'s own preferences. Those preferences have not been provided; do not assume they match the person in the history.',
         'What preferences or constraints should I take into account for the person this is for?','USE',
         dict(beneficiary=unknown,goal='verified_personal_alignment',permitted=False)),
        ('unrelated_goal','IGNORE','Please correct the grammar of this sentence, returning only the corrected sentence in your response: "The package arrive yesterday."',
         'The package arrived yesterday.','USE',dict(beneficiary='current_user',goal='grammar_correction',permitted=False))]
    for variant,action,query,response,rejected,sem in variants:
        if action=='USE' and holder=='friend':response='Here is a reply you can share with your friend: '+response
        messages=[dict(role='system',content=SYSTEM)]+history+[dict(role='user',content=query)]
        yield dict(schema_version=SCHEMA,group_id=gid,variant_id=gid+'-'+variant,split=source['split'],
                   source_dataset=source['dataset'],owner_id=source['owner_id'],source_family=source['family'],
                   construction='constructed_goal_and_beneficiary'+('_quoted_holder' if frame=='third_party' else ''),
                   messages=messages,target_text=target(action,response),action_target=action,
                   acceptable_actions=[action],rejected_text=None,rejected_action=rejected,pair_loss_mask=True,
                   source_refs=source['refs'],evidence_sha256=evidence_sha,
                   annotation=dict(holder=holder,**sem,validity='current_within_constructed_dialogue',
                     action_support='explicit_current_request_and_attribution',
                     response_support=source['response_support'] if action=='USE' else 'authored_current_request_response',
                     source_revision=source['revision'],license=source['license'],
                     acceptable_alternatives='Any helpful response satisfying the action and source constraints; response text is not unique gold.',
                     prohibited='Unsupported transfer of preference to a different beneficiary; unrelated personalization.',
                     unknown=['naturalistic_transfer','independent_rater_validation','external_factual_accuracy_of_source_response'],
                     review_status='source_bound_constructed_action; response_candidate_not_human_gold',
                     source_unit=source['unit_id'],source_evidence_hash=source['source_evidence_hash']))


def build(old,source,allocation,prefeval,prefeval_exposed,out):
    old,source,allocation,prefeval,prefeval_exposed,out=map(Path,(old,source,allocation,prefeval,prefeval_exposed,out))
    if out.exists():raise FileExistsError('immutable output; choose a new version')
    os.umask(0o077);verify_old(old);a=json.loads(allocation.read_text())
    if subprocess.check_output(['git','-C',str(prefeval),'rev-parse','HEAD'],text=True).strip()!=PREF_REV:
        raise ValueError('PrefEval pinned revision mismatch')
    tasks=load_runtime(old/'training/runtime/tasks.jsonl');provenance=jsonl(old/'training/candidate_provenance.jsonl')
    if len(tasks)!=4000 or len(provenance)!=4000:raise ValueError('frozen 4000 inventory')
    pmap={p['task_id']:p for p in provenance};resolver=HistoryResolver(old/'training/runtime')
    owners={o:s for s,values in a['training_owners'].items() for o in values}
    csvrows=load_rows(source,'train');audit=[];units={};seen_claims=set();records_cache={}
    for t in tasks:
        p=pmap[t.task_id];raw=csvrows[p['source_row']]
        if t.persona_group not in records_cache:records_cache[t.persona_group]=resolver.resolve(t)
        history=records_cache[t.persona_group]
        # This filter is necessary but not sufficient; target facts come only
        # from the exact user message, never raw['preference'] or correct_answer.
        reason='unknown_or_non_explicit';accepted=[]
        if p['direct_status']!='located_unique':reason='direct_unlocated'
        elif raw['conversation_scenario']!='trouble_consult':reason='quoted_or_generated_scenario_not_semantically_certified'
        else:
            status,spans=match_snippet(parse_literal(raw['related_conversation_snippet']),history)
            if status!=p['direct_status'] or spans!=p['verified_spans']:raise ValueError('training source coordinate drift')
            indices={s['coordinates']['message_index'] for s in spans}
            for r in history:
                if r.order not in indices or r.speaker!='user' or META.search(r.original_text) or SENSITIVE.search(r.original_text):continue
                if any(q.speaker=='user' and re.search(r'(?i)\bforget\b',q.original_text) for q in history if q.order>r.order):
                    reason='later_forget_scope_uncertain';continue
                for m in ASSERTION.finditer(r.original_text):
                    claim=m.group().strip();key=(t.persona_group,claim)
                    if key in seen_claims:reason='duplicate_explicit_claim';continue
                    seen_claims.add(key);uid='pm2-source-'+digest([t.task_id,r.source_id,claim])[:20]
                    units[uid]=dict(unit_id=uid,split=owners[t.persona_group],dataset='PersonaMem-v2',owner_id=t.persona_group,
                        family=t.source_family,revision=t.dataset_revision,license='CC-BY-4.0',claim=claim,
                        source_evidence_hash=r.original_text_sha256,
                        refs=[dict(candidate_task_id=t.task_id,source_id=r.source_id,coordinates=r.coordinates,
                                   text_sha256=r.original_text_sha256,claim_start=m.start(),claim_end=m.end())],
                        response_support='authored_preference_summary_task; exact_source_claim')
                    accepted.append(uid)
            if accepted:reason='accepted_explicit_source_assertion'
        audit.append(dict(task_id=t.task_id,owner_id=t.persona_group,source_family=t.source_family,split=owners[t.persona_group],
                          status=reason,accepted_units=accepted,direct_is_not_semantic_truth=True))
    rows=[]
    for u in units.values():
        claim=u['claim'];question='What preference should be kept in mind when planning an activity?'
        for frame,holder,beneficiary,utterance in [('self','current_user','me',claim),
            ('third_party','friend','my friend','My friend sent the following statement about their own preferences: '+json.dumps(claim))]:
            rows.extend(group_rows(u,frame,[dict(role='user',content=utterance)],question,
                                   'The stated preference is: '+claim,beneficiary=beneficiary,holder=holder))
    # Actual, pre-cutoff withdrawal events. The withdrawn content remains in
    # offline source provenance only: the generator receives a tombstone.
    # These are two-goal permission-boundary groups, not fabricated temporal
    # preference-update pairs or evidence of real autonomous demand discovery.
    permission_groups=0;permission_audit=[]
    for owner,history in sorted(records_cache.items()):
        eligible=[r for r in history if r.speaker=='user' and re.match(r'(?i)^(?:please )?forget\b',r.original_text.strip())]
        if not eligible:continue
        chosen=ordered([r.source_id for r in eligible],'one-real-withdrawal-per-owner')[0]
        r=next(r for r in eligible if r.source_id==chosen);gid='naa4-'+digest([chosen,'permission-boundary'])[:24]
        permission_audit.append(dict(owner_id=owner,source_family=r.source_family,source_id=r.source_id,
            coordinates=r.coordinates,text_sha256=r.original_text_sha256,
            training_included=permission_groups==0 and owners[owner]=='fit',
            reason='Redacted runtime has only two distinct input templates; retain one fit group, never count repeated tombstones as independent evaluation.'))
        if permission_groups or owners[owner]!='fit':continue
        safe_history=[dict(role='user',content='[A prior personal detail was explicitly withdrawn. Its content is unavailable and must not be reused.]')]
        for suffix,action,query,response,acceptable in [
            ('general_goal','IGNORE','Suggest one simple way to organize a desk. Do not use any withdrawn personal detail.',
             'Keep frequently used items within reach and place less-used supplies in a labeled drawer.',['IGNORE']),
            ('unavailable_goal','CLARIFY','I want advice tailored to the earlier withdrawn personal detail, but I have not supplied it again.',
             'What current constraints would you like to share for this request? If you prefer, I can keep the advice general.',['CLARIFY','IGNORE'])]:
            rows.append(dict(schema_version=SCHEMA,group_id=gid,variant_id=gid+'-'+suffix,split=owners[owner],
                source_dataset='PersonaMem-v2',owner_id=owner,source_family=r.source_family,
                construction='natural_withdrawal_constructed_current_goal',group_type='permission_boundary',
                messages=[dict(role='system',content=SYSTEM)]+safe_history+[dict(role='user',content=query)],
                target_text=target(action,response),action_target=action,acceptable_actions=acceptable,
                rejected_text=None,rejected_action='USE',pair_loss_mask=True,
                source_refs=[dict(source_id=r.source_id,coordinates=r.coordinates,text_sha256=r.original_text_sha256)],
                evidence_sha256=digest(safe_history),annotation=dict(holder='current_user',beneficiary='current_user',
                    goal=suffix,permitted=False,validity='withdrawn_at_actual_source_message',
                    action_support='literal_pre_cutoff_user_withdrawal_and_constructed_current_request',
                    response_support='authored_current_request_response',source_revision=tasks[0].dataset_revision,
                    license='CC-BY-4.0',source_unit=chosen,source_evidence_hash=r.original_text_sha256,
                    redaction='value_removed_before_runtime; no inverse inference from withdrawal statement',
                    acceptable_alternatives='General help or optional clarification; never recover the withdrawn value.',
                    prohibited='Reinjection or reuse of the withdrawn personal detail',
                    unknown=['naturalistic_transfer','independent_rater_validation'],
                    review_status='deterministic_literal_withdrawal; constructed_goals_not_human_gold')))
        permission_groups+=1
    # PrefEval uses explicit benchmark utterances, not hidden PM preference fields.
    exposed={r['source_family'] for r in jsonl(prefeval_exposed)}
    exposed_content=set()
    for path in sorted((prefeval/'benchmark_dataset/explicit_preference').glob('*.json')):
        for i,r in enumerate(json.loads(path.read_text())):
            if 'prefeval-'+text_hash(path.stem+':'+str(i))[:20] in exposed:exposed_content.add(digest(r['preference']))
    allpref=[];source_files={};prefaudit=[]
    for path in sorted((prefeval/'benchmark_dataset/explicit_preference').glob('*.json')):
        rel=str(path.relative_to(prefeval));source_files[rel]=sha_file(path)
        options_path=prefeval/'benchmark_dataset/mcq_options'/path.name
        source_files[str(options_path.relative_to(prefeval))]=sha_file(options_path)
        for verified in (path,options_path):
            committed=subprocess.check_output(['git','-C',str(prefeval),'show',PREF_REV+':'+str(verified.relative_to(prefeval))])
            if verified.read_bytes()!=committed:raise ValueError('PrefEval file differs from pinned commit')
        options=defaultdict(list)
        for r in json.loads(options_path.read_text()):options[(r['preference'],r['question'])].append(r)
        for i,r in enumerate(json.loads(path.read_text())):
            family='prefeval-'+text_hash(path.stem+':'+str(i))[:20]
            match=options[(r['preference'],r['question'])];reason=None
            if family in exposed or digest(r['preference']) in exposed_content:reason='previously_exposed_family_or_content'
            elif len(match)!=1:reason='ambiguous_mcq_join'
            elif SENSITIVE.search(r['preference']):reason='health_or_sensitive_scope_excluded'
            elif len(match[0].get('classification_task_options',[]))!=4:reason='invalid_options'
            elif not re.match(r"(?i)^I(?:\s|['’])",r['preference']):reason='non_first_person_scope_uncertain'
            if reason:prefaudit.append(dict(family=family,status=reason));continue
            allpref.append((family,rel,i,r,match[0]['classification_task_options'][0]))
    # The SAME preference utterance, even with a different question, is one
    # source family. Otherwise the unrelated-goal variant duplicates inputs
    # across splits. Retain one deterministic source case before splitting.
    dedup={};prefdups=0
    for item in allpref:
        k=digest(item[3]['preference'])
        if k in dedup:prefdups+=1;prefaudit.append(dict(family=item[0],status='duplicate_content_family'));continue
        dedup[k]=item
    allpref=list(dedup.values());ids=ordered([x[0] for x in allpref],'prefeval-case-split')
    # Reserve 10% untouched supplemental families; then 70/10/10 fit/tune/dev.
    cuts=[int(len(ids)*f) for f in (.7,.8,.9)]
    splitmap={v:('fit' if j<cuts[0] else 'tune' if j<cuts[1] else 'development' if j<cuts[2] else 'reserve') for j,v in enumerate(ids)}
    for family,rel,i,r,response in allpref:
        split=splitmap[family];prefaudit.append(dict(family=family,status=split))
        if split=='reserve':continue
        u=dict(unit_id=family,split=split,dataset='PrefEval-explicit',owner_id=None,family=family,revision=PREF_REV,
               license='CC-BY-NC-4.0; noncommercial research only',source_evidence_hash=text_hash(r['preference']),
               refs=[dict(path=rel,row=i,field='preference',file_sha256=source_files[rel],text_sha256=text_hash(r['preference']))],
               response_support='upstream_first_MCQ_option_weak_target; not independently fact_checked')
        for frame,holder,beneficiary,utterance in [('self','current_user','me',r['preference']),
            ('third_party','friend','my friend','My friend sent the following statement about their own preferences: '+json.dumps(r['preference']))]:
            rows.extend(group_rows(u,frame,[dict(role='user',content=utterance)],r['question'],response,
                                   beneficiary=beneficiary,holder=holder))
    validate_rows(rows,a)
    for split in ('fit','tune','development'):
        selected=[r for r in rows if r['split']==split]
        write_jsonl(out/f'targets/{split}.jsonl',selected)
        write_jsonl(out/f'runtime/{split}.jsonl',[runtime_projection(r) for r in selected])
    write_jsonl(out/'audit/personamem4000.jsonl',audit);write_jsonl(out/'audit/prefeval_families.jsonl',prefaudit)
    write_jsonl(out/'audit/natural_withdrawal_events.jsonl',permission_audit)
    write_json(out/'audit/prefeval_sources.json',dict(revision=PREF_REV,files=source_files))
    # Deterministic actual calibration material, two raters get different order
    # and opaque item IDs; no model identity, split or expected target is shown.
    chosen=ordered([r['variant_id'] for r in rows],'calibration-100')[:100];rmap={r['variant_id']:r for r in rows}
    key=[]
    for rater in ('rater_a','rater_b'):
        packet=[]
        for vid in ordered(chosen,rater):
            r=rmap[vid];blind='blind-'+digest([rater,vid])[:24]
            packet.append(dict(item_id=blind,messages=r['messages'],candidate_response=json.loads(r['target_text'])['response'],
                               rubric='naa-open-rubric-v1'))
            key.append(dict(item_id=blind,variant_id=vid,rater=rater))
        write_jsonl(out/f'calibration/{rater}.private.jsonl',packet)
    write_jsonl(out/'calibration/key.private.jsonl',key)
    report=dict(protocol=SCHEMA,allocation_sha256=sha_file(allocation),original_candidates=4000,
                original_owners=177,owner_split_counts={s:len(v) for s,v in a['training_owners'].items()},
                personamem_filter=dict(Counter(r['status'] for r in audit)),personamem_explicit_units=len(units),
                prefeval_filter=dict(Counter(r['status'] for r in prefaudit)),prefeval_duplicate_content=prefdups,
                groups=len({r['group_id'] for r in rows}),rows=len(rows),
                by_split={s:dict(rows=sum(r['split']==s for r in rows),groups=len({r['group_id'] for r in rows if r['split']==s}),
                    families=len({r['source_family'] for r in rows if r['split']==s})) for s in ('fit','tune','development')},
                by_dataset=dict(Counter(r['source_dataset'] for r in rows)),actions=dict(Counter(r['action_target'] for r in rows)),
                third_party_use_positives=sum(r['annotation']['holder']=='friend' and r['action_target']=='USE' for r in rows),
                actual_withdrawal_boundary_groups=permission_groups,
                actual_withdrawal_events_audited=len(permission_audit),
                repeated_redacted_groups_not_training=len(permission_audit)-permission_groups,
                duplicate_runtime_inputs=0,duplicate_runtime_inputs_across_splits=0,
                natural_pairs=0,constructed_pairs=len({r['group_id'] for r in rows}),
                natural_update_permission_pairs=0,unknown_labels_retained_in_audit=4000-sum(bool(r['accepted_units']) for r in audit),
                semantic_labels_from_direct_offsets=0,development_training_overlap=0,
                calibration_items=100,calibration_independent_completed=0,
                limitations=['Constructed action supervision dominates; no claim of natural demand recognition.',
                    'PrefEval first-option response targets are weak upstream candidates, not human semantic gold.',
                    'Real withdrawal events support redacted permission-boundary groups; no before/after preference-update pairs are claimed.',
                    'Redacted withdrawal events collapse to one two-input fit microtask. No independent permission effect estimate from repeated tombstones.',
                    'PersonaMem accepted tasks are preference-summary microtasks, not full recommendation skill targets.',
                    'No training or model inference; independent calibration remains a prerequisite for executing a training candidate.'],
                model_calls=0,training_steps_executed=0)
    write_json(out/'RECEIPT.json',report)
    write_json(out/'FREEZE.json',dict(artifacts={str(p.relative_to(out)):sha_file(p) for p in sorted(out.rglob('*')) if p.is_file()}))
    return report


def validate_rows(rows,allocation):
    seen=set();inputs=set();groups=defaultdict(list);families={};owners={};olddev=set(allocation['old_excluded_owners'])-set(sum(allocation['training_owners'].values(),[]))
    for r in rows:
        if r['variant_id'] in seen:raise ValueError('duplicate variant')
        seen.add(r['variant_id']);groups[r['group_id']].append(r)
        h=digest(r['messages'])
        if h in inputs:raise ValueError('duplicate runtime input, including cross-family/split duplicate')
        inputs.add(h)
        if r['owner_id'] in olddev or r['owner_id'] in allocation['wp3_owners']:raise ValueError('development leak')
        for index,key in ((families,r['source_family']),(owners,r['owner_id'])):
            if key is not None:
                if key in index and index[key]!=r['split']:raise ValueError('owner/family leakage')
                index[key]=r['split']
        if r['pair_loss_mask'] and r['rejected_action'] in r['acceptable_actions']:raise ValueError('acceptable alternative used as negative')
        if json.loads(r['target_text'])['action']!=r['action_target']:raise ValueError('target action mismatch')
        if digest(r['messages'][1:-1])!=r['evidence_sha256']:raise ValueError('evidence changed')
        if not r['source_refs']:raise ValueError('untraceable target')
    for rs in groups.values():
        permission=rs[0].get('group_type')=='permission_boundary'
        if len(rs)!=(2 if permission else 3) or len({r['evidence_sha256'] for r in rs})!=1 or {r['action_target'] for r in rs}!=({'IGNORE','CLARIFY'} if permission else {'USE','IGNORE','CLARIFY'}):
            raise ValueError('matched group mismatch')
    return True

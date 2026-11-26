"""Supply diagnostics and explicit, unqualified development review records.

Programs verify input/output identity and quote location only. They do not infer
semantic correctness, task helpfulness, or a formal reward from lexical matches.
"""
from pathlib import Path
from collections import Counter
import html,json
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from .selective_memory_validation import jl

FACT_STATES={'unreviewed','supported','partial','omitted','unsupported','unresolved'}
RULE_STATES={'unreviewed','pass','fail','uncertain','not_applicable'}
CLAIM_STATES={'unreviewed','supported','unsupported','uncertain','unresolved'}
DISPUTE_STATES={'unreviewed','unresolved','resolved_no_violation','resolved_violation'}
REVIEW_PROTOCOL='selective-memory-validation-review-v2'
POLICIES=('STOP','MS','C1','simple_visible')


def displayed_input(request):
    return '\n'.join(html.unescape(m['content']) for m in request['model_input']['messages'])


def supply_row(task,evaluation,request,reading):
    """Exact source delivery only; dependency groups avoid single-quote shortcuts."""
    available={r['atom_id']:r['quote'] in displayed_input(request) for r in evaluation['fact_references']}
    refs=[]
    for ref in evaluation['fact_references']:
        dependencies=ref.get('sufficiency_dependency_ids',[ref['atom_id']])
        refs.append(dict(atom_id=ref['atom_id'],required=ref['atom_id'] in evaluation['required_fact_ids'],
            exact_quote_in_current=ref['quote'] in task['query'],exact_quote_in_rendered_input=available[ref['atom_id']],
            dependency_ids=dependencies,declared_source_group_present=all(available.get(x,False) for x in dependencies),
            reference_kind=ref.get('reference_kind','reported_fact'),
            source_session_id=ref['session'],reported_at=ref['reported_at'],source_status=ref['source_status']))
    required=[r for r in refs if r['required']]
    return dict(task_id=task['task_id'],arm=request['arm'],channel=evaluation['channel'],
        situation=evaluation['situation'],case_id=evaluation['source_case_id'],
        required_slots=len(required),supplied_required_groups=sum(r['declared_source_group_present'] for r in required),
        all_required_source_groups_present=all(r['declared_source_group_present'] for r in required) if required else None,
        natural_support_has_no_exhaustive_fact_checklist=not required,
        atom_delivery=refs,selected_source_session_ids=reading['selected_source_session_ids'],input_tokens=request['input_tokens'],
        interpretation='Source delivery is mechanically checked; it is not answer correctness or a semantic task pass.')


def template(request,evaluation):
    return dict(review_protocol=REVIEW_PROTOCOL,logical_id=request['logical_id'],task_id=request['task_id'],arm=request['arm'],
        request_id=request['request_id'],payload_sha256=request['payload_sha256'],
        evalspec_sha256=object_sha256(evaluation),output_sha256=None,technical_status='not_run',
        review_status='unreviewed',reviewer=None,
        facts=[dict(atom_id=r['atom_id'],required=r['atom_id'] in evaluation['required_fact_ids'],
            status='unreviewed',output_quotes=[],source_quotes=[],note='') for r in evaluation['fact_references']],
        support=dict(status='not_applicable' if evaluation['channel']=='fact' else 'unreviewed',
            output_quotes=[],note=''),
        prohibitions=[dict(id='p'+str(i),status='unreviewed',output_quotes=[],note='')
            for i,_ in enumerate(evaluation['prohibitions'],1)],
        additional_claims_review_status='unreviewed',additional_claims=[],
        source_or_reference_disputes_review_status='unreviewed',
        source_or_reference_disputes=[],development_interval=None,formal_reward=None)


def check_supplemental_items(items,states,kind):
    """An explicit inventory; missing, duplicate or unknown states cannot pass."""
    if not isinstance(items,list):raise ValueError(kind+' inventory must be a list')
    ids=[]
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get('status'),str) or item['status'] not in states:
            raise ValueError(kind+' state')
        if not isinstance(item.get('id'),str) or not item['id'].strip():
            raise ValueError(kind+' id required')
        ids.append(item['id'])
    if len(ids)!=len(set(ids)):raise ValueError(kind+' duplicate id')


def validate_review(row,request,evaluation,*,output_text=None,output_sha256=None):
    if row.get('review_protocol')!=REVIEW_PROTOCOL:raise ValueError('review protocol mismatch')
    for key in ('logical_id','task_id','arm','request_id','payload_sha256'):
        if row[key]!=request[key]:raise ValueError('review/request identity mismatch')
    if row['evalspec_sha256']!=object_sha256(evaluation) or row['formal_reward'] is not None:
        raise ValueError('evaluation identity or formal reward mismatch')
    refs={r['atom_id']:r for r in evaluation['fact_references']}
    if len(row['facts'])!=len(refs) or {r['atom_id'] for r in row['facts']}!=set(refs):
        raise ValueError('fact inventory changed')
    for fact in row['facts']:
        if fact['status'] not in FACT_STATES or fact['required']!=(fact['atom_id'] in evaluation['required_fact_ids']):
            raise ValueError('fact state/scope changed')
    if row['support']['status'] not in RULE_STATES:raise ValueError('support state')
    expected=['p'+str(i) for i,_ in enumerate(evaluation['prohibitions'],1)]
    if [r['id'] for r in row['prohibitions']]!=expected:raise ValueError('prohibition inventory changed')
    if any(r['status'] not in RULE_STATES for r in row['prohibitions']):raise ValueError('prohibition state')
    if evaluation['channel']=='fact' and row['support']['status']!='not_applicable':raise ValueError('fact-only support scope')
    if evaluation['channel']!='fact' and row['support']['status']=='not_applicable':raise ValueError('required support scope')
    if any(r['status']=='not_applicable' for r in row['prohibitions']):raise ValueError('required prohibition scope')
    claims=row['additional_claims'];disputes=row['source_or_reference_disputes']
    check_supplemental_items(claims,CLAIM_STATES,'additional claim')
    check_supplemental_items(disputes,DISPUTE_STATES,'source/reference dispute')
    if output_text is None:
        if row['review_status']!='unreviewed' or row['output_sha256'] is not None or row['development_interval'] is not None:
            raise ValueError('unrun item cannot have an outcome')
        if any(f['status']!='unreviewed' for f in row['facts']):raise ValueError('unrun semantic judgement')
        if any(r['status']!='unreviewed' for r in row['prohibitions']):raise ValueError('unrun prohibition judgement')
        if row['support']['status'] not in ('unreviewed','not_applicable'):raise ValueError('unrun support judgement')
        if row['additional_claims_review_status']!='unreviewed' or row['additional_claims']:
            raise ValueError('unrun additional claims judgement')
        if row.get('source_or_reference_disputes_review_status')!='unreviewed' or disputes:
            raise ValueError('unrun source/reference dispute judgement')
        return dict(status='UNRUN_TEMPLATE_VALID',mechanical_only=True,formal_reward=None)
    if not output_text or row['output_sha256']!=output_sha256 or not output_sha256:
        raise ValueError('actual output identity required')
    if row['technical_status']!='eos':
        if row['development_interval'] is not None:raise ValueError('technical failure cannot receive semantic completion')
        return dict(status='TECHNICAL_NONCOMPLETION',mechanical_only=True,formal_reward=None)
    if row['review_status']!='development_observed' or not row['reviewer']:
        raise ValueError('explicit unqualified development review required')
    items=row['facts']+[row['support']]+row['prohibitions']+claims+disputes
    for item in items:
        if item['status']=='unreviewed':raise ValueError('review is incomplete')
        if item['status'] not in ('not_applicable',) and not item.get('note','').strip():
            raise ValueError('private development observation explanation required')
        for quote in item.get('output_quotes',[]):
            if not quote or quote not in output_text:raise ValueError('output quote not exact')
        for quote in item.get('source_quotes',[]):
            if not quote or html.unescape(quote) not in displayed_input(request):
                raise ValueError('claimed supplied quote absent from actual input')
    if row['additional_claims_review_status']!='development_observed':raise ValueError('additional claims unreviewed')
    if row.get('source_or_reference_disputes_review_status')!='development_observed':
        raise ValueError('source/reference disputes unreviewed')
    for claim in claims:
        if not isinstance(claim.get('output_quotes'),list) or not claim['output_quotes']:
            raise ValueError('additional claim requires located output quote')
    # Only propagate externally entered observations; never infer them from the text.
    # Completing the requested slots does not excuse an additional unwarranted
    # assertion. Any unresolved reference dispute blocks definite completion.
    required=[f for f in row['facts'] if f['required']]
    # Optional means it need not be repeated, not that an observed false
    # assertion is excused. An unresolved optional background reference alone
    # is not a response error; a located unresolved assertion is uncertain.
    optional_assertion_issues=[f for f in row['facts'] if not f['required'] and
        (f['status']=='unsupported' or (f['status']=='unresolved' and f.get('output_quotes')))]
    mandatory=required+optional_assertion_issues+row['prohibitions']+claims+disputes+([] if evaluation['channel']=='fact' else [row['support']])
    definite_fail=any(r['status'] in ('partial','omitted','unsupported','fail','resolved_violation') for r in mandatory)
    uncertain=any(r['status'] in ('unresolved','uncertain') for r in mandatory)
    interval=[0,0] if definite_fail else [0,1] if uncertain else [1,1]
    if row['development_interval']!=interval:raise ValueError('development interval differs from entered observations')
    return dict(status='DEVELOPMENT_RECORD_MECHANICALLY_VALID',mechanical_only=True,
        semantic_qualification=False,development_interval=interval,formal_reward=None)


def prepare(*,bundle,requests_dir,out):
    bundle,requests_dir,out=map(Path,(bundle,requests_dir,out))
    if out.exists():raise FileExistsError(out)
    manifest=json.loads((bundle/'MANIFEST.json').read_text())
    for name,h in manifest['files_sha256'].items():
        if file_sha256(bundle/name)!=h:raise ValueError('source/evaluation freeze changed')
    tasks={r['task_id']:r for r in jl(bundle/'TASKS.runtime.jsonl')}
    evals={r['task_id']:r for r in jl(bundle/'EVALSPEC.private.jsonl')}
    policies=jl(bundle/'POLICY_CHOICES.private.jsonl')
    requests=jl(requests_dir/'REQUESTS_ALL.private.jsonl')
    readings={(r['task_id'],r['arm']):r for r in jl(requests_dir/'READINGS.private.jsonl')}
    supplies=[];templates=[]
    for request in requests:
        task=tasks[request['task_id']];evaluation=evals[request['task_id']]
        supplies.append(supply_row(task,evaluation,request,readings[(request['task_id'],request['arm'])]))
        row=template(request,evaluation);validate_review(row,request,evaluation);templates.append(row)
    by={(r['task_id'],r['arm']):r for r in supplies}
    policy_summary={}
    for name in POLICIES:
        selected=[by[(r['task_id'],r[name])] for r in policies]
        policy_summary[name]=dict(choices=dict(Counter(r[name] for r in policies)),
            input_tokens=sum(r['input_tokens'] for r in selected),
            required_slots=sum(r['required_slots'] for r in selected),
            supplied_required_groups=sum(r['supplied_required_groups'] for r in selected),
            fact_or_joint_tasks_fully_supplied=sum(r['all_required_source_groups_present'] is True for r in selected),
            natural_support_tasks_without_exhaustive_fact_requirement=sum(r['all_required_source_groups_present'] is None for r in selected))
    summary=dict(protocol='selective-memory-validation-evaluation-preparation-v2',review_protocol=REVIEW_PROTOCOL,tasks=len(tasks),
        frozen_unrun_review_rows=len(templates),semantic_judgments_entered=0,actual_model_calls=0,formal_reward=None,
        policy_summary=policy_summary,required_slots_per_policy=policy_summary['STOP']['required_slots'],
        source_only_supply_not_quality=True,source_families=3,source_situations=5,
        true_conflict_instances=0,update_identity_unknown_instances=1,
        unseen_source_claim=False,sealed_text_read=False,
        code_sha256=file_sha256(__file__),bundle_manifest_sha256=file_sha256(bundle/'MANIFEST.json'),
        request_manifest_sha256=file_sha256(requests_dir/'REQUESTS_ALL.private.jsonl'))
    out.mkdir(parents=True)
    write_jsonl_once(out/'SOURCE_SUPPLY_PRIVATE.jsonl',supplies)
    write_jsonl_once(out/'REVIEW_TEMPLATE_PRIVATE.jsonl',templates)
    write_json_once(out/'REVIEW_CONTRACT.json',dict(protocol=REVIEW_PROTOCOL,
        claim_states=sorted(CLAIM_STATES),dispute_states=sorted(DISPUTE_STATES),
        complete_task_allows_additional_unwarranted_assertion=False,
        additional_claim_scope='Asserted personal facts or other task-relevant factual assertions, each with a located exact output quote and a private development explanation.',
        dispute_scope='Every entered source/reference dispute requires explicit review. Unresolved disputes block definite completion; resolved_no_violation permits completion only when all other requirements pass; resolved_violation means a documented task violation after resolution.',
        definite_incomplete='Any required partial/omitted/unsupported fact, prohibition failure, additional unsupported assertion, optional fact marked unsupported, or resolved_violation dispute yields [0,0]. Optional omission remains allowed.',
        uncertain='If no definite failure exists, any required unresolved item, additional uncertain/unresolved assertion, or unresolved source/reference dispute yields [0,1].',
        precedence='Entered definite violations retain [0,0] when a dispute is also unresolved. If that dispute undermines the violation judgement itself, the affected item must also be entered as unresolved; the program cannot infer that semantic revision. All item-level uncertainty remains recorded.',
        no_auto_semantic_judgment=True,formal_reward=None))
    write_json_once(out/'SUMMARY_PUBLIC.json',summary)
    text=['# Independent Memory development tasks — private source/readout',
        'No new model outputs. Every eventual semantic judgement is an unqualified development observation; quote checks do not qualify reward.']
    for i,(task_id,task) in enumerate(tasks.items(),1):
        ev=evals[task_id]
        text += ['\n## '+str(i)+' / '+task_id+' / '+ev['channel']+' / '+ev['situation'],
            '\nVisible task:\n'+task['query'],'\nRequired fact ids: '+str(ev['required_fact_ids']),
            '\nSupport operation: '+ev['support_goal'],'\nSource-only temporal boundary: '+ev['source_binding']['temporal_relation']]
        for ref in ev['fact_references']:
            text += ['\n- '+ref['atom_id']+' '+ref['semantic_reference'],
                '  Source '+ref['owner']+'/'+ref['session']+':'+str(ref['turn'])+' ['+ref['reported_at']['date']+'] '+ref['quote']]
        for arm in ('STOP','MS'):
            s=by[(task_id,arm)]
            text+=['\n'+arm+' selected='+str(s['selected_source_session_ids'])+'; requested source groups '+
                str(s['supplied_required_groups'])+'/'+str(s['required_slots'])+'; input tokens='+str(s['input_tokens'])]
        text+=['\nProhibitions (not mandatory verbatim disclaimers):']+['- '+x for x in ev['prohibitions']]
    (out/'TASKS_AND_SUPPLY_PRIVATE.md').write_text('\n'.join(text)+'\n')
    write_json_once(out/'MANIFEST.json',dict(files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},
        inputs_sha256={str(bundle/'MANIFEST.json'):file_sha256(bundle/'MANIFEST.json'),
                      str(requests_dir/'REQUESTS_ALL.private.jsonl'):file_sha256(requests_dir/'REQUESTS_ALL.private.jsonl')},
        code_sha256=file_sha256(__file__),unrun=True))
    return summary

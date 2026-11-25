"""Eighteen pre-output structured source tasks; finite CPU construction/evaluation.

These are assistant-authored development fields tied to explicit real clauses,
not independent human gold or a natural-support reward qualification.
"""
from collections import Counter
from pathlib import Path
import json
import re
import shutil
from .. import contracts as K
from ..compile import asof as A
from ..io import canonical_json, file_sha256, object_sha256, write_json_once, write_jsonl_once
from .memory_packages import next_real_prefix, budget
from .memory_port import SnapshotPrefixPort
from .runtime_binding import VerifiedEpisode, binding_for, plain
from .renderer import packet
from .structured_run import check, RUN_PROTOCOL, JOB_KIND

# All real source text, questions, and answer values are private seed inputs.
INSTRUCTION=(
 'This is a bounded structured source-reading development task, not a request for counselling. '
 'Answer only from the supplied visible evidence and historical resource. A source report is not present reality. '
 'Distinguish the report date from the event date; booking/intention is not attendance; '
 'different reports are not a correction or the same event unless explicit. If the requested field is absent, '
 'unsettled, or not established by the available evidence, choose unknown; do not guess a real-world negative. '
 'Return ONLY one compact JSON object with exactly these fields: value, certainty, quote, speaker, reported_date. '
 'Use certainty="supported" for a source-established value or "unknown" otherwise. '
 'For supported answers quote an exact short contiguous passage proving the requested value, '
 'speaker="seeker" or "supporter", and reported_date in YYYY-MM-DD. '
 'For unknown use value="unknown", certainty="unknown", quote="", speaker="unknown", reported_date=null.\n')


def jl(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]


def evaluate(text,reference,*,arm,delivered_text):
    """Exact field semantics + prebound source evidence, not citation-only success.

    Each value is a declared finite source field. No paraphrase judge or semantic
    model is hidden in this function. Natural language outside JSON is not repaired.
    """
    result=dict(structural_status='fail',value_correct=False,evidence_correct=False,
        epistemic_compliance=False,task_success=False,reward=None,errors=[])
    try:answer=json.loads(text)
    except (ValueError,TypeError):result['errors']=['invalid_json'];return result
    if not isinstance(answer,dict) or set(answer)!={'value','certainty','quote','speaker','reported_date'}:
        result['errors']=['schema'];return result
    if not all(isinstance(answer[k],str) for k in ('value','certainty','quote','speaker')):
        result['errors']=['field_types'];return result
    result['structural_status']='pass';value=answer['value'];quote=answer['quote']
    expected=reference['value'];result['value_correct']=value==expected
    unknown=value=='unknown' and answer['certainty']=='unknown' and quote=='' and answer['speaker']=='unknown' and answer['reported_date'] is None
    if expected=='unknown':
        result['evidence_correct']=unknown;result['epistemic_compliance']=unknown
    else:
        ev=reference['evidence'];available=all(q in delivered_text for q in reference['required_delivered_quotes'])
        bound=(len(quote)>=3 and quote in ev['text'] and reference['required_literal'].casefold() in quote.casefold()
            and quote in delivered_text and answer['speaker']==ev['speaker'] and answer['reported_date']==ev['reported_date'])
        result['evidence_correct']=bool(bound and available)
        result['epistemic_compliance']=bool((answer['certainty']=='supported' and bound and available) or (not available and unknown))
    result['task_success']=all(result[k] for k in ('value_correct','evidence_correct','epistemic_compliance'))
    if not result['value_correct']:result['errors'].append('wrong_or_missing_field_value')
    if not result['evidence_correct']:result['errors'].append('insufficient_or_wrong_source_evidence')
    if not result['epistemic_compliance']:result['errors'].append('unsupported_certainty_or_unknown_schema')
    return result


def prepare(*,registry,tokenizer,repo,smoke,measurements,seed,out):
    repo,smoke,measurements,seed,out=map(Path,(repo,smoke,measurements,seed,out));out.mkdir(parents=True,exist_ok=False)
    config=json.loads(seed.read_text())
    if config['protocol']!='structured-source-seed-v1' or len(config['specs'])!=18 or config['selection_before_generation'] is not True:
        raise ValueError('fixed private source seed required')
    specs=config['specs'];priors=config['priors']
    base=json.loads((smoke/'SMOKE_PLAN.json').read_text());baseline=json.loads(Path(base['baseline_path']).read_text())
    measured=json.loads(measurements.read_text());tasks=[];references=[];logical=[];checks=[];materials=[]
    from . import renderer
    renderer_sha=file_sha256(renderer.__file__)
    tokenizer.native_context_tokens=16384
    for sid,owner,session,turn,literal,question,value,choices,visible,category in specs:
        source=registry.entry(owner,session).source
        # Guard source indexing before any reference or request publication.
        if literal not in source.turns[turn].text:raise ValueError(f'{sid}: literal/source ordinal mismatch')
        evidence=dict(owner_id=owner,session_id=session,turn=turn,speaker=source.turns[turn].role,
            text=source.turns[turn].text,reported_date=source.date,start_char=source.turns[turn].text.index(literal),
            end_char=source.turns[turn].text.index(literal)+len(literal),source_sha256=A.source_sha(source))
        prefix=next_real_prefix(registry,source)
        writer='structured-raw:'+object_sha256(dict(task_id=sid,source_sha=A.source_sha(source)))
        ledger=A.Ledger(out/'ledgers'/sid);raw=A.record_from_source(registry.entry(owner,session),kind='MS_RAW',writer=writer,subject='session')
        ledger.append(raw,registry);snapshot=A.materialize(registry,prefix,ledger,writer=writer)
        port=SnapshotPrefixPort(registry,prefix,snapshot,tokenizer,g_id=baseline['binding_sha256'],
            decode_id='G0e-frozen',step2_id='structured-direct-v1',output_reserve_tokens=320)
        binding=binding_for(registry,prefix,snapshot,port)
        ep=VerifiedEpisode(registry=registry,prefix=prefix,snapshot=snapshot,port=port,binding=binding)
        state=ep.reset();state,info=ep.try_step(state,'GET_MS')
        if state.order!=('MS',):raise ValueError('actual MS read failed')
        terminal,_=ep.try_step(state,'STOP');_,invalid=ep.try_step(terminal,'GET_MS')
        assert terminal.done and invalid.reason=='after_stop' and ep.stop_value(terminal).status=='pending'
        read=port.read('MS');assert isinstance(read,K.ReadSuccess) and raw.record_id in read.record_ids
        assert literal in read.reading.reading_text and not port.verify_records(read.record_ids)
        prior=None;prior_text='';required=[literal]
        if sid in priors:
            ps,pt=priors[sid];src=registry.entry(owner,ps).source
            assert registry.reason(registry.entry(owner,ps).source_id,prefix) is None
            prior=dict(session_id=ps,turn=pt,reported_date=src.date,speaker=src.turns[pt].role,text=src.turns[pt].text,source_sha256=A.source_sha(src))
            prior_text=f'Earlier visible report (reported {src.date}; {prior["speaker"]}): {prior["text"]}\n'
            required.append(prior['text'])
        context_text=''
        if sid in config.get('extra_context',{}):
            ctx=config['extra_context'][sid]
            context=source.turns[ctx['turn']]
            assert ctx['required_literal'] in context.text
            context_text=f'Visible antecedent (reported {source.date}; {context.role}): {context.text}\n'
            required.append(ctx['required_literal'])
        visible_text=(f'Visible evidence (reported {source.date}; {evidence["speaker"]}): {evidence["text"]}\n' if visible else '')
        prompt=INSTRUCTION+'Question: '+question+'\nAllowed values: '+', '.join(choices+['unknown'])+'\n'+prior_text+context_text+visible_text
        task=dict(task_id=sid,owner_id=owner,source_group=owner,source_family=source.family_id,
            ancestor_families=list(source.ancestor_family_ids),source_session=session,category=category,
            question=question,choices=choices+['unknown'],base_has_target_evidence=visible,
            prior_visible_report=prior,real_prefix=plain(prefix),direct_source_selection=True)
        ref=dict(task_id=sid,value=value,evidence=evidence,required_literal=literal,required_delivered_quotes=required,
            reference_origin='assistant-authored deterministic field from explicit real source; not independent human label',
            unknown_semantics='requested field not established; no real-world negative or closed-world truth',
            conflict_policy='different dates/uncertain event identity are not contradiction; explicit correction required',
            multi_report_prior=prior,semantic_review='development_reference_not_human_approved')
        tasks.append(task);references.append(ref)
        checks.append(dict(task_id=sid,prefix_id=prefix.prefix_id,snapshot_sha=snapshot['snapshot_sha'],
            binding_sha256=binding.sha256,record_ids=list(read.record_ids),reading_sha256=read.reading.sha256,
            path=['GET_MS','STOP'],after_stop='rejected',reward='pending',raw_legal=True,
            source_group=owner,availability=port.availability(),no_semantic_candidate_approved=True))
        for arm in ('BASE','RAW'):
            material=dict(task_id=sid,visible_prefix=dict(turns=[dict(role='seeker',text=prompt)]),
                readings=[plain(read.reading)] if arm=='RAW' else [])
            packed,_=packet(material,tokenizer,baseline_sha256=baseline['binding_sha256'],implementation_sha256=renderer_sha)
            payload=packed.payload();sha=packed.payload_sha256
            row=dict(domain='structured',task_id=sid,arm=arm,logical_id=f'structured:{sid}:{arm}',request_id='jreq:'+sha,
                payload_sha256=sha,model_input=payload,input_ids_sha256=object_sha256(payload['input_ids']),
                input_tokens=len(payload['input_ids']),renderer_id=packed.renderer_id,baseline_sha256=baseline['binding_sha256'],
                authorized=False,model_called=False)
            logical.append(row);materials.append(dict(logical_id=row['logical_id'],material=material))
    write_jsonl_once(out/'TASKS.private.jsonl',tasks);write_jsonl_once(out/'REFERENCES.private.jsonl',references)
    write_jsonl_once(out/'REQUESTS_ALL.private.jsonl',logical);write_jsonl_once(out/'MATERIALS.private.jsonl',materials)
    write_jsonl_once(out/'PORT_CHECKS.private.jsonl',checks)
    rules=dict(protocol='structured-source-value-v1',task_count=18,conditions=['BASE','RAW'],reference_before_generation=True,
        original_four_source_mutation_protocol='reused exact source/speaker/date checking; extended with field values and explicit source clauses',
        original_four_sessions_reused=config['original_four_sessions_reused'],
        explicit_inconsistent_report_positive_cases=0,conflict_scope='no positive contradictory-report case; consistent reports and unknown event identity only',
        action_scope='BASE/GET_MS subset of four-head protocol, not Memory x RS joint completion',
        private_seed_sha256=file_sha256(seed),
        evaluator_sha256=file_sha256(__file__),structural_success_not_sufficient=True,success_fields=['value_correct','evidence_correct','epistemic_compliance'],
        BASE_unknown_when_missing='epistemically compliant, but not a correct substantive answer when target value is known',
        unknown_target='correct bounded unknown is a valid success; no reality-negative inference',
        source_group_count=9,base_target_visible=7,unknown_targets=4,models_used_to_select_tasks=0,
        task_reference_status='assistant-authored explicit-clause development fields, not independent human reference',
        sidecar_scope='structured prompts at real legal cutoffs, not original human dialogue continuation; Direct selected-source diagnostic',
        current_real_prefix_text_not_claimed_to_be_G_prompt=True,no_reward_promotion=True,
        unqualified_or_nonliteral_semantics='do not force pass; preserve unknown/development status',
        stop='first technical failure or third length termination; no retry',
        runtime_gold_isolation='references never serialized; public finite alternatives contain all allowed field categories')
    write_json_once(out/'EVALUATION_RULES.json',rules)
    executor=out/'executor';shutil.copytree(base['executor_root'],executor)
    additions=['project/src/metacom_pm/rl1v3/journal/structured_run.py','project/scripts/rl1v3/journal_structured_run.py']
    hashes=dict(base['executor_files_sha256'])
    for name,sha in hashes.items():assert file_sha256(executor/name)==sha
    for name in additions:shutil.copy2(repo/name,executor/name);hashes[name]=file_sha256(executor/name)
    receipts=[]
    for number in (1,2):
        job=out/f'batch-{number:02d}';job.mkdir();selected=logical[(number-1)*18:number*18]
        unique=list({r['request_id']:r for r in reversed(selected)}.values())[::-1]
        write_jsonl_once(job/'LOGICAL.private.jsonl',selected);write_jsonl_once(job/'REQUESTS.private.jsonl',unique)
        feasible=budget(unique,measured);write_json_once(job/'FEASIBILITY.json',feasible)
        plan=dict(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,batch_number=number,authorized=False,remaining_batches_authorized=False,
            research_qualified=False,executor_root=str(executor.resolve()),executor_files_sha256=hashes,
            requests_path=str((job/'REQUESTS.private.jsonl').resolve()),requests_sha256=file_sha256(job/'REQUESTS.private.jsonl'),
            frozen_requests_path=str((out/'REQUESTS_ALL.private.jsonl').resolve()),logical_requests_path=str((job/'LOGICAL.private.jsonl').resolve()),
            task_manifest_path=str((out/'TASKS.private.jsonl').resolve()),task_manifest_sha256=file_sha256(out/'TASKS.private.jsonl'),
            review_path=str((out/'REFERENCES.private.jsonl').resolve()),review_sha256=file_sha256(out/'REFERENCES.private.jsonl'),
            task_ids=[r['task_id'] for r in selected[::2]],logical_requests=18,max_calls=len(unique),
            ordered_request_ids=[r['request_id'] for r in unique],baseline_path=base['baseline_path'],baseline_sha256=base['baseline_sha256'],
            checkpoint_path=base['checkpoint_path'],model_path=base['model_path'],python=base['python'],max_model_loads=1,warmup_calls=0,
            automatic_retry=False,global_seconds=1200,load_seconds=600,request_seconds=300,renderer_id=unique[0]['renderer_id'],
            stop_rules=base['stop_rules'],paid_api_allowed=False)
        bound=[job/'REQUESTS.private.jsonl',job/'LOGICAL.private.jsonl',job/'FEASIBILITY.json',out/'REQUESTS_ALL.private.jsonl',
            out/'TASKS.private.jsonl',out/'REFERENCES.private.jsonl',out/'EVALUATION_RULES.json',out/'PORT_CHECKS.private.jsonl',
            Path(base['baseline_path']),Path(base['checkpoint_path']),measurements,seed,Path(__file__)]
        plan['files_sha256']={str(p.resolve()):file_sha256(p) for p in bound}
        write_json_once(job/'PLAN.json',plan);check(job/'PLAN.json')
        write_json_once(job/'AUTHORIZATION_PENDING.json',dict(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,authorized=False,
            plan_sha256=object_sha256(plan),max_calls=len(unique),max_model_loads=1,researcher=None,decision_evidence=None))
        receipt=dict(status='CPU_CHECK_PASSED',batch_number=number,plan_sha256=object_sha256(plan),
            plan_path=str((job/'PLAN.json').resolve()),authorized=False,logical=18,physical=len(unique),**feasible)
        write_json_once(job/'CPU_CHECK.json',receipt);receipts.append(receipt)
    report=dict(tasks=18,logical_requests=36,physical_requests=len({r['request_id'] for r in logical}),
        group_count=len({t['source_group'] for t in tasks}),categories=dict(Counter(t['category'] for t in tasks)),
        original_source_sessions_reused=rules['original_four_sessions_reused'],base_target_visible=sum(t['base_has_target_evidence'] for t in tasks),
        unknown_target_count=sum(r['value']=='unknown' for r in references),actual_port_episodes=len(checks),
        actual_G_calls=0,authorized=False,semantic_approved_new=0,plans=receipts,old_executor_files_changed=[],executor_additions=additions)
    write_json_once(out/'PACKAGE_REPORT.json',report)
    return report

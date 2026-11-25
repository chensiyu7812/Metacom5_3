"""Frozen complex RS materials and exact paired requests; CPU preparation only.

Task-specific direct selections and review text are private input, not code or
runtime features. Retrieval receives the visible current query and frozen bank.
"""
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
import shutil
import statistics
import time
import xml.etree.ElementTree as ET

from ..io import file_sha256, object_sha256
from .rs_tasks import GENERIC, select_visible, write_once
from .skills import build_skills

ARMS = ('R0', 'Generic', 'DP-RAW', 'DP-Method', 'RET-Method', 'F-resident')
TASK_MANIFEST_SHA = '0a84fac4aaa04bce056fc94398eadecf2827f2dcdcdb1485b76e3d68c22453dc'
SKILL_MANIFEST_SHA = 'a304e82fcb12749a0c4e65be09e7593fa5b17589ac300c0d917bf1e88271dcc5'
PROTOCOL = 'pmrl1-j-rs-complex72-material-v1'


def jl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def verify_manifest(directory, name, expected):
    directory = Path(directory)
    if file_sha256(directory/name) != expected:
        raise ValueError('frozen manifest identity changed')
    manifest = json.loads((directory/name).read_text())
    for filename, sha in manifest['files'].items():
        if file_sha256(directory/filename) != sha:
            raise ValueError('frozen file changed: '+filename)
    return manifest


def materials_for(task, skills, review):
    """No review content enters the selector or the runtime turn projection."""
    bank = {s['skill_id']: s for s in skills}
    direct = bank[review['direct_skill_id']]
    visible = {'task_id': task['task_id'], 'turns': [dict(role=t['role'], text=t['text'])
               for t in task['turns']], 'timestamp': task['timestamp']}
    score, selected = select_visible(visible['turns'][-1]['text'], skills, 'method_reading')
    texts = {'R0': None, 'Generic': GENERIC, 'DP-RAW': direct['raw_reading'],
             'DP-Method': direct['method_reading'], 'RET-Method': selected['method_reading'],
             'F-resident': '\n\n'.join(s['method_reading'] for s in skills)}
    out = [dict(task_id=task['task_id'], arm=arm, runtime=visible,
                readings=[] if texts[arm] is None else [dict(head='RS', view='method',
                reading_text=texts[arm], reported_at=None)]) for arm in ARMS]
    return out, dict(task_id=task['task_id'], direct_skill_id=direct['skill_id'],
        retrieved_skill_id=selected['skill_id'], lexical_score=score,
        exact_selection_match=direct['skill_id']==selected['skill_id'],
        query_sha256=object_sha256(visible['turns'][-1]['text']),
        retrieval='unchanged visible-query set-overlap Top1, skill_id tie break',
        direct='private evaluation-side applicable-method diagnostic, not a deployable selector')


def verify_projection(material, row, tokenizer):
    payload = row['model_input']
    actual = list(tokenizer.encode_messages(payload['messages']))
    if actual != payload['input_ids'] or len(actual) != row['input_tokens']:
        raise ValueError('native token delivery changed')
    blocks = []
    for m in payload['messages']:
        if '<Notes>' in m['content']:
            root = ET.fromstring(m['content'][m['content'].index('<Notes>'):])
            blocks.extend(e.text or '' for e in root)
    if blocks != [r['reading_text'] for r in material['readings']]:
        raise ValueError('resource omission, change, or truncation')
    turns = [dict(role='user' if t['role']=='seeker' else 'assistant', content=t['text'])
             for t in material['runtime']['turns']]
    if payload['messages'][-len(turns):] != turns:
        raise ValueError('visible turns changed')
    if set(payload) != {'messages','input_ids','decode'}:
        raise ValueError('runtime payload allowlist')


def validate_review(tasks, evaluations, reviews, skills):
    task_ids = [t['task_id'] for t in tasks]
    if len(task_ids)!=12 or len(set(task_ids))!=12:
        raise ValueError('all original 12 tasks required')
    if [e['task_id'] for e in evaluations]!=task_ids or [r['task_id'] for r in reviews]!=task_ids:
        raise ValueError('original task order/identity changed')
    bank = {s['skill_id']: s for s in skills}
    for task, ev, review in zip(tasks, evaluations, reviews):
        if review['runtime_sha256'] != object_sha256(task) or review['evalspec_sha256'] != object_sha256(ev):
            raise ValueError('review not bound to original task/evaluation')
        if review['direct_skill_id'] not in bank or review['professionally_approved'] is not False:
            raise ValueError('invalid direct method or invented approval')
        for field in ('applicability_evidence','method_support','coverage_gaps','acceptable_alternatives',
                      'evaluation_rule_review','ret_applicability_review'):
            if not review.get(field):
                raise ValueError('missing actual review: '+field)
        if ev['reward_qualified'] is not False or ev['outcome'] is not None:
            raise ValueError('frozen unqualified evaluation changed')


def build(*, tasks_dir, candidates, sources, review_path, review_sha256,
          template_plan, repo, model, assets, output):
    started = time.monotonic()
    from ..generator.g0e_port import PromptTokenizer
    from ..retrieve.native_tokens import NativeTokenizer
    from . import renderer
    from .rs_complex_run import check, RUN_PROTOCOL, JOB_KIND
    output, repo = Path(output).resolve(), Path(repo).resolve()
    if output.exists():
        raise FileExistsError('new version directory required')
    tasks_dir, candidates = Path(tasks_dir), Path(candidates)
    verify_manifest(tasks_dir, 'MANIFEST.json', TASK_MANIFEST_SHA)
    verify_manifest(candidates, 'manifest.json', SKILL_MANIFEST_SHA)
    if file_sha256(review_path) != review_sha256:
        raise ValueError('private applicability review changed')
    review_document = json.loads(Path(review_path).read_text())
    if review_document['generated_responses_read_for_this_package'] != 0:
        raise ValueError('pre-generation review required')
    reviews = review_document['reviews']
    tasks, evaluations = jl(tasks_dir/'TASKS.runtime.jsonl'), jl(tasks_dir/'EVALSPEC.private.jsonl')
    skills = jl(candidates/'skills.private.jsonl')
    rebuilt = build_skills(sources)
    if len(skills)!=6 or {s['skill_id'] for s in skills}!={s['skill_id'] for s in rebuilt}:
        raise ValueError('fixed six-skill library changed')
    for s, b in zip(skills, rebuilt):
        if any(s[field]!=b[field] for field in ('skill_id','source_refs','method_reading','raw_reading')):
            raise ValueError('official source/content identity mismatch')
    validate_review(tasks, evaluations, reviews, skills)
    template = json.loads(Path(template_plan).read_text())
    baseline = json.loads(Path(template['baseline_path']).read_text())
    if object_sha256(baseline)!=template['baseline_sha256']:
        raise ValueError('template baseline changed')
    native = NativeTokenizer(model, assets);tokenizer = PromptTokenizer(native)
    if tokenizer.identity != baseline['spec']['tokenizer_identity']:
        raise ValueError('native tokenizer/baseline mismatch')
    impl = file_sha256(renderer.__file__)
    materials=[];selections=[];requests=[];details=[];unique={}
    for task, review in zip(tasks, reviews):
        items, selection = materials_for(task, skills, review)
        selections.append(selection)
        if selection['retrieved_skill_id'] != review['retrieved_skill_id_checked']:
            raise ValueError('reviewed real retrieval identity changed')
        off_tokens = None
        for material in items:
            p, views = renderer.packet(material, tokenizer, baseline_sha256=baseline['binding_sha256'],
                                       implementation_sha256=impl)
            row = dict(logical_id='rs:'+task['task_id']+':'+material['arm'], domain='rs',
                task_id=task['task_id'], arm=material['arm'], request_id='jreq:'+p.payload_sha256,
                model_input=p.payload(), payload_sha256=p.payload_sha256,
                input_ids_sha256=object_sha256(list(p.input_ids)), input_tokens=len(p.input_ids),
                renderer_id=p.renderer_id, baseline_sha256=baseline['binding_sha256'],
                source_material_sha256=object_sha256(material), authorized=False,model_called=False,
                status='frozen_candidate_awaiting_separate_run_authorization',evaluation_status='unqualified_pending')
            verify_projection(material, row, tokenizer)
            if material['arm']=='R0':off_tokens=len(p.input_ids)
            content=material['readings'][0]['reading_text'] if material['readings'] else ''
            supplied = []
            if material['arm']=='F-resident':supplied=skills
            elif material['arm'].startswith('DP-'):supplied=[s for s in skills if s['skill_id']==selection['direct_skill_id']]
            elif material['arm']=='RET-Method':supplied=[s for s in skills if s['skill_id']==selection['retrieved_skill_id']]
            details.append(dict(logical_id=row['logical_id'],task_id=task['task_id'],arm=material['arm'],
                request_id=row['request_id'],input_tokens=len(p.input_ids),resource_tokens=native.count(content) if content else 0,
                marginal_input_tokens_vs_R0=len(p.input_ids)-off_tokens,
                source_paragraph_sha256=[p['paragraph_sha256'] for s in supplied for p in s['source_refs']],
                supplied_skill_ids=[s['skill_id'] for s in supplied], exact_reading_delivery=True,
                native_retokenization_exact=True, no_truncation=True))
            materials.append(material);requests.append(row);unique.setdefault(row['request_id'], row)
    if len(requests)!=72 or len({r['renderer_id'] for r in requests})!=1:
        raise ValueError('fixed request or renderer cardinality')
    output.mkdir(parents=True)
    for name, rows in [('MATERIALS.private.jsonl',materials),('REQUESTS_LOGICAL.private.jsonl',requests),
                       ('REQUESTS_UNIQUE.private.jsonl',list(unique.values())),('SELECTION.private.jsonl',selections),
                       ('DELIVERY.private.jsonl',details)]:
        write_once(output/name, rows, lines=True)
    shutil.copy2(review_path, output/'APPLICABILITY_REVIEW.private.json')
    shutil.copy2(tasks_dir/'EVALSPEC.private.jsonl', output/'EVALSPEC.private.jsonl')
    shutil.copy2(tasks_dir/'TASKS.runtime.jsonl', output/'TASKS.runtime.jsonl')
    readable=['# Frozen complex RS: complete task / source / method / evaluator package',
        'All original task and EvalSpec identities are unchanged. These are constructed development tasks; no expert approval or efficacy is asserted.',
        'DP selects a candidate method using a private applicability review. RET uses only the visible query. RAW versus Method includes nonclinical normative adaptation.',
        'CASE remains unapproved and is absent from all requests. The same frozen G0e renderer, model and decode apply to all arms.']
    for task, ev, review, selection in zip(tasks,evaluations,reviews,selections):
        readable += ['\n## '+task['task_id'], '\n### Exact visible task\n'+task['turns'][-1]['text'],
            '\n### Applicability review\n```json\n'+json.dumps(review,ensure_ascii=False,indent=2)+'\n```',
            '\n### Original evaluation and source evidence\n```json\n'+json.dumps(ev,ensure_ascii=False,indent=2)+'\n```',
            '\n### Actual retrieval\n```json\n'+json.dumps(selection,ensure_ascii=False,indent=2)+'\n```']
        for m in [m for m in materials if m['task_id']==task['task_id']]:
            readable += ['\n### '+m['arm']+' supplied text\n'+(m['readings'][0]['reading_text'] if m['readings'] else '(none)')]
    with (output/'READABLE_PACKAGE.private.md').open('x') as f:f.write('\n'.join(readable)+'\n')
    # Copy the old executor and add exactly the independently named admission.
    executor=output/'executor';shutil.copytree(template['executor_root'],executor)
    admission='project/src/metacom_pm/rl1v3/journal/rs_complex_run.py'
    shutil.copy2(repo/admission,executor/admission)
    executor_hashes={name:file_sha256(executor/name) for name in template['executor_files_sha256']}
    if executor_hashes!=template['executor_files_sha256']:
        raise ValueError('preserved executor copy changed')
    executor_hashes[admission]=file_sha256(executor/admission)
    files=[output/n for n in ('MATERIALS.private.jsonl','REQUESTS_LOGICAL.private.jsonl','REQUESTS_UNIQUE.private.jsonl',
        'APPLICABILITY_REVIEW.private.json','EVALSPEC.private.jsonl','TASKS.runtime.jsonl','SELECTION.private.jsonl','DELIVERY.private.jsonl')]
    files += [Path(template['baseline_path']),Path(template['checkpoint_path']),Path(template_plan),Path(assets),
              tasks_dir/'MANIFEST.json',candidates/'manifest.json']
    batches=[]
    for index in range(4):
        task_ids=[t['task_id'] for t in tasks[3*index:3*index+3]]
        logical=[r for r in requests if r['task_id'] in task_ids]
        ids=list(dict.fromkeys(r['request_id'] for r in logical));physical=[unique[r] for r in ids]
        batchdir=output/f'batch-{index+1:02d}';batchdir.mkdir()
        write_once(batchdir/'REQUESTS.private.jsonl',physical,lines=True)
        write_once(batchdir/'LOGICAL_REQUESTS.private.jsonl',logical,lines=True)
        plan={k:copy.deepcopy(template[k]) for k in ('baseline_path','baseline_sha256','checkpoint_path','python',
            'model_path','renderer_id','stop_rules','global_seconds','load_seconds','request_seconds','automatic_retry',
            'max_model_loads','warmup_calls','paid_api_allowed')}
        plan.update(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,authorized=False,batch_number=index+1,
            executor_root=str(executor),executor_files_sha256=executor_hashes,max_calls=len(physical),
            logical_requests=18,task_ids=task_ids,requests_path=str(batchdir/'REQUESTS.private.jsonl'),
            requests_sha256=file_sha256(batchdir/'REQUESTS.private.jsonl'),ordered_request_ids=ids,
            logical_requests_path=str(batchdir/'LOGICAL_REQUESTS.private.jsonl'),
            frozen_requests_path=str(output/'REQUESTS_LOGICAL.private.jsonl'),
            task_manifest_path=str(tasks_dir/'MANIFEST.json'),task_manifest_sha256=TASK_MANIFEST_SHA,
            review_path=str(output/'APPLICABILITY_REVIEW.private.json'),review_sha256=review_sha256,
            renderer_id=requests[0]['renderer_id'],remaining_batches_authorized=False,
            selection='original frozen task file order, three complete six-arm tasks per batch; no outcome access')
        bound=files+[batchdir/'REQUESTS.private.jsonl',batchdir/'LOGICAL_REQUESTS.private.jsonl']
        plan['files_sha256']={str(p.resolve()):file_sha256(p) for p in bound}
        write_once(batchdir/'PLAN.json',plan)
        checked, checked_rows, _=check(batchdir/'PLAN.json')
        receipt=dict(status='CPU_CHECK_PASSED',authorized=False,plan_sha256=object_sha256(checked),
            plan_file_sha256=file_sha256(batchdir/'PLAN.json'),logical_requests=18,
            physical_calls=len(checked_rows),exact_payload_reuses=18-len(checked_rows),
            input_tokens=sum(r['input_tokens'] for r in physical),max_model_loads=1,
            global_seconds=1200,automatic_retry=False,model_loads=0,device_access=False)
        write_once(batchdir/'CPU_CHECK.json',receipt)
        write_once(batchdir/'AUTHORIZATION_PENDING.json',dict(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,
            authorized=False,plan_sha256=receipt['plan_sha256'],max_calls=len(physical),max_model_loads=1,
            researcher=None,decision_evidence=None))
        batches.append(dict(batch_number=index+1,plan_path=str(batchdir/'PLAN.json'),**receipt))
    summaries={}
    for arm in ARMS:
        group=[r for r in details if r['arm']==arm]
        summaries[arm]={key:dict(min=min(r[key] for r in group),median=statistics.median(r[key] for r in group),
            max=max(r[key] for r in group),total=sum(r[key] for r in group))
            for key in ('input_tokens','resource_tokens','marginal_input_tokens_vs_R0')}
    summary=dict(protocol=PROTOCOL,authorized=False,tasks=12,source_video_families=12,arms=list(ARMS),
        logical_requests=72,unique_physical_requests=len(unique),exact_payload_reuses=72-len(unique),
        native_delivery_checks=72,readable_content_checks=72,source_paragraphs=sum(len(s['source_refs']) for s in skills),
        official_source_recompile_matched=True,original_task_manifest_sha256=TASK_MANIFEST_SHA,
        original_24_tasks_and_144_requests_unchanged=True,private_review_sha256=review_sha256,
        direct_retrieval_exact_match=sum(s['exact_selection_match'] for s in selections),
        direct_retrieval_different=sum(not s['exact_selection_match'] for s in selections),
        different_selection_is_not_automatically_error=True,
        direct_applicability=dict(Counter(r['direct_coverage'] for r in reviews)),
        retrieved_applicability=dict(Counter(r['ret_applicability_class'] for r in reviews)),
        by_arm=summaries,batches=batches,renderer_id=requests[0]['renderer_id'],
        tokenizer_identity=native.identity,tokenizer_files_sha256=native.file_hashes,
        max_input_tokens=max(r['input_tokens'] for r in requests),runtime_capacity=16384,output_reserve=320,
        qualified_rewards=0,CASE_positive_or_runtime_eligible=0,new_generation_calls=0,new_model_loads=0,
        no_truncation=True,paid_api_calls=0,prior_generated_response_files_read=0,
        independent_confirmatory=False,professional_method_efficacy_established=False,
        interpretation='DP is a privileged method-supply diagnostic; RET is actual unchanged visible-query lexical retrieval. RAW/Method differs by normative nonclinical adaptation, not merely compression. Partial coverage and retrieved stop-boundary conflicts are retained.',
        CPU_prepare_seconds=time.monotonic()-started)
    write_once(output/'SUMMARY.json',summary)
    write_once(output/'MANIFEST.json',dict(protocol=PROTOCOL,
        files={str(p.relative_to(output)):file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file() and 'executor' not in p.relative_to(output).parts},
        code_sha256=file_sha256(__file__),admission_sha256=file_sha256(repo/admission),
        source_files_sha256={str(p.resolve()):file_sha256(p) for p in files}))
    return summary

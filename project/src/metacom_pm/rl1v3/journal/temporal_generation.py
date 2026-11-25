"""Materialize all previously frozen explicit-date tasks, without outcome selection.

This CPU proposal does not authorize execution or alter the end-history bank.
Ranking and prompt construction accept no reference/gold/evaluation input.
"""
from collections import Counter
import copy
import json
from pathlib import Path
import time

from ..io import file_sha256, object_sha256, write_json_once, write_jsonl_once
from . import renderer
from .evidence_audit import parse_question_time
from .memory_packages import budget
from .temporal_retrieval import eligible, evidence_coverage, read_rows

ARMS=('RET-v1-filtered', 'Time-Lexical', 'Hybrid')
METHODS={'RET-v1-filtered':'RET-v1-end-history', 'Time-Lexical':'strict-lexical-v1',
         'Hybrid':'strict-hybrid-rrf-v1'}
PROTOCOL='pmrl1-j-explicit-date-generation-proposal-v1'


def legal_selection(task, records, ranking):
    scope=parse_question_time(task['visible_prefix']['turns'][0]['text'])
    if scope['lower'] is None:
        raise ValueError('only the complete pre-existing explicit-date task subset is eligible')
    allowed={r['record_id']:r for r in eligible(records, ranking['owner_id'], scope['lower'])}
    # The legacy sensitivity condition filters its already selected Top4 and
    # never refills it. The other two methods ranked the full legal pool.
    ids=[rid for rid in ranking['selected_record_ids'] if rid in allowed]
    if ranking['method']!='RET-v1-end-history' and ids!=ranking['selected_record_ids']:
        raise ValueError('previous strict ranking contains an illegal source')
    selected=sorted((allowed[rid] for rid in ids),key=lambda r:(r['source_rank'],r['record_id']))
    return scope,selected


def prepare(memory, rankings, template, measurements, model, assets, output):
    from ..generator.g0e_port import PromptTokenizer
    from ..retrieve.native_tokens import NativeTokenizer
    memory,rankings,output=map(Path,(memory,rankings,output))
    output.mkdir(parents=True,exist_ok=False)
    freeze=json.loads((rankings/'RANKING_FREEZE.json').read_text())
    if file_sha256(rankings/'RANKINGS_PRIVATE.jsonl')!=freeze['rankings_sha256'] or freeze['audit_accessed_by_retrieval']:
        raise ValueError('prior retrieval freeze changed')
    tasks=read_rows(memory/'tasks_runtime.jsonl')
    chosen=[t for t in tasks if parse_question_time(t['visible_prefix']['turns'][0]['text'])['lower'] is not None]
    if len(tasks)!=30 or len(chosen)!=8:raise ValueError('frozen complete 30/8 task scope changed')
    selected_ids=[t['task_id'] for t in chosen]
    write_json_once(output/'SELECTION_FROZEN.json',dict(protocol=PROTOCOL,task_ids=selected_ids,
        original_tasks=30,explicit_date_tasks=8,selection='all explicit-date tasks in original file order; no evidence-coverage/outcome filtering',
        arms=ARMS,month_policy='original lower-bound primary; interval ambiguity preserved',
        original_end_history_identity_preserved=True,code_sha256=file_sha256(__file__),
        input_sha256={str(memory/'tasks_runtime.jsonl'):file_sha256(memory/'tasks_runtime.jsonl'),
                      str(rankings/'RANKING_FREEZE.json'):file_sha256(rankings/'RANKING_FREEZE.json')}))
    records=read_rows(memory/'resources_private.jsonl')
    ranks={(r['task_id'],r['method']):r for r in read_rows(rankings/'RANKINGS_PRIVATE.jsonl') if r['bound']=='lower'}
    template=json.loads(Path(template).read_text());baseline=json.loads(Path(template['baseline_path']).read_text())
    tokenizer=PromptTokenizer(NativeTokenizer(model,assets))
    materials=[];requests=[];unique={};deliveries=[]
    for task in chosen:
        question=task['visible_prefix']['turns'][0]['text']
        for arm in ARMS:
            rank=ranks[task['task_id'],METHODS[arm]];start=time.perf_counter()
            scope,sources=legal_selection(task,records,rank)
            filtered_seconds=time.perf_counter()-start
            runtime=copy.deepcopy(task['visible_prefix'])
            notice=('Answer strictly from reports available on or before '+scope['lower']+
                ' (end of day). A report date is not necessarily the date of the event. '
                'If the available reports do not establish the requested fact, say so.\n\n')
            runtime['turns'][0]['text']=notice+question
            reading='\n\n'.join('Completed historical session; reported '+r['reported_at']['date']+':\n'+r['reading_text'] for r in sources)
            identity='strict-date:'+object_sha256(dict(original_task=task['task_id'],scope=scope,cutoff=scope['lower'],protocol=PROTOCOL))
            material=dict(task_id=identity,original_task_id=task['task_id'],arm=arm,visible_prefix=runtime,
                readings=[] if not reading else [dict(head='MS',view='raw',reading_text=reading,reported_at=None)])
            packet,views=renderer.packet(material,tokenizer,baseline_sha256=baseline['binding_sha256'],implementation_sha256=file_sha256(renderer.__file__))
            payload=packet.payload();request_id='temporal:'+packet.payload_sha256
            row=dict(request_id=request_id,logical_id=identity+':'+arm,payload_sha256=packet.payload_sha256,
                task_id=identity,original_task_id=task['task_id'],arm=arm,domain='memory_temporal',
                model_input=payload,input_ids_sha256=object_sha256(payload['input_ids']),input_tokens=len(payload['input_ids']),
                renderer_id=packet.renderer_id,baseline_sha256=packet.baseline_sha256,authorized=False,model_called=False)
            assert list(tokenizer.encode_messages(payload['messages']))==payload['input_ids']
            assert all(r['reported_at']['date']<=scope['lower'] for r in sources)
            requests.append(row);unique.setdefault(request_id,row);materials.append(material)
            deliveries.append(dict(task_id=identity,original_task_id=task['task_id'],arm=arm,scope=scope,cutoff=scope['lower'],
                source_sessions=[r['parent_session_id'] for r in sources],source_records=[r['record_id'] for r in sources],
                source_reports=[r['reported_at']['date'] for r in sources],reading_tokens=sum(v.tokens for v in views),
                input_tokens=len(payload['input_ids']),source_selection_seconds=filtered_seconds,
                original_retrieval_query_seconds=rank['cold_query_seconds'],future_sources=0,native_delivery_exact=True,
                selection='filter frozen original Top4 without refill' if arm==ARMS[0] else 'reuse frozen ranking over full eligible pool',
                original_ranking_identity=rank['retrieval_identity']))
    write_jsonl_once(output/'MATERIALS.private.jsonl',materials)
    write_jsonl_once(output/'DELIVERY.private.jsonl',deliveries)
    write_jsonl_once(output/'REQUESTS_LOGICAL.private.jsonl',requests)
    write_jsonl_once(output/'REQUESTS_UNIQUE.private.jsonl',list(unique.values()))
    batches=[];measure=json.loads(Path(measurements).read_text())
    for i in range(2):
        subset=set(selected_ids[4*i:4*i+4]);logical=[r for r in requests if r['original_task_id'] in subset]
        physical=list({r['request_id']:unique[r['request_id']] for r in logical}.values())
        batch=output/f'batch-{i+1:02d}';batch.mkdir()
        write_jsonl_once(batch/'LOGICAL.private.jsonl',logical);write_jsonl_once(batch/'REQUESTS.private.jsonl',physical)
        proposal=dict(protocol=PROTOCOL,authorized=False,execution_admission='pending separate admission; this is not an executable approval plan',
            task_ids=selected_ids[4*i:4*i+4],logical_arms=12,exact_payload_reuses=12-len(physical),
            requests_sha256=file_sha256(batch/'REQUESTS.private.jsonl'),logical_requests_sha256=file_sha256(batch/'LOGICAL.private.jsonl'),
            proposed_same_generator=baseline['binding_sha256'],proposed_loads=1,warmup=0,retries=0,**budget(physical,measure))
        write_json_once(batch/'PROPOSAL.json',proposal);batches.append(proposal)
    write_json_once(output/'EVALUATION_RULES.json',dict(protocol=PROTOCOL,
        scope='new strict-date tasks; original end-history QA and requests unchanged',
        outcomes=['strict legal atomic completion','use of supplied evidence','unsupported assertions','speaker/date/stage errors',
                  'technical outcome','actual input/output tokens and generation time'],
        reference='existing status_explicit_date; unknown/reference conflict and archive absence stay separate',
        timing='report-date frontier, not proof of event chronology; month lower-bound result remains sensitivity',
        reward_qualified=False,automatic_semantic_labels=False,selection_on_new_outputs=False))
    report=dict(protocol=PROTOCOL,tasks=8,date_days=7,date_month_intervals=1,logical_arms=24,physical_calls=len(unique),
        exact_payload_reuses=24-len(unique),arms=ARMS,batches=batches,native_checks=24,future_sources=0,
        generated_calls=0,authorized=False,original_30_and_220_requests_unchanged=True,
        hypothesis='legal evidence supply may improve answers; lexical engineering baseline, hybrid competitor, neither a frozen winner',
        scope_notice='common strict-date notice added to all three arms under a new identity; original question retained verbatim')
    write_json_once(output/'SUMMARY_PUBLIC.json',report)
    write_json_once(output/'PAYLOAD_FREEZE.json',dict(protocol=PROTOCOL,code_sha256=file_sha256(__file__),
        source_files_sha256={str(p):file_sha256(p) for p in [memory/'tasks_runtime.jsonl',memory/'resources_private.jsonl',rankings/'RANKING_FREEZE.json',rankings/'RANKINGS_PRIVATE.jsonl']},
        output_files_sha256={str(p.relative_to(output)):file_sha256(p) for p in output.rglob('*') if p.is_file()},
        reference_or_gold_read=False,generation_calls=0))
    return report


def evaluate_supply(output,audit):
    output=Path(output);freeze=json.loads((output/'PAYLOAD_FREEZE.json').read_text())
    for name,h in freeze['output_files_sha256'].items():
        if file_sha256(output/name)!=h:raise ValueError('payload freeze changed')
    atoms={r['task_id']:r for r in read_rows(audit)};results=[]
    for row in read_rows(output/'DELIVERY.private.jsonl'):
        atoms_for_task=atoms[row['original_task_id']]['atoms']
        results.append(dict(task_id=row['task_id'],arm=row['arm'],**evidence_coverage(atoms_for_task,row['source_sessions'],'status_explicit_date')))
    write_jsonl_once(output/'SUPPLY_EVALUATION.private.jsonl',results)
    summary={arm:dict(tasks=8,covered_atoms=sum(r['covered_sufficient_groups'] for r in results if r['arm']==arm),
        supported_atoms=sum(r['supported_necessary_atoms'] for r in results if r['arm']==arm),
        statuses=dict(Counter(r['status'] for r in results if r['arm']==arm))) for arm in ARMS}
    write_json_once(output/'SUPPLY_PUBLIC.json',dict(by_arm=summary,scope='all eight preselected date tasks only; not the previous 30-task denominator',
        ranking_or_payload_changed=False,payload_freeze_sha256=file_sha256(output/'PAYLOAD_FREEZE.json'),audit_sha256=file_sha256(audit)))
    return summary

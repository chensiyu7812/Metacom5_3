"""One finite MS action over the existing Time-Lexical Top4 full-session bundle.

This changes the separately identified reading amount, not the source pool,
visible task, frozen policies, generator, or historical Top1 artifacts.
"""
from pathlib import Path
from time import perf_counter
import json
from .. import contracts as K
from ..compile import asof as A
from ..retrieve.v0 import ReadPlan
from ..io import canonical_json, decode_contract, file_sha256, object_sha256, write_json_once, write_jsonl_once
from . import temporal_retrieval
from .runtime_binding import VerifiedEpisode, binding_for, plain
from .selective_memory_validation import VisibleMemoryPort, jl, ARMS, PROTOCOL

READ_PROTOCOL = 'selective-memory-validation-time-lexical-top4-v1'
K_SESSIONS = 4


class TimeLexicalTop4Port(VisibleMemoryPort):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._single_measure = self.reader.measure
        self.reader.measure = self._measure_top4

    @property
    def identity(self):
        result = super().identity
        result['step2_id'] = READ_PROTOCOL+':'+object_sha256(dict(parent=result['step2_id'],
            implementation=file_sha256(__file__), lexical=file_sha256(temporal_retrieval.__file__),
            k=K_SESSIONS, ordering='selected records chronological rank then id'))
        return result

    def _search_visible(self, head):
        candidates = self.bank.candidates(head, self.prefix) if head == 'MS' else ()
        ranked, scores = temporal_retrieval.lexical([plain(r) for r in candidates], self.query)
        result = K.RetrievalResult(head=head, ranked=tuple(K.RankedCandidate(record_id=r['record_id'],
            score=scores[r['record_id']], components=(K.ScoreComponent(name='lexical',
                score=scores[r['record_id']], rank=i+1),)) for i,r in enumerate(ranked)),
            query_identity=object_sha256(dict(query=self.query_sha256, bank=self.bank.version,
                method=READ_PROTOCOL)), filters_applied=('source_integrity','owner','strict_past',
                'reported_time','ready_at','visible_task_query_only'),
            bank_version=self.bank.version,index_version=self.bank.index_version)
        self.private_rankings[head] = plain(result)
        return result

    def _measure_top4(self, head, **kwargs):
        # Preserve all existing argument/version/availability/action validation.
        first = self._single_measure(head, **kwargs)
        if isinstance(first, K.ReadFailure):
            return first
        if head != 'MS':
            raise ValueError('only MS is available')
        ranked = self._search_visible(head)
        selected = sorted((self.bank.by_id[r.record_id] for r in ranked.ranked[:K_SESSIONS]),
            key=lambda r:(r.source_rank,r.record_id))
        text = '\n\n'.join('Completed historical session; reported '+r.reported_at.date+':\n'+r.reading_text for r in selected)
        tokens = self.tokenizer.count(text)
        view = K.ReadingView(head='MS', view='raw', ordinal=first.ordinal, reading_text=text,
            reported_at=None, tokens=tokens, stage=None, expandable=False)
        acquired = tuple(kwargs.get('acquired', ()))
        native = self.tokenizer.prompt_tokens(self.prefix, (*acquired, view))
        after = max(first.input_tokens_before+tokens,
            self.base_tokens+sum(r.tokens for r in acquired)+tokens,native)
        return ReadPlan('MS','raw',text,None,None,first.ordinal,tokens,
            tuple(r.record_id for r in selected),first.input_tokens_before,after,native)


def prepare(*, registry, tokenizer, bundle, base_plan, selection_freeze, out):
    bundle,base_plan,selection_freeze,out=map(Path,(bundle,base_plan,selection_freeze,out))
    freeze=json.loads(selection_freeze.read_text())
    if freeze['k']!=K_SESSIONS or freeze['new_generation_outputs_seen']!=0:
        raise ValueError('pre-generation fixed selection required')
    if freeze['implementation_sha256']!=file_sha256(__file__) or freeze['lexical_sha256']!=file_sha256(temporal_retrieval.__file__):
        raise ValueError('retrieval implementation changed after freeze')
    manifest=json.loads((bundle/'MANIFEST.json').read_text())
    for name in ('TASKS.runtime.jsonl','TASK_ENVELOPES.private.jsonl'):
        if file_sha256(bundle/name)!=manifest['files_sha256'][name]:raise ValueError('runtime input changed')
    tasks=jl(bundle/'TASKS.runtime.jsonl');envelopes={r['task_id']:r for r in jl(bundle/'TASK_ENVELOPES.private.jsonl')}
    base=json.loads(base_plan.read_text());baseline=json.loads(Path(base['baseline_path']).read_text())
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);requests=[];checks=[];readings=[];pools=[]
    for task in tasks:
        envelope=envelopes[task['task_id']]
        if object_sha256(task)!=envelope['visible_task_sha256'] or task!=envelope['visible_task']:
            raise ValueError('task/envelope mismatch')
        prefix=decode_contract(K.PrefixSpec,canonical_json(envelope['actual_prefix']))
        if prefix.runtime_sha256!=envelope['asof_runtime_sha256']:raise ValueError('prefix mismatch')
        registry.context(prefix)
        entries=sorted((e for e in registry.entries if e.source.owner_id==prefix.owner_id
            and registry.reason(e.source_id,prefix) is None),key=lambda e:e.source.chronological_rank)
        writer=PROTOCOL+':full-legal-raw'
        ledger=A.Ledger(out/'ledgers'/task['task_id'].replace(':','-'))
        for entry in entries:ledger.append(A.record_from_source(entry,kind='MS_RAW',writer=writer,subject='session'),registry)
        snapshot=A.materialize(registry,prefix,ledger,writer=writer)
        pools.append(dict(task_id=task['task_id'],owner_id=prefix.owner_id,
            source_session_ids=[e.source.session_id for e in entries],source_ids=[e.source_id for e in entries],
            asof_runtime_sha256=prefix.runtime_sha256,snapshot_sha256=snapshot['snapshot_sha']))
        for arm in ARMS:
            started=perf_counter()
            port=TimeLexicalTop4Port(registry=registry,prefix=prefix,snapshot=snapshot,tokenizer=tokenizer,
                task=task,baseline_sha256=baseline['binding_sha256'])
            binding=binding_for(registry,prefix,snapshot,port)
            episode=VerifiedEpisode(registry=registry,prefix=prefix,snapshot=snapshot,port=port,binding=binding)
            state=episode.reset()
            if arm=='MS':
                state,info=episode.try_step(state,'GET_MS')
                if 'MS' not in state.order:raise ValueError('actual GET rejected: '+str(info))
            terminal,_=episode.try_step(state,'STOP')
            if not terminal.done or episode.stop_value(terminal).status!='pending':raise ValueError('terminal/pending reward')
            _,invalid=episode.try_step(terminal,'GET_MS')
            if invalid.reason!='after_stop':raise ValueError('read after stop')
            views=tuple(r.public_view for r in state.readings);packet=port.tokenizer.make_packet(views);payload=packet.payload()
            selected=[rid for r in state.readings for rid in r.record_ids]
            sources=[port.bank.by_id[r].parent_session_id for r in selected]
            requests.append(dict(domain='selective_memory_validation',task_id=task['task_id'],arm=arm,
                logical_id='selective-memory-validation:'+task['task_id']+':'+arm,
                request_id='jreq:'+packet.payload_sha256,payload_sha256=packet.payload_sha256,
                model_input=payload,input_ids_sha256=object_sha256(payload['input_ids']),input_tokens=len(payload['input_ids']),
                renderer_id=packet.renderer_id,baseline_sha256=baseline['binding_sha256'],task_query_sha256=port.query_sha256,
                source_port_binding_sha256=binding.sha256,authorized=False,model_called=False,
                endpoint_scope='constructed task/query/payload/renderer/evaluation; not original dialogue terminal'))
            checks.append(dict(task_id=task['task_id'],arm=arm,order=list(state.order),actual_input_tokens=len(payload['input_ids']),
                selected_record_ids=selected,selected_source_session_ids=sources,source_port_binding_sha256=binding.sha256,
                asof_runtime_sha256=prefix.runtime_sha256,source_frontier_sha256=snapshot['source_frontier_sha256'],
                after_stop_rejected=True,pending_reward=True,query_is_source_prefix=False,policy_input_contains_evaluation=False,
                retrieval=READ_PROTOCOL,k=K_SESSIONS,whole_sessions=True,truncation=False,
                actual_path_cpu_ms=(perf_counter()-started)*1000,private_rankings=port.private_rankings))
            readings.append(dict(task_id=task['task_id'],arm=arm,selected_record_ids=selected,
                selected_source_session_ids=sources,readings=[plain(v) for v in views]))
    for name,rows in [('REQUESTS_ALL.private.jsonl',requests),('READ_CHECKS.private.jsonl',checks),
                      ('READINGS.private.jsonl',readings),('LEGAL_POOLS.private.jsonl',pools)]:write_jsonl_once(out/name,rows)
    report=dict(protocol=PROTOCOL,retrieval=READ_PROTOCOL,tasks=len(tasks),actual_CPU_paths=len(checks),
        successful_MS_reads=sum(bool(r['selected_record_ids']) for r in checks),
        total_MS_sessions=sum(len(r['selected_record_ids']) for r in checks),
        unique_payloads=len({r['payload_sha256'] for r in requests}),actual_input_tokens=sum(r['input_tokens'] for r in requests),
        input_tokens_by_arm={a:sum(r['input_tokens'] for r in requests if r['arm']==a) for a in ARMS},
        input_tokens_min=min(r['input_tokens'] for r in requests),input_tokens_max=max(r['input_tokens'] for r in requests),
        CPU_paths_seconds=sum(r['actual_path_cpu_ms'] for r in checks)/1000,
        runtime_context_tokens=16384,max_output_tokens=320,actual_model_calls=0,
        parsed_evaluation_for_retrieval=False,sealed_body_read=False,authorized=False,
        selection_freeze_sha256=file_sha256(selection_freeze),
        files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()})
    write_json_once(out/'CPU_READ_SUMMARY.json',report)
    return report

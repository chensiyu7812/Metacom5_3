"""Small task-visible MS+RS adapter over existing As-of, PrefixPort and C0 reads.

The genuine source prefix is a private legality anchor. Retrieval, generation,
public observations and token budgets use only the separate visible task text.
MP/ME remain masked. No evaluation input is accepted by this module.
"""
from dataclasses import replace
from time import perf_counter
from .. import contracts as K
from ..io import object_sha256,file_sha256
from ..retrieve.v0 import words,ReadPlan
from .memory_port import SnapshotPrefixPort
from .renderer import packet
from .runtime_binding import plain

PROTOCOL='pmrl1-j-joint-task-port-v1'


class TaskTokenizer:
    def __init__(self,native,turns,baseline_sha256,renderer_sha256):
        self.native=native;self.identity=native.identity;self.native_context_tokens=16384
        self.turns=tuple(dict(t) for t in turns);self.baseline_sha256=baseline_sha256;self.renderer_sha256=renderer_sha256
    def count(self,text):return self.native.count(text)
    def encode_messages(self,messages):return self.native.encode_messages(messages)
    def make_packet(self,readings=()):
        material=dict(visible_prefix=dict(turns=list(self.turns)),readings=[plain(v) if isinstance(v,K.ReadingView) else dict(
            head=v.head,view=v.view,reading_text=v.reading_text,reported_at=plain(v.reported_at),stage=v.stage) for v in readings])
        return packet(material,self,baseline_sha256=self.baseline_sha256,implementation_sha256=self.renderer_sha256)[0]
    def prompt_tokens(self,_source_prefix,readings):return len(self.make_packet(readings).input_ids)


class JointTaskPort:
    """Canonical STOP/MS/RS/MS→RS reads, with actual full-pool lexical selection."""
    def __init__(self,*,registry,prefix,snapshot,tokenizer,task_id,turns,rs_candidate,baseline_sha256,renderer_sha256):
        if not turns or any(set(t)-{'role','text'} for t in turns):raise ValueError('public turns allowlist')
        if not all(t.get('role') in ('seeker','supporter') and isinstance(t.get('text'),str) for t in turns):raise ValueError('public turn type')
        if turns[-1]['role']!='seeker':raise ValueError('task must end in seeker')
        self.prefix=prefix;self.snapshot=snapshot;self.task_id=task_id;self.turns=tuple(dict(t) for t in turns)
        self.query='\n'.join(t['text'] for t in turns);self.query_sha256=object_sha256(self.turns)
        self.tokenizer=TaskTokenizer(tokenizer,turns,baseline_sha256,renderer_sha256)
        self.rs=dict(rs_candidate)
        if self.rs.get('view')!='method' or not self.rs.get('reading_text') or not self.rs.get('candidate_id'):
            raise ValueError('source-bound RS method required')
        if not self.rs.get('source_sha256') or not self.rs.get('official_url'):raise ValueError('formal RS source binding required')
        self.ms=SnapshotPrefixPort(registry,prefix,snapshot,self.tokenizer,g_id=baseline_sha256,
            decode_id='frozen-G0e',step2_id=PROTOCOL,output_reserve_tokens=320)
        self.private_rankings={}
        # Explicit override: never use original natural-conversation prefix text as query.
        self.ms.reader._search=self._search_ms
        self.bank_version='joint-bank:'+object_sha256(dict(ms=self.ms.bank_version,rs=self.rs))
        self.index_version='joint-index:'+object_sha256(dict(ms=self.ms.index_version,query=self.query_sha256,
            rule='query-overlap, most-recent-source, record-id; single legal RS candidate'))
        self._identity=dict(bank_version=self.bank_version,index_version=self.index_version,
            renderer_id=self.tokenizer.make_packet().renderer_id,
            step2_id=PROTOCOL+':'+object_sha256(dict(task_id=task_id,visible_query=self.query_sha256,code=file_sha256(__file__))),
            g_id=baseline_sha256,decode_id='frozen-G0e')
        self.base_tokens=self.tokenizer.prompt_tokens(prefix,());self.native_context_tokens=16384;self.output_reserve_tokens=320
        self._validated={():self.base_tokens}
        self._plans={}
        self.private_cost=dict(measure_calls=0,measure_cpu_ms=0.0,read_calls=0,read_cpu_ms=0.0,mask_calls=0,unit_calls=0)
    @property
    def identity(self):return dict(self._identity)
    def _search_ms(self,head):
        candidates=self.ms.bank.candidates(head,self.prefix) if head=='MS' else ()
        query_words=words(self.query)
        def score(r):return len(query_words & words(r.reading_text))/max(1,len(query_words))
        ranked=sorted(candidates,key=lambda r:(-score(r),-r.source_rank,r.record_id))
        result=K.RetrievalResult(head=head,ranked=tuple(K.RankedCandidate(record_id=r.record_id,score=score(r),
            components=(K.ScoreComponent(name='lexical',score=score(r),rank=i+1),)) for i,r in enumerate(ranked)),
            query_identity=object_sha256(dict(task_query=self.query_sha256,bank=self.ms.bank_version,head=head)),
            filters_applied=('source_integrity','owner','strict_past','reported_time','ready_at','task_visible_query_only'),
            bank_version=self.ms.bank_version,index_version=self.ms.index_version)
        self.private_rankings[head]=plain(result)
        return result
    def availability(self):return dict(RS=1,MP=0,ME=0,MS=int(bool(self.ms.bank.candidates('MS',self.prefix))))
    def _context(self,acquired):
        acquired=tuple(acquired);stamp=tuple(v.sha256 for v in acquired)
        if stamp not in self._validated:
            past=()
            for v in acquired:
                res=self.read(v.head,acquired=past)
                if not isinstance(res,K.ReadSuccess) or res.reading!=v:raise ValueError('foreign reading rejected')
                past+=(v,)
        return acquired,stamp,self._validated[stamp]
    def measure(self,head,*,acquired=(),input_tokens_before=None,bank_version=None,index_version=None):
        start=perf_counter();self.private_cost['measure_calls']+=1
        try:
            acquired,stamp,before=self._context(acquired)
            def fail(reason,detail):return K.ReadFailure(reason=reason,detail=detail,input_tokens_unchanged=before,elapsed_ms=(perf_counter()-start)*1000)
            if input_tokens_before not in (None,before):return fail('integrity','token_account_mismatch')
            if bank_version not in (None,self.bank_version) or index_version not in (None,self.index_version):return fail('integrity','version_mismatch')
            if head not in ('MS','RS') or head in {v.head for v in acquired}:return fail('invalid_action','masked_or_already_read')
            if head=='MS' and acquired:return fail('invalid_action','canonical_MS_then_RS_only')
            key=(head,stamp,before)
            if key in self._plans:return self._plans[key]
            if head=='MS':
                plan=self.ms.reader.measure('MS')
                if isinstance(plan,K.ReadFailure):return plan
                record_ids=plan.record_ids
                view=K.ReadingView(head='MS',view=plan.view,ordinal=len(acquired)+1,reading_text=plan.reading_text,
                    reported_at=plan.reported_at,tokens=plan.tokens,stage=None,expandable=False)
            else:
                score=len(words(self.query)&words(self.rs['reading_text']))/max(1,len(words(self.query)))
                self.private_rankings['RS']=dict(candidate_count=1,selected=self.rs['candidate_id'],query_sha256=self.query_sha256,
                    lexical_overlap=score,not_multi_candidate_ranking=True,applicability_is_not_legality=True)
                view=K.ReadingView(head='RS',view='method',ordinal=len(acquired)+1,reading_text=self.rs['reading_text'],
                    reported_at=None,tokens=self.tokenizer.count(self.rs['reading_text']),stage=None,expandable=False)
                record_ids=(self.rs['candidate_id'],)
            native=self.tokenizer.prompt_tokens(self.prefix,(*acquired,view))
            after=max(before+view.tokens,native)
            if after+320>16384:return fail('capacity','whole_unit_exceeds_runtime')
            plan=ReadPlan(view.head,view.view,view.reading_text,view.reported_at,view.stage,view.ordinal,
                view.tokens,record_ids,before,after,native)
            self._plans[key]=plan
            return plan
        except (ValueError,AttributeError) as exc:
            return K.ReadFailure(reason='integrity',detail='measurement_integrity:'+str(exc)[:120],input_tokens_unchanged=self.base_tokens,elapsed_ms=(perf_counter()-start)*1000)
        finally:self.private_cost['measure_cpu_ms']+=(perf_counter()-start)*1000
    def read(self,head,*,acquired=(),input_tokens_before=None,bank_version=None,index_version=None):
        start=perf_counter();self.private_cost['read_calls']+=1
        plan=self.measure(head,acquired=acquired,input_tokens_before=input_tokens_before,bank_version=bank_version,index_version=index_version)
        if isinstance(plan,K.ReadFailure):return plan
        view=K.ReadingView(head=plan.head,view=plan.view,ordinal=plan.ordinal,reading_text=plan.reading_text,
            reported_at=plan.reported_at,tokens=plan.tokens,stage=plan.stage,expandable=False)
        elapsed=(perf_counter()-start)*1000;self.private_cost['read_cpu_ms']+=elapsed
        self._validated[(*tuple(v.sha256 for v in acquired),view.sha256)]=plan.input_tokens_after
        return K.ReadSuccess(reading=view,record_ids=plan.record_ids,input_tokens_before=plan.input_tokens_before,
            input_tokens_after=plan.input_tokens_after,native_context_tokens=16384,output_reserve_tokens=320,elapsed_ms=elapsed)
    def action_mask(self,acquired=(),*,input_tokens_before=None):
        self.private_cost['mask_calls']+=1
        return tuple('GET_'+h for h in ('MS','RS') if isinstance(self.measure(h,acquired=acquired,input_tokens_before=input_tokens_before),ReadPlan))+('STOP',)
    def unit_tokens(self,*,acquired=(),input_tokens_before=None):
        self.private_cost['unit_calls']+=1;result={}
        for head in ('MS','RS'):
            plan=self.measure(head,acquired=acquired,input_tokens_before=input_tokens_before)
            if isinstance(plan,ReadPlan):result[head]=plan.input_tokens_after-plan.input_tokens_before
        return result
    def records(self,ids):
        result=self.ms.records(ids)
        if self.rs['candidate_id'] in ids:result[self.rs['candidate_id']]=dict(self.rs)
        return result
    def verify_records(self,ids):
        unknown=[i for i in ids if i!=self.rs['candidate_id'] and i not in self.ms.bank.by_id]
        return ['unknown_resource'] if unknown else self.ms.verify_records(tuple(i for i in ids if i!=self.rs['candidate_id'])) if any(i!=self.rs['candidate_id'] for i in ids) else []
    def public_observation(self,acquired=()):
        _,_,tokens=self._context(acquired)
        return dict(task_id=self.task_id,visible_turns=list(self.turns),readings=[plain(v) for v in acquired],
            availability=self.availability(),action_mask=list(self.action_mask(acquired)),input_tokens=tokens,
            source_prefix_body_exposed=False,unread_candidate_text_exposed=False,private_scores_exposed=False)


from .runtime_binding import VerifiedEpisode
from ..env import research_v32 as R

class JointTaskEpisode(VerifiedEpisode):
    """Use original C0 transitions, with separately bound external RS evidence."""
    def try_step(self,state,action):
        self._validate_current()
        result,info=R.BoundEpisode.try_step(self,state,action)
        if action.startswith('GET_') and not isinstance(info,R.Invalid):
            read=result.readings[-1]
            if action=='GET_MS':
                legal={v['record'].record_id:v['record'] for v in self.snapshot['views'] if v['disposition']=='raw_available'}
                if any(rid not in legal or legal[rid].text not in read.reading_text for rid in read.record_ids):
                    raise R.BindingMismatch('MS read not grounded in actual snapshot')
            elif action=='GET_RS':
                if (self.binding.external_snapshot!=object_sha256(self.port.rs) or
                    read.record_ids!=(self.port.rs['candidate_id'],) or read.reading_text!=self.port.rs['reading_text']):
                    raise R.BindingMismatch('RS read not grounded in bound external procedure')
            else:raise R.BindingMismatch('MP/ME masked in joint task')
        return result,info
    def observe(self,state,**_kwargs):
        return self.port.public_observation(self.env.readings(state))

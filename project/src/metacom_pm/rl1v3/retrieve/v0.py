"""Filter first, static lexical ordering, one complete unit; no relation expansion."""
from __future__ import annotations
import re
from time import perf_counter
from functools import lru_cache
from .. import contracts as K
from ..io import object_sha256
from ..bank.bank_v0 import RENDERER_ID
from ..render.v0 import SYSTEM

@lru_cache(maxsize=10000)
def words(text):return frozenset(re.findall(r"[a-z0-9']+",text.casefold()))


def search(bank,head,prefix):
    candidates=bank.candidates(head,prefix)
    query='\n'.join(t.text for t in prefix.turns[-3:]);query_words=words(query)
    def score(r):return len(query_words & words(r.reading_text))/max(1,len(query_words))
    def key(r):
        # Explicit resource-specific deterministic v0 tie-breaks, not learned utility.
        if head=='RS':return (-score(r),r.record_id)
        return (-score(r),-r.source_rank,r.record_id)
    ranked=sorted(candidates,key=key)
    return K.RetrievalResult(head=head,ranked=tuple(K.RankedCandidate(record_id=r.record_id,score=score(r),
        components=(K.ScoreComponent(name='lexical',score=score(r),rank=i+1),)) for i,r in enumerate(ranked)),
        query_identity=object_sha256(dict(prefix_context=prefix.runtime_sha256,head=head,query=query,
            bank=bank.version,index=bank.index_version,mode='static')),
        filters_applied=('source_integrity','owner','strict_past','reported_time','ready_at','family_closure',
            'train_only_RS','review','no_unverified_relation_propagation'),bank_version=bank.version,index_version=bank.index_version)


class Reader:
    """Stateless read executor; caller supplies successful readings explicitly.

    Failed reads never mutate bank, caller state, or ordinal. input_tokens_after
    is conservative billing max(actual native full prompt, additive unit bill).
    `last native prompt` is separately inspectable using tokenizer.prompt_tokens.
    """
    def __init__(self,bank,prefix,tokenizer,*,g_id,decode_id,step2_id='none-v0-read-replay',output_reserve_tokens=320):
        self.bank,self.prefix,self.tokenizer=bank,prefix,tokenizer
        self.g_id,self.decode_id,self.step2_id=g_id,decode_id,step2_id
        if output_reserve_tokens<=0:raise ValueError('output reserve must be positive')
        self.output_reserve_tokens=output_reserve_tokens
        self.renderer_id='renderer:'+object_sha256(dict(protocol=RENDERER_ID,tokenizer=tokenizer.identity,
            system=SYSTEM,output_reserve_tokens=output_reserve_tokens,order='canonical_head_order',escaping='html'))
        self.base_tokens=tokenizer.prompt_tokens(prefix,())

    @property
    def identity(self):
        return dict(bank_version=self.bank.version,index_version=self.bank.index_version,renderer_id=self.renderer_id,
                    step2_id=self.step2_id,g_id=self.g_id,decode_id=self.decode_id)

    def _billed(self,acquired):
        return max(self.tokenizer.prompt_tokens(self.prefix,acquired),self.base_tokens+sum(r.tokens for r in acquired))

    def _failure(self,reason,detail,before,started):
        return K.ReadFailure(reason=reason,detail=detail,input_tokens_unchanged=before,
                             elapsed_ms=(perf_counter()-started)*1000)

    def read(self,head,*,acquired=(),bank_version=None,index_version=None):
        start=perf_counter();before=self._billed(acquired)
        fail=lambda reason,detail:self._failure(reason,detail,before,start)
        if head not in K.HEAD_ORDER:return fail('invalid_action','v0 supports GET_RS/MP/ME/MS only')
        if tuple(r.ordinal for r in acquired)!=tuple(range(1,len(acquired)+1)) or len({r.head for r in acquired})!=len(acquired):
            return fail('invalid_action','invalid acquired sequence')
        if head in {r.head for r in acquired}:return fail('invalid_action','Phase-1 head already read')
        if (bank_version and bank_version!=self.bank.version) or (index_version and index_version!=self.bank.index_version):
            return fail('integrity','version_mismatch')
        if not self.bank.records:return fail('empty','empty_bank')
        try:result=search(self.bank,head,self.prefix)
        except (ValueError,KeyError) as exc:return fail('integrity','source_or_prefix_integrity: '+str(exc))
        if not result.ranked:return fail('unavailable','no_legal_candidates')
        record=self.bank.by_id[result.ranked[0].record_id]
        stamp=record.reported_at.date if record.reported_at and record.reported_at.date else 'unknown'
        text=f'[{record.head}; reported {stamp}'+(f'; stage {record.stage}' if record.stage else '')+']\n'+record.reading_text
        tokens=self.tokenizer.count(text)
        if tokens<=0:return fail('empty','empty_native_tokenization')
        view=K.ReadingView(head=head,view=record.view,ordinal=len(acquired)+1,reading_text=text,
            reported_at=record.reported_at,tokens=tokens,stage=record.stage,expandable=False)
        after=max(before+tokens,self._billed((*acquired,view)))
        if after+self.output_reserve_tokens>self.tokenizer.native_context_tokens:
            return fail('capacity','whole_unit_exceeds_native_context; no truncation or lower-rank substitution')
        return K.ReadSuccess(reading=view,record_ids=(record.record_id,),input_tokens_before=before,
            input_tokens_after=after,native_context_tokens=self.tokenizer.native_context_tokens,
            output_reserve_tokens=self.output_reserve_tokens,elapsed_ms=(perf_counter()-start)*1000)

    def availability(self):
        return {head:len(self.bank.candidates(head,self.prefix)) for head in K.HEAD_ORDER}

    def action_mask(self,acquired=()):
        # Pool count remains independent of capacity. GET mask additionally checks capacity.
        return tuple('GET_'+h for h in K.HEAD_ORDER if isinstance(self.read(h,acquired=acquired),K.ReadSuccess))+('STOP',)

    def terminal_key(self,results):
        return K.TerminalKey.for_prefix(self.prefix,domain_id='finite_head_v1',
            ordered_path=tuple('GET_'+r.reading.head for r in results)+('STOP',),
            acquired=tuple(r.record_ids for r in results),**self.identity)

    def replay(self,key):
        start=perf_counter();fail=lambda reason,msg:self._failure(reason,msg,self.base_tokens,start)
        if key.owner_id!=self.prefix.owner_id:return fail('owner','terminal_owner_mismatch')
        if key.prefix_id!=self.prefix.prefix_id or key.prefix_context_sha256!=self.prefix.runtime_sha256:
            return fail('integrity','terminal_prefix_mismatch')
        if key.domain_id!='finite_head_v1' or any(getattr(key,k)!=v for k,v in self.identity.items()):
            return fail('integrity','terminal_version_mismatch')
        results=[]
        for action,group in zip(key.ordered_path[:-1],key.acquired):
            res=self.read(action[4:],acquired=tuple(r.reading for r in results))
            if isinstance(res,K.ReadFailure):return res
            if res.record_ids!=group:return fail('integrity','terminal_record_group_mismatch')
            results.append(res)
        trace=K.ExecutionTrace(domain_id='finite_head_v1',ordered_path=key.ordered_path,
            acquired=tuple(r.record_ids for r in results),readings=tuple(r.reading for r in results))
        trace.verify_key(key);return trace


def read(reader,head,**kwargs):return reader.read(head,**kwargs)

"""G0e extension over A's unchanged bank-v0 port. No weight/model load."""
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter

from .. import contracts as K
from ..bank.v0_port import PrefixPort, PortFactory, load_bank
from ..render.request_packet import messages, request_packet
from ..retrieve.native_tokens import NativeTokenizer
from .g0e import load_binding


class PromptTokenizer:
    def __init__(self, native):
        self.native = native
        self.identity = native.identity
        self.native_context_tokens = native.native_context_tokens

    def count(self, text): return self.native.count(text)
    def encode_messages(self, msgs):
        ids = self.native.tokenizer.apply_chat_template(msgs, tokenize=True,
            add_generation_prompt=True, enable_thinking=False)
        if isinstance(ids, Mapping): ids = ids['input_ids']
        if ids and isinstance(ids[0], (list,tuple)):
            if len(ids) != 1: raise ValueError('unexpected multiple tokenizer batches')
            ids = ids[0]
        if not ids or any(type(x) is not int or x < 0 for x in ids):
            raise ValueError('invalid native input token sequence')
        return tuple(ids)
    def prompt_tokens(self, prefix, readings):
        # Private pre-GET sizing only. A plan never escapes as a successful view.
        from ..retrieve.v0 import ReadPlan
        views = tuple(K.ReadingView(head=v.head, view=v.view, ordinal=v.ordinal,
            reading_text=v.reading_text, reported_at=v.reported_at, tokens=v.tokens,
            stage=v.stage, expandable=False) if isinstance(v, ReadPlan) else v for v in readings)
        return len(self.encode_messages(messages(prefix,views)))


class G0ePrefixPort(PrefixPort):
    protocol = 'pmrl1v3-g0e-read-port-1'

    def __init__(self, bank, prefix, tokenizer, binding):
        if tokenizer.identity != binding.spec['tokenizer_identity']:
            raise ValueError('tokenizer identity differs from G0e binding')
        if tokenizer.native_context_tokens != binding.spec['model']['native_context_tokens']:
            raise ValueError('native context differs from G0e binding')
        self.binding = binding
        identity = dict(binding.identity); identity.pop('renderer_id')
        super().__init__(bank,prefix,tokenizer,**identity,output_reserve_tokens=320)
        self.reader.renderer_id = binding.renderer_id
        self.effective_context_tokens = min(self.native_context_tokens,binding.spec['runtime']['max_model_len'])

    def read(self, head, *, acquired=(), input_tokens_before=None, **versions):
        start = perf_counter()
        if any(versions.get(k) not in (None, getattr(self,k)) for k in ('bank_version','index_version')):
            return super().read(head,acquired=acquired,input_tokens_before=input_tokens_before,**versions)
        try:
            views,before,stamp = self._context(acquired,input_tokens_before)
        except ValueError:
            return super().read(head,acquired=acquired,input_tokens_before=input_tokens_before,**versions)
        plan = self._plan(head,views,before,stamp)
        if not isinstance(plan,K.ReadFailure) and plan.input_tokens_after+320 > self.effective_context_tokens:
            return K.ReadFailure(reason='capacity',detail='G0e runtime context exceeded; no truncation',
                input_tokens_unchanged=before,elapsed_ms=(perf_counter()-start)*1000)
        return super().read(head,acquired=views,input_tokens_before=before,**versions)

    def replay(self, key):
        fail = lambda why: K.ReadFailure(reason='integrity',detail=why,
            input_tokens_unchanged=self.base_tokens,elapsed_ms=0.0)
        if (key.domain_id!='finite_head_v1' or key.owner_id!=self.prefix.owner_id or
            key.prefix_id!=self.prefix.prefix_id or key.prefix_context_sha256!=self.prefix.runtime_sha256 or
            any(getattr(key,k)!=v for k,v in self.identity.items())):
            return fail('terminal_prefix_or_version_mismatch')
        results = []
        for action, group in zip(key.ordered_path[:-1],key.acquired):
            res = self.read(action[4:],acquired=tuple(r.reading for r in results))
            if isinstance(res,K.ReadFailure): return res
            if res.record_ids!=group: return fail('terminal_record_group_mismatch')
            results.append(res)
        trace = self.execution_trace(results); trace.verify_key(key)
        return trace

    def request_packet(self, acquired=()): return request_packet(self.prefix,acquired,port=self)


class G0eFactory(PortFactory):
    def __init__(self, bank, tokenizer, binding):
        self.binding = binding
        identity = dict(binding.identity); identity.pop('renderer_id')
        super().__init__(bank,tokenizer,dict(identity,output_reserve_tokens=320))
    def for_prefix(self, prefix): return G0ePrefixPort(self.bank,prefix,self.tokenizer,self.binding)


def make_port_factory(*, root=None, backend='hf'):
    root = Path(root) if root else Path(__file__).resolve().parents[5]
    binding = load_binding(root,backend=backend)
    bank,cfg = load_bank(root)
    native = NativeTokenizer(cfg['tokenizer_model'],root/cfg['asset_manifest'])
    return G0eFactory(bank,PromptTokenizer(native),binding)

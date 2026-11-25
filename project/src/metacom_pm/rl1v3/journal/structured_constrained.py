"""One format-only diagnostic; no task, reference, or answer values are inputs.

XGrammar compiles the static JSON structure on CPU. Native torch masks scores,
avoiding a new Triton kernel. All EOS IDs remain unchanged and are allowed only
at a grammar-complete boundary. Semantic fields remain unrestricted strings.
"""
import time

PROTOCOL='structured-format-only-xgrammar-cpu-mask-v1'
SCHEMA={
    'type':'object',
    'properties':{k:{'type':'string'} for k in ('value','certainty','quote','speaker')},
    'required':['value','certainty','quote','speaker','reported_date'],
    'additionalProperties':False,
}
SCHEMA['properties']['reported_date']={'type':['string','null']}


def compile_grammar(tokenizer,*,vocab_size,eos_token_ids):
    import xgrammar as xg
    info=xg.TokenizerInfo.from_huggingface(tokenizer,vocab_size=vocab_size,stop_token_ids=eos_token_ids)
    return xg.GrammarCompiler(info,max_threads=1).compile_json_schema(SCHEMA,any_whitespace=True)


class StructuredConstrainedProcessor:
    """Fresh matcher per request; greedy single sequence only, as frozen G0e."""
    def __init__(self,compiled):
        import torch
        import xgrammar as xg
        self.torch=torch;self.xg=xg;self.vocab_size=compiled.tokenizer_info.vocab_size
        self.matcher=xg.GrammarMatcher(compiled)
        self.bitmask=xg.allocate_token_bitmask(1,self.vocab_size)
        self.shifts=torch.arange(32,dtype=torch.int64)
        self.prefilled=False;self.calls=0;self.cpu_seconds=0.0

    def __call__(self,input_ids,scores):
        if input_ids.shape[0]!=1 or tuple(scores.shape)!=(1,self.vocab_size):
            raise ValueError('constrained diagnostic requires one exact full-vocabulary sequence')
        t=time.monotonic()
        if self.prefilled:
            if not self.matcher.accept_token(int(input_ids[0,-1])):
                raise ValueError('generated token violates grammar; no repair/retry')
        else:self.prefilled=True
        self.matcher.fill_next_token_bitmask(self.bitmask)
        allowed=((self.bitmask.to(self.torch.int64).unsqueeze(-1)>>self.shifts)&1).flatten()[:self.vocab_size].bool()
        if not bool(allowed.any()):raise ValueError('grammar has no next token; stop without repair')
        self.cpu_seconds+=time.monotonic()-t;self.calls+=1
        return scores.masked_fill(~allowed.to(scores.device).unsqueeze(0),float('-inf'))

    def measurement(self):
        return dict(mask_calls=self.calls,cpu_mask_seconds=self.cpu_seconds,
            timing_scope='CPU matcher/mask only; score-device transfer/masking is in full generation time')

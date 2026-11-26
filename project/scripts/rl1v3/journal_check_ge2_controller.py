#!/usr/bin/env python3
"""Finite native GE2 syntax/decode replay on CPU; zero model construction."""
import argparse
import inspect
import json
import os
from pathlib import Path
import sys
import time


def run(model, vendor, out):
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '':
        raise RuntimeError('CUDA_VISIBLE_DEVICES must be empty')
    sys.path.insert(0, str(Path(vendor).resolve()))
    import torch
    import xgrammar as xg
    from transformers import AutoTokenizer, AutoConfig, GenerationConfig
    from transformers.generation.utils import GenerationMixin
    from transformers.generation.logits_process import LogitsProcessorList
    from transformers.generation.stopping_criteria import StoppingCriteriaList
    from metacom_pm.rl1v3.io import file_sha256, object_sha256, write_json_once
    from metacom_pm.rl1v3.generator.g0e import DECODE
    from metacom_pm.rl1v3.journal import ge2_controller as C
    torch.set_num_threads(1)
    assert not torch.cuda.is_initialized()
    started = time.monotonic_ns()
    tok = AutoTokenizer.from_pretrained(model, local_files_only=True, trust_remote_code=False)
    config = AutoConfig.from_pretrained(model, local_files_only=True, trust_remote_code=False)
    vocab = config.text_config.vocab_size
    assert vocab == len(tok) == 262144
    grammars = {role:C.compile_grammar(role,tok,vocab_size=vocab,eos_token_ids=DECODE['eos_token_id']) for role in C.ROLES}
    class CPUFacade(GenerationMixin):
        def __init__(self):
            self.config = config
    facade = CPUFacade()
    state = dict(status='unassessed', information_gap='Synthetic scope; no source or reference answer.')
    search = dict(action='SEARCH',query='new semantic activity status 中文',unread_only=True)
    stop = dict(action='STOP')
    handle = 'ge2:'+'a'*24+':v12'
    fixtures = [
        ('LLMOneShot',dict(evidence_state=state,actions=[stop])),
        ('LLMOneShot',dict(evidence_state=state,actions=[search,dict(action='EXPAND',scope='parent',from_search=0,hit_rank=3),stop])),
        ('LLMToolAgent',dict(evidence_state=state,action=stop)),
        ('LLMToolAgent',dict(evidence_state=state,action=search)),
        ('LLMToolAgent',dict(evidence_state=state,action=dict(action='EXPAND',scope='neighbor',handle=handle))),
    ]
    receipts=[];steps=0;minimum=vocab;processor_names=None
    for role, value in fixtures:
        text=json.dumps(value,ensure_ascii=False,separators=(',',':'))
        assert C.parse(text,role)==value
        encoded=tok.encode(text,add_special_tokens=False)
        assert len(encoded)+1<=768
        for eos in DECODE['eos_token_id']:
            matcher=xg.GrammarMatcher(grammars[role])
            assert all(matcher.accept_token(i) for i in encoded+[eos]) and matcher.is_terminated()
        obs=dict(protocol='synthetic-no-source',turns=[dict(role='seeker',text='Visible synthetic task')],
                 action_mask=['STOP','SEARCH','EXPAND'],hits=[dict(handle=handle)])
        prompt=list(tok.apply_chat_template(C.messages(obs,role),tokenize=True,add_generation_prompt=True,
                                           enable_thinking=False,return_dict=False))
        grammar_processor=C.ControllerConstraintProcessor(grammars[role],prompt_length=len(prompt))
        decode=C.controller_decode(DECODE,role,768)
        gc=GenerationConfig.from_pretrained(model,local_files_only=True)
        for key,value_ in decode.items():
            if key not in ('seed','enable_thinking'):setattr(gc,key,value_)
        gc.max_length=len(prompt)+gc.max_new_tokens
        facade._prepare_special_tokens(gc,kwargs_has_attention_mask=True,device='cpu',batch_size=1)
        processors=facade._get_logits_processor(gc,input_ids_seq_length=len(prompt),
            logits_processor=LogitsProcessorList([grammar_processor]),device='cpu')
        criteria=facade._get_stopping_criteria(gc,StoppingCriteriaList(),tokenizer=tok)
        names=[type(p).__name__ for p in processors]
        if processor_names is None:processor_names=names
        assert names==processor_names and 'NoRepeatNGramLogitsProcessor' not in names
        generated=[]
        for token in encoded+[106]:
            inputs=torch.tensor([prompt+generated],device='cpu')
            masked=processors(inputs,torch.zeros((1,vocab),device='cpu'))
            finite=torch.isfinite(masked);count=int(finite.sum())
            assert count>0 and bool(finite[0,token])
            assert all(torch.isneginf(masked[0,i]) for i in decode['suppress_tokens'])
            assert all(bool(finite[0,i])==(token==106) for i in decode['eos_token_id'])
            minimum=min(minimum,count);steps+=1;generated.append(token)
            assert bool(criteria(torch.tensor([prompt+generated]),masked)[0])==(token==106)
        assert grammar_processor.finalize(generated)['grammar_terminated']
        # The remaining-token contract changes length only; no new token quota.
        shortened=C.controller_decode(DECODE,role,17)
        assert shortened['max_new_tokens']==17 and shortened['no_repeat_ngram_size']==0
        assert {k:v for k,v in shortened.items() if k not in ('max_new_tokens','no_repeat_ngram_size')}=={
            k:v for k,v in DECODE.items() if k not in ('max_new_tokens','no_repeat_ngram_size')}
        receipts.append(dict(role=role,fixture_sha256=object_sha256(value),output_tokens=len(generated),
                             all_eos_reachable=True,finite_composed_path=True))
    assert not torch.cuda.is_initialized()
    result=dict(protocol='pmrl1-j-ge2-native-controller-cpu-v1',status='PASS',fixtures=len(fixtures),
        eos_witnesses=len(fixtures)*len(DECODE['eos_token_id']),native_mask_steps=steps,
        minimum_finite_logits=minimum,processor_order=processor_names,vocab_size=vocab,
        grammar_schema_sha256=object_sha256(C.protocol_contract()),controller_code_sha256=file_sha256(C.__file__),
        script_sha256=file_sha256(__file__),generation_utils_sha256=file_sha256(inspect.getfile(GenerationMixin)),
        cpu_seconds=(time.monotonic_ns()-started)/1e9,model_loads=0,model_forward_calls=0,gpu_calls=0,
        cuda_initialized=False,synthetic_fixture_not_model_output=True,rows=receipts,
        scope='Finite native-token grammar/HF processor witness paths only; not all prefixes or GPU numeric behavior.',
        formal_reward=None)
    write_json_once(out,result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('model','vendor','out'):p.add_argument('--'+key,required=True)
    run(**vars(p.parse_args()))

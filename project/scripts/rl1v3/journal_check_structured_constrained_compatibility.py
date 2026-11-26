#!/usr/bin/env python3
"""CPU-only composition check of the frozen HF decode and grammar processors.

No model construction/weights/forward or GPU calls. Imports the already frozen
packages-v3 runtime verbatim; writes a new receipt, never modifies that package.
"""
import argparse,hashlib,inspect,json,os,sys,time
from pathlib import Path


def check_compatibility(package,out):
    package,out=Path(package).resolve(),Path(out).resolve()
    if os.environ.get('CUDA_VISIBLE_DEVICES')!='':raise RuntimeError('require CUDA_VISIBLE_DEVICES empty')
    sys.path[:0]=[str(package/'executor/project/src'),str(package/'executor/vendor_constrained')]
    import torch
    from transformers import AutoTokenizer,AutoConfig,AutoModelForMultimodalLM,GenerationConfig
    from transformers.generation.utils import GenerationMixin
    from transformers.generation.logits_process import LogitsProcessorList
    from transformers.generation.stopping_criteria import StoppingCriteriaList
    from metacom_pm.rl1v3.journal.structured_constrained_run import check
    from metacom_pm.rl1v3.journal.structured_constrained import compile_grammar,StructuredConstrainedProcessor
    from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once
    torch.set_num_threads(1)
    if torch.cuda.is_initialized():raise RuntimeError('unexpected CUDA initialization')
    catalog_sha=file_sha256(package/'CATALOG_CONSTRAINED.json')
    if catalog_sha!='0574640d2be436b410bc6f5aca236218d4a4f5f4a313f634b5f5b5c2bf08289c':raise RuntimeError('wrong approved package')
    plans=[check(package/f'batch-{n:02d}/PLAN_CONSTRAINED.json') for n in (1,2)]
    model_path=plans[0][0]['model_path']
    tok=AutoTokenizer.from_pretrained(model_path,local_files_only=True,trust_remote_code=False)
    config=AutoConfig.from_pretrained(model_path,local_files_only=True,trust_remote_code=False)
    # Resolve the real class only; never instantiate it or load weights.
    model_class=AutoModelForMultimodalLM._model_mapping[type(config)]
    for name in ('_get_logits_processor','_get_stopping_criteria','_prepare_special_tokens'):
        if getattr(model_class,name) is not getattr(GenerationMixin,name):raise RuntimeError('model overrides HF helper: '+name)
    class CPUFacade(GenerationMixin):
        def __init__(self,configuration):self.config=configuration
    facade=CPUFacade(config)
    decode=plans[0][1][0]['model_input']['decode'];eos=decode['eos_token_id'];suppress=decode['suppress_tokens']
    assert not set(eos)&set(suppress)
    vocab=config.text_config.vocab_size;assert vocab==len(tok)==262144
    grammar=compile_grammar(tok,vocab_size=vocab,eos_token_ids=eos)
    tasks={r['task_id']:r for r in map(json.loads,Path(plans[0][0]['task_manifest_path']).read_text().splitlines())}
    scores=torch.linspace(-3,3,vocab).reshape(1,-1)
    step_count=0;witness_count=0;minimum_finite=vocab;rows_receipt=[];processor_names=None;criteria_names=None
    start=time.monotonic()

    def builders(row):
        nonlocal processor_names,criteria_names
        payload=row['model_input'];assert payload['decode']==decode
        gc=GenerationConfig.from_pretrained(model_path,local_files_only=True)
        for k,v in payload['decode'].items():
            if k not in {'seed','enable_thinking'}:setattr(gc,k,v)
        # HF's max_new_tokens precedence yields this exact effective max_length.
        gc.max_length=len(payload['input_ids'])+gc.max_new_tokens
        facade._prepare_special_tokens(gc,kwargs_has_attention_mask=True,device='cpu',batch_size=1)
        processors=facade._get_logits_processor(gc,input_ids_seq_length=len(payload['input_ids']),
            logits_processor=LogitsProcessorList([StructuredConstrainedProcessor(grammar)]),device='cpu')
        criteria=facade._get_stopping_criteria(gc,StoppingCriteriaList(),tokenizer=tok)
        names=[type(p).__name__ for p in processors];stops=[type(p).__name__ for p in criteria]
        if processor_names is None:processor_names,criteria_names=names,stops
        assert names==processor_names and stops==criteria_names
        assert names==['SuppressTokensLogitsProcessor','StructuredConstrainedProcessor']
        assert stops==['MaxLengthCriteria','EosTokenCriteria']
        assert gc.do_sample is False and gc.num_beams==1 and gc.repetition_penalty==1.0
        assert gc.max_new_tokens==320 and gc.eos_token_id==eos and gc.suppress_tokens==suppress
        return processors,criteria

    for plan,rows,_ in plans:
        for row in rows:
            prompt=row['model_input']['input_ids']
            actual=tok.apply_chat_template(row['model_input']['messages'],tokenize=True,add_generation_prompt=True,
                enable_thinking=False,return_dict=False)
            assert list(actual)==prompt
            choices=tasks[row['task_id']]['choices'];row_min=vocab;row_steps=0
            for value in choices:
                # Values are already in the visible prompt; all other fields synthetic.
                sample=dict(value=value,certainty='synthetic',quote='Unicode 中文; "quoted"; slash \\; line\n.',
                    speaker='synthetic',reported_date=None)
                ids=tok.encode(json.dumps(sample,ensure_ascii=False,separators=(',',':')),add_special_tokens=False)
                assert len(ids)+1<=320
                processors,criteria=builders(row);generated=[]
                for token in ids+[106]:
                    inputs=torch.tensor([prompt+generated]);masked=processors(inputs,scores.clone())
                    finite=torch.isfinite(masked);count=int(finite.sum())
                    assert count>0 and not torch.isnan(masked).any() and not torch.isposinf(masked).any()
                    assert bool(finite[0,token]) and all(torch.isneginf(masked[0,s]) for s in suppress)
                    if token in eos:assert all(bool(finite[0,e]) for e in eos)
                    else:assert all(torch.isneginf(masked[0,e]) for e in eos)
                    row_min=min(row_min,count);minimum_finite=min(minimum_finite,count)
                    generated.append(token);row_steps+=1;step_count+=1
                    assert bool(criteria(torch.tensor([prompt+generated]),masked)[0])==(token in eos)
                witness_count+=1
            _,criteria=builders(row)
            # Independent hard-length test, with a non-EOS trailing token.
            normal_id=tok.encode('x',add_special_tokens=False)[0];assert normal_id not in eos
            assert not bool(criteria(torch.tensor([prompt+[normal_id]*319]),scores)[0])
            assert bool(criteria(torch.tensor([prompt+[normal_id]*320]),scores)[0])
            assert all(bool(criteria(torch.tensor([prompt+[e]]),scores)[0]) for e in eos)
            rows_receipt.append(dict(task_id=row['task_id'],arm=row['arm'],request_id=row['request_id'],
                input_ids_identical=True,witnesses=len(choices),tested_steps=row_steps,minimum_finite_logits=row_min,
                suppression_preserved=True,eos_complete_boundary_preserved=True,length_320_stop=True))
    assert torch.cuda.is_initialized() is False
    result=dict(protocol='sc36-frozen-composed-logits-cpu-check-v1',status='PASS',
        catalog_sha256=catalog_sha,plan_sha256=[object_sha256(p) for p,_,_ in plans],
        model_class=model_class.__name__,model_instantiated=False,model_loads=0,gpu_calls=0,cuda_initialized=False,
        vocab_size=vocab,processor_order=processor_names,stopping_criteria=criteria_names,
        suppress_token_ids=suppress,eos_token_ids=eos,suppress_eos_intersection=[],
        requests=len(rows_receipt),witnesses=witness_count,mask_steps=step_count,minimum_finite_logits=minimum_finite,
        full_decode_sha256=object_sha256(decode),cpu_replay_seconds=time.monotonic()-start,
        hf_generation_utils_sha256=file_sha256(inspect.getfile(GenerationMixin)),
        script_sha256=file_sha256(__file__),rows=rows_receipt,
        scope='Finite reachable-prefix CPU composition test with finite synthetic logits; no model forward, GPU numerical behavior or all possible grammar prefixes proved.',
        official_api='https://huggingface.co/docs/transformers/v5.17.0/en/internal/generation_utils')
    assert file_sha256(package/'CATALOG_CONSTRAINED.json')==catalog_sha
    write_json_once(out,result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();check_compatibility(args.package,args.out)

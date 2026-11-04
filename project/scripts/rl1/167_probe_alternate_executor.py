#!/usr/bin/env python3
"""One local alternate-G probe, exact old messages, no training or reward."""
import argparse
from dataclasses import asdict
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.calibration_workflow import stamp,verify_identity
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.generation import NaturalEndPolicy
from metacom_pm.rl1.local_gpu_guard import LocalGPUCheck
from metacom_pm.rl1.schema import digest
BASE=PROJECT/'outputs/pm_rl1';PRIOR=BASE/'resource_value_probe_20261104_v1'
MODEL=Path('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3')


def read(p):return json.loads(p.read_text())


def prepare(out):
    from transformers import AutoTokenizer
    if out.exists():raise ValueError('new fixed package required')
    for name,h in read(PRIOR/'OUTPUT_MANIFEST.json').items():assert sha(PRIOR/name)==h
    inputs=read(PRIOR/'INPUTS_PRIVATE.json');cards=read(PRIOR/'CARDS_PRIVATE.json')
    originals=read(PRIOR/'RESULTS_PRIVATE.json');keys=list(dict.fromkeys(c['input_identity'] for c in cards))
    assert len(keys)==len(inputs)==36 and len(cards)==41
    tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    config=read(MODEL/'config.json');gc=read(MODEL/'generation_config.json')
    policy=NaturalEndPolicy(config['text_config']['max_position_embeddings'],tuple(gc['eos_token_id']))
    tokenized={}
    for key in keys:
        messages=inputs[key]['messages']
        a=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
        b=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
        assert a==b and 0<len(a)<policy.context_limit
        tokenized[key]=dict(input_tokens=len(a),token_ids_identity=digest(a))
    files=[p for p in MODEL.iterdir() if p.is_file()]
    code=[Path(__file__),PROJECT/'src/metacom_pm/rl1/generation.py',PROJECT/'src/metacom_pm/rl1/local_gpu_guard.py',
          PROJECT/'src/metacom_pm/rl1/durable.py']
    runtime=stamp(dict(model_dir=str(MODEL),model_files={p.name:sha(p) for p in files},
        model_class='AutoModelForMultimodalLM',dtype='bfloat16',attention='sdpa',adapter=None,
        packages={p:importlib.metadata.version(p) for p in ('torch','transformers','tokenizers','safetensors')},
        cuda_visible_devices='1',cuda_device_order='PCI_BUS_ID',policy=asdict(policy),
        enable_thinking=False,seed=0,do_sample=False,pad_token_id=tokenizer.pad_token_id,
        native_suppress_tokens=gc.get('suppress_tokens'),chat_template_identity=digest(tokenizer.chat_template)))
    requests=[]
    for key in keys:
        item=inputs[key]
        requests.append(stamp(dict(input_identity=key,messages=item['messages'],messages_identity=digest(item['messages']),
            selected_keys=item['selected_keys'],selected_resource_identities=item['selected_resource_identities'],
            runtime_identity=runtime['identity'],**tokenized[key])))
    sources=[PRIOR/'OUTPUT_MANIFEST.json',PRIOR/'INPUTS_PRIVATE.json',PRIOR/'CARDS_PRIVATE.json',PRIOR/'RESULTS_PRIVATE.json',
        PRIOR/'ANSWER_REGISTRY_PRIVATE.json',BASE/'executor_revision_20261104_v2/OUTPUT_MANIFEST.json']
    p=stamp(dict(scope='ALTERNATE_LOCAL_G_DIAGNOSTIC_NOT_SUPERIORITY_OR_REWARD',runtime=runtime,
        sources={str(x.resolve()):sha(x) for x in sources},code={str(x.resolve()):sha(x) for x in code},
        requests_identity=digest(requests),inputs_identity=digest(inputs),cards_identity=digest(cards),
        originals_identity=digest(originals),gpu_uuid='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4',
        max_loads=1,max_calls=36,automatic_retries=0,stage_seconds=1800,api_cost_usd=0,
        model_selection='Gemma4-12B exists locally, supported by existing environment, different from P2 author Qwen; not presumed stronger.',
        human_primary='All seven C-vs-A pairs; two preregistered OFF comparisons N18/N21. D optional up to three only if independently noted interference; no wait-tradeoff questions.',
        interpretation=['Analyze the 2x2 G-by-resource contrast within each context, not cross-model ON alone.',
            'Positive replicated helpful use supports attainability, not a population effect or exclusive cause.',
            'No positive comparison means no demonstrated benefit here under these configurations; not zero intrinsic resource value.',
            'Two OFF judgments only screen those cases; they cannot establish overall superiority.',
            'D harm in two generators is observed in two configurations, not G-independence.',
            'Human judgments and source use remain separate; missing stays null; no arbitrary 0/1/2 threshold.'],
        latency=dict(researcher_provisional_extra_wait_upper_seconds=3,above_upper='usually unacceptable, not a universal law',
            under_upper='not automatically acceptable',objective='Tokkio end-to-end audible useful response plus resource incremental wait',
            lambda_value=None,first_token_metric='local generation component only',deployment_claim=False),
        authorization='2026-11-04 researcher: compare whether G or small resource gain is the bottleneck; check local models; 按计划继续推进。',
        new_training=False,new_rewards=False,promote=False))
    out.mkdir(mode=0o700)
    for name,obj in [('PROTOCOL.json',p),('REQUESTS_PRIVATE.json',requests),('INPUTS_PRIVATE.json',inputs),
        ('CARDS_PRIVATE.json',cards),('ORIGINALS_PRIVATE.json',originals)]:save(out/name,obj)
    print(json.dumps(dict(status='PREPARED',inputs=36,cards=41,max_input_tokens=max(x['input_tokens'] for x in requests),runtime=runtime['identity'])),flush=True)


def run(out):
    import torch
    from transformers import AutoTokenizer,AutoModelForMultimodalLM,GenerationConfig,StoppingCriteria,StoppingCriteriaList
    p=read(out/'PROTOCOL.json');verify_identity(p);runtime=p['runtime'];verify_identity(runtime)
    requests=read(out/'REQUESTS_PRIVATE.json');assert digest(requests)==p['requests_identity']
    for group in ('sources','code'):
        for path,h in p[group].items():assert sha(Path(path))==h,path
    for name,h in runtime['model_files'].items():assert sha(MODEL/name)==h,name
    for name,v in runtime['packages'].items():assert importlib.metadata.version(name)==v
    assert all(os.environ.get(k)=='1' for k in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE'))
    if (out/'LOAD_STARTED.json').exists():raise RuntimeError('load already entered; preserve partials, no implicit retry')
    guard=LocalGPUCheck(p['gpu_uuid'],runtime,out/'gpu_checks',latest_snapshot=True);guard.check()
    save(out/'LOAD_STARTED.json',dict(protocol=p['identity'],pid=os.getpid(),time=time.time()))
    torch.set_num_threads(1);torch.manual_seed(0);began=time.monotonic()
    tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    model=AutoModelForMultimodalLM.from_pretrained(MODEL,local_files_only=True,dtype=torch.bfloat16,
        attn_implementation='sdpa').to('cuda:0').eval()
    assert digest(tokenizer.chat_template)==runtime['chat_template_identity']
    policy=NaturalEndPolicy(**{**runtime['policy'],'eos_token_ids':tuple(runtime['policy']['eos_token_ids'])})
    save(out/'RUNTIME.json',dict(runtime_identity=runtime['identity'],model_class=type(model).__name__,
        gpu=torch.cuda.get_device_name(0),load_seconds=time.monotonic()-began,model_parameter_count=sum(x.numel() for x in model.parameters())))
    (out/'raw').mkdir(mode=0o700);started=time.monotonic();done=[]
    for req in requests:
        if time.monotonic()-started>p['stage_seconds']:break
        verify_identity(req);guard.check(own_pid=os.getpid())
        encoded=tokenizer.apply_chat_template(req['messages'],tokenize=True,add_generation_prompt=True,
            enable_thinking=False,return_tensors='pt',return_dict=False);n=encoded.shape[-1]
        assert n==req['input_tokens'] and digest(encoded[0].tolist())==req['token_ids_identity']
        encoded=encoded.to('cuda:0');call_start=time.monotonic()
        class Watchdog(StoppingCriteria):
            reason=None;first_token_seconds=None
            def __call__(self,input_ids,scores,**kwargs):
                tail=input_ids[0,n:].tolist()
                if tail and self.first_token_seconds is None:self.first_token_seconds=time.monotonic()-call_start
                if tail and tail[-1] in policy.eos_token_ids:return False
                if len(tail)>=128 and all(tail[-32:]==tail[-32*(i+1):-32*i] for i in range(1,4)):self.reason='repetition_guard'
                elif time.monotonic()-call_start>=policy.timeout_seconds:self.reason='technical_timeout'
                return self.reason is not None
        watchdog=Watchdog();save(out/'raw'/(req['identity']+'.started.json'),dict(request=req,protocol_identity=p['identity']))
        gc=GenerationConfig.from_pretrained(MODEL,local_files_only=True)
        for key,value in policy.generation_kwargs(n).items():setattr(gc,key,value)
        torch.manual_seed(0);torch.cuda.reset_peak_memory_stats(0)
        with torch.inference_mode():generated=model.generate(encoded,attention_mask=torch.ones_like(encoded),
            generation_config=gc,stopping_criteria=StoppingCriteriaList([watchdog]))
        tokens=generated[0,n:].tolist();torch.cuda.synchronize();text=tokenizer.decode(tokens,skip_special_tokens=True).strip()
        finish=policy.finish_reason(tokens,n,watchdog.reason)
        if finish=='natural_stop' and not text:finish='empty_output'
        raw=dict(request_identity=req['identity'],runtime_identity=runtime['identity'],input_identity=req['input_identity'],
            text=text,text_identity=digest(text),decoded_with_special_tokens=tokenizer.decode(tokens,skip_special_tokens=False),
            output_token_ids=tokens,input_tokens=n,output_tokens=len(tokens),finish_reason=finish,
            terminal_token=tokenizer.convert_ids_to_tokens(tokens[-1]) if tokens else None,
            completed_assistant_turn=finish=='natural_stop' and tokens[-1] in (1,106),
            generation_seconds=time.monotonic()-call_start,first_token_seconds=watchdog.first_token_seconds,
            peak_allocated_bytes=torch.cuda.max_memory_allocated(0),api_cost_usd=0,quality=None,reward=None)
        save(out/'raw'/(req['identity']+'.json'),raw);done.append(raw)
        print(json.dumps(dict(completed=len(done),finish=finish,tokens=len(tokens),seconds=raw['generation_seconds'])),flush=True)
        del generated,encoded
    save(out/'CLOSED.json',stamp(dict(completed=len(done),planned=len(requests),natural=sum(x['finish_reason']=='natural_stop' for x in done),
        completed_assistant_turns=sum(x['completed_assistant_turn'] for x in done),api_cost_usd=0,training_updates=0,quality_qualified=False)))


def analyze(out):
    requests=read(out/'REQUESTS_PRIVATE.json');cards=read(out/'CARDS_PRIVATE.json');old=read(out/'ORIGINALS_PRIVATE.json')
    mapping={r['input_identity']:r['identity'] for r in requests};results=[]
    for card,original in zip(cards,old):
        assert card['case']==original['case'] and card['arm']==original['arm']
        path=out/'raw'/(mapping[card['input_identity']]+'.json');raw=read(path) if path.exists() else None
        results.append(dict(**card,old_reply=original['reply'],old_reply_identity=original['reply_identity'],
            new_reply=raw['text'] if raw else None,new_reply_identity=raw['text_identity'] if raw else None,
            raw_request_identity=mapping[card['input_identity']],finish_reason=raw['finish_reason'] if raw else 'pending',
            generation_seconds=raw['generation_seconds'] if raw else None,first_token_seconds=raw['first_token_seconds'] if raw else None))
    save(out/'RESULTS_PRIVATE.json',results)
    print(json.dumps(read(out/'CLOSED.json')),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','run','analyze']);a.add_argument('--output',type=Path,required=True)
    args=a.parse_args();globals()[args.mode](args.output.resolve())

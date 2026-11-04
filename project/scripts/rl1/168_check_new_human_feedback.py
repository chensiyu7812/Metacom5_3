#!/usr/bin/env python3
"""Fixed old local judge on eight new references, two orders; never rewards."""
import argparse,importlib.metadata,importlib.util,json,os,sys,time
from collections import Counter
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp,verify_identity
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.relative_diagnostic import messages,parse,RUBRIC
from metacom_pm.rl1.schema import digest
from metacom_pm.io import sha256_file as sha
BASE=PROJECT/'outputs/pm_rl1';OLD=BASE/'relative_feedback_pilot_20261104_v1'
HUMAN=BASE/'alternate_executor_human_review_20261105_v1'
def read(p):return json.loads(p.read_text())


def prepare(out):
    if out.exists():raise ValueError('new output required')
    for name,h in read(HUMAN/'OUTPUT_MANIFEST.json').items():assert sha(HUMAN/name)==h
    old=read(OLD/'PROTOCOL.json');pairs=[];requests=[]
    for h in read(HUMAN/'INTAKE_PRIVATE.json')['answers']:
        ev=h['evidence'];current=[dict(id=f'C:T{i:03d}',role=t['speaker'],text=t['text']) for i,t in enumerate(ev['current_prefix'])]
        evidence=dict(current_prefix=current,legal_past_sessions=[ev['legal_past_source']],
            scope='Same current text and one complete legal past session shown in this human instrument; not the full available inventory.')
        pair=stamp(dict(key=h['question_id'],case=h['case'],kind=h['kind'],human_pair_identity=h['pair_identity'],
            evidence=evidence,left=h['alias_bindings']['A']['reply'],right=h['alias_bindings']['B']['reply'],
            human_choice=h['original_answer']['choice'],coarse_expectation='near_equal_not_cardinal_zero'))
        pairs.append(pair)
        for reverse in (False,True):
            a,b=(pair['right'],pair['left']) if reverse else (pair['left'],pair['right'])
            requests.append(stamp(dict(pair_identity=pair['identity'],reverse=reverse,messages=messages(evidence,a,b))))
    code=[Path(__file__),PROJECT/'scripts/rl1/159_bounded_real_diagnostic.py',PROJECT/'src/metacom_pm/rl1/relative_diagnostic.py',
          PROJECT/'src/metacom_pm/rl1/local_gpu_guard.py',PROJECT/'src/metacom_pm/rl1/durable.py']
    sources=[HUMAN/'INTAKE_PRIVATE.json',HUMAN/'ANSWER_REGISTRY_PRIVATE.json',HUMAN/'OUTPUT_MANIFEST.json',OLD/'PROTOCOL.json',OLD/'ANALYSIS.json']
    p=stamp(dict(scope='NEW_HUMAN_REFERENCE_STRESS_TEST_OF_UNCHANGED_COARSE_JUDGE_NOT_TRAINING',
        model=old['model'],model_files=old['model_files'],parameters={k:old[k] for k in ['thinking','temperature','top_p','top_k','repetition_penalty','seed','request_timeout_seconds']},
        rubric_identity=digest(RUBRIC),old_judge_protocol=old['identity'],pairs_identity=digest(pairs),requests_identity=digest(requests),
        sources={str(f.resolve()):sha(f) for f in sources},code={str(f.resolve()):sha(f) for f in code},
        packages={k:importlib.metadata.version(k) for k in ('torch','transformers','tokenizers')},
        runtime=dict(cuda_device_order='PCI_BUS_ID',cuda_visible_devices='1',dtype='bfloat16',attention='sdpa'),
        gpu_uuid='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4',max_calls=16,max_model_loads=1,retries=0,stage_seconds=3000,
        interpretation=['All eight human judgments are tie or slight: old rubric expects coarse near_equal, but cannot preserve slight direction.',
          'Count material inflation and order/risk inconsistency separately. No pass threshold, scalar gain, promotion or follow-on training.',
          'New labels are not sent to the model. Same human visible text; evidence IDs normalized, no unseen history added.',
          'Known session-only citations may be separately normalized by existing helper, never invented turn citations.'],
        old_references_reused_without_new_calls=36,new_references=8,API_cost_usd=0,new_training=False,
        authorization='2026-11-05 researcher: 好的，按计划继续推进。'))
    out.mkdir(mode=0o700)
    for name,obj in [('PROTOCOL.json',p),('PAIRS_PRIVATE.json',pairs),('REQUESTS_PRIVATE.json',requests)]:save(out/name,obj)
    print(json.dumps(dict(prepared=16,API_cost_usd=0)),flush=True)


def run(out):
    from metacom_pm.rl1.local_gpu_guard import LocalGPUCheck
    import torch
    from transformers import AutoTokenizer,AutoModelForImageTextToText,StoppingCriteria,StoppingCriteriaList
    p=read(out/'PROTOCOL.json');verify_identity(p);requests=read(out/'REQUESTS_PRIVATE.json');pairs=read(out/'PAIRS_PRIVATE.json')
    assert digest(requests)==p['requests_identity'] and digest(pairs)==p['pairs_identity'] and digest(RUBRIC)==p['rubric_identity']
    for group in ('sources','code'):
        for path,h in p[group].items():assert sha(Path(path))==h,path
    for name,h in p['model_files'].items():assert sha(Path(p['model'])/name)==h,name
    for name,v in p['packages'].items():assert importlib.metadata.version(name)==v
    assert os.environ.get('HF_HUB_OFFLINE')==os.environ.get('TRANSFORMERS_OFFLINE')=='1'
    if (out/'LOAD_STARTED.json').exists():raise ValueError('no implicit second load or retry')
    guard=LocalGPUCheck(p['gpu_uuid'],p['runtime'],out/'gpu_checks',latest_snapshot=True);guard.check()
    save(out/'LOAD_STARTED.json',dict(protocol=p['identity'],pid=os.getpid(),time=time.time()));torch.set_num_threads(1)
    tokenizer=AutoTokenizer.from_pretrained(p['model'],local_files_only=True)
    model=AutoModelForImageTextToText.from_pretrained(p['model'],local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda:0').eval()
    context=read(Path(p['model'])/'config.json')['text_config']['max_position_embeddings']
    eos=model.generation_config.eos_token_id or tokenizer.eos_token_id;eos=[eos] if isinstance(eos,int) else eos
    save(out/'RUNTIME.json',dict(model_class=type(model).__name__,context=context,eos=eos,gpu=torch.cuda.get_device_name(0)))
    (out/'responses').mkdir(mode=0o700);start=time.monotonic();done=[];param=p['parameters']
    for req in requests:
        if time.monotonic()-start>p['stage_seconds']:break
        guard.check(own_pid=os.getpid());verify_identity(req)
        encoded=tokenizer.apply_chat_template(req['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=param['thinking'],return_tensors='pt',return_dict=True)
        encoded={k:v.to('cuda:0') for k,v in encoded.items()};n=encoded['input_ids'].shape[-1];assert n<context
        torch.manual_seed(param['seed']);began=time.monotonic()
        class Watchdog(StoppingCriteria):
            reason=None
            def __call__(self,input_ids,scores,**kwargs):
                tail=input_ids[0,n:].tolist()
                if tail and tail[-1] in eos:return False
                if time.monotonic()-began>param['request_timeout_seconds']:self.reason='technical_timeout'
                if len(tail)>=128 and all(tail[-32:]==tail[-32*(i+1):-32*i] for i in range(1,4)):self.reason='repetition_guard'
                return self.reason is not None
        watchdog=Watchdog();save(out/(req['identity']+'.started.json'),dict(request=req['identity'],input_tokens=n))
        with torch.inference_mode():generated=model.generate(**encoded,max_new_tokens=context-n,do_sample=True,temperature=param['temperature'],
            top_p=param['top_p'],top_k=param['top_k'],repetition_penalty=param['repetition_penalty'],eos_token_id=eos,pad_token_id=tokenizer.pad_token_id or eos[0],
            forced_eos_token_id=None,stopping_criteria=StoppingCriteriaList([watchdog]))
        tokens=generated[0,n:].tolist();raw=tokenizer.decode(tokens,skip_special_tokens=True)
        finish='natural_stop' if tokens and tokens[-1] in eos else watchdog.reason or 'context_exhaustion'
        record=dict(request_identity=req['identity'],raw=raw,output_token_ids=tokens,finish_reason=finish,input_tokens=n,
            output_tokens=len(tokens),seconds=time.monotonic()-began,parsed=None,API_cost_usd=0,training_reward=None)
        if finish=='natural_stop':
            try:record['parsed']=parse(raw,next(x for x in pairs if x['identity']==req['pair_identity'])['evidence'])
            except (ValueError,TypeError) as exc:record['parse_error']=str(exc)
        save(out/'responses'/(req['identity']+'.json'),record);done.append(record)
        print(json.dumps(dict(completed=len(done),finish=finish,verdict=record['parsed']['verdict'] if record['parsed'] else None,seconds=record['seconds'])),flush=True)
        del generated,encoded
    save(out/'CLOSED.json',dict(completed=len(done),planned=16,natural=sum(x['finish_reason']=='natural_stop' for x in done),API_cost_usd=0,training_updates=0))


def analyze(out):
    spec=importlib.util.spec_from_file_location('old_normalization',PROJECT/'scripts/rl1/159_bounded_real_diagnostic.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    pairs=read(out/'PAIRS_PRIVATE.json');requests=read(out/'REQUESTS_PRIVATE.json');rows=[]
    flip={'A_better':'B_better','B_better':'A_better','near_equal':'near_equal','uncertain':'uncertain'}
    for pair in pairs:
        values=[];records=[]
        for reverse in (False,True):
            req=next(r for r in requests if r['pair_identity']==pair['identity'] and r['reverse']==reverse);path=out/'responses'/(req['identity']+'.json')
            raw=read(path) if path.exists() else None;value=None;coarse=[];error=None
            if raw and raw['finish_reason']=='natural_stop':
                try:value,coarse=module.normalize_response(raw['raw'],pair['evidence'])
                except (ValueError,TypeError) as exc:error=str(exc)
            values.append(value);records.append(dict(request_identity=req['identity'],reverse=reverse,parsed=value,coarse_session_ids=coarse,error=error))
        a,b=values;consistent=bool(a and b and a['verdict']==flip[b['verdict']]);risk=bool(a and b and a['risk_A']==b['risk_B'] and a['risk_B']==b['risk_A'])
        rows.append(dict(key=pair['key'],human_choice=pair['human_choice'],both_parsed=bool(a and b),verdict_consistent=consistent,risk_consistent=risk,
            both_coarse_near_equal=bool(a and b and a['verdict']==b['verdict']=='near_equal'),
            material_inflation_any_order=any(x and x['verdict'] in ('A_better','B_better') for x in values),records=records,training_reward=None))
    summary=dict(status='DIAGNOSTIC_ONLY_NO_QUALIFICATION',pairs=8,**{k:sum(bool(r[k]) for r in rows) for k in ['both_parsed','verdict_consistent','risk_consistent','both_coarse_near_equal','material_inflation_any_order']},
        slight_direction_representable=False,old_reference_failure_not_cleared=True,training_rewards=0,API_cost_usd=0)
    save(out/'ANALYSIS_PRIVATE.json',rows);save(out/'SUMMARY.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','run','analyze']);a.add_argument('--output',type=Path,required=True)
    args=a.parse_args();globals()[args.mode](args.output.resolve())

#!/usr/bin/env python3
"""Bounded CPU grammar/tokenizer replay. No weights, generation or CUDA access."""
from pathlib import Path
import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import sys
import time


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tokenizer-path',required=True)
    p.add_argument('--vendor-path',required=True)
    p.add_argument('--out',required=True)
    args=p.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES']=''
    root=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root/'src'))
    sys.path.insert(0,args.vendor_path)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    import torch
    import xgrammar
    from transformers import AutoTokenizer,AutoConfig
    from transformers.generation.logits_process import NoRepeatNGramLogitsProcessor
    from metacom_pm.rl1v3.journal import pomdp_controller_protocol as P
    from metacom_pm.rl1v3.journal import pomdp_latency as L
    assert Path(xgrammar.__file__).resolve().is_relative_to(Path(args.vendor_path).resolve())
    torch.set_num_threads(1)
    started=time.monotonic_ns()
    tok=AutoTokenizer.from_pretrained(args.tokenizer_path,local_files_only=True,trust_remote_code=False)
    config=AutoConfig.from_pretrained(args.tokenizer_path,local_files_only=True,trust_remote_code=False)
    vocab=config.text_config.vocab_size
    compiled={role:P.compile_grammar(role,tok,vocab_size=vocab,eos_token_ids=[1,106,50]) for role in P.ROLES}
    def literal(module,name):
        tree=ast.parse((root/'src/metacom_pm/rl1v3/journal'/module).read_text())
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
                return ast.literal_eval(node.value)
        raise ValueError(name)
    systems={'LLMOneShot':literal('pomdp_memory_proposal.py','ONESHOT_SYSTEM'),
             'LLMToolAgent':literal('pomdp_memory_prepare.py','TOOL_SYSTEM')}
    observation={'query':'Please recall the hobby report','turns':[{'role':'seeker','text':'Please recall the hobby report'}],
        'hits':[],'last_hits':[],'action_mask':['STOP','SEARCH'],'accesses_remaining':4}
    prompts={role:tok.apply_chat_template([{'role':'system','content':systems[role]},
        {'role':'user','content':json.dumps(observation,sort_keys=True)}],tokenize=True,
        add_generation_prompt=True,enable_thinking=False,return_dict=False) for role in P.ROLES}
    stop={'action':'STOP'};search={'action':'SEARCH','query':'hobby report'}
    cases=[('tool_stop','LLMToolAgent',stop),('tool_search','LLMToolAgent',search),
        ('tool_expand','LLMToolAgent',{'action':'EXPAND','handle':'hit:'+'a'*24}),
        ('one_stop','LLMOneShot',[stop]),('one_search','LLMOneShot',[search]),
        ('one_expand','LLMOneShot',[search,{'action':'EXPAND','from_search':0,'hit_rank':1},stop]),
        ('one_four','LLMOneShot',[search,{'action':'EXPAND','from_search':0,'hit_rank':0},
            search,{'action':'EXPAND','from_search':1,'hit_rank':1},stop])]
    results=[]
    for name,role,value in cases:
        for style in ('compact','spaces'):
            text=json.dumps(value,separators=(',',':') if style=='compact' else (', ',': '))
            P.parse_controller(text,role)
            for repeat in (3,0):
                for eos in ([1,106,50] if name.endswith('_stop') and style=='compact' else [1]):
                    if time.monotonic_ns()-started>120_000_000_000:
                        raise RuntimeError('bounded CPU check timeout; no retry')
                    ids=tok.encode(text,add_special_tokens=False)+[eos]
                    prefix=list(prompts[role]);proc=P.ControllerConstraintProcessor(compiled[role],prompt_length=len(prefix))
                    seen=0;error=None;blocked=False
                    for token in ids:
                        inp=torch.tensor([prefix]);scores=torch.zeros(1,vocab)
                        if repeat:scores=NoRepeatNGramLogitsProcessor(repeat)(inp,scores)
                        try:masked=proc(inp,scores)
                        except P.ControllerProtocolError as exc:
                            error=str(exc);break
                        if not bool(torch.isfinite(masked[0,token])):
                            blocked=True;break
                        prefix.append(token);seen+=1
                    final=proc.finalize(ids) if seen==len(ids) else None
                    results.append(dict(case=name,role=role,style=style,eos=eos,no_repeat_ngram_size=repeat,
                        checked_prefixes=proc.calls,accepted_fixture_tokens=seen,total_fixture_tokens=len(ids),
                        expected_next_token_blocked=blocked,error=error,final=final))
    zero=[r for r in results if r['no_repeat_ngram_size']==0]
    assert all(r['final'] and r['final']['grammar_terminated'] for r in zero)
    boundary_checks={}
    def rejected(name,call):
        try:call()
        except P.ControllerProtocolError:boundary_checks[name]=True
        else:raise AssertionError('did not reject '+name)
    prompt=prompts['LLMToolAgent']; inp=torch.tensor([prompt])
    def processor():return P.ControllerConstraintProcessor(compiled['LLMToolAgent'],prompt_length=len(prompt))
    rejected('all_negative_infinity',lambda:processor()(inp,torch.full((1,vocab),float('-inf'))))
    for label,value in [('nan',float('nan')),('positive_infinity',float('inf'))]:
        scores=torch.zeros(1,vocab);scores[0,0]=value
        rejected(label,lambda scores=scores:processor()(inp,scores))
    rejected('multiple_sequences',lambda:processor()(torch.tensor([prompt,prompt]),torch.zeros(2,vocab)))
    first=processor()(inp,torch.zeros(1,vocab))
    assert not any(bool(torch.isfinite(first[0,eos])) for eos in [1,106,50])
    boundary_checks['eos_forbidden_before_json']=True
    body=tok.encode('{"action":"STOP"}',add_special_tokens=False)
    complete=processor();result=complete.finalize(body)
    assert result['grammar_completed'] and not result['grammar_terminated']
    boundary_checks['json_complete_without_eos_is_not_terminated']=True
    incomplete=processor().finalize(body[:2])
    assert not incomplete['grammar_completed'] and not incomplete['grammar_terminated']
    boundary_checks['truncation_not_completed']=True
    terminated=processor();terminated.finalize(body+[1])
    rejected('token_after_eos',lambda:terminated.finalize(body+[1,2]))
    rejected('changed_prefix',lambda:terminated.finalize(body+[106]))
    assert not torch.cuda.is_initialized()
    paths=[Path(args.tokenizer_path)/name for name in ['tokenizer.json','tokenizer_config.json','config.json','generation_config.json']]
    report=dict(protocol='pmrl1-j-controller-native-cpu-prefix-check-v1',cpu_only=True,model_loads=0,
        model_calls=0,gpu_calls=0,api_calls=0,training_calls=0,cuda_initialized=False,
        python=sys.version.split()[0],packages={k:importlib.metadata.version(k) for k in ['torch','transformers','xgrammar']},
        tokenizer_files_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        implementation_files_sha256={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in [P.__file__,L.__file__,__file__]},
        protocol_contract=P.protocol_contract(),latency_contract=L.latency_contract(),cases=results,
        boundary_checks=boundary_checks,
        no_repeat_0_pass=sum(bool(r['final'] and r['final']['grammar_terminated']) for r in zero),
        no_repeat_0_total=len(zero),no_repeat_3_incompatibilities=sum(bool(r['error'] or r['expected_next_token_blocked']) for r in results if r['no_repeat_ngram_size']==3),
        checked_prefixes=sum(r['checked_prefixes'] for r in results),wall_ns=time.monotonic_ns()-started,
        coverage='bounded native-tokenized JSON fixture paths and three EOS IDs; not all reachable token prefixes or semantic correctness',
        fixture_text_private=False,grammar_has_no_observation_or_reference_input=True)
    (out/'NATIVE_CPU_CHECK.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:report[k] for k in ['no_repeat_0_pass','no_repeat_0_total','no_repeat_3_incompatibilities','checked_prefixes','wall_ns','cuda_initialized']}))


if __name__=='__main__':main()

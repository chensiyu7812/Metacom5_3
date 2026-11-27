#!/usr/bin/env python3
"""Execute ONLY three pure upstream methods through an AST allowlist.

This never imports QueryLLM, runs the upstream CLI, or contacts a provider.
Upstream source remains outside the public repository.
"""
import argparse
import ast
import json
from pathlib import Path
from typing import Dict,List,Tuple
from metacom_pm.need_aware.data.personamem import load_rows,SEED,write_json
from metacom_pm.need_aware.evaluation.mcq import make_options,instruction,extract_final_answer


def verify(upstream,source):
    tree=ast.parse((Path(upstream)/'inference.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PersonaBenchmarkEvaluator')
    names={'create_mcq_options','extract_final_answer','check_mcq_correctness'}
    methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if len(methods)!=3:raise ValueError('upstream API changed')
    module=ast.Module(body=[ast.ClassDef(name='Reference',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])
    namespace={'Dict':Dict,'List':List,'Tuple':Tuple}
    exec(compile(ast.fix_missing_locations(module),'<pinned upstream pure methods>','exec'),namespace)
    reference=namespace['Reference']()
    outputs=['', 'A','A.','Final Answer: B','answer: c',r'\boxed{D}',r'$\boxed{b}$',
             'Final Answer: Z',r'Final Answer: A then \boxed{C}','Final Answer: B\nFinal Answer: A',
             'The answer is D', 'No selection', 'A.\nother text', 'Answer: apple']
    comparisons=0
    for index,row in enumerate(load_rows(source,'val')):
        wrong=json.loads(row['incorrect_answers']);opts,gold=make_options(row['correct_answer'],wrong,SEED+index)
        prompt,mapping=reference.create_mcq_options(row['correct_answer'],wrong,SEED+index)
        assert prompt==instruction(opts) and mapping=={o['id']:o['text'] for o in opts}
        for output in outputs+[f'Final Answer: {gold}']:
            parsed=extract_final_answer(output)
            assert parsed==reference.extract_final_answer(output)
            assert bool(parsed and mapping.get(parsed,'')==row['correct_answer'])==reference.check_mcq_correctness(parsed,row['correct_answer'],mapping)
            comparisons+=1
    return {'result_kind':'plumbing','model_calls':0,'val_rows':index+1,'parser_correctness_comparisons':comparisons,
            'option_prompt_mismatches':0,'parser_mismatches':0,'score_mismatches':0,
            'seed_note':'explicit SEED+row_index; upstream default process-salted hash intentionally not reused'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--upstream',required=True);p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=verify(a.upstream,a.source);write_json(a.output,result);print(json.dumps(result,indent=2))

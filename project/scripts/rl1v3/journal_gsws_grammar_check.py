#!/usr/bin/env python3
"""CPU finite-mask check using the real tokenizer and frozen syntax only."""
import argparse,json
from pathlib import Path
import torch
from transformers import AutoTokenizer,AutoConfig
from metacom_pm.rl1v3.journal import gsws as S
from metacom_pm.rl1v3.generator.g0e import DECODE
from metacom_pm.rl1v3.journal.gsws_runtime import interpreter_decode

p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--output',required=True);a=p.parse_args()
torch.set_num_threads(1)
tok=AutoTokenizer.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
cfg=AutoConfig.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
vocab=cfg.text_config.vocab_size;results=[]
for arm,value in [
 ('A1_READING_NOTES',dict(notes='Quoted "maybe"; not completed. 未知.',evidence_ids=['C0'])),
 ('A2_GSWS',dict(goal_and_boundaries='Visible goal; unknown hidden needs.',claims=[dict(text='A plan, not a completed action.',
     epistemic='reported',subject='user',stage='planned',event_time='unknown',applicability='unresolved',evidence_ids=['C0'])],
     gaps_or_conflicts='Unknown result.',response_implications='Do not assume success.'))]:
    grammar=S.compile_grammar(arm,tok,vocab_size=vocab,eos_token_ids=DECODE['eos_token_id'])
    processor=S.ControllerConstraintProcessor(grammar,prompt_length=1)
    target=tok.encode(json.dumps(value,ensure_ascii=False),add_special_tokens=False)+[DECODE['eos_token_id'][0]]
    generated=[];minimum=vocab
    decode=interpreter_decode(DECODE,arm)
    defaults=json.loads((Path(a.model)/'generation_config.json').read_text())
    effective=dict(defaults,**decode)
    assert effective['no_repeat_ngram_size']==0 and (effective.get('min_new_tokens') or 0)==0
    assert (effective.get('min_length') or 0)==0
    for token in target:
        scores=torch.zeros((1,vocab),dtype=torch.float32)
        # The frozen suppress_tokens processor runs before the syntax mask.
        for index in effective.get('suppress_tokens',[]) or []:scores[0,index]=float('-inf')
        masked=processor(torch.tensor([[tok.bos_token_id]+generated]),scores)
        assert torch.isfinite(masked[0,token]),'valid sample token blocked by decode + syntax'
        minimum=min(minimum,int(torch.isfinite(masked).sum()));generated.append(token)
    status=processor.finalize(generated);assert status['grammar_completed']
    # Hostile all-nonfinite logits must fail closed, never unmask an answer.
    fresh=S.ControllerConstraintProcessor(grammar,prompt_length=1)
    try:fresh(torch.tensor([[tok.bos_token_id]]),torch.full((1,vocab),float('-inf')))
    except ValueError:pass
    else:raise AssertionError('nonfinite mask intersection accepted')
    results.append(dict(arm=arm,target_tokens=len(target),minimum_finite_allowed=minimum,**status))
report=dict(status='CPU_GRAMMAR_PATHS_PASSED',checks=results,model_loads=0,gpu_access=False,
    learned_semantics_tested=False,scope='synthetic valid paths; not proof every possible model-logit sequence terminates; runtime fails closed')
Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

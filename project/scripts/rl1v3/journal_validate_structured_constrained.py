#!/usr/bin/env python3
"""Finite CPU tokenizer/grammar admission tests; no model weights or GPU imports."""
import argparse,json,statistics,time
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once
from metacom_pm.rl1v3.journal.structured_constrained import compile_grammar,StructuredConstrainedProcessor,SCHEMA
from metacom_pm.rl1v3.journal.structured_constrained_run import check,admit

def main(package,out):
    import torch,xgrammar as xg
    from transformers import AutoTokenizer,AutoConfig,LogitsProcessorList
    torch.set_num_threads(1)
    package=Path(package);plans=[check(package/f'batch-{n:02d}/PLAN_CONSTRAINED.json') for n in (1,2)]
    plan=plans[0][0];path=plan['model_path'];start=time.monotonic()
    tok=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
    config=AutoConfig.from_pretrained(path,local_files_only=True,trust_remote_code=False)
    grammar_started=time.monotonic()
    grammar=compile_grammar(tok,vocab_size=config.text_config.vocab_size,eos_token_ids=[1,106,50])
    grammar_compile_seconds=time.monotonic()-grammar_started
    compile_seconds=time.monotonic()-start
    assert not any(k in json.dumps(SCHEMA) for k in ('"enum"','"const"','"pattern"'))
    def accepted(text,eos=106):
        matcher=xg.GrammarMatcher(grammar)
        ids=tok.encode(text,add_special_tokens=False)
        return all(matcher.accept_token(x) for x in ids) and matcher.accept_token(eos) and matcher.is_terminated()
    synthetic=dict(value='UNSEEN_VALUE_27_中文',certainty='unrestricted',quote='A "quote"; slash \\ and newline\n.',speaker='unrestricted',reported_date='not-a-date')
    synthetic_text=json.dumps(synthetic,ensure_ascii=False,separators=(',',':'))
    assert all(accepted(synthetic_text,x) for x in (1,106,50))
    null_sample=dict(value='unknown',certainty='unknown',quote='',speaker='unknown',reported_date=None)
    assert accepted(json.dumps(null_sample,separators=(',',':')))
    bad=['{}','```json\n'+synthetic_text+'\n```','thought\n'+synthetic_text,
        json.dumps(dict(synthetic,value=2)),json.dumps(dict(synthetic,extra='x')),
        synthetic_text[:-1]+',"value":"second"}',synthetic_text+' trailing',synthetic_text[:-2]]
    assert all(not accepted(x) for x in bad)
    tasks={r['task_id']:r for r in map(json.loads,Path(plan['task_manifest_path']).read_text().splitlines())}
    rows_receipt=[];witnesses=0;largest=0
    for p,rows,_ in plans:
        for row in rows:
            payload=row['model_input'];actual=tok.apply_chat_template(payload['messages'],tokenize=True,
                add_generation_prompt=True,enable_thinking=False,return_dict=False)
            assert list(actual)==payload['input_ids']
            values=tasks[row['task_id']]['choices']
            visible='\n'.join(m['content'] for m in payload['messages'])
            for value in values:
                assert value in visible
                sample=dict(synthetic,value=value)
                text=json.dumps(sample,ensure_ascii=False,separators=(',',':'))
                ids=tok.encode(text,add_special_tokens=False);assert len(ids)+1<=320 and accepted(text)
                witnesses+=1;largest=max(largest,len(ids)+1)
            rows_receipt.append(dict(task_id=row['task_id'],arm=row['arm'],request_id=row['request_id'],
                input_ids_identical=True,input_tokens=len(actual),all_visible_choices_reachable=True,choice_count=len(values)))
    # Real 262144-vocabulary score masking through the actual Transformers list.
    processor=StructuredConstrainedProcessor(grammar);processors=LogitsProcessorList([processor])
    generated=[];step_ms=[];ids=tok.encode(synthetic_text,add_special_tokens=False)
    for token in ids+[106]:
        input_ids=torch.tensor([[2]+generated]);scores=torch.zeros((1,config.text_config.vocab_size))
        t=time.monotonic();masked=processors(input_ids,scores);step_ms.append((time.monotonic()-t)*1000)
        assert torch.isfinite(masked[0,token])
        if token==106:assert all(torch.isfinite(masked[0,x]) for x in (1,106,50))
        else:assert all(torch.isneginf(masked[0,x]) for x in (1,106,50))
        generated.append(token)
    assert processor.calls==len(ids)+1
    rejected_approvals=0
    for p,_,_ in plans:
        for auth in ({'authorized':False},{'authorized':True,'protocol':'pmrl1-j-structured-paired-run-v1','job_kind':'JOURNAL_STRUCTURED_PAIRED'}):
            try:admit(p,auth)
            except Exception:rejected_approvals+=1
            else:raise AssertionError('approval transfer')
    receipt=dict(protocol='structured-constrained-cpu-validation-v1',requests=36,complete_pairs=18,
        messages_input_ids_decode_unchanged=True,tokenizer_model='GemmaTokenizer',vocab_size=config.text_config.vocab_size,
        compile_including_tokenizer_seconds=compile_seconds,grammar_compile_cpu_seconds=grammar_compile_seconds,visible_choice_witnesses=witnesses,
        maximum_witness_output_tokens=largest,grammar_bad_cases_rejected=len(bad),all_three_original_eos_tested=True,
        arbitrary_value_quote_speaker_certainty_date_accepted=True,grammar_does_not_prove_semantics=True,
        real_cpu_logits_mask_steps=len(step_ms),mask_ms=dict(median=statistics.median(step_ms),maximum=max(step_ms)),
        old_or_missing_approvals_rejected=rejected_approvals,model_loads=0,gpu_calls=0,cuda_initialized=torch.cuda.is_initialized(),
        schema_sha256=object_sha256(SCHEMA),rows=rows_receipt,
        catalog_sha256=file_sha256(package/'CATALOG_CONSTRAINED.json'))
    assert receipt['cuda_initialized'] is False
    write_json_once(out,receipt);print(json.dumps({k:v for k,v in receipt.items() if k!='rows'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();main(a.package,a.out)

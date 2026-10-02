#!/usr/bin/env python3
"""Exercise real Llama chat-template loss masks on cached train replies only.

No new generation, no semantic admission, no parameter update or training export.
"""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.executor_encoding import encode_response, collate_responses

PILOT = PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'
OUT = PROJECT/'outputs/pm_rl1/measurement_resolution_20260929_v1'


def read(path): return json.loads(path.read_text())


def main():
    from transformers import AutoTokenizer
    pointer = read(PILOT/'generation_pointer.json'); folder = Path(pointer['run_dir'])
    assert sha256_file(folder/'summary.json') == pointer['summary_sha256']
    runtime = read(folder/'runtime.json'); model = Path(runtime['model_dir'])
    tokenizer = AutoTokenizer.from_pretrained(model,local_files_only=True)
    assert sha256_file(model/'tokenizer.json') == runtime['model_files']['tokenizer.json']
    assert digest(tokenizer.chat_template) == runtime['chat_template_sha256']
    specs = read(PILOT/'episode_specs_private.json')
    assert len(specs) == 12 and all(s['prefix']['split'] == 'train' for s in specs)
    rows = []; sources = {}
    for row in read(folder/'summary.json')['rows']:
        req_path = folder/(row['request_id']+'.request.json')
        raw_path = folder/(row['request_id']+'.response.json')
        req, raw = read(req_path), read(raw_path)
        assert req['request_id'] == digest({k:v for k,v in req.items() if k!='request_id'})
        assert raw['request_id'] == req['request_id'] and raw['finish_reason'] == 'natural_stop'
        assert raw['output_token_ids'][-1] in runtime['policy']['eos_token_ids']
        e = encode_response(tokenizer, req['messages'], raw['text'],
            context_limit=runtime['policy']['context_limit'], eos_token_ids=runtime['policy']['eos_token_ids'])
        batch = collate_responses([e],pad_token_id=tokenizer.eos_token_id)
        assert sum(x!=-100 for x in batch['labels'][0]) == e.target_tokens
        rows.append(dict(pilot_index=row['pilot_index'],condition=row['arm'],generation_request_id=req['request_id'],
            prompt_tokens=e.prompt_tokens,target_tokens=e.target_tokens,total_tokens=len(e.input_ids),
            terminal_token_id=e.input_ids[-1],messages_identity=e.messages_identity,
            trailing_template_tokens_removed=e.trailing_template_tokens_removed,
            response_identity=e.response_identity,tensor_identity=digest(batch),
            supervision_admitted=False,reason='encoding diagnostic only; no accepted teacher/verifier record'))
        sources[str(req_path.relative_to(PROJECT))] = sha256_file(req_path)
        sources[str(raw_path.relative_to(PROJECT))] = sha256_file(raw_path)
    result = dict(status='REAL_TOKENIZER_ENCODING_VERIFIED_NOT_SFT_DATA',rows=rows,encoded_responses=len(rows),
        splits={'train':len(rows),'dev':0,'test':0},LLM_calls=0,parameter_updates=0,API_usd=0,
        production_training_runner=False,semantic_admission=False,source_hashes=sources,
        module_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/executor_encoding.py'),
        runner_sha256=sha256_file(Path(__file__)))
    dest = OUT/'executor_encoding_probe.json'
    if dest.exists(): raise RuntimeError('preserve existing diagnostic')
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(encoded=len(rows),max_tokens=max(r['total_tokens'] for r in rows),
        target_token_range=[min(r['target_tokens'] for r in rows),max(r['target_tokens'] for r in rows)],
        supervision_admitted=0,training_updates=0)))


if __name__ == '__main__': main()

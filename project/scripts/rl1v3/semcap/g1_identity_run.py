#!/usr/bin/env python3
"""G1 identity-contract bounded contrast (approved 2026-11-27: 24 calls, 1 load, 900 s, A6000).

  prepare  (CPU)  build the 24 frozen requests from the frozen prefixes and the frozen G0e
                  baseline (system prompt + decode); tokenizes with the native chat template.
  run      (GPU)  admit -> one load -> exactly the frozen requests -> stop. No warmup, no retry.
                  A watchdog kills the process at the 900 s hard limit (clock starts before load).

Arm a  frozen G0e: system=G0e, seeker->user, supporter->assistant (journal/renderer.py mapping).
Arm b  identity contract: system=identity.system_prompt(G0e, A), render_current_dialogue(A).
Both arms: same prefix, same model, same decode; no history evidence, no notes.
"""
import argparse, hashlib, json, os, sys, threading, time
from pathlib import Path


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def fsha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''): h.update(b)
    return h.hexdigest()


def arm_messages(turns, arm, system):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
    from metacom_pm.rl1v3.semcap import identity as I
    if arm == 'a_frozen_g0e':
        return [dict(role='system', content=system)] + [
            dict(role='user' if t['role'] == 'seeker' else 'assistant', content=t['text']) for t in turns]
    if arm == 'b_identity_contract':
        return [dict(role='system', content=I.system_prompt(system, I.IMPORTED_HUMAN))] + \
            I.render_current_dialogue(turns, I.IMPORTED_HUMAN)
    raise ValueError(arm)


def prepare(a):
    from transformers import AutoTokenizer
    base = json.loads(Path(a.baseline).read_text())['spec']
    tok = AutoTokenizer.from_pretrained(a.model, local_files_only=True)
    rows = [json.loads(s) for s in Path(a.prefixes).read_text().splitlines() if s.strip()]
    assert len(rows) == 12 and sum(r['group'] == 'M' for r in rows) == 6
    reqs = []
    for r in rows:
        for arm in ('a_frozen_g0e', 'b_identity_contract'):
            msgs = arm_messages(r['turns'], arm, base['system_prompt'])
            ids = list(tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True,
                                               enable_thinking=False, return_dict=False))
            assert len(ids) + base['decode']['max_new_tokens'] <= 16384
            body = dict(alias=r['alias'], group=r['group'], arm=arm, messages=msgs, input_ids=ids, decode=base['decode'])
            body['request_sha256'] = sha(body); reqs.append(body)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    p = out / 'REQUESTS.private.jsonl'
    p.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in reqs))
    model_files = {n: fsha(Path(a.model) / n) for n in ('config.json', 'tokenizer.json', 'tokenizer_config.json',
                                                         'chat_template.jinja', 'generation_config.json')}
    rep = dict(protocol='semcap-g1-identity-v1', requests=len(reqs), requests_file_sha256=fsha(p),
               prefixes_file_sha256=fsha(a.prefixes), baseline_file_sha256=fsha(a.baseline),
               model_path=a.model, model_small_files_sha256=model_files,
               input_tokens={r['alias'] + '/' + r['arm']: len(r['input_ids']) for r in reqs})
    (out / 'PREPARE_REPORT.json').write_text(json.dumps(rep, indent=2) + '\n')
    print(json.dumps({k: rep[k] for k in ('requests', 'requests_file_sha256', 'prefixes_file_sha256')}, indent=1))


def run(a):
    approval = json.loads(Path(a.approval).read_text())
    reqs_path = Path(a.requests)
    assert fsha(reqs_path) == approval['requests_file_sha256'], 'requests not the approved set'
    assert fsha(approval['researcher_approval_path']) == approval['researcher_approval_sha256'], 'approval evidence'
    assert approval['max_calls'] == 24 and approval['max_model_loads'] == 1 and approval['warmup_calls'] == 0 \
        and approval['retry_calls'] == 0 and approval['global_seconds'] == 900
    reqs = [json.loads(s) for s in reqs_path.read_text().splitlines() if s.strip()]
    assert len(reqs) == approval['max_calls'] and all(sha({k: v for k, v in r.items() if k != 'request_sha256'})
                                                      == r['request_sha256'] for r in reqs)
    out = Path(a.run_root); out.mkdir(parents=True, exist_ok=False)
    t0 = time.monotonic(); deadline = t0 + approval['global_seconds']
    log = (out / 'RESULTS.private.jsonl').open('x')

    def event(**k):
        k['t_since_start_s'] = round(time.monotonic() - t0, 3)
        with (out / 'EVENTS.jsonl').open('a') as f: f.write(json.dumps(k) + '\n')

    def watchdog():
        while time.monotonic() < deadline: time.sleep(0.5)
        event(kind='hard_deadline_kill'); os._exit(9)
    threading.Thread(target=watchdog, daemon=True).start()
    import torch, subprocess
    from transformers import AutoTokenizer, AutoModelForMultimodalLM, GenerationConfig
    uuid = subprocess.run(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader', '-i',
                           os.environ['CUDA_VISIBLE_DEVICES']], capture_output=True, text=True).stdout.strip()
    assert uuid == approval['gpu_uuid'] and torch.cuda.device_count() == 1, 'wrong device'
    torch.manual_seed(0); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    loads = calls = 0
    event(kind='load_start'); ls = time.monotonic()
    tok = AutoTokenizer.from_pretrained(a.model, local_files_only=True)
    model = AutoModelForMultimodalLM.from_pretrained(a.model, local_files_only=True, dtype=torch.bfloat16,
                                                     attn_implementation='sdpa').to('cuda:0').eval()
    torch.cuda.synchronize(); loads += 1; assert loads <= approval['max_model_loads']
    event(kind='load_end', seconds=round(time.monotonic() - ls, 3))
    for r in reqs:
        assert calls < approval['max_calls'] and time.monotonic() < deadline
        ids = list(tok.apply_chat_template(r['messages'], tokenize=True, add_generation_prompt=True,
                                           enable_thinking=False, return_dict=False))
        assert ids == r['input_ids'], 'tokenizer drift'
        gc = GenerationConfig.from_pretrained(a.model, local_files_only=True)
        for k, v in r['decode'].items():
            if k not in ('seed', 'enable_thinking'): setattr(gc, k, v)
        inp = torch.tensor([ids], device='cuda:0'); torch.manual_seed(0)
        calls += 1; s = time.monotonic()
        with torch.inference_mode():
            g = model.generate(inp, attention_mask=torch.ones_like(inp), generation_config=gc)
        torch.cuda.synchronize(); e = time.monotonic()
        o = g[0, len(ids):].tolist(); eos = r['decode']['eos_token_id']
        stop = next((i + 1 for i, x in enumerate(o) if x in eos), len(o)); o = o[:stop]
        rec = dict(alias=r['alias'], group=r['group'], arm=r['arm'], request_sha256=r['request_sha256'], call=calls,
                   input_tokens=len(ids), output_tokens=len(o), finish_reason='eos' if o and o[-1] in eos else 'length',
                   seconds=round(e - s, 3), text=tok.decode(o, skip_special_tokens=True), token_ids=o)
        log.write(json.dumps(rec, ensure_ascii=False) + '\n'); log.flush()
        event(kind='call', call=calls, alias=r['alias'], arm=r['arm'], seconds=rec['seconds'], finish=rec['finish_reason'])
    total = time.monotonic() - t0
    (out / 'RUN_SUMMARY.json').write_text(json.dumps(dict(status='FINISHED', calls=calls, model_loads=loads,
        warmup_calls=0, retry_calls=0, wall_seconds=round(total, 3), gpu_uuid=uuid,
        peak_allocated_bytes=torch.cuda.max_memory_allocated()), indent=2) + '\n')
    event(kind='finished', calls=calls); print('FINISHED', calls, round(total, 1))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    q = sub.add_parser('prepare')
    for n in ('prefixes', 'baseline', 'model', 'output'): q.add_argument('--' + n, required=True)
    q = sub.add_parser('run')
    for n in ('requests', 'approval', 'model', 'run-root'): q.add_argument('--' + n, required=True)
    a = p.parse_args(); a.run_root = getattr(a, 'run_root', None)
    prepare(a) if a.cmd == 'prepare' else run(a)

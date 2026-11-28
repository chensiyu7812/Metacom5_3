"""NAA internal HF worker (one model load, many validated generate calls).

Adapted from the historical limited_hf_worker / ge2_worker generation path: same
deterministic torch settings, bf16 + sdpa, checkpoint header and HF loading-info
checks, native-tokenizer revalidation, EOS trimming and passive first-token
observation. It refuses standalone startup (admitted supervisor PID required), and
it re-verifies every request's exact identity against the binding it was loaded with.
Importing this module never imports torch or touches a device.
"""
from __future__ import annotations

import contextlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

from ...rl1v3.generator.limited_run import require
from ...rl1v3.generator.runprep_checkpoint import check_loading_info, read_header
from ...rl1v3.journal.pomdp_latency import FirstOutputObserver, MonotonicClock, duration_ns
from .requests import physical_identity


def _load(command, clock):
    spec = command['spec']; runtime = command['runtime']
    require(command['boot_id'] == clock.boot_id, 'cross-process boot mismatch')
    require(platform.python_version() == runtime['python'], 'Python version')
    for name, version in runtime['packages'].items():
        require(importlib.metadata.version(name) == version, 'package ' + name)
    headers = [read_header(p)[1] for p in sorted(Path(spec['path']).glob('*.safetensors'))]
    require(headers and [h['header_sha256'] for h in headers] == command['header_sha256'], 'checkpoint header')
    import torch
    from transformers import AutoModelForMultimodalLM, AutoTokenizer, GenerationConfig
    torch.set_num_threads(1); torch.manual_seed(0); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    started = clock.stamp()
    tok = AutoTokenizer.from_pretrained(spec['path'], local_files_only=True, trust_remote_code=False)
    model, info = AutoModelForMultimodalLM.from_pretrained(spec['path'], local_files_only=True,
        trust_remote_code=False, ignore_mismatched_sizes=False, output_loading_info=True,
        dtype=torch.bfloat16, attn_implementation='sdpa')
    require(type(model).__name__ == spec['architecture'], 'loaded architecture mismatch')
    require(not any(t.is_meta for t in model.state_dict().values()), 'unloaded meta tensor')
    tied = {k: k for k in command.get('allowed_missing', [])}
    loading = check_loading_info(info, tied_aliases=tied, allowed_unused=command.get('allowed_unused', []))
    if 'lm_head.weight' in tied:   # an allowed "missing" head must really be the tied embedding
        require(model.get_output_embeddings().weight is model.get_input_embeddings().weight,
                'checkpoint alias not actually tied')
    adapter = command.get('adapter')   # WP4 U2/U3: base checkpoint (unchanged) + SHA-bound LoRA, merged once
    require(bool(adapter) == bool(spec.get('adapter')), 'adapter binding/checkpoint mismatch')
    if adapter:
        from .lora import merge
        require(spec['adapter']['adapter_sha256'] == adapter['sha256'], 'adapter identity differs from binding')
        loading = dict(loading, adapter=merge(model, adapter['path'], expected_sha256=adapter['sha256']))
    model = model.to('cuda:0').eval(); torch.cuda.synchronize()
    finished = clock.stamp()
    gc_base = (GenerationConfig.from_pretrained(spec['path'], local_files_only=True)
               if spec['generation_config_file'] else GenerationConfig())
    state = dict(torch=torch, tok=tok, model=model, gc_base=gc_base, spec=spec, inferences=0)
    result = dict(load_ns=duration_ns(started, finished), started=started, finished=finished, loading=loading,
                  architecture=type(model).__name__, model_loads=1, warmup_calls=0,
                  peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                  peak_reserved_bytes=torch.cuda.max_memory_reserved())
    return state, result


def _generate(state, command, clock):
    torch, tok, model, spec = state['torch'], state['tok'], state['model'], state['spec']
    request = command['request']
    require(set(request) == {'request_sha256', 'g_id', 'messages', 'input_ids', 'decode'}, 'request whitelist')
    require(request['g_id'] == spec['g_id'], 'generator binding differs')
    require(request['request_sha256'] == physical_identity(request['g_id'], request['messages'],
            request['input_ids'], request['decode']), 'request identity')
    require(request['decode'] == spec['decode'], 'decode differs from binding')
    v0 = clock.stamp()
    ids = [int(x) for x in tok.apply_chat_template(request['messages'], tokenize=True, add_generation_prompt=True,
                                                   enable_thinking=False, return_dict=False)]
    require(ids == request['input_ids'], 'native tokenizer differs')
    require(len(ids) <= command['input_cap'] and len(ids) + request['decode']['max_new_tokens'] <= command['backend_cap'],
            'native context capacity')
    v1 = clock.stamp()
    gc = state['gc_base'].__class__.from_dict(state['gc_base'].to_dict())
    for key, value in request['decode'].items():
        if key not in {'seed', 'enable_thinking'}:
            setattr(gc, key, value if value != [] else None)   # no empty suppress list processor
    inp = torch.tensor([ids], device='cuda:0'); mask = torch.ones_like(inp)
    torch.manual_seed(0); torch.cuda.reset_peak_memory_stats()
    started = clock.stamp(); state['inferences'] += 1
    observer = FirstOutputObserver(tok, prompt_token_count=len(ids), clock=clock, generation_start_stamp=started)
    with torch.inference_mode():
        generated = model.generate(inp, attention_mask=mask, generation_config=gc, streamer=observer)
    torch.cuda.synchronize(); ended = clock.stamp()
    out = generated[0, len(ids):].tolist(); eos = request['decode']['eos_token_id']
    stop = next((i + 1 for i, x in enumerate(out) if x in eos), len(out)); out = out[:stop]
    require(observer.tokens[:len(out)] == out, 'passive observer output differs')
    gen_ns = duration_ns(started, ended)
    first = observer.measurement()
    result = dict(token_ids=out, text=tok.decode(out, skip_special_tokens=True),
                  finish_reason='eos' if out and out[-1] in eos else 'length',
                  input_tokens=len(ids), output_tokens=len(out), generation_ns=gen_ns,
                  validation_ns=duration_ns(v0, v1), started=started, finished=ended,
                  inference_ordinal=state['inferences'], first_inference_after_load=state['inferences'] == 1,
                  first_output_observation=first,
                  peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                  peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                  timing_scope='same-boot worker monotonic; first-token stamps are internal streamer '
                               'observations, not client-visible TTFT')
    del inp, mask, generated
    return result


def main():
    parent = os.environ.get('PMRL1_LIMITED_SUPERVISOR_PID')
    require(parent and int(parent) == os.getppid(), 'internal worker requires admitted supervisor')
    wire = sys.stdout; clock = MonotonicClock(); state = None
    for line in sys.stdin:
        try:
            command = json.loads(line)
            require(clock.now_ns() < command['deadline_ns'], 'worker command deadline')
            with contextlib.redirect_stdout(sys.stderr):
                if command['operation'] == 'load':
                    require(state is None, 'one model load only')
                    state, result = _load(command, clock)
                elif command['operation'] == 'generate':
                    require(state is not None, 'load required')
                    result = _generate(state, command, clock)
                else:
                    raise ValueError('unknown worker operation')
            wire.write(json.dumps({'ok': True, 'result': result}) + '\n'); wire.flush()
        except BaseException as error:
            wire.write(json.dumps({'ok': False, 'error': type(error).__name__ + ': ' + str(error),
                                   'failure_stamp': clock.stamp()}) + '\n'); wire.flush()
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

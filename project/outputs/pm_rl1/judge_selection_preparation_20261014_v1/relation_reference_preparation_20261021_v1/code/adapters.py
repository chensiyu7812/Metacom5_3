"""Transport adapters only; no rubric, scale, parsing-rule or label changes."""
import json
import os
from pathlib import Path
import time


def api_body(config, messages):
    if [m['role'] for m in messages] != ['system', 'user']:
        raise ValueError('only the frozen two-message input is permitted')
    body = dict(model='deepseek-flash', messages=messages,
        thinking={'type': config['thinking']},
        response_format={'type': 'json_object'}, max_tokens=393216,
        stream=True, stream_options={'include_usage': True})
    if config['thinking']=='enabled':
        body.update(reasoning_effort='high',top_p=1)
    elif config['thinking']=='disabled':
        body.update(temperature=1.0)
    else:
        raise ValueError('unsupported native thinking mode')
    return body


def token_accounting(raw):
    if raw['transport']=='gemma':
        return raw.get('token_accounting',dict(input=raw.get('input_tokens'),
            total_output=raw.get('output_tokens'),thinking=None,final=None,format=None))
    u=raw.get('usage') or {};total=u.get('completion_tokens')
    thinking=(u.get('completion_tokens_details') or {}).get('reasoning_tokens')
    if type(thinking) is not int or type(total) is not int or not 0<=thinking<=total:
        thinking=None
    return dict(input=u.get('prompt_tokens'),total_output=total,thinking=thinking,
        final=(total-thinking) if thinking is not None else None,format=None,
        attribution='provider usage; unknown split remains null; reasoning subset counted once')


def gemma_token_accounting(ids,tokenizer,input_tokens):
    """Partition ACTUAL generated IDs, not re-tokenized reasoning text estimates."""
    ids=list(map(int,ids));special=set(tokenizer.all_special_ids)
    header=tokenizer.encode('<|channel>thought\n',add_special_tokens=False)
    close=tokenizer.convert_tokens_to_ids('<channel|>')
    header_at=next((i for i in range(len(ids)-len(header)+1) if ids[i:i+len(header)]==header),None)
    thinking_positions=set();format_positions={i for i,t in enumerate(ids) if t in special}
    if header_at is not None:
        start=header_at+len(header)
        end=next((i for i in range(start,len(ids)) if ids[i]==close),None)
        if end is None:
            return dict(input=input_tokens,total_output=len(ids),thinking=None,final=None,format=None,
                        attribution='incomplete thought channel; no invented token split')
        format_positions.update(range(header_at,start))
        thinking_positions=set(range(start,end))-format_positions
    elif close in ids:
        return dict(input=input_tokens,total_output=len(ids),thinking=None,final=None,format=None,
                    attribution='unexpected channel boundary; split unknown')
    final_positions=set(range(len(ids)))-format_positions-thinking_positions
    return dict(input=input_tokens,total_output=len(ids),thinking=len(thinking_positions),
        final=len(final_positions),format=len(format_positions),attribution='partition of actual generated token IDs')


def final_content(raw):
    if raw['transport'] == 'deepseek':
        c = raw['choices'][0]
        text = c['message']['content']
        return text, 'natural_stop' if c['finish_reason'] == 'stop' else 'non_natural_stop'
    if raw['transport'] == 'gemma':
        # Native processor parses channel/turn markers. Preserve original raw text;
        # no Markdown repair, quote fix, q/m rescale, or inferred EOS.
        parsed = raw['native_parsed']
        if parsed.get('tool_calls'):
            raise ValueError('unexpected tool call')
        text = parsed.get('content')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('empty final channel')
        return text, 'natural_stop' if raw['natural_eos'] else 'non_natural_stop'
    raise ValueError('unknown transport')


def billed_peak_nanodollars(raw):
    u = raw.get('usage')
    if not u or type(u.get('prompt_tokens')) is not int or type(u.get('completion_tokens')) is not int:
        return None
    if min(u['prompt_tokens'], u['completion_tokens']) < 0:
        raise ValueError('negative usage')
    # completion_tokens already includes reasoning. Do not add its subset again.
    # Peak, cache-miss liability until account billing is reconciled; never understate.
    return u['prompt_tokens'] * 300 + u['completion_tokens'] * 1200


class DeepSeekTransport:
    def __init__(self, config):
        self.config = config

    def send(self, messages, schema, *, request, raw_path):
        # stdlib means no SDK auto-retries; no credential is written to disk.
        import urllib.request
        key = os.environ.get('DEEPSEEK_API_KEY')
        if not key:
            raise RuntimeError('credential unavailable')
        body = json.dumps(api_body(self.config, messages), ensure_ascii=False).encode()
        req = urllib.request.Request('https://api.deepseek.com/chat/completions', data=body,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        start = time.monotonic(); content = ''; reasoning = ''; finish = None
        merged = dict(transport='deepseek', request_identity=request['request_id'],
                      native_thinking=self.config['thinking'],request_started_unix=time.time())
        done = False
        # Keep every SSE chunk on failure; no partial content is eligible as a score.
        with Path(raw_path).open('x') as archive:
            with opener.open(req, timeout=30) as response:
                merged['response_headers'] = {k: v for k, v in response.headers.items()
                    if k.lower() in ('date', 'x-request-id', 'request-id')}
                for line in response:
                    archive.write(line.decode('utf-8', errors='replace')); archive.flush()
                    if time.monotonic() - start > self.config['timeout_seconds']:
                        raise TimeoutError('total wall-clock guard')
                    if not line.startswith(b'data: '):
                        continue
                    data = line[6:].strip()
                    if data == b'[DONE]':
                        done = True; break
                    x = json.loads(data)
                    for k in ('id', 'model', 'created', 'system_fingerprint'):
                        if k in x:
                            if k in merged and merged[k] != x[k]:
                                raise ValueError('identity drift within stream')
                            merged[k] = x[k]
                    if x.get('usage'):
                        merged['usage'] = x['usage']
                    for c in x.get('choices', []):
                        if c.get('index', 0) != 0:
                            raise ValueError('unexpected multiple completion')
                        delta = c.get('delta', {})
                        content += delta.get('content') or ''
                        reasoning += delta.get('reasoning_content') or ''
                        finish = c.get('finish_reason') or finish
        if not done or finish is None:
            raise ValueError('incomplete stream')
        merged['choices'] = [dict(message=dict(content=content, reasoning_content=reasoning), finish_reason=finish)]
        merged['total_seconds']=time.monotonic()-start
        return merged


class GemmaTransport:
    def __init__(self, config, local_path):
        # Only called following live approval and readiness checks; all file reads local.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['CUDA_VISIBLE_DEVICES'] = config['gpu_uuid']
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM
        self.config = config
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(local_path, local_files_only=True, trust_remote_code=False)
        load_start=time.monotonic()
        self.model = AutoModelForMultimodalLM.from_pretrained(local_path, local_files_only=True,
            trust_remote_code=False, dtype=torch.bfloat16, attn_implementation='sdpa').to('cuda:0').eval()
        self.load_seconds=time.monotonic()-load_start

    def gpu_condition(self):
        import subprocess
        query=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid',
                                       '--format=csv,noheader,nounits'],text=True)
        if any(line.split(',')[0].strip()==self.config['gpu_uuid'] and
               int(line.split(',')[1])!=os.getpid() for line in query.splitlines() if line.strip()):
            raise ValueError('other GPU process appeared; do not kill or switch devices')
        return subprocess.check_output(['nvidia-smi','--query-gpu=uuid,memory.used,utilization.gpu',
                                        '--format=csv,noheader,nounits'],text=True)

    def send(self, messages, schema, *, request, raw_path):
        from transformers import StoppingCriteria, StoppingCriteriaList
        start=time.monotonic();before=self.gpu_condition()
        self.torch.cuda.reset_peak_memory_stats()
        inputs = self.processor.apply_chat_template(messages, tokenize=True, return_dict=True,
            return_tensors='pt', add_generation_prompt=True,
            enable_thinking=self.config['enable_thinking']).to('cuda:0')
        n = inputs['input_ids'].shape[-1]
        if n + 32768 > self.config['context_tokens']:
            raise ValueError('full input plus predeclared reserve does not fit; never truncate')
        self.torch.manual_seed(request['seed'])
        timeout = self.config['timeout_seconds']
        class WallClock(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return time.monotonic() - start > timeout
        with self.torch.inference_mode():
            output = self.model.generate(**inputs, do_sample=False, use_cache=True,
                max_new_tokens=self.config['context_tokens'] - n,
                stopping_criteria=StoppingCriteriaList([WallClock()]))
        tokens = output[0][n:]
        text = self.processor.decode(tokens, skip_special_tokens=False)
        self.torch.cuda.synchronize()
        elapsed=time.monotonic()-start
        raw = dict(transport='gemma', request_identity=request['request_id'], raw_text=text,
            input_tokens=n, output_tokens=len(tokens), last_token=int(tokens[-1]),
            native_thinking=self.config['enable_thinking'],total_seconds=elapsed,
            gpu_seconds=elapsed,load_seconds=self.load_seconds,gpu_before=before,
            peak_allocated_bytes=self.torch.cuda.max_memory_allocated(),
            peak_reserved_bytes=self.torch.cuda.max_memory_reserved(),
            token_accounting=gemma_token_accounting(tokens.tolist(),self.processor.tokenizer,n),
            natural_eos=int(tokens[-1]) in self.config['eos_token_ids'] and elapsed <= timeout)
        # Save raw even if native parsing raises. Actual JSON still passes original strict parser.
        with Path(raw_path).open('x') as f:
            json.dump(raw, f, ensure_ascii=False)
        raw['native_parsed'] = self.processor.parse_response(text, prefix=inputs['input_ids'])
        return raw


class MockTransport:
    """All-uncertain synthetic response: exercises plumbing, cannot qualify a judge."""
    def __init__(self, plan, fail_at=None):
        self.plan, self.fail_at, self.calls = plan, fail_at, 0

    def send(self, messages, schema, *, request, raw_path):
        self.calls += 1
        if self.calls == self.fail_at:
            Path(raw_path).write_text('MOCK: simulated incomplete stream\n')
            raise TimeoutError('mock failure')
        data = json.loads(messages[1]['content'])
        units = data['response_units']; turns = data['legal_evidence']['current_prefix']
        value = dict(status='uncertain', q=None,
            q_rationale=dict(current_need='MOCK only; no semantic judgment.',
                response_unit_ids=[u['id'] for u in units], source_turn_ids=[turns[-1]['id']],
                reason='MOCK uncertainty; no labels inferred.'),
            assessments=[dict(response_unit_id=u['id'], relation='uncertain', severity=0,
                source_turn_ids=[], reason='MOCK unresolved') for u in units],
            coverage='MOCK only; complete source supplied but not semantically evaluated.',
            uncertainty_reasons=['Synthetic offline plumbing check; not a real score.'])
        c = next(c for c in self.plan['configs'].values() if c['identity'] == request['configuration_identity'])
        if c['backend'] == 'gemma':
            return dict(transport='gemma', natural_eos=True, native_parsed={'content': json.dumps(value)},
                        raw_text=json.dumps(value), request_identity=request['request_id'],
                        token_accounting=dict(input=1000,total_output=1000,
                            thinking=100 if c['enable_thinking'] else 0,
                            final=890 if c['enable_thinking'] else 990,format=10),
                        gpu_seconds=0,peak_allocated_bytes=0,mock_telemetry=True)
        return dict(transport='deepseek', id='MOCK-' + request['request_id'], created=1,
            model='MOCK-deepseek-flash', system_fingerprint='MOCK-ONLY',
            request_identity=request['request_id'], usage={'prompt_tokens': 1000, 'completion_tokens': 1000,
                'completion_tokens_details':{'reasoning_tokens':100 if c['thinking']=='enabled' else 0}},
            choices=[dict(message=dict(content=json.dumps(value), reasoning_content='MOCK'), finish_reason='stop')])

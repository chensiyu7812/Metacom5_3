"""Local streaming instrumentation and complete online acquisition paths.

Frozen historical generation code is untouched. The new streaming executor
has a separate identity; same decoded outputs must be checked, not assumed.
"""
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import time

from .organized_feedback import generation_request, visible_generation_request, bind_generation_result
from .organized_policy_interface import HeadSession, VERSION as INTERFACE_VERSION
from .resource_organization import OrganizationSession, RANKING
from .schema import HEADS, digest
from .supervised_learning import file_sha

VERSION = 'pmrl1-streaming-online-path-v1'


def streaming_identity(base_runtime_identity):
    return digest(dict(version=VERSION,base_runtime_identity=base_runtime_identity,
        code_sha256=file_sha(Path(__file__)),streamer='pinned-transformers-TextStreamer-skip-prompt',
        natural_end_policy='unchanged',response_cache=False))


@contextmanager
def stage(events,name):
    start = time.perf_counter_ns()
    try:
        yield
    finally:
        end = time.perf_counter_ns()
        events.append(dict(stage=name,start_ns=start,end_ns=end,seconds=(end-start)/1e9))


class RequestVectors:
    """Content cache scoped to one request, never the offline training cache."""
    def __init__(self, planner, invoke):
        self.planner,self.invoke = planner,invoke
        self.cache = {}; self.calls = 0; self.new_blocks = 0

    def sequential(self, observation):
        plan = self.planner.plan(observation)
        blocks = [c['input_ids'] for d in plan['documents'] for c in d['chunks']]
        for block in blocks:
            key = digest(block)
            if key not in self.cache:
                vectors = self.invoke([block])
                if len(vectors) != 1:
                    raise ValueError('one complete-block vector required')
                self.cache[key] = vectors[0]; self.calls += 1; self.new_blocks += 1
        result = self.planner.assemble(observation,plan,
            vectors=[self.cache[digest(b)] for b in blocks],encoder_feature_identity=self.planner.identity)
        return result['values'],result['action_mask']


def prepare_online(catalog, renderer, *, actions, sequential_view, decide,
                   executor_identity, draw_identity):
    """Run inside the service after client send, including initial observation.

    A fixed head program uses no policy observation/encoding. A sequential
    chooser sees ONLY public feature values/mask. Script replay is identified
    by its caller and cannot be reported as a trained adaptive policy.
    """
    actions = tuple(actions)
    if not actions or actions[-1] != 0 or 0 in actions[:-1] or any(type(a) is not int or a not in range(5) for a in actions):
        raise ValueError('complete fixed diagnostic program required')
    events = []
    if sequential_view is not None:
        with stage(events,'initial_observation'):
            session = HeadSession(catalog,renderer)
            obs = session.observe()
        for planned in actions:
            with stage(events,'online_encoding'):
                values,mask = sequential_view.sequential(obs)
            with stage(events,'actor_forward_scripted_action'):
                action = decide(values,mask,planned)
            if action != planned:
                raise ValueError('diagnostic replay changed its precommitted action')
            with stage(events,'retrieval_and_observation'):
                obs = session.step(action)
        with stage(events,'terminal_render'):
            terminal = session.terminal(executor_identity=executor_identity,draw_identity=draw_identity)
    else:
        with stage(events,'fixed_retrieval_and_render'):
            # OFF bypasses all catalog ranking and PM feature construction.
            session = OrganizationSession(catalog,renderer)
            for action in actions:
                if action == 0: session.stop()
                else: session.get(HEADS[action-1])
            receipt = session.receipt(); keys = receipt['acquired']
            body = dict(version=INTERFACE_VERSION,prefix_identity=catalog.prefix.identity,
                catalog_identity=catalog.identity,renderer_identity=renderer.identity,
                interface_identity=digest(dict(version=VERSION,path='fixed_head_program')),
                retrieval_method=RANKING,executor_identity=executor_identity,draw_identity=draw_identity,
                messages=renderer.messages(catalog,keys),selected_keys=[x.key for x in catalog.canonical(keys)],
                selected_resource_identities=[x.identity for x in catalog.canonical(keys)],usage=receipt['usage'])
            terminal = dict(body,identity=digest(body))
    with stage(events,'request_binding'):
        request = generation_request(terminal)
    return request,events


def stream_generate(generator, request, emit):
    """Original kwargs/watchdog, with word-visible streaming and a new identity."""
    import torch
    from transformers import GenerationConfig, StoppingCriteria, StoppingCriteriaList, TextStreamer
    identity = streaming_identity(generator.identity)
    visible = visible_generation_request(request)
    if visible['executor_identity'] != identity:
        raise ValueError('streaming runtime identity changed')
    tokenizer = generator.tokenizer
    inputs = tokenizer.apply_chat_template(visible['messages'],tokenize=True,
        add_generation_prompt=True,return_tensors='pt').to('cuda:0')
    n = inputs.shape[-1]; policy = generator.policy
    kwargs = policy.generation_kwargs(n)
    started = time.monotonic()

    class Watchdog(StoppingCriteria):
        reason = None
        def __call__(self,input_ids,scores,**unused):
            tail = input_ids[0,n:].tolist(); width,repeats = policy.cycle_width,policy.cycle_repetitions
            if tail and tail[-1] in policy.eos_token_ids: return False
            if len(tail) >= width*repeats and all(tail[-width:] == tail[-width*(i+1):-width*i] for i in range(1,repeats)):
                self.reason = 'repetition_guard'
            elif time.monotonic()-started >= policy.timeout_seconds:
                self.reason = 'technical_timeout'
            return self.reason is not None

    class ClientText(TextStreamer):
        def on_finalized_text(self,text,stream_end=False):
            emit(text)

    guard = Watchdog(); streamer = ClientText(tokenizer,skip_prompt=True,skip_special_tokens=True)
    torch.manual_seed(0); torch.cuda.reset_peak_memory_stats(0)
    with torch.inference_mode():
        result = generator.model.generate(inputs,attention_mask=torch.ones_like(inputs),
            generation_config=GenerationConfig(**kwargs,bos_token_id=tokenizer.bos_token_id,
                pad_token_id=tokenizer.eos_token_id),stopping_criteria=StoppingCriteriaList([guard]),streamer=streamer)
    tokens = result[0,n:].tolist(); torch.cuda.synchronize()
    text = tokenizer.decode(tokens,skip_special_tokens=True).strip()
    reason = policy.finish_reason(tokens,n,guard.reason)
    if reason == 'natural_stop' and not text: reason = 'empty_output'
    raw = dict(request_id=visible['request_id'],runtime_identity=identity,text=text,finish_reason=reason,
        output_token_ids=tokens,input_tokens=n,output_tokens=len(tokens),
        generation_seconds=time.monotonic()-started,peak_allocated_bytes=torch.cuda.max_memory_allocated(0),api_cost_usd=0)
    return bind_generation_result(request,raw)

"""Passive Linux monotonic timestamps; never infer TTFT from total duration."""
from __future__ import annotations

import os
from pathlib import Path
import time
import unicodedata

PROTOCOL = 'pmrl1-j-dynamic-monotonic-observer-v1'
CLOCK_ID = 'CLOCK_MONOTONIC'


class TimingError(ValueError):
    pass


class MonotonicClock:
    def __init__(self, *, now=None, boot_id=None):
        self._now = now or time.monotonic_ns
        self.boot_id = boot_id or Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if type(self.boot_id) is not str or not self.boot_id:
            raise TimingError('Linux boot identity required')

    def now_ns(self):
        value = self._now()
        if type(value) is not int or value < 0:
            raise TimingError('monotonic_ns must be a nonnegative integer')
        return value

    def stamp(self):
        return dict(clock=CLOCK_ID, boot_id=self.boot_id,
                    monotonic_ns=self.now_ns(), pid=os.getpid())


def record_stamp():
    return MonotonicClock().stamp()


def duration_ns(start, end):
    if (start.get('clock') != CLOCK_ID or end.get('clock') != CLOCK_ID
            or not start.get('boot_id') or start.get('boot_id') != end.get('boot_id')):
        raise TimingError('duration requires the same host boot and monotonic clock')
    a, b = start.get('monotonic_ns'), end.get('monotonic_ns')
    if type(a) is not int or type(b) is not int or a < 0 or b < a:
        raise TimingError('invalid/reversed monotonic interval')
    return b - a


def remaining_ns(deadline_ns, clock=None):
    if type(deadline_ns) is not int or deadline_ns < 0:
        raise TimingError('deadline integer required')
    return max(0, deadline_ns - (clock or MonotonicClock()).now_ns())


def timing_contract():
    return dict(protocol=PROTOCOL, clock=CLOCK_ID, unit='nanoseconds',
        cross_process='comparable only for same Linux host boot_id and clock',
        durations='monotonic_ns differences; never UTC or token/throughput estimates',
        fields=['generate_start', 'prompt_callback', 'first_generated_token',
                'first_non_special_token', 'first_nonempty_decoded_text', 'stream_end'],
        first_text_definition='decoded prefix contains a non-whitespace, non-control, non-U+FFFD character',
        first_text_is_semantic_success=False, semantic_text_validity='not_machine_qualified',
        client_ttft_ns=None, client_delivery='not observed by this worker-side callback',
        observer_effect='passive token copy/decode consumes measured wall time; no logits or tokens changed',
        instrumentation_overhead='HF may transfer tokens to CPU before put; callback_work_ns excludes that transfer, full generation wall includes it; overhead is not zero',
        no_text_policy_changed=False)


def latency_contract():
    """Static, pure-Python identity for supervisor/admission manifests."""
    result = timing_contract()
    result.update(
        supervisor_timestamps=['job_start', 'worker_spawn', 'load_start', 'load_end',
                               'job_end'],
        runtime_timestamps=['agent_start', 'pm_start', 'controller_start',
                            'controller_end', 'resource_start', 'resource_end',
                            'terminal_start', 'terminal_end', 'agent_end'],
        cache='terminal result reuse disabled in this comparison; record every physical call',
        cold='one actual cold load per job measured separately; never impute it to every task',
        warm='later calls share the admitted loaded model; zero extra warmup calls',
        aggregation='actual intervals only; shared load and overlapping intervals not double-counted',
        agent_scope='runtime must bind agent_start/pm_start/end; callback does not invent them',
        deadline='supervisor supplies absolute monotonic_ns in the same verified boot domain',
        client_scope='no actual client event => client TTFT remains null')
    return result


def _has_text(text):
    return any(not char.isspace() and char != '\ufffd'
               and not unicodedata.category(char).startswith('C') for char in text)


class FirstOutputObserver:
    """HF streamer duck type: put(prompt), put(generated token IDs), end().

    No stdout/client streaming. Callback timing is internal token observation.
    The first token can be EOS, a special token or whitespace, unlike first text.
    """
    def __init__(self, tokenizer, *, prompt_token_count, clock=None,
                 generation_start_stamp=None):
        if type(prompt_token_count) is not int or prompt_token_count < 1:
            raise TimingError('prompt token count')
        self.tokenizer = tokenizer
        self.prompt_token_count = prompt_token_count
        self.clock = clock or MonotonicClock()
        self.events = {'generate_start': generation_start_stamp,
                       'prompt_callback': None, 'first_generated_token': None,
                       'first_non_special_token': None,
                       'first_nonempty_decoded_text': None, 'stream_end': None}
        self.special_ids = set(getattr(tokenizer, 'all_special_ids', []))
        self.tokens = []
        self.prompt_seen = self.ended = False
        self.callback_work_ns = 0

    def put(self, value):
        entered = self.clock.now_ns()
        if self.ended:
            raise TimingError('token after stream end')
        ids = value.tolist() if hasattr(value, 'tolist') else value
        if type(ids) is not list:
            raise TimingError('streamer token vector')
        if ids and type(ids[0]) is list:
            if len(ids) != 1:
                raise TimingError('single-sequence streamer required')
            ids = ids[0]
        if any(type(token) is not int or token < 0 for token in ids):
            raise TimingError('streamer token IDs')
        observed = self.clock.stamp()
        if not self.prompt_seen:
            if len(ids) != self.prompt_token_count:
                raise TimingError('initial streamer callback must contain exact prompt length')
            self.prompt_seen = True
            self.events['prompt_callback'] = observed
        elif ids:
            self.tokens.extend(ids)
            if self.events['first_generated_token'] is None:
                self.events['first_generated_token'] = observed
            if self.events['first_non_special_token'] is None and any(x not in self.special_ids for x in ids):
                self.events['first_non_special_token'] = observed
            if self.events['first_nonempty_decoded_text'] is None:
                text = self.tokenizer.decode(self.tokens, skip_special_tokens=True,
                                             clean_up_tokenization_spaces=False)
                if _has_text(text):
                    self.events['first_nonempty_decoded_text'] = self.clock.stamp()
        self.callback_work_ns += self.clock.now_ns() - entered

    def end(self):
        if self.ended or not self.prompt_seen:
            raise TimingError('invalid stream end')
        self.ended = True
        self.events['stream_end'] = self.clock.stamp()

    def measurement(self):
        start = self.events['generate_start']
        durations = {key + '_latency_ns': (duration_ns(start, value)
            if start is not None and value is not None else None)
            for key, value in self.events.items() if key != 'generate_start'}
        return dict(protocol=PROTOCOL, events=dict(self.events), **durations,
            generated_token_count=len(self.tokens), prompt_callback_seen=self.prompt_seen,
            stream_ended=self.ended, callback_work_ns=self.callback_work_ns,
            callback_work_scope='inside put only; HF pre-callback CPU transfer is excluded here but included in generation wall',
            first_text_status=('nonempty_decoded_text_observed'
                if self.events['first_nonempty_decoded_text'] else 'not_observed'),
            semantic_text_validity='not_machine_qualified', client_ttft_ns=None,
            timing_scope='worker-side passive observation, not client delivery')

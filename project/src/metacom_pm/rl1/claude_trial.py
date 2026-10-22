"""Bounded Claude pilot transport and accounting, no implicit requests/retries.

The launch entry binds user scope, immutable inputs and the shared ledger.
No alternate provider, account reload, schema repair or training lives here.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error

from .schema import digest

VERSION = 'pmrl1-claude-bounded-pilot-v1-20261022'
ENDPOINT = 'https://api.anthropic.com/v1/messages'


class Collector:
    def __init__(self):
        self.message = None
        self.blocks = {}
        self.closed = set()
        self.done = False
        self.final_usage = False
        self.other_events = []

    def feed(self, event):
        kind = event['type']
        if self.done:
            raise ValueError('event after message_stop')
        if kind == 'message_start':
            if self.message is not None:
                raise ValueError('duplicate message_start')
            self.message = deepcopy(event['message'])
            if self.message.get('content') != []:
                raise ValueError('nonempty initial content')
        elif kind == 'content_block_start':
            i = event['index']
            if self.message is None or i in self.blocks or i != len(self.blocks):
                raise ValueError('invalid content block ordering')
            self.blocks[i] = deepcopy(event['content_block'])
        elif kind == 'content_block_delta':
            i, delta = event['index'], event['delta']
            if i not in self.blocks or i in self.closed:
                raise ValueError('delta outside open block')
            fields = {'text_delta': ('text', 'text'), 'thinking_delta': ('thinking', 'thinking'),
                      'signature_delta': ('thinking', 'signature')}
            if delta['type'] not in fields:
                raise ValueError('unexpected delta; no tools or fallback allowed')
            expected, key = fields[delta['type']]
            if self.blocks[i]['type'] != expected:
                raise ValueError('block/delta type mismatch')
            self.blocks[i][key] = self.blocks[i].get(key, '') + delta[key]
        elif kind == 'content_block_stop':
            i = event['index']
            if i not in self.blocks or i in self.closed:
                raise ValueError('invalid block stop')
            self.closed.add(i)
        elif kind == 'message_delta':
            if self.message is None:
                raise ValueError('delta without message')
            delta = event['delta']
            if 'model' in delta and delta['model'] != self.message['model']:
                raise ValueError('provider changed model')
            self.message.update(delta)
            # Counts in successive message_delta events are cumulative, not additive.
            self.message.setdefault('usage', {}).update(event.get('usage', {}))
            self.final_usage = self.final_usage or 'output_tokens' in event.get('usage', {})
        elif kind == 'message_stop':
            if self.message is None or set(self.blocks) != self.closed or not self.final_usage:
                raise ValueError('incomplete blocks or final usage')
            self.done = True
        elif kind == 'error':
            raise RuntimeError('stream_error:' + event.get('error', {}).get('type', 'unknown'))
        elif kind != 'ping':
            self.other_events.append(deepcopy(event))

    def complete(self):
        if not self.done or self.message is None or self.message.get('stop_reason') is None:
            raise ValueError('incomplete message stream')
        return self.message | dict(content=[self.blocks[i] for i in sorted(self.blocks)],
                                   unrecognized_events=self.other_events)


class Transport:
    def __init__(self, key, *, opener=None, timeout=900):
        if not key:
            raise ValueError('credential absent')
        self.key, self.timeout = key, timeout
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def send(self, prepared, raw_path):
        from .claude_delivery import VERSION as DELIVERY_VERSION
        if prepared['identity'] != digest(dict(version=DELIVERY_VERSION, body=prepared['wire_body'])):
            raise ValueError('outbound payload drift')
        body = json.dumps(prepared['wire_body'], ensure_ascii=False).encode()
        req = urllib.request.Request(ENDPOINT, data=body, headers={
            'Content-Type': 'application/json', 'x-api-key': self.key,
            'anthropic-version': '2023-06-01'})
        collector = Collector()
        start = time.monotonic()
        try:
            with Path(raw_path).open('xb') as archive:
                with self.opener.open(req, timeout=90) as response:
                    headers = {k.lower(): v for k, v in response.headers.items()
                               if k.lower() in ('request-id', 'x-request-id', 'date')}
                    for line in response:
                        archive.write(line); archive.flush()
                        if time.monotonic() - start > self.timeout:
                            raise TimeoutError('total stream watchdog')
                        if line.startswith(b'data:'):
                            collector.feed(json.loads(line[5:].strip()))
                        if collector.done and not line.strip():
                            break
                    archive.flush();os.fsync(archive.fileno())
            return dict(http_status=200, message=collector.complete(),
                        headers=headers, elapsed_seconds=time.monotonic()-start)
        except urllib.error.HTTPError as exc:
            # Explicit server rejection can be reconciled as failed/unbilled.
            # Never infer zero cost from timeout, broken stream or ambiguous 5xx.
            error_body = exc.read()
            error_path = Path(str(raw_path)+'.http_error')
            with error_path.open('xb') as f:
                f.write(error_body)
            return dict(http_status=exc.code, rejection_body_sha256=digest(error_body.hex()),
                headers={k.lower():v for k,v in exc.headers.items() if k.lower() in ('request-id','x-request-id')},
                elapsed_seconds=time.monotonic()-start)


def nominal_nanodollars(message):
    """Frozen standard Sonnet 5.5 rates; full output includes thinking.

    No cache was requested. Returned cache reads are still counted at base rate
    as a conservative envelope. Unexpected cache writes/tool/fast/geo settings
    fail settlement rather than silently applying an incomplete price formula.
    """
    if message.get('model') != 'claude-sonnet-5-5':
        raise ValueError('unknown price/model identity')
    u = message['usage']
    for k in ('input_tokens', 'output_tokens'):
        if type(u.get(k)) is not int or u[k] < 0:
            raise ValueError('missing full usage')
    reads = u.get('cache_read_input_tokens', 0)
    writes = u.get('cache_creation_input_tokens', 0)
    if type(reads) is not int or reads < 0 or writes != 0 or any((u.get('server_tool_use') or {}).values()):
        raise ValueError('unexpected extra billing dimensions')
    if u.get('inference_geo') not in (None, 'global') or u.get('speed') not in (None, 'standard'):
        raise ValueError('unpriced geography/speed')
    # $2/$10 per million tokens = 2,000/10,000 nanodollars per token.
    return (u['input_tokens'] + reads)*2000 + u['output_tokens']*10000


def budget_class(engine):
    class ClaudeBudget(engine.DiagnosticBudget):
        def reserve(self, rid, amount, binding):
            with self.locked():
                total, trial, reserved, settled = self._totals(self.events())
                if rid in reserved:
                    raise ValueError('already reserved; no implicit redispatch')
                if set(reserved) - set(settled):
                    raise ValueError('unsettled global liability; reconcile before dispatch')
                if amount < 0 or self.stage_total(reserved, settled) + amount > self.stage_cap:
                    raise ValueError('stage liability cap')
                if trial + amount > self.trial_cap:
                    raise ValueError('scoped trial liability cap')
                if total-self.baseline+self.external_liability+amount > self.shared_cap:
                    raise ValueError('shared followup cap')
                if total+self.external_liability+amount > self.old_cap:
                    raise ValueError('legacy programme cap')
                self._append(dict(event='RESERVED', reservation_id=rid, maximum_cost_usd=engine.s.usd(amount),
                    selection_trial=self.trial, stage=self.study, call_class='PRIMARY' if binding['ordinal']==0 else 'TECHNICAL_RECOVERY',
                    logical_call_id=binding['slot_id'], call_hash=binding['input_identity'],
                    provider='Anthropic official API', model='claude-sonnet-5-5',
                    funding='user-reported API credits; redemption not independently verified',
                    binding=binding, timestamp=time.time(), protocol=VERSION))
    return ClaudeBudget

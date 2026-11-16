"""Opt-in RS applicability intervention; no changes to the frozen v3 renderer.

This is a development prompt intervention, not a factuality classifier or a new
reward. Resource bodies and the current user turn are preserved in full.
"""
from copy import deepcopy
import json

from .representation import RESOURCE_GUIDANCE_V2
from .representation_direct import DirectReplyRenderer
from .schema import digest

VERSION = 'pm-rl1-rs-applicability-v1-20261019'
INSTRUCTION = (
    'RS applicability: A conversational move may mention a situation as part of '
    'its suggestion. That mention alone is not evidence that the situation applies '
    'to this user. Separate the move from its assumptions about the user\'s '
    'circumstances, actions or outcomes. Use such assumptions as facts only when '
    'established in the current conversation or in relevant acquired MP, MS or ME '
    'evidence, respecting attribution and time. If an assumption is not established, '
    'omit it or, when relevant, ask without presupposing it. General encouragement '
    'and open questions need not introduce an unsupported situation.\n'
)
BLOCK_START = '\n\n' + RESOURCE_GUIDANCE_V2 + '<resources>\n'


def adapt_messages(messages, counts):
    """Adapt a validated v3 request. No text search for topic-specific fixes."""
    if len(counts) != 4 or any(type(n) is not int or n < 0 for n in counts) or sum(counts) > 4:
        raise ValueError('invalid canonical counts')
    if (len(messages) != 2 or [m.get('role') for m in messages] != ['system', 'user']
            or any(set(m) != {'role', 'content'} for m in messages)):
        raise ValueError('expected complete direct-user v3 messages')
    out = deepcopy(messages)
    system = out[0]['content']
    if sum(counts) == 0:
        if BLOCK_START in system:
            raise ValueError('OFF unexpectedly contains a resource block')
        return out
    if system.count(BLOCK_START) != 1 or not system.endswith('\n</resources>'):
        raise ValueError('unknown, partial or already adapted resource interface')
    before, body = system.split(BLOCK_START)
    resources = json.loads(body[:-len('\n</resources>')])
    heads = [r['head'] for r in resources]
    if heads != [h for h, n in zip(('RS', 'MP', 'MS', 'ME'), counts) for _ in range(n)]:
        raise ValueError('resource list/counts mismatch')
    if counts[0]:
        out[0]['content'] = before + '\n\n' + INSTRUCTION + RESOURCE_GUIDANCE_V2 + '<resources>\n' + body
    return out


class RSApplicabilityRenderer(DirectReplyRenderer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parent_identity = self.identity
        self.identity = digest(dict(parent=self.parent_identity, version=VERSION,
                                    instruction=INSTRUCTION))

    def resource_block(self, spec, counts):
        block = super().resource_block(spec, counts)
        # The extra instruction is charged in the normal full-block token cost.
        return INSTRUCTION + block if counts[0] and block else block


def paired_request(original, *, arm, renderer_identity, draw_identity):
    if arm not in ('baseline', 'rs_applicability'):
        raise ValueError('unknown arm')
    payload = deepcopy({k: v for k, v in original.items() if k != 'request_id'})
    if digest(payload) != original['request_id']:
        raise ValueError('old request binding changed')
    if arm == 'rs_applicability':
        payload['messages'] = adapt_messages(payload['messages'], payload['provenance']['canonical_counts'])
    payload.update(renderer_identity=renderer_identity, draw_identity=draw_identity)
    return dict(request_id=digest(payload), **payload)

"""Opt-in common head-action interface; no G/J, reward or training execution.

This development contract compares adaptive head choices with a head program
committed before reading. Both use the SAME content-adaptive retriever. It does
not silently promote that OneShot definition, a cost scale, or a checkpoint.
"""
from dataclasses import asdict, dataclass, replace

from .resource_organization import OrganizationSession, RANKING
from .schema import Action, HEADS, PublicTurn, digest

VERSION = 'pmrl1-organized-head-interface-dev-v1'


@dataclass(frozen=True)
class ReadText:
    head: str
    content: str | None
    reported_at: str | None


@dataclass(frozen=True)
class HeadObservation:
    """Actor/critic whitelist. No resource addresses or private state hashes."""
    current_prefix: tuple[PublicTurn, ...]
    acquired: tuple[ReadText, ...]
    counts: tuple[int, ...]
    remaining_items: tuple[int, ...]
    next_input_tokens: tuple[int | None, ...]
    resource_tokens: int
    input_tokens: int
    native_context_limit: int
    action_mask: tuple[bool, ...]
    stopped: bool
    body_visible: bool = True


def validate_observation(o):
    if type(o) is not HeadObservation:
        raise TypeError('only the new public HeadObservation is accepted')
    if (not o.current_prefix or any(type(t) is not PublicTurn for t in o.current_prefix)
            or o.current_prefix[-1].role != 'seeker' or type(o.body_visible) is not bool
            or type(o.stopped) is not bool or len(o.counts) != 4 or len(o.remaining_items) != 4
            or len(o.next_input_tokens) != 4 or len(o.action_mask) != 5
            or any(type(n) is not int or n < 0 for n in (*o.counts, *o.remaining_items))
            or any(type(x) is not bool for x in o.action_mask)
            or any(type(n) is not int or n < 0 for n in (o.resource_tokens, o.input_tokens))
            or type(o.native_context_limit) is not int or not 0 < o.input_tokens < o.native_context_limit
            or len(o.acquired) != sum(o.counts)):
        raise ValueError('invalid organized observation')
    for x in o.acquired:
        if (type(x) is not ReadText or x.head not in HEADS
                or (o.body_visible and (not isinstance(x.content, str) or not x.content.strip()))
                or (not o.body_visible and x.content is not None)):
            raise ValueError('invalid acquired-text visibility')
    if tuple(sum(a.head == h for a in o.acquired) for h in HEADS) != o.counts:
        raise ValueError('acquired/count mismatch')
    expected = [not o.stopped]
    for remaining, tokens in zip(o.remaining_items, o.next_input_tokens):
        if (remaining == 0) != (tokens is None) or (tokens is not None and (type(tokens) is not int or tokens < 1)):
            raise ValueError('next-item metadata differs from inventory availability')
        expected.append(not o.stopped and tokens is not None and tokens < o.native_context_limit)
    if tuple(expected) != o.action_mask:
        raise ValueError('mask differs from native-capacity contract')


def no_text(o):
    validate_observation(o)
    result = replace(o, acquired=tuple(replace(x, content=None) for x in o.acquired), body_visible=False)
    validate_observation(result)
    return result


class HeadSession:
    """Construction-side environment. Only observe() crosses the policy boundary.

    GET selects the current top result of its head. No skipping oversized items,
    free graph expansion, arbitrary action cap, or hidden generation occurs.
    """
    def __init__(self, catalog, renderer, *, without_text=False):
        if type(without_text) is not bool:
            raise ValueError('explicit boolean text visibility required')
        self._without_text = without_text
        self._catalog, self._renderer = catalog, renderer
        self._session = OrganizationSession(catalog, renderer)
        self._trace = []
        self._cached = None
        self.interface_identity = digest(dict(version=VERSION, ranking=RANKING,
            actions=[a.name for a in Action], retrieval='prefix_plus_acquired_for_all_methods',
            capacity='native_context_only', oneshot='precommitted_head_program_candidate',
            status='DEVELOPMENT_NOT_FROZEN_FOR_RESEARCH'))

    def observe(self):
        if self._cached is None:
            base = self._session.observe()
            keys = tuple(self._session.receipt()['acquired'])
            remaining, tokens = [], []
            for h in HEADS:
                hits = self._catalog.rank(h, keys)
                remaining.append(len(hits))
                tokens.append(self._renderer.usage(self._catalog, keys + (hits[0]['key'],))['input_tokens'] if hits else None)
            mask = (not base.stopped,) + tuple(not base.stopped and n is not None and n < self._renderer.context_limit for n in tokens)
            self._cached = HeadObservation(base.current_prefix,
                tuple(ReadText(*a) for a in base.acquired), base.counts, tuple(remaining), tuple(tokens),
                base.resource_tokens, base.input_tokens, self._renderer.context_limit, mask, base.stopped)
            validate_observation(self._cached)
        return no_text(self._cached) if self._without_text else self._cached

    def step(self, action, *, expected_observation=None):
        if type(action) not in (int, Action) or action not in tuple(Action):
            raise ValueError('one of STOP/GET_RS/GET_MP/GET_MS/GET_ME required')
        before = self.observe()
        if expected_observation is not None and expected_observation != digest(asdict(before)):
            raise ValueError('stale observation; action not executed')
        if not before.action_mask[action]:
            raise ValueError('masked action; no fallback or truncated acquisition')
        if action == Action.STOP:
            self._session.stop()
        else:
            self._session.get(HEADS[action-1])
        self._cached = None
        after = self.observe()
        self._trace.append(dict(action=int(action), before=digest(asdict(before)), after=digest(asdict(after)),
            resource_token_delta=after.resource_tokens-before.resource_tokens, reward=None))
        return after

    def terminal(self, *, executor_identity, draw_identity):
        if not self.observe().stopped or not executor_identity or not draw_identity:
            raise ValueError('STOP and explicit executor/draw identities required')
        receipt = self._session.receipt()
        selected = self._catalog.canonical(tuple(receipt['acquired']))
        messages = self._renderer.messages(self._catalog, tuple(receipt['acquired']))
        body = dict(version=VERSION, prefix_identity=self._catalog.prefix.identity,
            catalog_identity=self._catalog.identity, renderer_identity=self._renderer.identity,
            interface_identity=self.interface_identity, retrieval_method=RANKING,
            executor_identity=executor_identity, draw_identity=draw_identity, messages=messages,
            selected_resource_identities=[x.identity for x in selected], selected_keys=[x.key for x in selected],
            usage=receipt['usage'])
        # A content identity is diagnostic; it does NOT grant cross-provenance cache reuse.
        return dict(**body, identity=digest(body), message_identity=digest(messages),
            status='PREPARED_ONLY', reward=None, measurement_qualified=False,
            model_calls=0, trace=list(self._trace), cost_contract=None)


@dataclass(frozen=True)
class HeadProgram:
    initial_observation_identity: str
    interface_identity: str
    actions: tuple[int, ...]

    @property
    def identity(self):
        return digest(asdict(self))


def commit_program(initial, actions, *, interface_identity):
    validate_observation(initial)
    actions = tuple(actions)
    if (initial.stopped or any(initial.counts) or not interface_identity or not actions
            or any(type(a) not in (int, Action) or a not in tuple(Action) for a in actions)
            or actions[-1] != Action.STOP or Action.STOP in actions[:-1]):
        raise ValueError('complete program must be committed before any GET and end at STOP')
    return HeadProgram(digest(asdict(initial)), interface_identity, tuple(int(a) for a in actions))


def replay_program(session, program):
    if (type(program) is not HeadProgram or session.interface_identity != program.interface_identity
            or digest(asdict(session.observe())) != program.initial_observation_identity):
        raise ValueError('program belongs to another initial observation/interface')
    # Revalidate a deserialized/tampered program too. No future feasibility oracle
    # is returned to its chooser. An infeasible program fails without swapping arms.
    if commit_program(session.observe(), program.actions, interface_identity=session.interface_identity) != program:
        raise ValueError('invalid program')
    for action in program.actions:
        session.step(action)
    return session.observe()

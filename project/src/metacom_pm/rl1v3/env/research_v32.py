"""V3.2 research layer over the finite-head environment (``pmrl1v3-v32-research-env-v1``).  CPU only.

Keeps the Phase-1 semantics (STOP / GET_RS / GET_MP / GET_ME / GET_MS, each head at most once,
reward only at STOP) and adds what the V3.2 brief requires before research use:

* ``BoundEpisode``: an episode is bound to one ``PrefixAsOfBinding``; the env's TerminalIdentity
  must equal the binding's identity fields, and every terminal is addressed by the composite key
  ``asof_terminal_key_sha256(C0 key, binding)``;
* ``try_step``: invalid actions return a typed ``Invalid`` (already_read, no_legal_candidates,
  over_capacity, max_gets, after_stop, unknown_action, read_failure:<reason>) and leave the state
  unchanged - no fabricated empty reading, no ordinal advance;
* ``observe``: the C0 observation, checked against the PM whitelist; unread resources expose only
  the approved availability metadata; ``notext=True`` gives the NoText ablation (same fields minus
  the delivered reading text);
* ``stop_value``: incomplete terminals return a reward interval or ``pending`` - never 0;
* ``ReplayCache``: version-isolated store; a lookup under another binding / G / decode / renderer
  misses (no migration of old outcomes to new identities).
"""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass

from ..asof import binding as AB
from ..asof import visibility as VIS
from . import finite_head as E

PROTOCOL = "pmrl1v3-v32-research-env-v1"
INVALID_REASONS = ("after_stop", "unknown_action", "already_read", "no_legal_candidates", "over_capacity",
                   "max_gets", "read_failure")


class BindingMismatch(ValueError):
    pass


class ObservationLeak(RuntimeError):
    """The observation contains a field or value outside the PM whitelist."""


@dataclass(frozen=True)
class Invalid:
    action: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class Interval:
    status: str                 # complete | partial | pending
    lower: float | None
    upper: float | None
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        if self.status == "pending" and (self.lower is not None or self.upper is not None):
            raise ValueError("pending has no numeric bounds")
        if self.status != "pending" and (self.lower is None or self.upper is None or self.lower > self.upper):
            raise ValueError("bounds required, lower <= upper")
        if self.status == "complete" and self.lower != self.upper:
            raise ValueError("complete means a point value")


def _identity_of(env) -> dict:
    return dataclasses.asdict(env.identity)


class BoundEpisode:
    def __init__(self, env, binding: AB.PrefixAsOfBinding, *, intervals=None):
        ident = _identity_of(env)
        want = {k: getattr(binding, k) for k in ident}
        if ident != want:
            raise BindingMismatch(f"env identity differs from the as-of binding: "
                                  f"{sorted(k for k in ident if ident[k] != want[k])}")
        if env.prefix.prefix_id != binding.prefix_id or env.prefix.runtime_sha256 != binding.prefix_context_sha256:
            raise BindingMismatch("env prefix differs from the binding prefix")
        self.env, self.binding = env, binding
        self.intervals = dict(intervals or {})          # composite key -> Interval
        self.invalid_log: list[Invalid] = []

    # ------------------------------------------------------------------ actions
    def reset(self):
        return self.env.reset()

    def try_step(self, s, action: str):
        """Returns (state, Invalid | info).  Never raises for an invalid GET; state unchanged then."""
        if s.done:
            return self._invalid(s, action, "after_stop")
        if action not in E.ACTIONS:
            return self._invalid(s, action, "unknown_action")
        if action == E.STOP:
            # R3 (round 13): STOP ends the episode; later actions are typed ``after_stop``.  The terminal key is
            # unchanged because it depends on the readings, not on the done flag.
            return dataclasses.replace(s, done=True), dict(stop=True)
        head = E.HEAD_OF[action]
        if head in s.order:
            return self._invalid(s, action, "already_read")
        if self.env.availability[head] <= 0:
            return self._invalid(s, action, "no_legal_candidates")
        if len(s.order) >= self.env.max_gets:
            return self._invalid(s, action, "max_gets")
        if action not in self.env.legal_actions(s):
            return self._invalid(s, action, "over_capacity")
        try:
            nxt, _, _, info = self.env.step(s, action)
        except E.IllegalAction as exc:
            return self._invalid(s, action, "read_failure", str(exc)[:200])
        return nxt, info

    def _invalid(self, s, action, reason, detail=""):
        inv = Invalid(action, reason, detail)
        self.invalid_log.append(inv)
        return s, inv

    # ------------------------------------------------------------------ views
    def observe(self, s, *, notext: bool = False, private_tokens=(), future_texts=(), legal_texts=()) -> dict:
        obs = VIS.to_plain(self.env.observe(s))
        if notext:
            for r in obs["acquired"]:
                r.pop("reading_text", None)
        rep = VIS.scan(obs, VIS.PM_OBSERVATION_NOTEXT if notext else VIS.PM_OBSERVATION,
                       private_tokens=private_tokens, future_texts=future_texts, legal_texts=legal_texts)
        if not rep["ok"]:
            raise ObservationLeak(rep)
        return obs

    def composite_key(self, s) -> str:
        return AB.asof_terminal_key_sha256(self.env.terminal_key(s).sha256, self.binding)

    def stop_value(self, s) -> Interval:
        """Reward of STOP at ``s`` as an interval; ``pending`` when nothing is known.  Never 0."""
        return self.intervals.get(self.composite_key(s), Interval("pending", None, None, ("no_terminal",)))


class ReplayCache:
    """Generation / judgement cache keyed by composite as-of key; identity mismatches always miss."""

    def __init__(self):
        self._rows: dict[str, dict] = {}

    @staticmethod
    def key(c0_key_sha256: str, binding: AB.PrefixAsOfBinding) -> str:
        return AB.asof_terminal_key_sha256(c0_key_sha256, binding)

    def put(self, c0_key_sha256: str, binding, value: dict) -> str:
        """Write-once; an identical retry is idempotent (R4, round 13).  The stored row is a deep copy."""
        k = self.key(c0_key_sha256, binding)
        row = copy.deepcopy(dict(value, binding_sha256=binding.sha256, binding_tier=binding.tier))
        if k in self._rows:
            if self._rows[k] != row:
                raise ValueError("write-once: a different value for the same identity")
            return k
        self._rows[k] = row
        return k

    def get(self, c0_key_sha256: str, binding):
        """Returns a deep copy, so callers cannot alias the stored row (R4, round 13)."""
        row = self._rows.get(self.key(c0_key_sha256, binding))
        return copy.deepcopy(row) if row is not None else None

    def migrate(self, *_a, **_k):
        raise PermissionError("outcomes are never migrated to a new writer/snapshot/G/decode/renderer identity")

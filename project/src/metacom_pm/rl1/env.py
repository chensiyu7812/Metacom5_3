"""No-model deterministic acquisition; STOP awaits bound real G/J records.

Private receipts/snapshots are deliberately separate from policy StepResult.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy

from .render import Renderer
from .schema import Action, CandidateMetadata, Counts, EpisodeSpec, Observation, PLANS, Score, digest

ZERO: Counts = (0, 0, 0, 0)


@dataclass(frozen=True)
class StepResult:
    observation: Observation
    reward: float | None
    terminated: bool
    phase: str


class ResourceEnv:
    def __init__(self, spec: EpisodeSpec, renderer: Renderer):
        self._spec, self._renderer = spec, renderer
        self._binding = digest(dict(spec=spec.identity, renderer=renderer.identity))
        self._counts = ZERO
        self._phase = "acquiring"
        self._actions: list[int] = []
        self._receipts: list[dict] = []
        self._generation: dict | None = None
        self._feedback: dict | None = None
        self._failure: str | None = None
        if not renderer.fits(spec, ZERO):
            raise ValueError("public prefix alone exhausts context")
        # Reachability matters if tokenizer length is non-monotone. OneShot
        # receives exactly the sequentially reachable terminal treatments.
        reachable = {ZERO}
        for plan in PLANS[1:]:
            if (any(plan[i] > min(4, len(spec.inventory[i])) for i in range(4)) or
                    not renderer.fits(spec, plan)):
                continue
            if any(tuple(n - (j == i) for j, n in enumerate(plan)) in reachable
                   for i in range(4) if plan[i]):
                reachable.add(plan)
        self._initial_mask = tuple(p in reachable for p in PLANS)

    @property
    def state_hash(self) -> str:
        return digest(dict(binding=self._binding, counts=self._counts, phase=self._phase,
                           actions=self._actions, generation=self._generation,
                           feedback=self._feedback, failure=self._failure))

    @property
    def phase(self) -> str:
        return self._phase

    def _mask(self) -> tuple[bool, ...]:
        if self._phase != "acquiring":
            return (False,) * 5
        allowed = [True]
        for i, n in enumerate(self._counts):
            next_plan = tuple(v + (j == i) for j, v in enumerate(self._counts))
            allowed.append(sum(self._counts) < 4 and n < min(4, len(self._spec.inventory[i]))
                           and self._renderer.fits(self._spec, next_plan))
        return tuple(allowed)

    def observe(self) -> Observation:
        metadata = tuple(tuple(CandidateMetadata(i + 1, items[i].similarity,
                            items[i].raw_tokens, items[i].coarse_age) if i < len(items) else None
                               for i in range(4)) for items in self._spec.inventory)
        return Observation(self._spec.prefix.turns,
                           self._renderer.acquired(self._spec, self._counts), self._counts,
                           self._spec.resource_budget - self._renderer.cost(self._spec, self._counts),
                           4 - sum(self._counts),
                           tuple(len(items) - n for items, n in zip(self._spec.inventory, self._counts)),
                           metadata, self._mask(), self._initial_mask)

    def step(self, action: Action | int, *, expected_state_hash: str) -> StepResult:
        if expected_state_hash != self.state_hash:
            raise ValueError("stale state / duplicate action")
        if isinstance(action, bool) or not isinstance(action, int):
            raise ValueError("action must be an integer enum value")
        action = Action(action)
        if not self._mask()[action]:
            raise ValueError("illegal action")
        before = self.state_hash
        old_cost = self._renderer.cost(self._spec, self._counts)
        self._actions.append(int(action))
        if action == Action.STOP:
            self._phase = "pending_generation"
            reward = None
        else:
            i = int(action) - 1
            self._counts = tuple(v + (j == i) for j, v in enumerate(self._counts))
            delta = self._renderer.cost(self._spec, self._counts) - old_cost
            reward = -self._spec.cost_weight * delta / self._spec.resource_budget
        self._receipts.append(dict(before=before, action=int(action), after=self.state_hash,
                                   counts=self._counts, reward=reward))
        return StepResult(self.observe(), reward, False, self._phase)

    def generation_request(self) -> dict:
        if self._phase not in ("pending_generation", "pending_score", "terminal"):
            raise ValueError("STOP must freeze a plan first")
        return self._request(self._counts)

    def _request(self, counts: Counts) -> dict:
        payload = dict(messages=self._renderer.messages(self._spec, counts),
                       executor_identity=self._spec.executor_identity,
                       draw_identity=self._spec.draw_identity,
                       renderer_identity=self._renderer.identity)
        return dict(request_id=digest(payload), **payload)

    def accept_generation(self, *, request_id: str, text: str, finish_reason: str,
                          runtime_identity: str) -> None:
        if self._phase != "pending_generation" or request_id != self._request(self._counts)["request_id"]:
            raise ValueError("generation identity/phase mismatch")
        if runtime_identity != self._spec.executor_identity:
            raise ValueError("executor runtime mismatch")
        self._generation = dict(request_id=request_id, text=text, finish_reason=finish_reason,
                                runtime_identity=runtime_identity)
        if finish_reason != "natural_stop" or not text.strip():
            self.fail("incomplete_generation:" + finish_reason)
        else:
            self._phase = "pending_score"

    def accept_scores(self, *, on: Score, off: Score, judge_identity: str,
                      on_response_sha256: str, off_request_id: str,
                      off_response: str, off_finish_reason: str,
                      off_runtime_identity: str) -> StepResult:
        if self._phase != "pending_score" or self._generation is None:
            raise ValueError("real generation required before scoring")
        if (judge_identity != self._spec.judge_identity or
                on_response_sha256 != digest(self._generation["text"]) or
                off_request_id != self._request(ZERO)["request_id"] or
                off_runtime_identity != self._spec.executor_identity):
            raise ValueError("score/OFF cache identity mismatch")
        if not off_response.strip() or off_finish_reason != "natural_stop":
            raise ValueError("OFF requires completed generation")
        if self._counts == ZERO and (off_response != self._generation["text"] or on != off):
            raise ValueError("true OFF must share the same observed reply and score")
        if on.uncertain or off.uncertain:
            raise ValueError("uncertain measurement remains pending; not reward zero")
        reward = on.utility(self._spec.alpha) - off.utility(self._spec.alpha)
        self._feedback = dict(on=asdict(on), off=asdict(off), judge_identity=judge_identity,
                              on_response_sha256=on_response_sha256, off_request_id=off_request_id,
                              off_response=off_response, off_finish_reason=off_finish_reason,
                              off_runtime_identity=off_runtime_identity, stop_reward=reward)
        self._phase = "terminal"
        return StepResult(self.observe(), reward, True, self._phase)

    def fail(self, reason: str) -> None:
        if self._phase in ("terminal", "technical_failure") or not reason:
            raise ValueError("invalid failure transition")
        self._failure, self._phase = reason, "technical_failure"

    def snapshot(self) -> dict:
        # Audit-only. Never forward this to actor or critic.
        return deepcopy(dict(binding=self._binding, actions=self._actions.copy(), phase=self._phase,
                    generation=self._generation, feedback=self._feedback, failure=self._failure,
                    receipts=self._receipts.copy(), state_hash=self.state_hash))

    @classmethod
    def restore(cls, spec: EpisodeSpec, renderer: Renderer, saved: dict) -> ResourceEnv:
        env = cls(spec, renderer)
        if saved["binding"] != env._binding:
            raise ValueError("snapshot belongs to another episode/runtime")
        for action in saved["actions"]:
            env.step(action, expected_state_hash=env.state_hash)
        if saved["generation"] is not None:
            env.accept_generation(**saved["generation"])
        if saved["feedback"] is not None:
            feedback = saved["feedback"].copy()
            feedback.pop("stop_reward")
            for key in ("on", "off"):
                feedback[key] = Score(**{**feedback[key], "evidence": tuple(feedback[key]["evidence"])})
            env.accept_scores(**feedback)
        if saved["failure"] is not None and env.phase != "technical_failure":
            env.fail(saved["failure"])
        if digest(env.snapshot()) != digest(saved):
            raise ValueError("snapshot integrity/replay mismatch")
        return env

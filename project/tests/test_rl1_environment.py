from dataclasses import asdict, replace
from itertools import product
import json

import pytest

from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.schema import Action, EpisodeSpec, HEADS, PLANS, PrefixSpec, PublicTurn, Resource, Score, digest
from metacom_pm.rl1.generation import NaturalEndPolicy
from metacom_pm.rl1.cache import AttemptCache


def fixture_spec(budget=10000):
    prefix = PrefixSpec("PRIVATE_OWNER", "PRIVATE_SESSION", 5, 0, "2026-01-05", "train",
                        (PublicTurn("seeker", "I need to talk."),))
    inventory = tuple(tuple(Resource(f"PRIVATE_ID_{h}_{i}", h, f"HIDDEN_{h}_{i}", 1 - i / 10,
                        4, None if h == "RS" else prefix.owner_id, None if h == "RS" else 1,
                        None if h == "RS" else "2026-01-01", "past", ("PRIVATE_SOURCE",))
                    for i in range(4)) for h in HEADS)
    return EpisodeSpec(prefix, inventory, "bge-test", "executor-test", "judge-test", "draw-0", budget)


def renderer():
    return Renderer(count_text=len, count_chat=lambda m: len(json.dumps(m)),
                    tokenizer_identity="TEST_CHARACTER_COUNTER", context_limit=100000)


def act(env, action):
    return env.step(action, expected_state_hash=env.state_hash)


def test_all_341_acquisition_sequences_have_70_canonical_terminal_prompts():
    spec, render = fixture_spec(), renderer()
    prompts, paths = {}, 0
    assert len(PLANS) == 70
    for length in range(5):
        for sequence in product(range(1, 5), repeat=length):
            env = ResourceEnv(spec, render)
            rewards = []
            for action in sequence:
                rewards.append(act(env, action).reward)
            counts = env.observe().counts
            if length == 4:
                assert env.observe().action_mask == (True, False, False, False, False)
            stopped = act(env, 0)
            assert stopped.reward is None and not stopped.terminated
            request = env.generation_request()
            if counts in prompts:
                assert prompts[counts] == request
            prompts[counts] = request
            assert sum(rewards) == pytest.approx(-.05 * render.cost(spec, counts) / spec.resource_budget)
            paths += 1
    assert paths == 341 and len(prompts) == 70


def test_whitelist_reveals_only_acquired_text_to_both_actor_and_critic():
    env = ResourceEnv(fixture_spec(), renderer())
    before = json.dumps(asdict(env.observe()))
    assert "PRIVATE" not in before and "HIDDEN" not in before
    act(env, Action.GET_ME)
    after = json.dumps(asdict(env.observe()))
    assert "HIDDEN_ME_0" in after and "HIDDEN_ME_1" not in after and "PRIVATE" not in after
    assert env.observe().metadata[3][1].rank == 2


def test_wrong_owner_future_and_unsorted_inventory_fail_closed():
    spec = fixture_spec()
    for change in ({"owner_id": "OTHER"}, {"source_rank": 5}, {"similarity": -1}):
        inventory = list(spec.inventory)
        inventory[1] = (replace(inventory[1][0], **change),) + inventory[1][1:]
        with pytest.raises(ValueError):
            replace(spec, inventory=tuple(inventory))


def test_zero_based_first_session_is_legal_past_for_second_session():
    spec = fixture_spec()
    inventory = tuple(tuple(replace(r, source_rank=0) if r.head != "RS" else r
                            for r in items) for items in spec.inventory)
    second = replace(spec, prefix=replace(spec.prefix, cutoff_rank=1), inventory=inventory)
    assert ResourceEnv(second, renderer()).observe().action_mask == (True,) * 5


def test_illegal_get_does_not_skip_first_item_or_become_training_negative():
    spec = fixture_spec(budget=5)
    env = ResourceEnv(spec, renderer())
    assert env.observe().action_mask == (True, False, False, False, False)
    saved = env.snapshot()
    with pytest.raises(ValueError):
        act(env, 1)
    assert env.snapshot() == saved


@pytest.mark.parametrize("action", [True, 1.0, "1", -1, 5])
def test_malformed_action_cannot_mutate_state(action):
    env = ResourceEnv(fixture_spec(), renderer())
    before = env.state_hash
    with pytest.raises(ValueError):
        env.step(action, expected_state_hash=before)
    assert env.state_hash == before


def test_nonmonotone_token_cost_preserves_telescoping_and_plan_reachability():
    class Nonmonotone(Renderer):
        def cost(self, spec, counts):
            return (0, 10, 9, 15, 20)[sum(counts)]
    r = Nonmonotone(count_text=len, count_chat=lambda _: 1, tokenizer_identity="TEST", context_limit=100)
    env = ResourceEnv(fixture_spec(budget=10), r)
    assert sum(env.observe().initial_plan_mask) == 15
    rewards = [act(env, 1).reward, act(env, 1).reward]
    assert rewards[1] > 0
    assert sum(rewards) == pytest.approx(-.05 * 9 / 10)
    # Individually fitting 2-item sets cannot jump past an overflowing first GET.
    env = ResourceEnv(fixture_spec(budget=9), r)
    assert sum(env.observe().initial_plan_mask) == 1


def test_stop_pending_replay_and_identity_bound_reward():
    spec, r = fixture_spec(), renderer()
    env = ResourceEnv(spec, r)
    get_reward = act(env, 2).reward
    stale = env.state_hash
    act(env, 0)
    with pytest.raises(ValueError):
        env.step(0, expected_state_hash=stale)
    restored = ResourceEnv.restore(spec, r, json.loads(json.dumps(env.snapshot())))
    assert restored.state_hash == env.state_hash
    request = env.generation_request()
    env.accept_generation(request_id=request["request_id"], text="ON real response fixture",
                          finish_reason="natural_stop", runtime_identity=spec.executor_identity)
    off_env = ResourceEnv(spec, r)
    act(off_env, 0)
    kwargs = dict(on=Score(4, 0, ("on evidence",)), off=Score(2, 0, ("off evidence",)),
                  judge_identity=spec.judge_identity, on_response_sha256=digest("ON real response fixture"),
                  off_request_id=off_env.generation_request()["request_id"],
                  off_response="OFF real response fixture", off_finish_reason="natural_stop",
                  off_runtime_identity=spec.executor_identity)
    with pytest.raises(ValueError):
        env.accept_scores(**{**kwargs, "off_runtime_identity": "OTHER_X"})
    assert env.phase == "pending_score"
    result = env.accept_scores(**kwargs)
    assert result.terminated and result.reward == .5
    assert get_reward + result.reward == pytest.approx(.5 - .05 * r.cost(spec, (0, 1, 0, 0)) / spec.resource_budget)
    assert ResourceEnv.restore(spec, r, json.loads(json.dumps(env.snapshot()))).state_hash == env.state_hash
    with pytest.raises(ValueError):
        ResourceEnv.restore(replace(spec, draw_identity="another-draw"), r, env.snapshot())


@pytest.mark.parametrize("reason", ["context_exhausted", "technical_timeout", "repetition_guard", "empty_output"])
def test_incomplete_generation_is_not_zero_reward(reason):
    spec, r = fixture_spec(), renderer()
    env = ResourceEnv(spec, r)
    assert act(env, 0).reward is None
    env.accept_generation(request_id=env.generation_request()["request_id"], text="partial",
                          finish_reason=reason, runtime_identity=spec.executor_identity)
    assert env.phase == "technical_failure" and env.snapshot()["feedback"] is None
    assert ResourceEnv.restore(spec, r, env.snapshot()).phase == "technical_failure"


def test_natural_end_uses_native_remainder_and_true_eos_at_boundary():
    p = NaturalEndPolicy(131072, (128001, 128008, 128009))
    kwargs = p.generation_kwargs(1000)
    assert kwargs["max_new_tokens"] == 130072 and kwargs["forced_eos_token_id"] is None
    assert p.finish_reason([1] * 255 + [128009], 131072 - 256, None) == "natural_stop"
    assert p.finish_reason([1] * 256, 131072 - 256, None) == "context_exhausted"
    assert p.finish_reason([1] * 300, 1000, "technical_timeout") == "technical_timeout"
    with pytest.raises(ValueError):
        p.generation_kwargs(131072)


def test_atomic_cache_claim_survives_two_instances_and_restart(tmp_path):
    path = tmp_path / "cache.sqlite"
    first, second = AttemptCache(path), AttemptCache(path)
    payload = dict(messages=[{"role": "user", "content": "test"}], executor_identity="X",
                   draw_identity="draw-0", renderer_identity="render")
    request = dict(request_id=digest(payload), **payload)
    assert first.claim(request) is None
    with pytest.raises(RuntimeError):
        second.claim(request)
    result = dict(request_id=request["request_id"], runtime_identity="X", text="result", finish_reason="natural_stop")
    first.finish(request["request_id"], result)
    assert AttemptCache(path).claim(request) == result
    with pytest.raises(ValueError):
        second.finish(request["request_id"], result)

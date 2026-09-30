import random
import torch
import pytest
from metacom_pm.rl1.e0_learning import ToyState, ToyActorCritic, PPO, rollout, exact_value


def setup():
    torch.set_num_threads(1)
    torch.manual_seed(17)
    model = ToyActorCritic()
    return model, PPO(model)


def test_complementarity_has_negative_first_step_and_positive_joint_return():
    state = ToyState(2)
    one, c1, _ = state.step(2)
    assert c1 + one.step(0)[1] < 0
    two, c2, _ = one.step(2)
    assert c1 + c2 + two.step(0)[1] == pytest.approx(.975)
    assert exact_value(state) == pytest.approx(.975)


def test_budget_mask_and_masked_distribution():
    model, _ = setup()
    state = ToyState(4)
    assert state.mask()[1] is False
    with pytest.raises(ValueError): state.step(1)
    dist, _ = model(torch.tensor(state.observation()), torch.tensor(state.mask()))
    assert dist.probs[1] == 0


def test_returns_have_no_terminal_bootstrap_and_updates_change_parameters():
    model, trainer = setup()
    episodes = [rollout(model, i % 5, trainer.version) for i in range(16)]
    for episode in episodes:
        ts = episode['transitions']
        assert ts[-1]['return'] == ts[-1]['reward']
        assert ts[0]['return'] == pytest.approx(episode['total_return'])
    before = {k: v.clone() for k, v in model.state_dict().items()}
    stats = trainer.update(episodes)
    assert trainer.version == 1 and stats['behavior_log_probability_max_error'] < 1e-5
    assert any(not torch.equal(before[k], v) for k, v in model.state_dict().items())
    with pytest.raises(ValueError): trainer.update(episodes)


def test_incomplete_batches_never_update():
    model, trainer = setup()
    episodes = [rollout(model, i % 5, 0) for i in range(16)]
    episodes[-1]['complete'] = False
    with pytest.raises(ValueError): trainer.update(episodes)
    assert trainer.version == 0


def test_restore_replays_next_rollout_and_optimizer_update(tmp_path):
    model, trainer = setup(); rng = random.Random(17)
    trainer.update([rollout(model, rng.randrange(5), 0) for _ in range(16)])
    path = tmp_path / 'checkpoint.pt'; trainer.save(path, rng, 16)
    episodes = [rollout(model, rng.randrange(5), 1) for _ in range(16)]
    trainer.update(episodes)
    expected = {k: v.clone() for k, v in model.state_dict().items()}
    recovered_model = ToyActorCritic(); recovered = PPO(recovered_model); rng2 = random.Random()
    assert recovered.restore(path, rng2) == 16
    replay = [rollout(recovered_model, rng2.randrange(5), 1) for _ in range(16)]
    assert [[int(t['action']) for t in e['transitions']] for e in replay] == [[int(t['action']) for t in e['transitions']] for e in episodes]
    recovered.update(replay)
    assert all(torch.equal(expected[k], v) for k, v in recovered_model.state_dict().items())


def test_behavior_mutation_is_rejected_before_learning():
    model, trainer = setup()
    episodes = [rollout(model, i % 5, 0) for i in range(16)]
    with torch.no_grad(): model.policy.bias[0] += 1
    with pytest.raises(ValueError, match='behavior policy changed'): trainer.update(episodes)


def test_value_initialization_uses_observed_returns_without_changing_actor():
    from metacom_pm.rl1.e0_value_initialization import fit_value_head
    model, _ = setup()
    episodes = [rollout(model, i, 0) for i in range(5)]
    before = {k: v.clone() for k, v in model.state_dict().items() if not k.startswith('value.')}
    report = fit_value_head(model, episodes)
    assert report['after_mse'] < report['before_mse']
    assert all(torch.equal(v, model.state_dict()[k]) for k, v in before.items())
    episodes[0]['complete'] = False
    with pytest.raises(ValueError): fit_value_head(model, episodes)

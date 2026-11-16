"""Fit only the value head from completed toy trajectories before joint PPO.

The actor/body stay byte-identical. This is supervised critic initialization from
observed returns, not an oracle injected as an actor feature or PPO advantage.
"""
import torch


def fit_value_head(model, episodes, ridge=1e-6):
    if not episodes or any(not e['complete'] or not e['transitions'][-1]['done'] for e in episodes):
        raise ValueError('value initialization requires completed trajectories')
    rows=[t for e in episodes for t in e['transitions']]
    observations=torch.stack([t['observation'] for t in rows])
    targets=torch.tensor([t['return'] for t in rows],dtype=torch.float64)
    actor_before={k:v.clone() for k,v in model.state_dict().items() if not k.startswith('value.')}
    with torch.no_grad():
        hidden=model.body(observations)
        before=(model.value(hidden).squeeze(-1).double()-targets).square().mean()
        design=torch.cat([hidden.double(),torch.ones(len(hidden),1,dtype=torch.float64)],dim=1)
        solution=design.T@torch.linalg.solve(design@design.T+ridge*torch.eye(len(design),dtype=torch.float64),targets)
        model.value.weight.copy_(solution[:-1].float().unsqueeze(0));model.value.bias.copy_(solution[-1:].float())
        after=(model.value(hidden).squeeze(-1).double()-targets).square().mean()
    assert all(torch.equal(v,model.state_dict()[k]) for k,v in actor_before.items())
    return dict(observed_episodes=len(episodes),observed_transitions=len(rows),before_mse=float(before),
                after_mse=float(after),actor_and_shared_body_unchanged=True,ridge=ridge,
                source='completed frozen-actor toy rollouts; actual Monte Carlo returns',
                unseen_state_values_filled=False)

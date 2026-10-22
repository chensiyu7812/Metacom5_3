"""Original-plan BC, value initialization and OneShot return regression.

Only small CPU policy networks are created here. Research data require a
qualified handoff and a bound stage approval; engineering fixtures are marked
separately in every checkpoint. No G/J client or credential access exists.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path

import torch
from torch import nn

from .calibration_workflow import stamp, verify_identity
from .bound_generation import BoundResourceEnv
from .learning_handoff import (prepare_handoff, compile_supervision,
    checkpoint_requirements, verify_checkpoint_receipt)
from .learning_preparation import compile_demonstration
from .natural_batch import parameter_identity
from .observation_features import make_actor_critic
from .schema import PLANS, digest

VERSION = 'pmrl1-original-supervised-v1'
ENGINEERING = 'ENGINEERING_ONLY'
NATURAL = 'QUALIFIED_NATURAL_STUDY'
CONFIG = dict(epochs=50, batch_size=64, lr=.0003, weight_decay=.0001,
              value_head_only_steps=500)


def save_json(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    Path(path).chmod(0o600)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_execution(scope, identity, approval, operation):
    if scope == ENGINEERING:
        return
    if (scope != NATURAL or not isinstance(approval, dict)
            or approval.get('status') != 'APPROVED'
            or approval.get('artifact_identity') != identity
            or operation not in approval.get('operations', [])
            or not approval.get('user_authorization_reference')):
        raise ValueError('bound research stage authorization required')


def plan_features(counts):
    counts = tuple(counts)
    if counts not in PLANS or any(type(n) is not int for n in counts):
        raise ValueError('invalid canonical plan')
    x = tuple(n/4 for n in counts)
    return x + tuple(x[i]*x[j] for i in range(4) for j in range(i+1, 4))


class OneShotReturnModel(nn.Module):
    """Shared scalar return predictor; no unacquired text, no winner labels."""
    def __init__(self, feature_dimension):
        super().__init__()
        self.feature_dimension = feature_dimension
        self.body = nn.Sequential(nn.Linear(feature_dimension+10, 128), nn.Tanh(),
            nn.Linear(128, 128), nn.Tanh(), nn.Linear(128, 128), nn.Tanh())
        self.return_head = nn.Linear(128, 1)

    def forward(self, features, plans):
        if features.shape[-1] != self.feature_dimension or plans.shape[-1] != 10:
            raise ValueError('OneShot public/plan feature shape mismatch')
        return self.return_head(self.body(torch.cat((features, plans), dim=-1))).squeeze(-1)

    @torch.no_grad()
    def choose(self, features, mask):
        if len(mask) != 70 or any(type(v) is not bool for v in mask) or not any(mask):
            raise ValueError('shared reachable 70-plan mask required')
        x = torch.tensor(features, dtype=torch.float32).expand(70, -1)
        scores = self(x, torch.tensor([plan_features(p) for p in PLANS], dtype=torch.float32))
        if not torch.isfinite(scores).all():
            raise ValueError('nonfinite OneShot returns')
        scores = scores.masked_fill(~torch.tensor(mask), -torch.inf)
        return PLANS[int(scores.argmax())]


def prepare_supervised(candidates, *, menu, receipts, qualification_bundle,
                       episodes, view, method):
    handoff = prepare_handoff(candidates, menu=menu, receipts=receipts,
        qualification_bundle=qualification_bundle, episodes=episodes)
    if handoff['status'] != 'READY':
        return stamp(dict(version=VERSION, status=handoff['status'],
            handoff_identity=handoff['identity'], rows=[], method=method))
    scope = ENGINEERING if qualification_bundle['inputs']['code'].get('synthetic_only') is True else NATURAL
    contract = qualification_bundle['inputs']['contract']
    if contract['policy']['supervised'] != CONFIG:
        raise ValueError('supervised hyperparameters differ from original contract')
    factories = {pid:(lambda spec=spec, r=r: BoundResourceEnv(spec,r))
        for pid,(spec,r) in episodes.items()}
    if method == 'OneShot':
        if menu['scope'] != 'final_train_union' or view.no_text:
            raise ValueError('OneShot needs final common train union and initial full view')
        off = {c.prefix_identity:c for c in candidates if c.counts == (0,0,0,0)}
        rows = []
        for c in candidates:
            initial = factories[c.prefix_identity]().observe()
            x, mask = view.oneshot(initial)
            if not mask[PLANS.index(c.counts)]:
                raise ValueError('measured plan is unreachable')
            m, b = receipts[c.request_identity], receipts[off[c.prefix_identity].request_identity]
            value = m['q']/4-m['m']-(b['q']/4-b['m'])-.05*c.resource_tokens/2048
            rows.append(dict(features=x, plan=plan_features(c.counts), return_target=value))
        meta = stamp(dict(method=method, feature_identity=view.identity,
            handoff_identity=handoff['identity'], menu_identity=menu['identity'],
            qualification_identity=handoff['qualification_identity'],
            freeze_identity=handoff['freeze_identity'], plan_order_identity=digest(PLANS),
            executors=handoff['executors'], renderers=handoff['renderers'], acquired_text_zero=False,
            objective='MSE of all measured OFF-relative net returns', rows_identity=digest(rows)))
    else:
        rows, old_meta = compile_supervision(handoff, method=method, view=view, env_factories=factories)
        rows = deepcopy(rows)
        cursor = 0
        for target in handoff['targets']:
            factory = factories[target['prefix_identity']]
            env = factory()
            paid = 0.
            for _, action in compile_demonstration(factory, tuple(target['target'])):
                # The already-paid GET cost is not charged to later states.
                rows[cursor]['return_target'] = target['reward'] - paid
                result = env.step(action, expected_state_hash=env.state_hash)
                if action:
                    paid += result.reward
                cursor += 1
        meta = stamp({k:v for k,v in old_meta.items() if k != 'identity'} | dict(
            predecessor_identity=old_meta['identity'], rows_identity=digest(rows),
            objective='masked BC; measured remaining-return value initialization'))
    return stamp(dict(version=VERSION, status='READY', scope=scope, method=method,
        rows=rows, metadata=meta, config=CONFIG, contract_identity=digest(contract),
        feature_dimension=view.encoder.feature_dimension,
        qualification_identity=handoff['qualification_identity'],
        measurement_identity=handoff['measurement_identity'],
        qualification_bundle_identity=digest(qualification_bundle),
        training_authorized=False))


def validate_prepared(prepared):
    verify_identity(prepared)
    if prepared.get('status') != 'READY' or not prepared.get('rows'):
        raise ValueError('complete qualified training data required')
    meta = prepared['metadata']; verify_identity(meta)
    if (prepared['version'] != VERSION or prepared['config'] != CONFIG
            or meta['rows_identity'] != digest(prepared['rows'])
            or meta['method'] != prepared['method']
            or prepared['scope'] not in (ENGINEERING, NATURAL)):
        raise ValueError('prepared learning identity mismatch')


def _model(prepared):
    d = prepared['feature_dimension']
    return OneShotReturnModel(d) if prepared['method'] == 'OneShot' else make_actor_critic(d)


def fit_supervised(prepared, *, seed, directory, approval=None):
    validate_prepared(prepared)
    require_execution(prepared['scope'], prepared['identity'], approval, 'supervised_training')
    requirements = checkpoint_requirements(prepared['metadata'], seed=seed)
    out = Path(directory); out.mkdir(parents=True, exist_ok=False, mode=0o700)
    save_json(out/'STARTED.json', dict(prepared_identity=prepared['identity'], seed=seed,
        scope=prepared['scope'], approval_identity=digest(approval), config=CONFIG))
    rows = prepared['rows']; one = prepared['method'] == 'OneShot'
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        model = _model(prepared)
        initial = parameter_identity(model)
        optimizer = torch.optim.Adam(model.parameters(), lr=CONFIG['lr'], weight_decay=CONFIG['weight_decay'])
        x = torch.tensor([r['features'] for r in rows], dtype=torch.float32)
        y = torch.tensor([r['return_target'] for r in rows], dtype=torch.float32)
        if not torch.isfinite(x).all() or not torch.isfinite(y).all():
            raise ValueError('nonfinite training data')
        if one:
            plans = torch.tensor([r['plan'] for r in rows], dtype=torch.float32)
        else:
            masks = torch.tensor([r['mask'] for r in rows], dtype=torch.bool)
            actions = torch.tensor([r['target'] for r in rows], dtype=torch.long)
            if not masks.gather(1, actions[:,None]).all():
                raise ValueError('illegal supervised action')
        losses=[]; steps=0
        for _ in range(CONFIG['epochs']):
            order = torch.randperm(len(rows))
            for batch in order.split(CONFIG['batch_size']):
                loss = ((model(x[batch],plans[batch])-y[batch])**2).mean() if one else \
                    -model(x[batch],masks[batch])[0].log_prob(actions[batch]).mean()
                if not torch.isfinite(loss):raise ValueError('nonfinite supervised loss')
                optimizer.zero_grad(); loss.backward(); optimizer.step()
                losses.append(float(loss.detach())); steps+=1
        after_bc = parameter_identity(model)
        actor_before = {k:v.clone() for k,v in model.state_dict().items() if not k.startswith('value.')}
        value_optimizer = None; value_losses=[]
        if not one:
            for p in model.parameters():p.requires_grad_(False)
            for p in model.value.parameters():p.requires_grad_(True)
            value_optimizer = torch.optim.Adam(model.value.parameters(),lr=CONFIG['lr'],weight_decay=CONFIG['weight_decay'])
            for _ in range(CONFIG['value_head_only_steps']):
                idx = torch.randint(len(rows),(min(CONFIG['batch_size'],len(rows)),))
                loss = (model(x[idx],masks[idx])[1]-y[idx]).square().mean()
                if not torch.isfinite(loss):raise ValueError('nonfinite value loss')
                value_optimizer.zero_grad();loss.backward();value_optimizer.step()
                value_losses.append(float(loss.detach()))
            for p in model.parameters():p.requires_grad_(True)
        actor_unchanged = all(torch.equal(v,model.state_dict()[k]) for k,v in actor_before.items())
        if not actor_unchanged:raise ValueError('critic initialization changed actor/shared body')
        # PPO starts its explicitly recorded fresh Adam state, not stale BC
        # moments/weight decay. The BC and critic optimizer states are archived.
        ppo_optimizer = None if one else torch.optim.Adam(model.parameters(),lr=.0003)
        state = dict(model=model.state_dict(), supervised_optimizer=optimizer.state_dict(),
            value_optimizer=None if one else value_optimizer.state_dict(),
            ppo_optimizer=None if one else ppo_optimizer.state_dict(),
            torch_rng=torch.get_rng_state(), requirements=requirements,
            prepared_identity=prepared['identity'], scope=prepared['scope'])
        path=out/'checkpoint.pt'
        with path.open('xb') as f:torch.save(state,f);f.flush();os.fsync(f.fileno())
        path.chmod(0o600)
        receipt = stamp(dict(version=VERSION,status='ONESHOT_REGRESSION_COMPLETED' if one else 'BC_OPTIMIZATION_COMPLETED',
            scope=prepared['scope'], prepared_identity=prepared['identity'], requirements=requirements,
            checkpoint_sha256=file_sha(path), optimizer_steps=steps,value_steps=len(value_losses),
            actor_unchanged_during_value_initialization=actor_unchanged,
            initial_parameters=initial, after_supervision=after_bc, final_parameters=parameter_identity(model),
            parameter_count=sum(p.numel() for p in model.parameters()),
            first_supervised_loss=losses[0],last_supervised_loss=losses[-1],
            last_value_loss=value_losses[-1] if value_losses else None,
            PPO_optimizer_initialization='fresh Adam lr3e-4; state archived' if not one else None,
            natural_policy_updates=0,research_checkpoint=prepared['scope']==NATURAL))
        save_json(out/'RECEIPT.json',receipt)
        return receipt


def load_initialization(prepared, *, seed, path, receipt):
    validate_prepared(prepared)
    requirements=checkpoint_requirements(prepared['metadata'],seed=seed)
    one=prepared['method']=='OneShot'
    if one:
        verify_identity(receipt)
        if (receipt.get('status')!='ONESHOT_REGRESSION_COMPLETED'
                or receipt.get('requirements')!=requirements or receipt.get('checkpoint_sha256')!=file_sha(path)):
            raise ValueError('completed bound OneShot checkpoint required')
    else:
        verify_checkpoint_receipt(receipt,requirements=requirements,checkpoint_sha256=file_sha(path))
    if (receipt.get('prepared_identity')!=prepared['identity'] or receipt.get('scope')!=prepared['scope']
            or receipt['optimizer_steps']!=50*math.ceil(len(prepared['rows'])/64)
            or receipt['value_steps']!=(0 if one else 500)
            or receipt['actor_unchanged_during_value_initialization'] is not True):
        raise ValueError('incomplete or cross-scope initialization')
    state=torch.load(path,map_location='cpu',weights_only=True)
    if state['requirements']!=requirements or state['prepared_identity']!=prepared['identity'] or state['scope']!=prepared['scope']:
        raise ValueError('checkpoint payload binding mismatch')
    # Loading does not disturb the caller's sampling RNG.
    with torch.random.fork_rng(devices=[]):model=_model(prepared)
    model.load_state_dict(state['model'])
    if parameter_identity(model)!=receipt['final_parameters']:
        raise ValueError('checkpoint parameters differ from receipt')
    return model,state

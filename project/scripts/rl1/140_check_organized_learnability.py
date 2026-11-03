#!/usr/bin/env python3
"""Controlled read-then-decide diagnostic; synthetic CPU networks only.

Two cases have identical initial public information and different acquired MP
text. That text determines whether MS or ME is useful. A third public task
requires STOP. Exact utilities are programmed ONLY on the environment side.
This is not natural-task training, a BGE capability test or judge qualification.
"""
import argparse
from dataclasses import replace
from itertools import permutations
import json
import random
from pathlib import Path
import sys

import torch

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT/'src'), str(PROJECT/'tests')]

from metacom_pm.rl1.measurement_identity import binding
from metacom_pm.rl1.organized_encoding import BlockCache, EncodedHeadView
from metacom_pm.rl1.organized_features import FullTextFeatures
from metacom_pm.rl1.organized_oneshot import ProgramReturnModel, program_tensor
from metacom_pm.rl1.organized_policy_interface import HeadSession
from metacom_pm.rl1.organized_rollout import OrganizedRollout
from metacom_pm.rl1.organized_supervision import endpoint, training_menu, prepare_supervised, prepare_targets
from metacom_pm.rl1.e0_learning import PPO
from metacom_pm.rl1.resource_organization import OrganizationCatalog
from metacom_pm.rl1.schema import digest, PublicTurn
from metacom_pm.rl1.supervised_learning import CONFIG, fit_supervised, load_initialization, save_json
# Reuse explicitly synthetic qualification and source helpers, never real data.
from test_rl1_organized_learning_bridge import episode, route_for, raw
from test_rl1_organized_policy_interface import setup, item


def make_view(root, no_text=False):
    identity = 'SYNTHETIC_TEXT_MARKERS_NOT_BGE'
    planner = FullTextFeatures(encode_tokens=lambda s:list(s.encode()),
        add_special_tokens=lambda ids:[300]+ids+[301], native_window=8192, special_tokens=2,
        tokenizer_identity='SYNTHETIC_BYTES', encoder_identity=identity, dimension=4)
    cache = BlockCache(root/'blocks.sqlite', encoder_identity=identity, dimension=4, native_window=8192)
    def encode(blocks):
        out = []
        for block in blocks:
            text = bytes(block[1:-1]).decode()
            # These markers are actual visible text. Hidden catalog fields,
            # labels and owner IDs never enter this feature function.
            out.append([float(mark in text) for mark in ('REDD','BLUE','STOP_TASK','Need help')])
        return out
    return EncodedHeadView(planner, cache, invoke=encode, encoder_identity=identity, without_text=no_text)


def sources():
    cases = {}
    for name in ('REDD', 'BLUE', 'STOP_TASK'):
        c, r = setup([item('p','MP', 'REDD' if name == 'STOP_TASK' else name),
                      item('s','MS','session'), item('e','ME','events!')])
        p = replace(c.prefix, session_id=name, turns=(PublicTurn('seeker',
            'STOP_TASK' if name == 'STOP_TASK' else 'Need help'),))
        c = OrganizationCatalog(p, list(c._items.values()), provenance_identity='SYNTHETIC_ORACLE_TASK')
        route = route_for(c, r)
        def factory(tid='probe', hidden=False, c=c, r=r, route=route):
            return episode(c, r, route, tid=tid, no_text=hidden)
        cases[name] = factory
    return cases


def scores(name, keys):
    selected = set(keys)
    if name == 'STOP_TASK':
        return 2, 0
    good, bad = ('s','e') if name == 'REDD' else ('e','s')
    return (0 if bad in selected else 4 if {'p', good} <= selected else 2), 0


def feedback(e, name):
    responses, receipts = {}, {}
    for req in e.requests.values():
        q, m = scores(name, req['provenance']['selected_keys'])
        text = f'SYNTHETIC_REPLY_QUALITY_{q}'
        responses[req['request_id']] = raw(req, text)
        query = binding(req['request_id'], digest(text), digest(e.evidence), e.route.bundle['freeze'], e.route.qualification)
        receipts[req['request_id']] = dict(binding=query, measurement_status='measured_candidate', q=q, m=m)
    return responses, receipts


def evaluate(model, view, cases):
    out = {}
    for name, factory in cases.items():
        e = factory(hidden=view.no_text)
        initial_x, initial_mask = view.sequential(e.session.observe())
        with torch.no_grad():
            _, initial_value = model(torch.tensor(initial_x, dtype=torch.float32), torch.tensor(initial_mask))
        def choose(obs):
            x, mask = view.sequential(obs)
            with torch.no_grad():
                dist, _ = model(torch.tensor(x, dtype=torch.float32), torch.tensor(mask))
            return int(dist.probs.argmax())
        e.acquire(choose)
        rs, js = feedback(e, name)
        result = e.advance(lambda r:rs[r['request_id']], lambda q,*_:js[q['generation_request_id']])
        leaves = []
        def enumerate_policy(path=(), probability=1.):
            # Exact finite environment expectation; no Monte Carlo noise and
            # no gradient/RNG changes. Labels stay outside the actor inputs.
            node = factory(hidden=view.no_text)
            for action in path:
                node.step(action)
            x, mask = view.sequential(node.session.observe())
            with torch.no_grad():
                dist, _ = model(torch.tensor(x, dtype=torch.float32), torch.tensor(mask))
            for action, legal in enumerate(mask):
                if not legal:
                    continue
                weight = probability * float(dist.probs[action])
                if action:
                    enumerate_policy(path+(action,), weight)
                else:
                    node.step(0)
                    rs, js = feedback(node, name)
                    value = node.advance(lambda r:rs[r['request_id']], lambda q,*_:js[q['generation_request_id']])['return_value']
                    leaves.append((weight, value))
        enumerate_policy()
        mass = sum(p for p,_ in leaves)
        if abs(mass-1.) > 1e-5:
            raise ValueError('incomplete exact policy enumeration')
        optimal = max(r for _,r in leaves)
        expected = sum(p*r for p,r in leaves)/mass
        out[name] = dict(actions=[s['action'] for s in e.steps], return_value=result['return_value'],
            exact_stochastic_return=expected, initial_value_estimate=float(initial_value),
            critic_bias_vs_policy=float(initial_value)-expected,
            probability_of_optimal_program=sum(p for p,r in leaves if abs(r-optimal)<1e-10)/mass)
    return out


def run(output, episodes):
    output.mkdir(parents=True, exist_ok=False)
    (output/'SCRIPT.py').write_bytes(Path(__file__).read_bytes())
    torch.set_num_threads(1)
    cases = sources(); factories = {f().catalog.prefix.identity:f for f in cases.values()}
    programs = [(0,)] + [p+(0,) for n in (1,2,3) for p in permutations((2,3,4), n)]
    ends = []; responses = {}; receipts = {}; by_name = {}
    for name, factory in cases.items():
        by_name[name] = {}
        for program in programs:
            x, e = endpoint(factory, program); ends.append(x)
            rs, js = feedback(e, name); responses.update(rs); receipts.update(js)
            result = e.advance(lambda r:rs[r['request_id']], lambda q,*_:js[q['generation_request_id']])
            by_name[name][program] = result['return_value']
    menu = training_menu(ends, source_identity='complete synthetic three-item environment; all 16 programs')
    targets = prepare_targets(menu, factories=factories, responses=responses, receipts=receipts)
    save_json(output/'SYNTHETIC_TARGETS.json', targets)
    full, hidden = make_view(output), make_view(output, True)
    a, b = cases['REDD'](), cases['BLUE']()
    initial_equal = full.sequential(a.session.observe()) == full.sequential(b.session.observe())
    a.step(2); b.step(2)
    read_distinguishable = full.sequential(a.session.observe()) != full.sequential(b.session.observe())
    ah, bh = cases['REDD'](hidden=True), cases['BLUE'](hidden=True)
    ah.step(2); bh.step(2)
    hidden_equal = hidden.sequential(ah.session.observe()) == hidden.sequential(bh.session.observe())
    records = []
    for seed in (17,29,43):
        for v, method in ((full,'BC-init'), (hidden,'PPO-NoText')):
            data = prepare_supervised(menu, factories=factories, responses=responses, receipts=receipts, view=v, method=method)
            folder = output/f'{seed}-{method}'
            rec = fit_supervised(data, seed=seed, directory=folder)
            model, state = load_initialization(data, seed=seed, path=folder/'checkpoint.pt', receipt=rec)
            before = evaluate(model, v, cases)
            trainer = PPO(model); trainer.optimizer.load_state_dict(state['ppo_optimizer'])
            order=[list(cases)[i % 3] for i in range(episodes)]
            random.Random(seed).shuffle(order)
            rng=state['torch_rng'].tolist(); curve=[]
            for version in range(episodes//16):
                names=order[version*16:(version+1)*16]
                es=[cases[n](tid=f'{seed}-{method}-{version}-{i}',hidden=v.no_text) for i,n in enumerate(names)]
                collector=OrganizedRollout(model,v,folder/f'collection_{version}',run_identity='SYNTHETIC_ONLY',
                    policy_version=version,seed=seed,rng_state=rng)
                collector.collect(es)
                for e,name in zip(es,names):
                    rs,js=feedback(e,name)
                    e.advance(lambda r:rs[r['request_id']],lambda q,*_:js[q['generation_request_id']])
                inputs=collector.ppo_inputs(es)
                with torch.random.fork_rng(devices=[]):
                    torch.set_rng_state(torch.tensor(collector.rng,dtype=torch.uint8))
                    stats=trainer.update(inputs);rng=torch.get_rng_state().tolist()
                curve.append(dict(episodes=(version+1)*16,evaluation=evaluate(model,v,cases),PPO=stats,
                    sampled_mean_return=sum(e['total_return'] for e in inputs)/16))
            after=evaluate(model,v,cases)
            torch.save(dict(model=model.state_dict(),optimizer=trainer.optimizer.state_dict(),
                torch_rng=rng,policy_version=trainer.version,scope='ENGINEERING_ONLY'),folder/'AFTER_PPO.pt')
            again = OrganizedRollout(model,v,folder/'next_collection',run_identity='SYNTHETIC_ONLY',policy_version=trainer.version,seed=seed,rng_state=rng)
            again.collect([cases[n](tid=f'next-{seed}-{method}-{i}',hidden=v.no_text) for i,n in enumerate(names)])
            records.append(dict(seed=seed,method=method,fit=rec['final_fit'],before_PPO=before,
                after_PPO=after,curve=curve,resampled_trajectories=16))
        # Model-level regression probe: all 48 exact measured terminal returns.
        # No final-union completion receipt is invented for this diagnostic.
        rows=[]
        for name,factory in cases.items():
            x,_=full.sequential(factory().session.observe())
            rows.extend((x,p,by_name[name][p]) for p in programs)
        x=torch.tensor([r[0] for r in rows],dtype=torch.float32)
        p=program_tensor([r[1] for r in rows]); y=torch.tensor([r[2] for r in rows])
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed); model=ProgramReturnModel(full.feature_dimension)
            opt=torch.optim.Adam(model.parameters(),lr=CONFIG['lr'],weight_decay=CONFIG['weight_decay'])
            first=float((model(x,p)-y).square().mean().detach())
            for _ in range(CONFIG['epochs']):
                order=torch.randperm(len(rows))
                for ids in order.split(CONFIG['batch_size']):
                    loss=(model(x[ids],p[ids])-y[ids]).square().mean()
                    opt.zero_grad();loss.backward();opt.step()
            last=float((model(x,p)-y).square().mean().detach())
        decisions={}
        for name,factory in cases.items():
            e=factory(); chosen=model.choose(e.session.observe(),programs,view=full,interface_identity=e.session.interface_identity)
            decisions[name]=dict(actions=list(chosen.actions),return_value=by_name[name][chosen.actions])
        records.append(dict(seed=seed,method='OneShot_model_regression_probe',rows=len(rows),
            initial_mse=first,final_mse=last,decisions=decisions,formal_final_union_training=False))
        print(json.dumps(dict(seed=seed,completed=True)),flush=True)
    result=dict(scope='ENGINEERING_ONLY',source='three programmed cases, synthetic text encoder; no research data',
        natural_updates=0,real_model_loads=0,API_calls=0,human_labels=0,synthetic_episodes_per_run=episodes,
        initial_REDD_BLUE_identical=initial_equal,acquired_text_distinguishes=read_distinguishable,
        NoText_REDD_BLUE_identical_after_MP=hidden_equal,
        exact_oracle={n:max(xs.values()) for n,xs in by_name.items()},
        exact_best_shared_initial_program_mean=max(sum(by_name[n][p] for n in ('REDD','BLUE'))/2 for p in programs),
        records=records)
    save_json(output/'RESULTS.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--episodes',type=int,choices=(16,128),default=128)
    args=parser.parse_args();run(args.output,args.episodes)

"""Public-observation batch bridge and durable, provider-free feedback queue.

The optimizer is the existing E0 PPO implementation, not a new algorithm.
MOCK remains the default. The separately approved diagnostic path requires a
complete protocol/permission pair; production measurement gates stay unchanged.
No model loader, API client, credential reader or automatic retry lives here.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sqlite3

import torch

from .e0_learning import PPO
from .schema import digest

MOCK = 'MOCK_ENGINEERING_ONLY'
VERSION = 'pmrl1-natural-batch-engineering-v1-20261020'


def parameter_identity(model):
    h = hashlib.sha256()
    for name, value in model.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


class FeedbackQueue:
    """Pending requests stay pending across polling/restarts; no re-dispatch.

    A worker may explicitly claim WAITING exactly once. An interrupted STARTED
    request is never returned by claim_next. Completed semantic unknowns remain
    immutable; any future authorized review needs its own provenance pathway.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS feedback '
                '(id TEXT PRIMARY KEY, kind TEXT, payload TEXT, state TEXT, result TEXT)')
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _get(self, kind, payload):
        key = digest(dict(kind=kind, payload=payload))
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        with self.transaction() as db:
            row = db.execute('SELECT kind,payload,state,result FROM feedback WHERE id=?', (key,)).fetchone()
            if row is None:
                db.execute('INSERT INTO feedback VALUES (?,?,?,\'WAITING\',NULL)', (key, kind, encoded))
                return None
            if row[:2] != (kind, encoded):
                raise ValueError('feedback cache binding mismatch')
            return json.loads(row[3]) if row[2] == 'SETTLED' else None

    def generate(self, request):
        if request['request_id'] != digest({k:v for k,v in request.items() if k != 'request_id'}):
            raise ValueError('generation request identity mismatch')
        return self._get('generation', request)

    def measure(self, binding, evidence, reply):
        if binding['evidence_identity'] != digest(evidence) or binding['response_identity'] != digest(reply):
            raise ValueError('source/response binding mismatch')
        return self._get('measurement', dict(binding=binding, evidence=evidence, reply=reply))

    def claim_next(self):
        with self.transaction() as db:
            row = db.execute("SELECT id,kind,payload FROM feedback WHERE state='WAITING' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                return None
            payload = json.loads(row[2])
            if row[0] != digest(dict(kind=row[1], payload=payload)):
                raise ValueError('queued payload identity changed; never dispatch')
            db.execute("UPDATE feedback SET state='STARTED' WHERE id=? AND state='WAITING'", (row[0],))
            return dict(id=row[0], kind=row[1], payload=payload)

    def settle(self, key, result):
        encoded = json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False)
        with self.transaction() as db:
            row = db.execute('SELECT kind,payload,state,result FROM feedback WHERE id=?', (key,)).fetchone()
            if row is None:
                raise ValueError('unknown feedback request')
            kind, payload, state, previous = row
            if state == 'SETTLED':
                if previous == encoded:
                    return  # Idempotent ingestion, not a repeated model request.
                raise ValueError('settled feedback is immutable')
            if state != 'STARTED':
                raise ValueError('claim before settling')
            p = json.loads(payload)
            if kind == 'generation':
                if (result.get('request_id') != p['request_id']
                        or result.get('runtime_identity') != p['executor_identity']):
                    raise ValueError('wrong generation identity')
            elif result.get('binding') != p['binding']:
                raise ValueError('wrong measurement identity')
            db.execute("UPDATE feedback SET state='SETTLED',result=? WHERE id=?", (encoded, key))

    def counts(self):
        with self.transaction() as db:
            return [dict(kind=k, state=s, count=n) for k,s,n in db.execute(
                'SELECT kind,state,COUNT(*) FROM feedback GROUP BY kind,state')]


class PendingBatch:
    """Collect once under one frozen behavior policy; poll feedback separately."""
    def __init__(self, model, encoder, workdir, *, mode=MOCK, no_text=False,
                 protocol=None, approval=None):
        self.protocol, self.approval = deepcopy(protocol), deepcopy(approval)
        if mode != MOCK:
            from .diagnostic_scope import DIAGNOSTIC, require_approval
            if mode != DIAGNOSTIC or no_text:
                raise ValueError('no formal/NoText training in the bounded diagnostic')
            require_approval(protocol, approval)
            if encoder.identity != protocol['encoder_identity']:
                raise ValueError('diagnostic encoder identity mismatch')
        self.mode, self.no_text = mode, no_text
        self.model, self.encoder = model, encoder
        self.trainer = PPO(model)
        self.rng = random.Random(17)
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.batch_id, self.behavior_identity, self.records = None, None, []
        self.consumed = False
        self.identity = digest(dict(version=VERSION, mode=mode, encoder=encoder.identity,
            no_text=no_text, optimizer='existing e0_learning.PPO', batch_size=16))
        if mode != MOCK:
            self.identity = digest(dict(base=self.identity, protocol=protocol['identity'],
                                        approval=digest(approval)))

    def _check_behavior(self):
        if self.behavior_identity != parameter_identity(self.model):
            raise ValueError('behavior weights changed while batch is outstanding')

    def collect(self, episodes, *, batch_id):
        if self.batch_id is not None or len(episodes) != 16 or not batch_id:
            raise ValueError('one new, named 16-episode batch required')
        if len({e.trajectory_id for e in episodes}) != 16:
            raise ValueError('trajectory identities must be unique even for cached terminals')
        for e in episodes:
            if self.mode == MOCK and (getattr(e, 'feedback_scope', None) != MOCK or
                    not e.spec.executor_identity.startswith('MOCK:') or
                    not e.spec.judge_identity.startswith('MOCK:') or
                    e.spec.prefix.owner_id != 'MOCK_OWNER' or e.env.phase != 'acquiring'):
                raise ValueError('only explicit synthetic engineering episodes are accepted')
            if self.mode != MOCK:
                from .diagnostic_scope import require_approval
                require_approval(self.protocol, self.approval)
                expected = self.protocol['train_batches'][self.trainer.version] if self.trainer.version < 2 else []
                if (getattr(e, 'feedback_scope', None) != self.mode
                        or e.protocol['identity'] != self.protocol['identity']
                        or e.spec.prefix.split != 'train'
                        or [x.trajectory_id for x in episodes] != expected
                        or e.env.phase != 'acquiring'):
                    raise ValueError('unapproved, repeated or out-of-order diagnostic trajectory')
        self.batch_id = digest(dict(batch=batch_id, bridge=self.identity,
            version=self.trainer.version, trajectories=[e.trajectory_id for e in episodes]))
        self.behavior_identity = parameter_identity(self.model)
        for episode in episodes:
            transitions = []
            def sample(observation):
                feature = self.encoder.encode(observation)
                values = list(feature.values)
                if self.no_text:
                    # Current-prefix vector remains; only acquired-body vectors
                    # are zero throughout this independently initialized run.
                    values[self.encoder.dimension:5*self.encoder.dimension] = [0.]*(4*self.encoder.dimension)
                x = torch.tensor(values, dtype=torch.float32)
                mask = torch.tensor(feature.action_mask, dtype=torch.bool)
                with torch.no_grad():
                    dist, value = self.model(x, mask)
                    action = dist.sample()
                transitions.append(dict(observation=x, mask=mask, action=action.detach(),
                    old_log_prob=dist.log_prob(action).detach(), old_value=value.detach(),
                    forced=int(mask.sum()) == 1, done=False, reward=None))
                return int(action)
            episode.acquire(sample)
            for t, step in zip(transitions, episode.steps):
                t['reward'] = step['reward']
            transitions[-1]['done'] = True
            self.records.append(dict(episode=episode, transitions=transitions))
        self._check_behavior()

    def poll(self, queue):
        if self.batch_id is None or self.consumed:
            raise ValueError('no unconsumed batch')
        self._check_behavior()
        results = []
        for record in self.records:
            result = record['episode'].advance(queue.generate, queue.measure)
            record['transitions'][-1]['reward'] = result['terminal_reward']
            results.append(result)
        return results

    def _complete_episodes(self):
        self._check_behavior()
        if self.consumed or len(self.records) != 16:
            raise ValueError('batch already updated or not complete')
        episodes = []
        for rec in self.records:
            if self.mode != MOCK:
                from .diagnostic_scope import require_approval
                require_approval(self.protocol, self.approval)
                rec['episode'].require_update_feedback()
            result = rec['episode'].result()
            if result['phase'] != 'terminal' or result['return_value'] is None:
                raise ValueError('all 16 rewards must be complete; never drop or zero pending episodes')
            ts = deepcopy(rec['transitions'])
            remaining = 0.
            for t in reversed(ts):
                remaining += t['reward']
                t['return'], t['advantage'] = remaining, remaining-float(t['old_value'])
            episodes.append(dict(complete=True, policy_version=self.trainer.version,
                transitions=ts, total_return=remaining))
        return episodes

    def update_once(self):
        episodes = self._complete_episodes()
        intent = self.workdir / (self.batch_id + '.update_intent.json')
        # Exclusive durable intent prevents replay from an older checkpoint.
        with intent.open('x') as f:
            json.dump(dict(batch_id=self.batch_id, behavior=self.behavior_identity,
                version=self.trainer.version, scope=self.mode), f)
            f.flush()
            import os
            os.fsync(f.fileno())
        receipt = self.trainer.update(episodes)
        self.consumed = True
        after = self.workdir / (self.batch_id + '.after.pt')
        self.save(after)
        receipt.update(batch_id=self.batch_id, scope=self.mode, policy_version=self.trainer.version,
            real_natural_updates=int(self.mode != MOCK), qualification_granted=False,
            before=self.behavior_identity, after=parameter_identity(self.model),
            checkpoint_sha256=hashlib.sha256(after.read_bytes()).hexdigest())
        with intent.with_name(self.batch_id + '.update_done.json').open('x') as f:
            json.dump(receipt, f, indent=2)
        return receipt

    def next_batch(self):
        """Keep model/optimizer/RNG while beginning a new on-policy batch."""
        if not self.consumed or (self.mode != MOCK and self.trainer.version >= 2):
            raise ValueError('batch not consumed or diagnostic two-update cap reached')
        self.batch_id = self.behavior_identity = None
        self.records, self.consumed = [], False

    def save(self, path):
        state = dict(bridge_identity=self.identity, batch_id=self.batch_id,
            behavior_identity=self.behavior_identity, consumed=self.consumed,
            records=[dict(trajectory_id=r['episode'].trajectory_id,
                snapshot=r['episode'].snapshot(), transitions=r['transitions']) for r in self.records])
        path = Path(path)
        if path.exists():
            raise FileExistsError('checkpoint history is immutable')
        self.trainer.save(path, self.rng, state)
        path.chmod(0o600)

    def restore(self, path, episodes):
        # Only locally created trusted torch checkpoints may be loaded.
        state = torch.load(path, map_location='cpu', weights_only=False)
        meta = state['episodes']
        if meta['bridge_identity'] != self.identity:
            raise ValueError('checkpoint encoder/mode/ablation identity mismatch')
        by_id = {e.trajectory_id:e for e in episodes}
        if len(by_id) != len(episodes) or set(by_id) != {r['trajectory_id'] for r in meta['records']}:
            raise ValueError('checkpoint trajectory manifest mismatch')
        for r in meta['records']:
            if by_id[r['trajectory_id']].binding != r['snapshot']['binding']:
                raise ValueError('checkpoint sources or runtime changed')
        meta = self.trainer.restore(path, self.rng)
        self.batch_id, self.behavior_identity, self.consumed = meta['batch_id'], meta['behavior_identity'], meta['consumed']
        self.records = []
        for r in meta['records']:
            episode = by_id[r['trajectory_id']]
            episode.restore(r['snapshot'])
            self.records.append(dict(episode=episode, transitions=r['transitions']))
        if not self.consumed and self.batch_id is not None:
            self._check_behavior()


def baseline_schedule(contract, *, episodes_per_seed):
    """Offline schedule only: no choice of scale or execution authorization."""
    if episodes_per_seed not in (128, 384):
        raise ValueError('use an original contract scale')
    seeds = (17, 29, 43)
    checks = [64,128] if episodes_per_seed == 128 else [128,384]
    return dict(scope='SCHEDULE_ONLY_NOT_EXECUTION_AUTHORIZED', contract_identity=digest(contract),
        train_runs=[dict(method=method, seed=seed, episodes=episodes_per_seed, dev_checkpoints=checks,
            initialization='own BC initialization', feedback='own fresh trajectories; exact terminal cache allowed')
            for method in ('PPO','PPO-NoText') for seed in seeds],
        test_instances=[dict(method=m, seed=s) for m in ('OFF','FixedDev','MatchedRandom','OneShot',
            'BC-init','BC-union','PPO','PPO-NoText') for s in ((None,) if m in ('OFF','FixedDev') else seeds)],
        real_training_authorized=False)

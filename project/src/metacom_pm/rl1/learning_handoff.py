"""Offline qualified-feedback -> BC/OneShot/NoText handoff.

No provider, model loader, optimizer, label decryption or execution permission.
The complete planned menu is bound before inspecting scores. A pending group
never becomes a smaller, apparently complete training set.
"""
from collections import defaultdict
from dataclasses import asdict

from .bound_generation import BoundResourceEnv
from .calibration_workflow import qualify, stamp, verify_identity
from .learning_preparation import (adapt_qualified_episode_feedback,
    compile_demonstration, select_bc_target)
from .schema import PLANS, digest

METHODS = ('BC-init', 'BC-union', 'OneShot', 'PPO-NoText')


def candidate_menu(candidates, *, source_identity, scope):
    if scope not in ('initial_train', 'final_train_union') or not source_identity or not candidates:
        raise ValueError('explicit nonempty training menu and source required')
    rows = [asdict(c) for c in candidates]
    if any(c.split != 'train' for c in candidates):
        raise ValueError('only train feedback belongs in BC')
    keys = [(c.prefix_identity, c.counts) for c in candidates]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate scheduled prefix/plan')
    return stamp(dict(version='pmrl1-learning-menu-v1', scope=scope,
        source_identity=source_identity, candidate_rows_identity=digest(rows),
        prefix_identities=sorted({c.prefix_identity for c in candidates}),
        candidates=len(rows), plan_order_identity=digest(PLANS)))


def prepare_handoff(candidates, *, menu, receipts, qualification_bundle=None,
                    episodes=None):
    """Recompute original qualification; accept no manually asserted PASS flag.

    `episodes` maps prefix identity to (EpisodeSpec, renderer). All evidence
    remains coordinator-side. A missing qualification needs no model/tokenizer.
    The bundle contains already-authorized qualification evidence; this API
    never opens sealed labels. It adds no new qualification thresholds.
    """
    verify_identity(menu)
    if candidate_menu(candidates, source_identity=menu['source_identity'], scope=menu['scope']) != menu:
        raise ValueError('planned candidate menu changed')
    groups = defaultdict(list)
    for c in candidates:
        groups[c.prefix_identity].append(c)
    base = dict(version='pmrl1-learning-handoff-v1', menu_identity=menu['identity'],
        menu_scope=menu['scope'], plan_order_identity=digest(PLANS),
        automatic_training_authorization=False, targets=[])
    if qualification_bundle is None:
        return stamp(base | dict(status='PENDING_QUALIFICATION',
            pending_prefixes=sorted(groups), qualified_prefixes=0))
    qualification = qualify(**qualification_bundle)
    if qualification['status'] not in ('CALIBRATED_FOR_BOUNDED_STUDY', 'CALIBRATED_LOW_CONTRAST'):
        return stamp(base | dict(status='PENDING_QUALIFICATION',
            qualification_identity=qualification['identity'],
            qualification_status=qualification['status'],
            pending_prefixes=sorted(groups), qualified_prefixes=0))
    if episodes is None or set(episodes) != set(groups):
        raise ValueError('exact complete episode set required')
    freeze = qualification_bundle['freeze']
    inputs = qualification_bundle['inputs']
    targets, pending = [], []
    for pid, cs in groups.items():
        spec, renderer = episodes[pid]
        normalized, scores = None, {}
        for c in cs:
            if c.renderer_identity != renderer.identity:
                raise ValueError('candidate renderer changed')
            # Replay also binds resource cost, current prefix, inventory and G.
            env = BoundResourceEnv(spec, renderer)
            path = compile_demonstration(lambda: BoundResourceEnv(spec, renderer), c.counts)
            for _, action in path:
                env.step(action, expected_state_hash=env.state_hash)
            if (env.generation_request()['request_id'] != c.request_identity
                    or renderer.cost(spec, c.counts) != c.resource_tokens):
                raise ValueError('candidate generation path changed')
            rec = receipts.get(c.request_identity)
            if rec is None:
                continue
            q, score = adapt_qualified_episode_feedback(c, rec, spec=spec,
                freeze=freeze, freeze_inputs=inputs, qualification=qualification)
            if normalized is not None and normalized != q:
                raise ValueError('mixed qualified runtimes')
            normalized = q
            scores[c.request_identity] = score
        result = select_bc_target(cs, scores, qualification=normalized)
        if result['target'] is None:
            pending.append(pid)
        else:
            targets.append(dict(prefix_identity=pid, **result))
    # Keep successfully checked target provenance, but do not release partial
    # training rows. All planned prefixes must be present for this handoff.
    return stamp(base | dict(status='READY' if not pending else 'PENDING_SCHEDULED_FEEDBACK',
        targets=targets, pending_prefixes=pending, qualified_prefixes=len(targets),
        qualification_identity=qualification['identity'], freeze_identity=freeze['identity'],
        measurement_identity=freeze['runtime_identity'],
        receipt_identities={k:digest(v) for k,v in sorted(receipts.items())
                            if k in {c.request_identity for c in candidates}},
        executors=sorted({c.executor_identity for c in candidates}),
        renderers=sorted({c.renderer_identity for c in candidates})))


def compile_supervision(handoff, *, method, view, env_factories):
    """Return learner rows containing only encoded Observation/mask/target.

    Dataset provenance is separate from the rows. OneShot uses the final union;
    PPO-NoText learns its own BC from the same initial targets with body masking.
    """
    verify_identity(handoff)
    if handoff['status'] != 'READY' or handoff['pending_prefixes']:
        raise ValueError('all scheduled qualified feedback required')
    expected_scope = 'final_train_union' if method in ('BC-union', 'OneShot') else 'initial_train'
    if method not in METHODS or handoff['menu_scope'] != expected_scope:
        raise ValueError('method requires the original initial/union feedback scope')
    if view.no_text != (method == 'PPO-NoText'):
        raise ValueError('NoText view must apply from its own BC initialization')
    if set(env_factories) != {t['prefix_identity'] for t in handoff['targets']}:
        raise ValueError('complete bound environment set required')
    rows, groups = [], []
    for target in handoff['targets']:
        factory = env_factories[target['prefix_identity']]
        path = compile_demonstration(factory, tuple(target['target']))
        replay = factory()
        for obs, action in path:
            if replay.observe() != obs:
                raise ValueError('environment factory is not stable')
            replay.step(action, expected_state_hash=replay.state_hash)
        if replay.generation_request()['request_id'] != target['request_identity']:
            raise ValueError('supervision belongs to another generation request')
        first = len(rows)
        if method == 'OneShot':
            x, mask = view.oneshot(path[0][0])
            label = PLANS.index(tuple(target['target']))
            if not mask[label]:
                raise ValueError('target outside shared reachable plan space')
            rows.append(dict(features=x, mask=mask, target=label))
        else:
            for obs, action in path:
                x, mask = view.sequential(obs)
                if not mask[action]:
                    raise ValueError('illegal BC action')
                rows.append(dict(features=x, mask=mask, target=action))
        groups.append(dict(prefix_identity=target['prefix_identity'], start=first, end=len(rows)))
    metadata = stamp(dict(version='pmrl1-bc-supervision-v1', method=method,
        handoff_identity=handoff['identity'], menu_identity=handoff['menu_identity'],
        qualification_identity=handoff['qualification_identity'],
        freeze_identity=handoff['freeze_identity'], feature_identity=view.identity,
        plan_order_identity=digest(PLANS), executors=handoff['executors'],
        renderers=handoff['renderers'], acquired_text_zero=view.no_text,
        rows_identity=digest(rows), groups=groups, training_authorized=False))
    return rows, metadata


def checkpoint_requirements(metadata, *, seed):
    verify_identity(metadata)
    if seed not in (17, 29, 43):
        raise ValueError('seed outside original plan')
    return stamp(dict(version='pmrl1-bc-checkpoint-binding-v1', seed=seed,
        supervision_identity=metadata['identity'], **{k:metadata[k] for k in
        ('method', 'feature_identity', 'qualification_identity', 'freeze_identity',
         'menu_identity', 'plan_order_identity', 'executors', 'renderers', 'acquired_text_zero')}))


def verify_checkpoint_receipt(receipt, *, requirements, checkpoint_sha256):
    """Verify caller-hashed checkpoint provenance before deserializing weights.

    The trainer must supply a completed optimization receipt. This checks its
    bindings, not whether an untrusted author really performed optimization.
    A valid receipt never creates training/rollout permission.
    """
    verify_identity(receipt)
    verify_identity(requirements)
    if (receipt.get('requirements') != requirements
            or receipt.get('checkpoint_sha256') != checkpoint_sha256
            or len(checkpoint_sha256) != 64
            or any(c not in '0123456789abcdef' for c in checkpoint_sha256)
            or receipt.get('status') != 'BC_OPTIMIZATION_COMPLETED'
            or type(receipt.get('optimizer_steps')) is not int or receipt['optimizer_steps'] <= 0):
        raise ValueError('completed bound BC checkpoint required; random init is not BC')
    return True

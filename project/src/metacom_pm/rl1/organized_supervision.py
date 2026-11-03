"""Source-addressed supervision for the opt-in organized resource domain.

No providers or weight loaders. Menus are registered before measurement; all
scheduled ON/OFF feedback is required. A missing endpoint is never a negative
example. Ordered programs replace the old 70 count vectors, not their labels.
"""
from collections import defaultdict
from copy import deepcopy

from .calibration_workflow import stamp, verify_identity
from .measurement_identity import canonical
from .organized_feedback import OrganizedEpisode
from .organized_policy_interface import HeadSession, commit_program
from .schema import digest

VERSION = 'pmrl1-organized-supervision-dev-v1'
PROGRAM_IDENTITY = digest(dict(version=VERSION, actions=['STOP','RS','MP','MS','ME'],
    representation='ordered complete head program; no fixed horizon', padding=-1))


def endpoint(factory, actions):
    """Construction-side replay; no future feasibility oracle enters the actor."""
    e = factory()
    if type(e) is not OrganizedEpisode or e.phase != 'acquiring' or e.steps:
        raise ValueError('fresh organized episode required')
    if e.catalog.prefix.split != 'train':
        raise ValueError('supervision accepts train sources only')
    program = commit_program(e.session.observe(), actions,
                             interface_identity=e.session.interface_identity)
    for action in program.actions:
        e.step(action)
    return stamp(dict(version=VERSION, prefix_identity=e.catalog.prefix.identity,
        actions=list(program.actions), requests=deepcopy(e.requests),
        resource_tokens=e.session.observe().resource_tokens, cost_identity=e.cost.identity,
        evidence_source=deepcopy(e.evidence_source), domain_identity=e.domain)), e


def training_menu(endpoints, *, source_identity, scope='initial_train', union_identity=None):
    if (not endpoints or not source_identity or scope not in ('initial_train','final_train_union')
            or (scope == 'final_train_union') != bool(union_identity)):
        raise ValueError('explicit initial source or completed final union required')
    groups = defaultdict(list)
    for x in endpoints:
        verify_identity(x)
        if x['version'] != VERSION:
            raise ValueError('old count menu is not an organized program')
        groups[x['prefix_identity']].append(x)
    keys = [(x['prefix_identity'], tuple(x['actions'])) for x in endpoints]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate scheduled program')
    if len({(x['domain_identity'],x['cost_identity']) for x in endpoints}) != 1:
        raise ValueError('one common resource/G/cost domain required')
    for xs in groups.values():
        off = [x for x in xs if x['actions'] == [0]]
        if len(off) != 1 or off[0]['resource_tokens'] != 0:
            raise ValueError('explicit true OFF program required per prefix')
        if len({digest(x['requests']['OFF']) for x in xs}) != 1 or len({digest(x['evidence_source']) for x in xs}) != 1:
            raise ValueError('same-prefix OFF/evidence differs')
    ordered = sorted(deepcopy(endpoints), key=lambda x:(x['prefix_identity'],x['actions']))
    return stamp(dict(version=VERSION, scope=scope, source_identity=source_identity,
        union_identity=union_identity, endpoints=ordered, program_identity=PROGRAM_IDENTITY,
        automatic_training_authorization=False))


def _check_menu(menu, factories, union_proof):
    verify_identity(menu)
    if menu != training_menu(menu['endpoints'], source_identity=menu['source_identity'],
                            scope=menu['scope'], union_identity=menu['union_identity']):
        raise ValueError('scheduled menu changed')
    if set(factories) != {x['prefix_identity'] for x in menu['endpoints']}:
        raise ValueError('exact complete train prefix set required')
    if menu['scope'] == 'final_train_union':
        if union_proof is None:
            raise ValueError('final union needs completed comparison provenance')
        verify_identity(union_proof)
        if (union_proof['identity'] != menu['union_identity']
                or union_proof.get('endpoint_identities') != [x['identity'] for x in menu['endpoints']]
                or union_proof.get('status') != 'COMPLETE_COMMON_TRAIN_UNION'):
            raise ValueError('final union was reduced or relabeled')


def prepare_targets(menu, *, factories, responses, receipts, union_proof=None):
    """Recompute qualification and replay every source, action and token cost."""
    _check_menu(menu, factories, union_proof)
    if menu['scope'] == 'final_train_union' and (
            union_proof['response_identities'] != {k:digest(v) for k,v in sorted(responses.items())}
            or union_proof['receipt_identities'] != {k:digest(v) for k,v in sorted(receipts.items())}):
        raise ValueError('final common feedback was reduced or relabeled')
    base = dict(version=VERSION, menu_identity=menu['identity'], menu_scope=menu['scope'],
        program_identity=PROGRAM_IDENTITY, automatic_training_authorization=False)
    checked, pending, measurements, routes, scopes = [], [], {}, set(), set()
    for x in menu['endpoints']:
        rebuilt, e = endpoint(factories[x['prefix_identity']], x['actions'])
        if rebuilt != x:
            raise ValueError('program source/rendering/evidence/cost changed')
        if e.route is None:
            pending.append(dict(endpoint=x['identity'], reason='missing_qualification'))
            continue
        e.route.check(e.domain)
        routes.add(e.route.identity)
        scopes.add(e.route.bundle['inputs']['code'].get('synthetic_only') is True)
        if len(routes) > 1 or len(scopes) > 1:
            raise ValueError('mixed measurement qualification or engineering scope')
        def measure(query, evidence, reply):
            rec = receipts.get(query['generation_request_id'])
            if rec is None:
                return None
            if rec.get('binding') != query:
                raise ValueError('qualified canonical training feedback binding changed')
            content = digest(canonical(query,evidence,reply))
            if rec.get('measurement_status') == 'measured_candidate':
                label = (rec.get('q'),rec.get('m'))
                if content in measurements and measurements[content] != label:
                    raise ValueError('identical scoring input has conflicting labels')
                measurements[content] = label
            return rec
        result = e.advance(lambda req: responses.get(req['request_id']), measure)
        if result['phase'] != 'terminal':
            pending.append(dict(endpoint=x['identity'],reason=result['phase']))
            continue
        labels = {}
        for role, req in e.requests.items():
            rec = e.receipts[req['request_id']]
            content = digest(canonical(rec['binding'],e.evidence,e.responses[req['request_id']]['text']))
            labels[role] = dict(content=content,q=rec['q'],m=rec['m'])
        checked.append(dict(endpoint_identity=x['identity'],prefix_identity=x['prefix_identity'],
            actions=x['actions'],resource_tokens=x['resource_tokens'],return_target=result['return_value'],
            rewards=[s['reward'] for s in e.steps],labels=labels,
            receipt_identities={k:digest(v) for k,v in e.receipts.items()}))
    # No partial target/row release, even when some prefixes are already complete.
    if pending:
        return stamp(base | dict(status='PENDING_SCHEDULED_FEEDBACK',pending=pending,
            targets=[],measured=[],complete_endpoints=len(checked)))
    groups = defaultdict(list)
    for x in checked:
        groups[x['prefix_identity']].append(x)
    targets, sensitivity = [], []
    for pid, xs in sorted(groups.items()):
        key = lambda x:(-x['return_target'],x['resource_tokens'],tuple(x['actions']))
        best = min(xs,key=key); targets.append(best)
        # Sensitivity, not an error-rate estimate: perturb one shared scoring
        # input by one q category. Identical ON/OFF inputs move together.
        changes=[]
        contents={v['content']:v['q'] for x in xs for v in x['labels'].values()}
        for content,q in sorted(contents.items()):
            for step in (-1,1):
                if not 0 <= q+step <= 4: continue
                perturbed=[]
                for x in xs:
                    delta=step/4*((x['labels']['ON']['content']==content)-(x['labels']['OFF']['content']==content))
                    perturbed.append(x | dict(return_target=x['return_target']+delta))
                chosen=min(perturbed,key=key)
                if chosen['endpoint_identity'] != best['endpoint_identity']:
                    changes.append(dict(content=content,q_step=step,selected=chosen['endpoint_identity']))
        sensitivity.append(dict(prefix_identity=pid,shared_input_q_step_switches=changes,
            interpretation='sensitivity only; no inferred probability or automatic relabeling'))
    return stamp(base | dict(status='READY',pending=[],targets=targets,measured=checked,
        sensitivity=sensitivity,scope='ENGINEERING_ONLY' if scopes == {True} else 'QUALIFIED_NATURAL_STUDY',
        route_identity=next(iter(routes)),unmeasured_programs_are_negative=False))


def prepare_supervised(menu, *, factories, responses, receipts, view, method, union_proof=None):
    """Feed existing BC/value optimizer; OneShot regresses ALL measured returns."""
    from .supervised_learning import CONFIG
    expected = 'final_train_union' if method in ('BC-union','OneShot') else 'initial_train'
    if method not in ('BC-init','BC-union','PPO-NoText','OneShot') or menu['scope'] != expected:
        raise ValueError('method requires its initial or final common pool')
    if view.no_text != (method == 'PPO-NoText'):
        raise ValueError('NoText requires its own persistently hidden initialization')
    handoff = prepare_targets(menu,factories=factories,responses=responses,receipts=receipts,union_proof=union_proof)
    if handoff['status'] != 'READY':
        return stamp(dict(version=VERSION,status=handoff['status'],method=method,rows=[],handoff=handoff))
    rows=[];groups=[]
    selected=handoff['measured'] if method == 'OneShot' else handoff['targets']
    for t in selected:
        e=factories[t['prefix_identity']]()
        if e.route.bundle['inputs']['contract']['policy']['supervised'] != CONFIG:
            raise ValueError('supervised hyperparameters changed')
        s=HeadSession(e.catalog,e.renderer,without_text=view.no_text)
        start=len(rows)
        if method == 'OneShot':
            features,_=view.sequential(s.observe())
            rows.append(dict(features=features,program=t['actions'],return_target=t['return_target']))
        else:
            for i,action in enumerate(t['actions']):
                features,mask=view.sequential(s.observe())
                if not mask[action]:raise ValueError('supervised action is not available')
                rows.append(dict(features=features,mask=mask,target=action,
                                 return_target=sum(t['rewards'][i:])))
                s.step(action)
        groups.append(dict(prefix_identity=t['prefix_identity'],endpoint_identity=t['endpoint_identity'],start=start,end=len(rows)))
    meta=stamp(dict(method=method,feature_identity=view.identity,acquired_text_zero=view.no_text,
        handoff_identity=handoff['identity'],menu_identity=menu['identity'],
        qualification_identity=e.route.qualification['identity'],freeze_identity=e.route.bundle['freeze']['identity'],
        measurement_use_identity=e.route.use_record['identity'],cost_identity=e.cost.identity,
        # Legacy checkpoint key, explicitly bound to ordered programs, not PLANS.
        plan_order_identity=PROGRAM_IDENTITY,program_representation='ordered heads, STOP, variable length',
        executors=sorted({x['requests']['ON']['executor_identity'] for x in menu['endpoints']}),
        renderers=sorted({x['requests']['ON']['renderer_identity'] for x in menu['endpoints']}),
        rows_identity=digest(rows),groups=groups))
    return stamp(dict(version=VERSION,status='READY',scope=handoff['scope'],method=method,
        rows=rows,metadata=meta,config=CONFIG,feature_dimension=view.feature_dimension,
        handoff_identity=handoff['identity'],qualification_identity=e.route.qualification['identity'],
        measurement_identity=e.route.bundle['freeze']['runtime_identity'],
        qualification_bundle_identity=digest(e.route.bundle),training_authorized=False))


def validate_prepared(prepared):
    verify_identity(prepared);meta=prepared['metadata'];verify_identity(meta)
    if (prepared['version'] != VERSION or prepared['status'] != 'READY'
            or meta['rows_identity'] != digest(prepared['rows']) or not prepared['rows']
            or meta['plan_order_identity'] != PROGRAM_IDENTITY
            or meta['method'] != prepared['method']):
        raise ValueError('organized supervised identity changed')


def comparison_union(*, study, manifests, completions, batches, initial_menu, initial_feedback, factories):
    """All fixed-scale seeds/methods, initial pool, ON and OFF; no curated subset."""
    from .study_schedule import validate_runset
    validate_runset(study,manifests);verify_identity(initial_menu)
    if initial_menu['scope'] != 'initial_train':raise ValueError('initial pool required')
    expected={m['identity']:m for m in manifests}
    if len(completions) != len(expected) or {x['run_identity'] for x in completions} != set(expected):
        raise ValueError('every method/seed must complete before common union')
    endpoints={(x['prefix_identity'],tuple(x['actions'])):x for x in initial_menu['endpoints']}
    feedback=deepcopy(initial_feedback);used=[]
    if not feedback:raise ValueError('initial feedback cannot disappear')
    initial_responses, initial_receipts = {}, {}
    initial_requests = {r['request_id'] for x in initial_menu['endpoints'] for r in x['requests'].values()}
    for row in feedback:
        key = row['request']['request_id']
        if key not in initial_requests:
            raise ValueError('foreign feedback in initial pool')
        if key in initial_responses and (initial_responses[key] != row['response'] or initial_receipts[key] != row['receipt']):
            raise ValueError('contradictory initial feedback')
        initial_responses[key], initial_receipts[key] = row['response'], row['receipt']
    initial_factories = {x['prefix_identity']: factories[x['prefix_identity']] for x in initial_menu['endpoints']}
    if prepare_targets(initial_menu, factories=initial_factories, responses=initial_responses,
                       receipts=initial_receipts)['status'] != 'READY':
        raise ValueError('initial pool must be complete before adding later feedback')
    for done in completions:
        verify_identity(done);m=expected[done['run_identity']]
        bs=sorted((b for b in batches if b['run_identity']==m['identity']),key=lambda b:b['policy_version'])
        if (m.get('initial_menu_identity') != initial_menu['identity']
                or done.get('status') != 'FIXED_TRAINING_ENDPOINT_COMPLETED'
                or done.get('episodes') != study['episodes'] or done.get('updates') != m['max_updates']
                or [b['policy_version'] for b in bs] != list(range(1,m['max_updates']+1))
                or done.get('update_receipt_identities') != [b['identity'] for b in bs]
                or done.get('parameters') != bs[-1]['after']):
            raise ValueError('incomplete or replaced comparison run')
        for b in bs:
            verify_identity(b);used.append(b['identity'])
            bindings=m['trajectories'][16*(b['policy_version']-1):16*b['policy_version']]
            rows=b['training_feedback']
            if len(rows)!=32 or b.get('completed_episodes')!=16*b['policy_version']:
                raise ValueError('complete 16 ON/OFF feedback required')
            if len({v['trajectory_id'] for v in bindings}) != 16 or {r['trajectory_id'] for r in rows}!={v['trajectory_id'] for v in bindings}:
                raise ValueError('comparison trajectory coverage changed')
            for v in bindings:
                pair=[r for r in rows if r['trajectory_id']==v['trajectory_id']]
                if len(pair)!=2 or {r['role'] for r in pair}!={'ON','OFF'}:
                    raise ValueError('missing ON or OFF')
                for r in pair:
                    x,e=endpoint(factories[v['prefix_identity']],r['actions'])
                    if (r['split']!='train' or r['request']!=e.requests[r['role']]
                            or (r['role']=='OFF' and r['actions']!=[0])
                            or r['cost_identity']!=e.cost.identity or e.route is None
                            or r['measurement_use_identity']!=e.route.use_record['identity']
                            or v['evidence_identity']!=digest(e.evidence)
                            or v['renderer_identity']!=e.renderer.identity
                            or e.executor_identity not in m['executors']
                            or e.route.qualification['identity']!=study['qualification_identity']):
                        raise ValueError('union source/domain/qualification changed')
                    key=(x['prefix_identity'],tuple(x['actions']))
                    if key in endpoints and endpoints[key]!=x:raise ValueError('program source changed between runs')
                    endpoints[key]=x
                feedback.extend(pair)
    if len(used)!=len(batches):raise ValueError('extra comparison batches')
    responses,receipts={},{}
    for r in feedback:
        req=r['request'];key=req['request_id']
        if key in responses and (responses[key]!=r['response'] or receipts[key]!=r['receipt']):
            raise ValueError('same generation input has contradictory feedback')
        responses[key],receipts[key]=r['response'],r['receipt']
    ordered=sorted(endpoints.values(),key=lambda x:(x['prefix_identity'],x['actions']))
    proof=stamp(dict(status='COMPLETE_COMMON_TRAIN_UNION',study_identity=study['identity'],
        completed_runs=sorted(expected),batches=sorted(used),
        endpoint_identities=[x['identity'] for x in ordered],feedback_identity=digest(feedback),
        response_identities={k:digest(v) for k,v in sorted(responses.items())},
        receipt_identities={k:digest(v) for k,v in sorted(receipts.items())}))
    menu=training_menu(ordered,source_identity=proof['identity'],scope='final_train_union',union_identity=proof['identity'])
    checked=prepare_targets(menu,factories=factories,responses=responses,receipts=receipts,union_proof=proof)
    if checked['status']!='READY':raise ValueError('common union still has missing feedback')
    return menu,responses,receipts,proof

"""Common scale and completed-feedback union for the original comparison."""
from dataclasses import asdict
import math

from .calibration_workflow import stamp, verify_identity
from .learning_preparation import TerminalCandidate
from .schema import digest

SEEDS=(17,29,43)


def freeze_scale(qualification, evidence, executors):
    verify_identity(qualification)
    if qualification['status'] not in ('CALIBRATED_FOR_BOUNDED_STUDY','CALIBRATED_LOW_CONTRAST'):
        raise ValueError('qualified measurement required for a formal common scale')
    for name in ('hours_128','hours_384'):
        v=evidence.get(name)
        if type(v) not in (int,float) or not math.isfinite(v) or v<0:
            raise ValueError('finite full-engine throughput estimates required')
    if not evidence.get('source_identity') or not executors or len(set(executors))!=len(executors):
        raise ValueError('bound full-study throughput and executor set required')
    size=128 if qualification['status']=='CALIBRATED_LOW_CONTRAST' or evidence['hours_384']>96 else 384
    if size==128 and evidence['hours_128']>96:
        raise ValueError('128 still exceeds envelope; researcher scheduling decision required')
    return stamp(dict(version='pmrl1-common-comparison-scale-v1',
        qualification_identity=qualification['identity'],scale_evidence=evidence,
        executors=sorted(executors),seeds=list(SEEDS),learning_methods=['PPO','PPO-NoText'],
        episodes=size,dev_checks=[64,128] if size==128 else [128,384]))


def validate_runset(study, manifests):
    verify_identity(study)
    if (study['learning_methods']!=['PPO','PPO-NoText'] or study['seeds']!=list(SEEDS)
            or study['episodes'] not in (128,384)):
        raise ValueError('original common method/seed comparison required')
    expected={(x,m,s) for x in study['executors'] for m in study['learning_methods'] for s in SEEDS}
    actual=[]
    for m in manifests:
        verify_identity(m)
        if (m.get('study_scale')!=study or m['episodes']!=study['episodes']
                or m['qualification_identity']!=study['qualification_identity']
                or m['scale_evidence']!=study['scale_evidence'] or len(m['executors'])!=1
                or m['max_updates']!=study['episodes']//16 or m['batch_size']!=16
                or len(m['trajectories'])!=study['episodes']):
            raise ValueError('every method/seed must use the same frozen study scale')
        actual.append((m['executors'][0],m['method'],m['seed']))
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise ValueError('complete shared method/seed comparison required')


def common_union(*, study, manifests, completions, batch_receipts, initial_candidates, initial_receipts, initial_menus):
    """Rebuild from all completed runs, not a caller-labeled final_union menu.

    Return all actually obtained train feedback including initial supervision.
    Every batch contributes its OFF and selected terminal, with exact-source
    duplicates reused. Missing runs/batches or contradictory feedback fail closed.
    """
    validate_runset(study,manifests)
    expected={m['identity']:m for m in manifests}
    if len(completions)!=len(expected) or {r['run_identity'] for r in completions}!=set(expected):
        raise ValueError('all comparison runs must finish before final union')
    candidates={};receipts={};producers={}
    def add(c,r,producer):
        if (c.split!='train' or c.executor_identity not in study['executors']
                or not r or r.get('measurement_status')!='measured_candidate'
                or r['binding'].get('generation_request_id')!=c.request_identity
                or r['binding'].get('response_identity')!=c.response_identity
                or r['binding'].get('evidence_identity')!=c.evidence_identity
                or r['binding'].get('qualification_identity')!=study['qualification_identity']
                or r['binding'].get('measurement_purpose')!='training'):
            raise ValueError('only qualified bound train feedback belongs in the final union')
        key=(c.executor_identity,c.prefix_identity,c.counts)
        if key in candidates and (candidates[key]!=c or
                any(receipts[c.request_identity].get(k)!=r.get(k) for k in ('q','m','content_receipt_identity'))):
            raise ValueError('same training terminal has conflicting source or feedback')
        candidates[key]=c;receipts[c.request_identity]=r
        producers.setdefault(c.request_identity,[]).append(producer)
    if not initial_candidates:raise ValueError('initial supervised pool cannot disappear from final union')
    from .learning_handoff import candidate_menu
    for executor in study['executors']:
        menu=initial_menus[executor];verify_identity(menu)
        cs=[c for c in initial_candidates if c.executor_identity==executor]
        if (candidate_menu(cs,source_identity=menu['source_identity'],scope='initial_train')!=menu
                or any(m['initial_menu_identity']!=menu['identity'] for m in manifests if executor in m['executors'])):
            raise ValueError('initial pool differs from the common BC source')
    for c in initial_candidates:add(c,initial_receipts.get(c.request_identity),'initial_pool')
    used=[]
    for done in completions:
        verify_identity(done);m=expected[done['run_identity']]
        batches=[r for r in batch_receipts if r['run_identity']==m['identity']]
        batches.sort(key=lambda r:r['policy_version'])
        if (done['status']!='FIXED_TRAINING_ENDPOINT_COMPLETED' or done['episodes']!=study['episodes']
                or done['updates']!=m['max_updates']
                or [r['policy_version'] for r in batches]!=list(range(1,m['max_updates']+1))
                or done.get('update_receipt_identities')!=[r['identity'] for r in batches]):
            raise ValueError('missing or replaced completed training batch')
        for r in batches:
            verify_identity(r);used.append(r['identity'])
            v=r['policy_version'];bindings=m['trajectories'][16*(v-1):16*v]
            if r.get('completed_episodes')!=16*v:raise ValueError('completed episode count mismatch')
            rows=r.get('training_feedback',[])
            if len(rows)!=32:raise ValueError('each complete batch must export all 16 ON and OFF records')
            expected_ids={b['trajectory_id'] for b in bindings}
            if {row['trajectory_id'] for row in rows}!=expected_ids:
                raise ValueError('final union trajectory coverage mismatch')
            for b in bindings:
                pair=[x for x in rows if x['trajectory_id']==b['trajectory_id']]
                if len(pair)!=2 or {x['role'] for x in pair}!={'ON','OFF'}:
                    raise ValueError('ON/OFF source coverage mismatch')
                for row in pair:
                    c=TerminalCandidate(**(row['candidate']|dict(counts=tuple(row['candidate']['counts']))))
                    if (c.prefix_identity!=b['prefix_identity'] or c.evidence_identity!=b['evidence_identity']
                            or c.renderer_identity!=b['renderer_identity']
                            or (row['role']=='OFF' and c.counts!=(0,0,0,0))):
                        raise ValueError('union feedback differs from frozen train source')
                    add(c,row['receipt'],m['identity'])
        if done['parameters']!=batches[-1]['after']:raise ValueError('final checkpoint differs from completed run')
    if len(used)!=len(batch_receipts):raise ValueError('extra or foreign training batches')
    ordered=[candidates[k] for k in sorted(candidates)]
    receipt=stamp(dict(version='pmrl1-completed-training-union-v1',study_identity=study['identity'],
        completed_runs=sorted(expected),batch_receipt_identities=sorted(used),
        candidate_rows_identity=digest([asdict(c) for c in ordered]),
        receipt_identities={k:digest(v) for k,v in sorted(receipts.items())},
        producers={k:sorted(set(v)) for k,v in sorted(producers.items())},
        test_or_dev_feedback_included=False))
    return ordered,receipts,receipt

"""Different G plans share one formal score, but independent draws never do."""
from dataclasses import replace

import pytest

from metacom_pm.rl1.bound_generation import BoundResourceEnv
from metacom_pm.rl1.calibration_workflow import qualify
from metacom_pm.rl1.learning_handoff import candidate_menu, prepare_handoff
from metacom_pm.rl1.learning_preparation import TerminalCandidate
from metacom_pm.rl1.measurement_identity import binding
from metacom_pm.rl1.natural_batch import FeedbackQueue
from metacom_pm.rl1.natural_runner import NaturalEpisode
from metacom_pm.rl1.schema import digest
from test_rl1_learning_handoff import inputs


def test_two_G_plans_identical_content_one_score_to_episode_and_BC(tmp_path):
    cs, kw, _ = inputs()
    bundle = kw['qualification_bundle']; q = qualify(**bundle)
    spec, renderer = next(iter(kw['episodes'].values()))
    evidence = 'MOCK legal full source'; reply = 'MOCK identical response'
    episode = NaturalEpisode(spec, renderer, evidence=evidence, freeze=bundle['freeze'],
        freeze_inputs=bundle['inputs'], qualification=q, trajectory_id='new-on-policy-draw')
    episode.acquire(lambda obs: 1 if obs.counts == (0,0,0,0) else 0)
    queue = FeedbackQueue(tmp_path/'queue.sqlite')
    def generate(req):
        return dict(request_id=req['request_id'], runtime_identity=spec.executor_identity,
                    text=reply, finish_reason='natural_stop')
    assert episode.advance(generate,queue.measure)['phase']=='pending_score'
    item = queue.claim_next(kind='measurement')
    assert item and queue.claim_next() is None
    assert 'generation_request_id' not in item['payload']['binding']
    queue.settle(item['id'],dict(binding=item['payload']['binding'],
        measurement_status='measured_candidate',q=3,m=0))
    result=episode.advance(generate,queue.measure)
    assert result['terminal_reward']==0 # no fictitious quality gain
    assert result['return_value']==pytest.approx(-.05*renderer.cost(spec,(1,0,0,0))/2048)
    assert len(result['measurement_receipts'])==2
    assert len({r['content_receipt_identity'] for r in result['measurement_receipts']})==1
    receipts={r['binding']['generation_request_id']:r for r in result['measurement_receipts']}
    cs=[replace(c,response_identity=digest(reply),evidence_identity=digest(evidence)) for c in cs]
    menu=candidate_menu(cs,scope='initial_train',source_identity='MOCK unchanged source')
    handoff=prepare_handoff(cs,menu=menu,receipts=receipts,qualification_bundle=bundle,episodes=kw['episodes'])
    assert handoff['status']=='READY' and handoff['targets'][0]['target']==(0,0,0,0)
    reopened=FeedbackQueue(queue.path)
    b=next(iter(receipts.values()))['binding']
    assert reopened.measure(b,evidence,reply)==receipts[b['generation_request_id']]
    with reopened.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM measurement_origins').fetchone()[0]==2


@pytest.mark.parametrize('field', ['runtime_identity','rubric_identity','freeze_identity',
    'qualification_identity','measurement_draw_identity','evidence_identity','response_identity'])
def test_version_content_and_repeat_isolation(tmp_path,field):
    queue=FeedbackQueue(tmp_path/'q.sqlite')
    source='MOCK source'; reply='MOCK reply'
    b=binding('G1',digest(reply),digest(source),dict(identity='freeze',runtime_identity='runtime',
        rubric_identity='rubric'),dict(identity='qualification'))
    queue.measure(b,source,reply)
    changed=dict(b,generation_request_id='G2')
    if field=='measurement_draw_identity':
        changed.update(measurement_purpose='independent_repeat',measurement_draw_identity='repeat-1')
    elif field=='evidence_identity':source+=' new';changed[field]=digest(source)
    elif field=='response_identity':reply+=' new';changed[field]=digest(reply)
    else:changed[field]+=' new'
    queue.measure(changed,source,reply)
    assert queue.claim_next() and queue.claim_next() and queue.claim_next() is None

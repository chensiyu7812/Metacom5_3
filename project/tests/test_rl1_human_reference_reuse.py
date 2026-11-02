from metacom_pm.rl1.human_reference_reuse import pair_reference, reuse_map
from metacom_pm.rl1.schema import digest


def test_pair_reuse_requires_both_exact_replies_and_full_evidence():
    refs=[pair_reference(source='old',record_id='p',evidence_id=digest({'full':'past'}),
        left=digest('A'),right=digest('B'),direction='right',raw_label='human B',
        observation_origin='human-1',purpose='exposed development')]
    ms=[dict(key='newdev_01_'+s,purpose='new_development_not_independent_validation',
             reply=r,evidence={'full':'past'}) for s,r in [('0','B'),('1','A')]]
    x=reuse_map(ms,refs,[])
    assert x['summary']['newdev_pairs_with_exact_old_preference']==1
    assert x['pair_rows'][0]['exact_pair_references'][0]['preferred_reply_identity']==digest('B')
    ms[1]['reply']='changed B'
    assert reuse_map(ms,refs,[])['summary']['newdev_pairs_with_exact_old_preference']==0
    for m in ms:m['evidence']={'full':'different past'}
    assert reuse_map(ms,refs,[])['summary']['current_reply_slots_with_old_pair_endpoint']==0


def test_range_and_tie_remain_references_without_numeric_reward():
    single=dict(source='old',record_id='q',evidence_identity=digest('e'),reply_identity=digest('A'),
                q_status='range',q_min=2,q_max=3,m_value=.25)
    p=pair_reference(source='old',record_id='p',evidence_id=digest('e'),left=digest('A'),right=digest('B'),
        direction='tie',raw_label='both acceptable',observation_origin='human',purpose='development')
    x=reuse_map([dict(key='old_case',purpose='known_regression',reply='A',evidence='e')],[p],[single])
    assert x['summary']['old_interval_q']==1
    assert x['reply_rows'][0]['q'] is None and x['reply_rows'][0]['m'] is None
    assert x['reply_rows'][0]['single_references'][0]['q_max']==3
    assert not x['summary']['qualified_reward']

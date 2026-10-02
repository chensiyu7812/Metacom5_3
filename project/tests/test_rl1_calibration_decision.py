import copy
import pytest
from metacom_pm.rl1.calibration_decision import decide


def fixture():
    source=dict(source_confirmed=True, confirmation_kind='independent_human',
                human_review_identity='a'*64, source_ids=['C:T000'])
    natural=[dict(pair_id=str(i),owner='owner'+str(i%4),prefix_identity=str(i),
        human={'a':'left','b':'left'}, scores=[dict(q=4,m=0),dict(q=3,m=0)]) for i in range(16)]
    controls=[dict(source,control_type=k,good_side=0,bad_side=1,
        scores=[dict(q=4,m=0),dict(q=1,m=1)]) for k in ('identity','subject','currentness','intent_to_result')]
    controls += [dict(source,control_type=k,scores=[dict(q=3,m=0),dict(q=3,m=0)])
                 for k in ('equivalent_wording','equivalent_wording','general_support','general_support')]
    repeats=[dict(cache_hit=False,primary_draw='first',repeat_draw='repeat',
        primary=dict(q=4,m=0),repeat=dict(q=4,m=0)) for _ in range(12)]
    return dict(natural=natural,controls=controls,repeats=repeats,
        technical=dict(planned=79,first_valid=79,processable_after_recovery=79),raters=['a','b'])


def test_bounded_pass_is_not_general_or_automatic_training_authorization():
    result=decide(**fixture())
    assert result['status']=='CALIBRATED_FOR_BOUNDED_STUDY'
    assert not result['automatic_training_authorization']


def test_clear_human_preference_vs_automatic_tie_counts_wrong():
    x=fixture()
    for r in x['natural'][:5]:r['scores'][1]=dict(q=4,m=0)
    result=decide(**x)
    assert result['natural']['clear_matched']==11 and result['status']=='MEASUREMENT_UNQUALIFIED'


def test_low_contrast_all_clear_directions_must_match():
    x=fixture()
    for r in x['natural'][:10]:r['human']={'a':'tie','b':'tie'};r['scores'][1]=dict(q=4,m=0)
    result=decide(**x)
    assert result['status']=='CALIBRATED_LOW_CONTRAST' and result['requires_128_episodes']
    x['natural'][-1]['scores'][0]=dict(q=2,m=0)
    assert decide(**x)['status']=='INSUFFICIENT_HUMAN_INFORMATION'


def test_disagreement_preserved_in_denominator_and_per_rater():
    x=fixture()
    for r in x['natural'][:9]:r['human']['b']='right'
    result=decide(**x)
    assert result['natural']['disagreed_or_uncertain']==9
    assert result['per_rater']['b']['right']==9
    assert result['status']=='INSUFFICIENT_HUMAN_INFORMATION'


def test_expected_control_key_is_not_a_human_source_confirmation():
    x=fixture();x['controls'][0]['confirmation_kind']='ai_coordinator'
    assert decide(**x)['status']=='INSUFFICIENT_HUMAN_INFORMATION'


def test_one_severe_repeat_flip_fails_even_if_utility_is_same():
    x=fixture();x['repeats'][0].update(primary=dict(q=0,m=0),repeat=dict(q=4,m=1))
    result=decide(**x)
    assert result['repeat_same_utility']==12 and result['repeat_severe_flips']==1
    assert result['status']=='MEASUREMENT_UNQUALIFIED'


def test_missing_is_not_imputed_and_bad_denominators_rejected():
    x=fixture();x['natural'][0]['scores'][0]=dict(q=None,m=None)
    assert decide(**x)['natural']['missing_auto']==1
    with pytest.raises(ValueError):decide(**dict(x,natural=x['natural'][:-1]))


def test_source_confirmed_severe_natural_error_overrides_aggregate_pass():
    x=fixture();x['natural'][0]['severe_facts']=[dict(x['controls'][0],side=0)]
    result=decide(**x)
    assert result['natural']['clear_matched']==16
    assert result['status']=='MEASUREMENT_UNQUALIFIED'


def test_single_rater_scope_is_reported_and_not_interhuman_agreement():
    x=fixture();x['raters']=['a']
    for r in x['natural']:r['human']={'a':r['human']['a']}
    assert decide(**x)['sample']['raters']==1


def test_reserve_cannot_be_just_one_chosen_extra_pair():
    x=fixture();x['natural'].append(dict(copy.deepcopy(x['natural'][0]),pair_id='extra'))
    with pytest.raises(ValueError):decide(**x)

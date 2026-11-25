import pytest
from metacom_pm.rl1v3.journal.semantic_validation import decision,metrics,wilson


@pytest.mark.parametrize('scores,want',[
    ([.05,.9,.05],'pass'),([.9,.05,.05],'fail'),([.1,.7,.2],'unknown'),
    ([.05,.05,.9],'unknown'),([.11,.89,0],'unknown'),
])
def test_fixed_threshold_neutral_and_opposite_margin(scores,want):
    assert decision(scores)==want


def test_ambiguous_reference_is_not_negative_and_zero_denominator_is_null():
    result=metrics([dict(reference='unknown',prediction='pass')])
    assert result['false_pass']['denominator']==0 and result['false_pass']['rate'] is None
    assert result['pass_on_ambiguous']['rate']==1 and result['false_fail']['wilson95'] is None


def test_abstention_keeps_known_negative_denominator():
    result=metrics([dict(reference='fail',prediction='unknown'),dict(reference='fail',prediction='pass')])
    assert result['false_pass']['count']==1 and result['false_pass']['denominator']==2
    assert result['abstention']['rate']==.5


def test_wilson_zero_and_small_samples_are_not_overconfident():
    assert wilson(0,0) is None
    assert wilson(0,1)[1]>.79 and wilson(1,1)[0]<.21

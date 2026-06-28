from metacom_pm.evo_metrics import observation_metrics
from metacom_pm.stats import paired_bootstrap_ci,success_modes,win_tie_loss

def test_official_observation_metric_formula():
    rows=[{'relevance':1.0,'used':True},{'relevance':1.0,'used':False},{'relevance':0.5,'used':True},{'relevance':0.0,'used':True}]
    result=observation_metrics(rows)
    assert result['observation_recall']==0.5
    assert abs(result['weighted_observation_use']-0.6)<1e-9

def test_success_modes():
    result=success_modes(response_difference_ci={'lower':-0.02,'upper':0.04},cost_difference_ci={'lower':-20,'upper':-3},misuse_difference_ci={'lower':-0.02,'upper':0.01},response_noninferiority_margin=0.05,misuse_noninferiority_margin=0.05)
    assert result['success_mode_b'] and result['primary_claim_supported']

def test_wtl():
    assert win_tie_loss(['A','tie','B'])['preference_score']==0.5

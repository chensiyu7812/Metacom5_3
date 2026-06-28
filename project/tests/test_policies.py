from metacom_pm.policies import FixedPolicy,FullAvailablePolicy
from metacom_pm.contracts import StrategyMode

def test_fixed_fallback_drops_unavailable_sources(tiny_state):
    assert FixedPolicy('MPMSME+RS').choose(tiny_state)=='MPE+RS'

def test_full_available(tiny_state):
    assert FullAvailablePolicy(StrategyMode.R0).choose(tiny_state)=='MPE+R0'

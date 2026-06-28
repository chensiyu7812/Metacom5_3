from collections import defaultdict
from metacom_pm.training import _action_regression_data
from metacom_pm.features import FeatureBuilder

def test_action_regression_weights_sum_to_one_per_card(tiny_state):
    raw=tiny_state.model_copy(deep=True);states={raw.card_id:raw}
    labels={(raw.card_id,a):0.5 for a in raw.allowed_actions}
    builder=FeatureBuilder(mode='metadata_only').fit([raw])
    _,_,weights,rows=_action_regression_data(states,labels,builder,{raw.card_id})
    assert abs(sum(weights)-1.0)<1e-12

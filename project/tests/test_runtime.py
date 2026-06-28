import pytest
from pydantic import ValidationError
from metacom_pm.contracts import RuntimeState

def test_runtime_json_roundtrip(tiny_state):
    dumped=tiny_state.model_dump(mode='json')
    loaded=RuntimeState.model_validate(dumped)
    assert loaded.allowed_actions==tiny_state.allowed_actions

def test_action_mask_must_match_inventory(tiny_state):
    raw=tiny_state.model_dump(mode='json');raw['allowed_actions']=raw['allowed_actions'][:-1]
    with pytest.raises(ValidationError): RuntimeState.model_validate(raw)

import pytest
from pydantic import ValidationError
from metacom_pm.contracts import (
    ACTION_MEMORY_MAP, ALL_ACTION_IDS, MemoryItem, MemorySource,
    MemoryOpportunityItem, SourceUseAssessment, canonical_action_id, parse_action_id,
)

def test_all_16_actions_roundtrip():
    assert len(ALL_ACTION_IDS)==16
    for action in ALL_ACTION_IDS:
        sources,strategy=parse_action_id(action)
        assert canonical_action_id(sources,strategy)==action
    assert parse_action_id('MPE+RS')[0]==frozenset({MemorySource.MP,MemorySource.ME})
    assert parse_action_id('MSE+R0')[0]==frozenset({MemorySource.MS,MemorySource.ME})

def test_json_enum_strings_parse_but_numbers_stay_strict():
    item=MemoryItem.model_validate({'memory_id':'mem_0123456789abcdef','source':'ME','created_session':1,'timestamp':None,'text':'A real past event.'})
    assert item.source is MemorySource.ME
    with pytest.raises(ValidationError):
        MemoryOpportunityItem.model_validate({'memory_id':'mem_0123456789abcdef','current_relevance':'2','potential_helpfulness':1,'stale':False,'conflicts_with_newer_information':False,'intrusive_if_mentioned':False})
    with pytest.raises(ValidationError):
        MemoryOpportunityItem.model_validate({'memory_id':'mem_0123456789abcdef','current_relevance':2,'potential_helpfulness':1,'stale':'false','conflicts_with_newer_information':False,'intrusive_if_mentioned':False})

def test_extra_fields_fail_closed():
    with pytest.raises(ValidationError):
        SourceUseAssessment.model_validate({'source':'ME','utilization':1,'unused_retrieval':0,'unnecessary_exposure':0,'stale_or_conflicting_use':0,'unsupported_personal_claim':0,'memory_relevance':2})

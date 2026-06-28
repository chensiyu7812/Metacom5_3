from metacom_pm.prompts import response_pair_messages,memory_opportunity_messages,memory_use_messages,generation_messages

def test_response_judge_is_blind(tiny_state):
    messages=response_pair_messages(tiny_state,'Response one','Response two')
    payload=messages[-1]['content'].lower()
    assert 'selected memory' not in payload and 'strategy guidance' not in payload and 'action_id' not in payload

def test_m1_has_no_gold_flags(tiny_state,tiny_memories):
    text=str(memory_opportunity_messages(tiny_state,tiny_memories)).lower()
    assert 'is_stale' not in text and 'is_conflicting' not in text and 'retrieval_score' not in text

def test_m2_has_no_m1_or_strategy(tiny_state,tiny_memories):
    text=str(memory_use_messages(tiny_state,tiny_memories,'That sounds difficult.')).lower()
    assert 'inventory_audit' not in text and 'current_relevance' not in text
    assert 'selected strategy guidance' not in text

def test_generation_only_contains_selected_resources(tiny_state,tiny_memories,tiny_strategy):
    text=str(generation_messages(tiny_state,[tiny_memories[0]],[tiny_strategy]))
    assert tiny_memories[0].text in text
    assert tiny_memories[1].text not in text

from pathlib import Path
from metacom_pm.io import write_jsonl,read_json
from metacom_pm.pairgraph import build_pair_graph

def test_graph_connected_covered_and_balanced(tmp_path,tiny_state):
    runtime=tmp_path/'runtime.jsonl';pairs=tmp_path/'pairs.jsonl';audit=tmp_path/'audit.json'
    rows=[]
    for i in range(8):
        raw=tiny_state.model_dump(mode='json');raw['card_id']=f"card_{i:012x}";raw['state_id']=f"state_{i:012x}";rows.append(raw)
    write_jsonl(runtime,rows)
    result=build_pair_graph(runtime,pairs,audit,reversal_fraction=.2,repeat_fraction=.1)
    assert result['ok']
    assert all(x['connected_components']==1 and not x['isolated_actions'] for x in result['per_card'].values())
    for value in result['orientation'].values():
        assert abs(value['a_is_rs']-value['b_is_rs'])<=1
        assert abs(value['a_has_more_memory']-value['b_has_more_memory'])<=1

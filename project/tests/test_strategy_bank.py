import json
from metacom_pm.strategy_bank import build_strategy_bank
from metacom_pm.io import iter_jsonl

def test_strategy_bank_uses_only_train_and_opaque_ids(tmp_path):
    dialogues=[]
    for i in range(30):
        dialogues.append({'situation':f'situation {i}','dialog':[{'speaker':'seeker','annotation':{},'content':f'help {i}'},{'speaker':'supporter','annotation':{'strategy':'Question'},'content':f'What happened {i}?'}]})
    es=tmp_path/'es.json';es.write_text(json.dumps(dialogues),encoding='utf-8')
    evo=tmp_path/'evo.json';evo.write_text(json.dumps([{'dialog_history':[]}]),encoding='utf-8')
    result=build_strategy_bank(es,evo,tmp_path/'cards.jsonl',tmp_path/'split.jsonl',tmp_path/'audit.json')
    cards=list(iter_jsonl(tmp_path/'cards.jsonl'));splits={x['dialogue_id']:x['split'] for x in iter_jsonl(tmp_path/'split.jsonl')}
    assert result['n_strategy_cards']>0
    assert all(x['strategy_id'].startswith('strat_') for x in cards)
    assert all(splits[x['source_dialogue_id']]=='train' for x in cards)

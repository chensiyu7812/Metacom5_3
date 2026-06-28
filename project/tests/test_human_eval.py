import csv
from metacom_pm.human_eval import export_blinded_pairs,analyze_annotations
from metacom_pm.io import write_jsonl,iter_jsonl

def test_human_export_and_analysis(tmp_path):
    source=tmp_path/'pairs.jsonl';blind=tmp_path/'blind.jsonl';key=tmp_path/'key.jsonl'
    write_jsonl(source,[{'pair_id':'p1','card_id':'c1','context':'ctx','response_a':'good','response_b':'bad','system_a':'pm','system_b':'rule'}])
    export_blinded_pairs(source,blind,key,n_pairs=1,seed=1)
    row=next(iter_jsonl(blind));ann=[]
    for i in range(3):
        p=tmp_path/f'a{i}.csv'
        with p.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['pair_code','preference','notes']);w.writeheader();w.writerow({'pair_code':row['pair_code'],'preference':'A','notes':''})
        ann.append(p)
    result=analyze_annotations(ann,key,tmp_path/'result.json')
    assert result['n_pairs']==1

def test_human_analysis_counts_pm_win_after_swap(tmp_path):
    key=tmp_path/'key.jsonl'
    write_jsonl(key,[{
        'pair_code':'p1',
        'source_id':'src1',
        'swap':True,
        'system_a':'rule',
        'system_b':'pm',
    }])
    ann=[]
    for i in range(3):
        p=tmp_path/f'a_swap_{i}.csv'
        with p.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['pair_code','preference','notes'])
            w.writeheader()
            w.writerow({'pair_code':'p1','preference':'B','notes':'PM shown as B'})
        ann.append(p)
    result=analyze_annotations(ann,key,tmp_path/'result_swap.json')
    assert result['rows'][0]['winner_system']=='pm'
    assert result['majority_wtl_pm']['wins']==1
    assert result['majority_wtl_pm']['losses']==0

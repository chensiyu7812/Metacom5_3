"""Publish only named aggregate/boolean/cost files from an actual SC36 run."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,write_json_once


def publish(root,out):
    root,out=map(Path,(root,out));out.mkdir(parents=True,exist_ok=True)
    allowed={
        'SC36_SUMMARY_PUBLIC.json':root/'analysis-v2/SC36_SUMMARY_PUBLIC.json',
        'SC36_TASKWISE_PUBLIC.json':root/'analysis-v2/SC36_TASKWISE_PUBLIC.json',
        'SC36_TASKWISE_ZH.md':root/'analysis-v2/SC36_TASKWISE_ZH.md',
        'SC36_SOURCE_CONTRACT_PUBLIC.json':root/'source-contract-v1/SC36_SOURCE_CONTRACT_PUBLIC.json',
        'SC36_TECHNICAL_PUBLIC.json':root/'technical-v1/SC36_TECHNICAL_PUBLIC.json',
        'SC36_PAIRED_COSTS_PUBLIC.jsonl':root/'technical-v1/SC36_PAIRED_COSTS_PUBLIC.jsonl',
        'SC1_AGGREGATE_PUBLIC.json':root/'SC1_results_v1/AGGREGATE_CONSTRAINED_PUBLIC.json',
        'SC2_AGGREGATE_PUBLIC.json':root/'SC2_results_v1/AGGREGATE_CONSTRAINED_PUBLIC.json',
    }
    for name,path in allowed.items():
        with (out/name).open('xb') as handle:handle.write(path.read_bytes())
    rows=json.loads((allowed['SC36_TASKWISE_PUBLIC.json']).read_text())['rows']
    mark={True:'通过',False:'未通过',None:'未评'}
    text=['# 原S36→新SC36的36个实际终点配对\n',
        '原严格任务0/36保持。旧body列为已存在的事后单围栏诊断，绝不作为旧任务成功。新旧字段/值均不在公开表中展示。\n',
        '|题/臂|旧→新严格任务|旧body值→新值|旧body契约→新严格任务|旧→新输出tokens|旧→新生成秒|',
        '|---|---|---|---|---:|---:|']
    for r in rows:
        outcome=lambda a,b:mark[a]+'→'+mark[b]
        text.append('|'+ '|'.join([r['task_id']+'/'+r['arm'],
            outcome(r['old_strict_success'],r['strict_success']),
            outcome(r['old_body_value_match'],r['value_correct']),
            outcome(r['old_body_contract_match'],r['strict_success']),
            f"{r['old_output_tokens']}→{r['output_tokens']}",
            f"{r['old_generation_seconds']:.3f}→{r['generation_seconds']:.3f}" if r['generation_seconds'] is not None else '未返回'])+'|')
    with (out/'SC36_OLD_NEW_PAIRED_ZH.md').open('x') as handle:handle.write('\n'.join(text)+'\n')
    write_json_once(out/'SC36_EXPORT_MANIFEST.json',dict(protocol='SC36-explicit-public-allowlist-v1',
        base_commit='4e78c03988167909a9291df4883214c51a018823',
        source_sha256={name:file_sha256(path) for name,path in allowed.items()},
        new_derived_table_sha256=file_sha256(out/'SC36_OLD_NEW_PAIRED_ZH.md'),
        raw_gold_replies_private_reviews_exported=False,formal_reward=None))
    return dict(copied_files=len(allowed),paired_rows=len(rows),new_table='SC36_OLD_NEW_PAIRED_ZH.md')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True)
    print(json.dumps(publish(**vars(p.parse_args())),indent=2))

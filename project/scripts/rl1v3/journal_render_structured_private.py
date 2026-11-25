#!/usr/bin/env python3
"""Render a local-only complete structured response/source review, without calls."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,write_bytes_once
p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--results',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
def jl(p):return [json.loads(x) for x in p.read_text().splitlines()]
refs={r['task_id']:r for r in jl(a.package/'REFERENCES.private.jsonl')};tasks={r['task_id']:r for r in jl(a.package/'TASKS.private.jsonl')}
diag={(r['task_id'],r['arm']):r for r in jl(a.results/'format_diagnostic_v1/FORMAT_DIAGNOSTIC_PRIVATE.jsonl')}
paired={r['task_id']:r for r in jl(a.results/'paired_v1/PAIRED_PRIVATE.jsonl')}
outputs={}
for name in ('S1_results_v1','S2_results_v1'):outputs.update(json.loads((a.results/name/'ACTUAL_OUTPUTS.private.json').read_text()))
lines=['# Structured36 完整私有逐题读回','包含18题×2原始模型输出、源字段、strict评分、一次独立块内诊断和块外原文。此文件含私有原文/答案，不得推送公开仓库。','所有strict结果保持冻结。块内字段匹配不等于完整回复成功；块外非空文本未被忽略。formal reward均null。','']
for tid in sorted(tasks):
 t=tasks[tid];r=refs[tid];e=r['evidence'];pair=paired[tid]
 lines+=['## '+tid,'','**问题**：'+t['question'],'','**源身份**：'+e['owner_id']+'/'+e['session_id']+'；ordinal turn '+str(e['turn'])+'；speaker '+e['speaker']+'；报告日期 '+e['reported_date'],'','**冻结字段参考**：`'+r['value']+'`。','', '**实际源原文**：','> '+e['text'],'', '**required_literal**：`'+r['required_literal']+'`。','']
 if r['multi_report_prior']:
  q=r['multi_report_prior'];lines+=['**此前共同可见报告**：'+q['session_id']+'；'+q['reported_date'],'> '+q['text'],'']
 for arm in ('BASE','RAW'):
  d=diag[(tid,arm)];o=outputs[d['request_id']]
  lines+=['### '+arm,'','**原始输出（未经清洗）**：','````text',o['text'],'````','',
   '**原strict结果**：`'+json.dumps(d['original_strict_score'],ensure_ascii=False)+'`','',
   '**一次块内诊断**：`'+json.dumps(d['body_diagnostic'],ensure_ascii=False)+'`','',
   '**块内冻结契约诊断**：`'+json.dumps(d['body_contract_diagnostic'],ensure_ascii=False)+'`','',
   '**块外文本（保留）**：','````text',d['extraction']['outside_text'] if d['extraction']['outside_text'] is not None else '(无唯一JSON块，整条原文保留为未解析)', '````','',
   '**成本**：输入 '+str(o['input_tokens'])+' tokens；输出 '+str(len(o['token_ids']))+' tokens；生成 '+str(o['seconds'])+' 秒。','']
 lines+=['**BASE→RAW原strict变化**：`'+json.dumps(pair,ensure_ascii=False)+'`','',
  '**块内字段/契约变化（非正式成功）**：BASE `'+json.dumps(dict(value=diag[(tid,'BASE')]['body_diagnostic']['value_correct'] if diag[(tid,'BASE')]['body_diagnostic'] else None,body_contract=diag[(tid,'BASE')]['body_contract_diagnostic']['task_success'] if diag[(tid,'BASE')]['body_contract_diagnostic'] else None))+'` → RAW `'+json.dumps(dict(value=diag[(tid,'RAW')]['body_diagnostic']['value_correct'] if diag[(tid,'RAW')]['body_diagnostic'] else None,body_contract=diag[(tid,'RAW')]['body_contract_diagnostic']['task_success'] if diag[(tid,'RAW')]['body_contract_diagnostic'] else None))+'`。','']
write_bytes_once(a.out,('\n'.join(lines)+'\n').encode());print(json.dumps(dict(path=str(a.out),sha256=file_sha256(a.out),tasks=len(tasks),outputs=len(outputs))))

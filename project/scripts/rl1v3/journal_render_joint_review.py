#!/usr/bin/env python3
"""Private complete J06 readback plus content-free public four-arm cells."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.io import write_bytes_once,write_json_once,file_sha256
p=argparse.ArgumentParser();p.add_argument('--joint-root',type=Path,required=True);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
def jl(p):return [json.loads(x) for x in p.read_text().splitlines()]
runtime=jl(a.joint_root/'source-bundle-v1/TASKS.runtime.jsonl');evals={x['task_id']:x for x in jl(a.joint_root/'source-bundle-v1/EVALSPEC.private.jsonl')}
joined={(x['task_id'],x['arm']):x for x in jl(a.analysis/'JOINED_ENDPOINTS_PRIVATE.jsonl')};responses={}
for n in range(1,7):
 for r in jl(a.joint_root/f'actual-v1/batch-{n:02d}/ACTUAL_RESPONSES_PRIVATE.jsonl'):responses[r['logical_id']]=r
arms=('STOP','MS','RS','MS_RS');groups={};public=[]
lines=['# J06 全24题四格实际输出与逐项开发审阅（私有）','含真实任务/源字段/模型输出与引用，不得发布到公共仓库。事实和支持是分工助手发展观察，不是独立人评。未知保留区间，正式reward均null。','近似语义的原partial观察和语境不确定sidecar并列；不覆盖原数据。整体因子交互和策略成本见公共聚合，不把resource供给或调用作为成功。','']
for index,t in enumerate(runtime,1):
 tid=t['task_id'];ev=evals[tid];owner=ev['source_binding']['owner_id'];groups.setdefault(owner,'G'+str(len(groups)+1).zfill(2))
 cell=dict(task_label='J'+str(index).zfill(2),source_group=groups[owner],stratum=ev['needs_stratum_private'],arms={})
 lines+=['## '+cell['task_label']+' / '+tid,'','**当前可见问题**：'+t['query'],'','**支持目标**：'+ev['support_goal'],'',
  '**原事实参考**：`'+json.dumps(ev['personal_fact_references'],ensure_ascii=False)+'`','',
  '**来源原句**：','> '+ev['source_binding']['exact_quote'],'',
  '**原requirements/prohibitions**：`'+json.dumps(dict(requirements=ev['requirements'],prohibitions=ev['prohibitions']),ensure_ascii=False)+'`','']
 for arm in arms:
  j=joined[(tid,arm)];r=responses[j['logical_id']];out=r['output'];support=j['support_review'];fact=j['fact_review']
  cell['arms'][arm]=dict(fact=j['fact_interval'],original_fact=j['original_fact_interval'],support=j['support_interval'],joint=j['joint_interval'],
   input_tokens=j['cost']['input_tokens'],output_tokens=j['cost']['output_tokens'],status=j['technical_status'])
  lines+=['### '+arm,'','**原始完整G输出（不清洗）**：','````text',out['text'] if out else '(未返回)','````','',
   '**三层区间**：fact `'+str(j['fact_interval'])+'`；support `'+str(j['support_interval'])+'`；joint `'+str(j['joint_interval'])+'`；原fact观察 `'+str(j['original_fact_interval'])+'`。','',
   '**事实逐原子**：`'+json.dumps(fact['fact_atoms'],ensure_ascii=False)+'`','',
   '**额外断言**：`'+json.dumps(fact['additional_claims'],ensure_ascii=False)+'`','',
   '**支持requirements**：`'+json.dumps(support['requirements'],ensure_ascii=False)+'`','',
   '**支持prohibitions（pass指遵守）**：`'+json.dumps(support['prohibitions'],ensure_ascii=False)+'`','',
   '**实际操作观察**：'+support['actual_operation'],'',
   '**语境解释sidecar**：`'+json.dumps(j['context_interpretation_disputes'],ensure_ascii=False)+'`','',
   '**身份**：`'+json.dumps({k:j[k] for k in ('logical_id','request_id','output_sha256','evalspec_sha256','endpoint_id')})+'`','',
   '**实际成本**：`'+json.dumps(j['cost'])+'`；formal_reward=null。','']
 public.append(cell)
write_bytes_once(a.out/'J06_FULL_REVIEW_PRIVATE.md',('\n'.join(lines)+'\n').encode())
write_json_once(a.out/'FOUR_ARM_CELLS_PUBLIC.json',dict(protocol='joint24-content-free-four-arm-cells-v1',tasks=public,
 no_questions_source_quotes_or_answer_values=True,source_groups=6,formal_reward_qualified=False))
print(json.dumps(dict(private_readback_sha256=file_sha256(a.out/'J06_FULL_REVIEW_PRIVATE.md'),public_cells_sha256=file_sha256(a.out/'FOUR_ARM_CELLS_PUBLIC.json'),tasks=24,outputs=96)))

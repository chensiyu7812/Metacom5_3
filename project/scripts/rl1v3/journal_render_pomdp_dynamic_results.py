#!/usr/bin/env python3
"""Render anonymous result tables; no private text or semantic relabeling."""
import argparse
import json
from pathlib import Path

ARMS=('STOP','FixedTop4Macro','LLMOneShot','LLMToolAgent','SequentialRule','SequentialNoText')
LABELS=('STOP','Top4','OneShot','ToolAgent','Rule','NoText')
STATUS={'complete':'完成','incomplete':'未完成','uncertain':'不确定'}

def seconds(value):
    return '—' if value is None else f'{value/1e9:.3f}'

def render(analysis,out):
    analysis,out=Path(analysis),Path(out)
    if out.exists():raise FileExistsError(out)
    rows=[json.loads(s) for s in (analysis/'TASKWISE_PUBLIC.jsonl').read_text().splitlines()]
    summary=json.loads((analysis/'SUMMARY_PUBLIC.json').read_text())
    by_key={(r['task'],r['method']):r for r in rows}
    tasks=list(dict.fromkeys(r['task'] for r in rows))
    def status(r):
        if r['technical_status']=='path_technical_failure':return '技术未完成'
        if r['technical_status']=='unexecuted':return '未执行'
        return STATUS.get(r['completion_status'],r['completion_status'])
    lines=['# DR1–DR4：完整逐题六臂结果与实际本地 Agent 时间','',
      '表中完成度是原合同下的助手开发观察，不是独立真人评价或正式 reward。',
      '“未完成”表示实际回复未完成任务；“不确定”是语义/要求范围未决；技术未完成与未执行没有语义分数。',
      '秒数是实际常驻模型、本地 Agent 入口至回复 ready；含实验守卫/日志，不含启动、网络、客户端和音频。',
      '没有完整回复的路径用“—”，不填 0。Tnn 与独立质量材料 Qnn 为同一任务的显示别名；实际连接用 task_id 和 SHA。','',
      '## 八题六臂；单元格为状态 / 实际 Agent 秒','',
      '|任务/通道|'+'|'.join(LABELS)+'|','|---|'+'|'.join(['---']*6)+'|']
    for t in tasks:
        first=by_key[t,ARMS[0]]
        cells=[status(by_key[t,m])+' / '+seconds(by_key[t,m]['agent_wall_ns']) for m in ARMS]
        lines.append('|'+t+(' / 事实' if first['channel']=='fact' else ' / 自然支持')+'|'+'|'.join(cells)+'|')
    lines+=['','## 48 槽逐项','',
      '“内容/必要”仅为与原参考相符的必要原子数；“原组/必要”是原证据群在实际输入中的完整供应数。二者都不等于任务成功。',
      '自然支持的历史复述需求为 0，以“—”显示；无终局的来源供应和原子完成保持未评。',
      '控制列为实际控制 start；获取列沿原计费语义，Top4 为 5 原语。输入/输出仅为终局 G tokens，全部控制调用另见 CALLS_PUBLIC.jsonl。','',
      '|任务|臂|任务状态|内容/必要|原组/必要|获取|控制|终局输入/输出|PM秒|守卫秒|G秒|worker首文字秒|Agent秒|',
      '|---|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|']
    for r in rows:
        known=r['completion_interval'] is not None
        required=r['required_fact_count']
        fact='—' if not required or not known else f"{r['required_fact_content_counts'].get('supported',0)}/{required}"
        source='—' if not required or r['original_evidence_groups_delivered'] is None else f"{r['original_evidence_groups_delivered']}/{required}"
        tok='—' if r['input_tokens'] is None else f"{r['input_tokens']}/{r['output_tokens']}"
        acq='—' if r['resource_accesses'] is None else str(r['resource_accesses'])
        fields=[r['task'],LABELS[ARMS.index(r['method'])],status(r),fact,source,acq,str(r['controller_starts']),tok]
        fields += [seconds(r[k]) for k in ('pm_ns','guard_ns','terminal_generation_ns','terminal_first_text_ns','agent_wall_ns')]
        lines.append('|'+'|'.join(fields)+'|')
    lines+=['','## 同一完整六臂集合的策略汇总','',
      '完整配对任务为 '+', '.join(summary['common_six_arm_tasks'])+'。T05仅两臂返回、T06无终局，均保留上表而不混入此比较分母。',
      'P50/P95为逐任务 nearest-rank；n=6 时 P95 就是最大值，不是稳定生产尾延迟。','',
      '|策略|任务完成开发区间 / 6|Agent总秒|P50秒|P95秒|PM总秒|',
      '|---|---:|---:|---:|---:|---:|']
    for arm,label in zip(ARMS,LABELS):
        d=summary['per_method_common_six_arm_tasks'][arm];v=d['completion_interval_observed']
        score=str(v[0]) if v[0]==v[1] else f'{v[0]}–{v[1]}'
        lines.append('|'+label+'|'+score+' / 6|'+'|'.join(seconds(d[k]) for k in ('agent_wall_sum_ns','agent_wall_p50_ns','agent_wall_p95_ns','pm_ns_sum_observed'))+'|')
    lines+=['','完整精度、逐题配对差、共同成功/失败/未知分层见 `QUALITY_LATENCY_TASKWISE_PUBLIC.jsonl`、`QUALITY_LATENCY_PAIRED_PUBLIC.jsonl` 和 `ANALYSIS_SUMMARY_PUBLIC.json`。',
      '阶段有包含关系，表中的PM、守卫、G时间不得直接相加；日志未独立计时。worker首文字可能是呈现标记，并非首段语义有效回复或客户端TTFT。','']
    out.write_text('\n'.join(lines))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--analysis',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();render(a.analysis,a.out)

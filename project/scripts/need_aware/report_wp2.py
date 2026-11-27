#!/usr/bin/env python3
"""Render only aggregate WP2 statistics; never read raw answers or histories."""
import argparse
import json
from pathlib import Path


def percent(x):
    return '—' if x is None else f'{100*x:.2f}%'


def interval(x):
    return '—' if x is None else '['+', '.join(percent(v) for v in x)+']'


def render(report):
    if not report.get('model_capability_result') or report['result_kind'] != 'model':
        raise ValueError('A model-results report cannot use plumbing data')
    lines = ['# WP2 冻结开发集实际模型统计', '',
             f"执行 manifest：`{report['manifest_sha256']}`。评价规则：`{report['evaluation_policy_sha256']}`。",
             f"封存终局：{report['snapshot_final']}；物理尝试：{report['physical_attempts']}。", '',
             'A 为近期历史窗口；B 为 dense user_only@8192；C 为离线定位的合法原文；D 为相同原文加状态投影与适用性指导。',
             '完成样本准确率包括解析失败；固定分母敏感性把技术未完成记为零成功，不把它们称为错误答案。结构性缺失不进入可评价分母。', '']
    for group, title, arms in [('all', '全部 240 题：仅 A/B 比较', 'AB'),
                               ('direct', '共同可评价 207 题：A/B/C/D', 'ABCD'),
                               ('direct_missing', 'Direct 缺失 33 题：仅 A/B', 'AB')]:
        lines += [f'## {title}', '', '| 模型/条件 | 预定 N | 完成 N（率） | 正确 | 错误/解析失败 | 技术未完成 | 完成准确率 | 固定分母敏感性 |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|']
        for model in ('G0e', 'Qwen35'):
            for arm in arms:
                s = report['cell_summaries'][model+'|'+arm][group]
                lines.append(f"| {model}/{arm} | {s['predefined_evaluable']} | {s['completed']}（{percent(s['completion_rate'])}） | {s['correct']} | {s['valid_wrong']}/{s['parse_failures']} | {s['technical_uncompleted']} | {percent(s['accuracy_on_completed'])} | {percent(s['fixed_denominator_success_sensitivity'])} |")
        lines.append('')
    lines += ['## 预定配对比较', '', '差异为右减左；完整配对使用双方均完成的相同任务。区间为 persona 聚类 bootstrap 95% 描述性区间；p 值对固定 8 组做 Holm 校正。', '',
              '| 任务集/左→右 | 预定/完整配对 | 修复/退步 | 配对差异 | 95% CI | Holm p | 固定分母差异敏感性 |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for s in report['primary_paired']:
        p = '—' if s['mcnemar_p_holm_8'] is None else f"{s['mcnemar_p_holm_8']:.4g}"
        lines.append(f"| {s['population']}/{s['left'].replace('|','/')}→{s['right'].replace('|','/')} | {s['predefined_evaluable_pairs']}/{s['complete_pairs']} | {s['repairs']}/{s['regressions']} | {percent(s['paired_difference'])} | {interval(s['ci95'])} | {p} | {percent(s['fixed_denominator_difference_sensitivity'])} |")
    lines += ['', '## 代表性与困难层', '', '180 题代表性层与 60 题困难层分别呈现；困难混合比例不是自然发生率。每层先报 A/B 全集，再报四臂共同可评价的 Direct 子集，仅在同一任务集内比较。', '',
              '| 模型/条件/层 | 可评价 N | 完成 N | 正确 | 完成准确率 | 固定分母敏感性 |', '|---|---:|---:|---:|---:|---:|']
    for group, arms in [('representative', 'AB'), ('hard', 'AB'), ('direct/representative', 'ABCD'), ('direct/hard', 'ABCD')]:
        for model in ('G0e', 'Qwen35'):
            for arm in arms:
                s = report['cell_summaries'][model+'|'+arm][group]
                lines.append(f"| {model}/{arm}/{group} | {s['predefined_evaluable']} | {s['completed']} | {s['correct']} | {percent(s['accuracy_on_completed'])} | {percent(s['fixed_denominator_success_sensitivity'])} |")
    lines += ['', '## 技术完整性与范围', '', '| 模型/条件 | 技术失败分类 | 长度停止 | EOS 完成 N/准确率 |', '|---|---|---:|---:|']
    for key, groups in report['cell_summaries'].items():
        s = groups['all']
        fail = ', '.join(f'{k}:{v}' for k, v in s['failures'].items()) or '0'
        lines.append(f"| {key.replace('|','/')} | {fail} | {s['length_stops']} | {s['eos_only_completed']}/{percent(s['eos_only_accuracy'])} |")
    lines += ['', 'Direct 缺失的 33 题包括 31 个 sensitive 与 2 个 forget，属于非随机缺失；C/D 对 sensitive 的能力没有测量。',
              'B 的用户陈述覆盖不能代替完整参考证据覆盖。C→D 只解释为状态投影与使用指导的联合增量。官方题面要求回忆偏好，因此本轮不证明自主需求识别、自然陪伴或开放生成质量。',
              '完整类别、四臂/八单元共同完成集合、缺失界限、覆盖归因和配对敏感性见对应 aggregate.json。WP3 决策须结合真实错误审阅，不由本渲染器自动决定。', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--aggregate', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    Path(a.out).write_text(render(json.loads(Path(a.aggregate).read_text())))

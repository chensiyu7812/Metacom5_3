#!/usr/bin/env python3
"""Read-only history replay + offline candidate artifacts; deliberately no live mode.

Writes a NEW private output directory once. Repeated invocation verifies the same
receipt instead of replacing records. Uses the existing parser and receipt engine.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.rl1 import feedback_score_audit as candidate
from metacom_pm.rl1 import feedback_source_evidence as original, feedback_workflow as workflow
from metacom_pm.rl1 import relation_reference as r

BASE = PROJECT / 'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
SOURCE = BASE / 'feedback_source_evidence_results_20261022_v2'
OUTPUT = BASE / 'feedback_score_audit_offline_20261022_v1'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x', encoding='utf-8') as f:
        f.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def verify(path):
    receipt = r.read(path / 'RECEIPT.json')
    for group in ('input_hashes', 'artifact_hashes'):
        for name, expected in receipt[group].items():
            if r.sha(name) != expected:
                raise ValueError('immutable offline artifact/history changed: ' + name)
    return dict(status='VERIFIED_EXISTING_OFFLINE_RESULT', new_calls=0,
                cumulative=receipt['cumulative'], artifact=str(path))


def build(output):
    if output.exists():
        return verify(output)
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location('preserved_feedback_launcher', PROJECT / 'scripts/rl1/121_continue_feedback_source_evidence.py')
    entry = importlib.util.module_from_spec(spec); spec.loader.exec_module(entry)
    pr, items, _ = entry.load()
    paired = entry.original.engine()
    actual = original.summary(pr, Path(pr['run_dir']), paired)
    saved = r.read(SOURCE / 'ALL_SLOTS.json')
    if actual != saved:
        raise ValueError('closed report no longer matches actual receipt replay')
    provenance = r.read(SOURCE / 'RAW_PROVENANCE.json')
    for name, expected in provenance.items():
        if r.sha(name) != expected:
            raise ValueError('original raw or STOP modified: ' + name)
    starts = {str(p): r.sha(p) for name in workflow.RUN_ROOTS for p in (BASE / name).rglob('*.started.json')
              if 'management' not in p.parts}
    cost = r.read(SOURCE / 'VALIDATION_AND_COST.json')
    ledger = PROJECT / 'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    if len(starts) + 66 != 302 or r.sha(ledger) != cost['ledger_sha256']:
        raise ValueError('actual attempts or financial baseline changed; no stale replay')
    input_paths = [Path(__file__), PROJECT / 'src/metacom_pm/rl1/feedback_score_audit.py',
                   PROJECT / 'tests/test_rl1_feedback_score_audit.py', ledger,
                   entry.PREP / 'protocol.json', SOURCE / 'ALL_SLOTS.json',
                   SOURCE / 'ORIGINAL_INPUTS.json', SOURCE / 'VALIDATION_AND_COST.json',
                   SOURCE / 'SOURCE_REVIEW.json', SOURCE / 'RAW_PROVENANCE.json']
    input_hashes = provenance | starts | pr['immutable_files'] | {str(p): r.sha(p) for p in input_paths}
    rows = []
    for joint_slot in (s for s in actual['slots'] if s['component'] == 'joint'):
        key = joint_slot['item_key']
        audit_slot = next(s for s in actual['slots'] if s['item_key'] == key and s['component'] == 'audit')
        repair_slot = next(s for s in actual['slots'] if s['item_key'] == key and s['component'] == 'repair')
        j, a = joint_slot['result'], audit_slot['result']
        valid = j['technical_valid'] and a['technical_valid']
        score = j['evaluation']['value']
        je = j['evaluation']
        associations = candidate.association_candidates(score, a['evaluation']['value']) if valid else []
        rows.append(dict(item_key=key, original_joint_request=j['request_identity'],
            original_audit_request=a['request_identity'], joint_slot=joint_slot['slot_id'],
            audit_slot=audit_slot['slot_id'], reply_identity=joint_slot['reply_identity'],
            evidence_identity=joint_slot['evidence_identity'], original_audit_technical_valid=a['technical_valid'],
            original_trigger=workflow.flagged(j, a) if valid else None,
            original_score={k: je[k] for k in ('q', 'm', 'U', 'model_unknown')},
            original_repair_status=repair_slot['status'],
            candidate_route_without_inventing_fields=candidate.decision(j, a),
            mechanical_associations_only=associations,
            original_q_rationale=score['q_rationale'],
            original_audit_findings=a['evaluation']['value']['findings'] if valid else None))
        # These payloads are interface inspection samples, NOT a planned live
        # schedule or queued requests. No human review or other arm is added.
        messages, schema = candidate.audit_payload(items[key], score, paired)
        screen = paired.input_guard(messages)
        write(output / 'interface_examples' / (key + '.json'), dict(
            status='OFFLINE_EXAMPLE_NOT_A_REQUEST', interface=candidate.INTERFACE,
            item_key=key, messages=messages, schema=schema, native_input_screen=screen))
    write(output / 'REPLAY.json', dict(version=candidate.VERSION, author='mechanical replay; no new semantic labels',
        original_protocol=pr['identity'], endpoints=rows, original_slots=actual['slots'],
        original_pairs=actual['paired'], original_endpoints=actual['endpoints'],
        candidate_routes=dict(Counter(x['candidate_route_without_inventing_fields']['action'] for x in rows)),
        new_calls=0, qualification_granted=False))
    components = defaultdict(lambda: dict(calls=0, cost=Decimal(0), seconds=0.0))
    for slot in actual['slots']:
        if not slot.get('result'): continue
        r0 = slot['result']; part = components[slot['component']]
        part['calls'] += 1
        part['cost'] += Decimal(r0['financial']['accounted_upper_usd'])
        part['seconds'] += r0['elapsed_seconds']
    breakdown = {k: dict(v, cost=str(v['cost'])) for k, v in components.items()}
    repair = next(s['result'] for s in actual['slots'] if s['component'] == 'repair' and s.get('result'))
    total = sum((v['cost'] for v in components.values()), Decimal(0))
    arithmetic = dict(actual_cost_by_component=breakdown,
        original_stage_usd=str(total), audit_cost_share=float(components['audit']['cost'] / total),
        unchanged_repair_usd=repair['financial']['accounted_upper_usd'],
        unchanged_repair_seconds=repair['elapsed_seconds'],
        repair_share=float(components['repair']['cost'] / total), actual_savings_usd='0',
        caveat='Avoiding this repair is only a counterfactual; unchanged output does not prove its ex ante uselessness. New audit overhead is unknown.',
        cumulative=302, capacity=369, trial_accounted_usd=cost['trial_accounted_usd'],
        known_unsettled_usd='0', new_calls=0, new_cost_usd='0', natural_updates=0)
    write(output / 'COST.json', arithmetic)
    write(output / 'CANDIDATE_POLICY.json', dict(version=candidate.VERSION, interface=candidate.INTERFACE,
        status='OFFLINE_IMPLEMENTED_NOT_ENABLED', policy=candidate.POLICY,
        substantive_change='Explicit linkage from reply findings to preliminary score defects; not a q/m rubric amendment.',
        historical_slots_replayed_not_rescored=24, no_new_execution_schedule=True,
        activation_requires_new_specific_authorization=True,
        not_authorized=['API', 'account query', 'credentials', 'generation', 'human task', 'PPO', 'C', 'freeze']))
    write(output / 'AUDIT_ADDITION_EN.txt', candidate.ADDITION)
    write(output / 'ORIGINAL_INPUTS.json', items)
    for name in ('sources', 'finals'):
        shutil.copytree(SOURCE / name, output / name)
    # A quoted comparison, not a filled model review and not a human gold label.
    focus = next(x for x in rows if x['item_key'] == 'V3_OFF')
    write(output / 'ANALYST_COMPARISON.json', dict(author='Codex, not independent human review',
        status='analyst interpretation; NOT a model score_review', item_key='V3_OFF',
        source_joint_request=focus['original_joint_request'], source_audit_request=focus['original_audit_request'],
        preliminary_q_rationale=focus['original_q_rationale'], audit_findings=focus['original_audit_findings'],
        candidate_associations=focus['mechanical_associations_only'],
        observation='Initial score explicitly recognized the unsupported home location and called it localized; audit repeated that defect and said core empathy remained intact. Repair retained q3/m.25.',
        unresolved='Whether q3 and m.25 are independently sufficiently justified is not certified by this agreement. Same-unit/source overlap alone cannot answer it.',
        auto_decision_filled=False, new_human_label=False))
    table = '\n'.join('| ' + ' | '.join([x['item_key'], str(x['original_score']['q']),
        str(x['original_score']['m']), '无效' if not x['original_audit_technical_valid'] else '有效',
        '缺测' if x['original_trigger'] is None else '触发' if x['original_trigger'] else '未触发',
        '旧技术失败保持' if not x['original_audit_technical_valid'] else '缺少显式评分关联，不倒填']) + ' |' for x in rows)
    report = f'''# PM-RL1：评分审查触发的离线修正

结论：原补核条件把“回复错误”和“初评分错”混在了一起，存在可以消除的重复评分。但本批只提供一条可能的重复补核证据，不能据此宣布自动审查已可靠，或用“少调用”替代测量验证。

## 做了什么

新增独立候选 `{candidate.INTERFACE}`。完整回复、完整合法来源、原初评分仍交给同一个审查接口，`findings.source_evidence` 保持。新增明确的评分关联：每条发现引用原评分的路径和原文，说明已处理、漏判/冲突或未决；另外检查 q 依据、严重度和覆盖。回复存在已处理的错误本身不再自动要求补核，但任何评分缺口、严重度/质量未决和模型 unknown 都保留。技术/绑定故障仍停。

这是新的审查任务与派发候选，尚未启用；不是旧提示未变的“纯改字段”。原联合提示、q/m/U、来源、旧 parser、旧 STOP、训练缓存与账本没改。新模块没有真实派发入口，也不能授予奖励资格。

## 八终点的原记录与回放

| 终点 | q | m | 原审查 | 原补核触发 | 新接口离线可确定什么 |
|---|---:|---:|---|---|---|
{table}

17次原请求、24逻辑槽全部保留；7份有效审查都没有新增的显式评分关联，1份旧技术失败仍失败。没有补造7份新接口“成功”，也没有倒改原来3/4完整配对的候选状态。8终点仅7份不同完整输入，4个已暴露来源情境，不是8个独立新样本。

V3_OFF 初评已写明：“The phrase 'recent changes at home (like Lily leaving)' implies Lily's move is a change at home”，并指出来源没有确认家庭成员/居家变化，记为 unsupported、.25；q理由也已提到这个缺陷。审查再次指出相同位置问题，且写“core empathic summary remains intact”。旧条件看到 identified_error 就派发，补核仍 q3/m.25/U.5。完整对照见 ANALYST_COMPARISON.json；这段解释属于分析者复核，不是新增人评或模型自动判据。

同一个 R002 内同时有“主要压力归纳获支持”和“家庭位置缺依据”两条初评。只看 R002 与来源重合会把它们混为一谈，因此程序只列候选关联，不自动认定已充分处理。q3是否应为q4、.25严重度是否充分，仍须分开判断。

其他边界保留：V2_OFF 的 how-effects 问句仍有解释边界，不能凭本批单一开放探询读法宣布唯一正确；V2_ON旧无效审查不能复活。V4两侧输入完全相同、分数一致，但审查粒度不同；这既不算资源收益，也不自动构成错误。模型 unknown 与分析者争议分别记录。

## 经济意义和限制

原阶段总账 ${total}：初评8次 ${breakdown['joint']['cost']}，审查8次 ${breakdown['audit']['cost']}，补核1次 ${breakdown['repair']['cost']}。审查占 {100*arithmetic['audit_cost_share']:.2f}%；这一次补核占 {100*arithmetic['repair_share']:.2f}%，耗时 {arithmetic['unchanged_repair_seconds']:.3f} 秒。

即使未来能正确避免同类补核，也只是这批约5%的潜在节约；原款项已发生，本次实际节省为0。补核未改分不证明事前毫无信息价值。新审查增加少量输出结构，其真实开销尚未测得。最大的费用仍是全量第二次审查，不能把修触发包装成完整研究预算已解决。

## 下一步的具体选择

优先把“审查是否发现初评分的具体缺陷”作为要验证的机制，停止以“回复有瑕疵”作为自动再评分理由。离线代码已能检验：已处理缺陷可保留；真正漏判、严重度无依据、q依据冲突或 unknown 不能被同一来源ID遮掉。

真实验证还缺一项证据：模型能否自己填写正确的评分关联，并同时区分已处理问题与真实初评错误。旧输出没有这个字段，不能用离线添加答案冒充自动效果。后续若申请验证，应同时包含已处理、未处理、正常探询和未决边界，按已有来源暴露记录报告；不再只拿这批未发现新增纠错机会的8终点刷一次“成功率”。先看漏判/误触发和覆盖，再看完整费用；不以大量拒判或更少补核单独判赢。本次未安排新付费清单或新增问卷。

四头顺序获取、BC真实起点、OFF/FixedDev/匹配随机/OneShot/BC-union/PPO/NoText、多种子及独立终评不变。这是奖励管线的一项具体修正候选，不替代其余研究。完整研究单评敏感性约$26.79/$39.13、等均价审查敏感性约$51.79/$76.48仍为旧未精确去重估算；本批审查更贵，不承诺装进共享$20。

本轮新增请求/费用/生成/人评/自然更新均为0；实际仍302/369，API试验及共享后续账${cost['trial_accounted_usd']}、未结0。原阶段CLOSED及未用3次不转为新授权。

复算入口：122_replay_score_audit.py（仅离线）。RECEIPT.json绑定原始回执、代码、账本和产物；重复执行只验证，不覆盖，不生成请求或APPROVED。测试记录另附 OFFLINE_TESTS.txt。
'''
    write(output / 'REPORT_ZH.md', report)
    for name, expected in input_hashes.items():
        if r.sha(name) != expected: raise ValueError('history changed during offline replay: ' + name)
    receipt = dict(version=candidate.VERSION, created_utc=datetime.now(timezone.utc).isoformat(),
        status='OFFLINE_COMPLETE_NOT_ENABLED', cumulative=302, new_calls=0, new_cost_usd='0',
        original_protocol_identity=pr['identity'], input_hashes=input_hashes,
        artifact_hashes={str(p): r.sha(p) for p in output.rglob('*') if p.is_file()},
        live_authorized=False, reward_eligible=False)
    receipt['identity'] = r.digest(receipt)
    write(output / 'RECEIPT.json', receipt)
    return dict(status=receipt['status'], identity=receipt['identity'], new_calls=0, cumulative=302,
                artifact=str(output), candidate_routes=Counter(x['candidate_route_without_inventing_fields']['action'] for x in rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), ensure_ascii=False, indent=2))

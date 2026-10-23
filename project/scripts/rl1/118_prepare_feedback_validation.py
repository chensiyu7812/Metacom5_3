#!/usr/bin/env python3
"""Freeze already-selected validation inputs and runnable dependency protocol.

Offline preparation only. No new selection, score, credential, account query,
authorization, amendment activation or human answer is created here.
"""
import argparse
from datetime import datetime,timezone
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import json
import os
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1 import feedback_workflow as w, paired_dependencies as d, relation_reference as r
BASE=PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
SOURCE=BASE/'feedback_prototype_20261022_v5/validation'
OUT=BASE/'feedback_validation_preparation_20261022_v2'


def prepare(out):
    out.mkdir(mode=0o700)  # Exclusive: previous engineering preparations remain intact.
    old=r.read(BASE/'task_reference_preparation_20261021_v1/protocol.json')
    sys.path.insert(0,str(BASE/'paired_diagnostic_20261019_v1'))
    import paired as p
    files={}
    for name in ('inputs_private.json','MATERIALS.json','SCHEDULE.json','JOINT_PROMPT_EN.txt',
                 'AUDIT_PROMPT_EN.txt','REPAIR_ADDITION_EN.txt','SELECTION_BEFORE_REPLY_READ.json'):
        origin=SOURCE/name;target=out/name
        with target.open('xb') as handle:handle.write(origin.read_bytes())
        target.chmod(0o600);files[str(origin)]=r.sha(origin);files[str(target)]=r.sha(target)
    items=r.read(out/'inputs_private.json');rows=w.schedule(r.read(out/'SCHEDULE.json')['fixed'],items)
    groups=defaultdict(list)
    for key,item in items.items():groups[r.digest(item)].append(key)
    count_audit=dict(planned_endpoints=len(items),unique_full_inputs=len(groups),
        identical_input_groups=[keys for keys in groups.values() if len(keys)>1],
        original_manifest_unique_replies_field='counts planned endpoints; retained unchanged as historical provenance',
        no_reselection=True,planned_requests_not_cache_merged=True,
        identical_pair_interpretation='no reply-content gain can be inferred from score variation; resource cost remains distinct')
    r.save_new(out/'MATERIAL_COUNT_AUDIT.json',count_audit);files[str(out/'MATERIAL_COUNT_AUDIT.json')]=r.sha(out/'MATERIAL_COUNT_AUDIT.json')
    for binding in r.read(out/'MATERIALS.json')['bindings']:
        source=binding['generation_source']
        for field in ('request','raw'):
            path=source[field+'_path'];expected=source[field+'_sha256']
            if r.sha(path)!=expected:raise ValueError('selected original generation binding changed')
            files[path]=expected
    starts={str(path):r.sha(path) for name in w.RUN_ROOTS for path in (BASE/name).rglob('*.started.json') if 'management' not in path.parts}
    if 66+len(starts)!=285:raise ValueError('actual baseline changed')
    stops={str(path):r.sha(path) for name in w.RUN_ROOTS for path in (BASE/name).rglob('STOP.json')}
    fin=dict(old['financial_baseline']);ledger=Path(fin['ledger_path'])
    budget=p.DiagnosticBudget(ledger,trial=fin['financial_trial_identity'],study=w.VERSION,stage_cap=p.s.nanodollars(2),
        trial_cap=p.s.nanodollars('3.15'),shared_cap=p.s.nanodollars(20),baseline=p.s.nanodollars('1.50724291'),opening=p.s.nanodollars('.03079930'))
    total,trial,reserved,settled=budget._totals(budget.events())
    if set(reserved)-set(settled):raise ValueError('existing unresolved financial responsibility')
    fin.update(ledger_sha256=r.sha(ledger),ledger_bytes=ledger.stat().st_size,trial_accounted_usd=p.s.usd(trial),
               shared_total_usd=p.s.usd(total),shared_followup_usd=p.s.usd(total-budget.baseline),known_unsettled=0)
    if fin['trial_accounted_usd']!='1.602273':raise ValueError('financial baseline changed')
    # Preserve all old implementation identities; no old data or prompts are rewritten.
    for path,h in old['immutable_files'].items():
        if path.endswith('.py'):
            if r.sha(path)!=h:raise ValueError('old engine changed')
            files[path]=h
    for relative in ('src/metacom_pm/rl1/feedback_prototype.py','src/metacom_pm/rl1/feedback_workflow.py',
                     'src/metacom_pm/rl1/paired_dependencies.py','scripts/rl1/118_prepare_feedback_validation.py',
                     'scripts/rl1/119_run_feedback_validation.py','tests/test_rl1_feedback_workflow.py'):
        path=PROJECT/relative;files[str(path)]=r.sha(path)
    config=dict(old['config'],wrapper='full original source + same-endpoint new machine score/audit; dependency interface v1')
    approval=dict(study=w.VERSION,baseline_cumulative=285,new_request_limit=20,cumulative_cap=305,capacity=369,
        stage_cap_usd='2',trial_cap_usd='3.65',shared_cap_usd='20',old_stops_released=False,reward_eligible=False,
        diagnostic_policy=w.POLICY,official_research_payload_authorized=True,
        same_stage_machine_score_audit_outbound_authorized=True,manual_reference_outbound_authorized=False,
        credential_process_read_authorized=True,management_requests={'models':1,'user/balance':1},
        natural_updates_authorized=False,new_generation_authorized=False,no_automatic_retries=True,
        local_review_proposed_max_items=12,local_review_proposed_max_minutes=120,
        local_review_dispatch_authorized=False)
    rules=dict(development_candidate_pairs_min=3,planned_pairs=4,repair_evidence_on_distinct_sources_required=True,
        no_new_confirmed_error_released_as_valid_feedback=True,zero_overall_error_claim=False,
        baseline_ceiling='report unable to distinguish; no extra samples',single_context_repair='local mechanism evidence only',
        review_time_cap_minutes=120,review_dispatch_authorized=False,model_or_analyst_not_independent_gold=True,
        systematic_check_failures='locate relationship supervision gap',valid_relation_bad_score='locate mapping/ambiguity policy',
        mixed_or_missing='show all tradeoffs and missing; no winner',after_close='stop; no C/freeze/training automatically')
    pr=dict(version=w.VERSION,dispatch_version=d.VERSION,status='PREPARED_PENDING_EXPLICIT_APPROVAL',
        prepared_utc=datetime.now(timezone.utc).isoformat(),run_dir=str(BASE/'feedback_validation_runs'/w.VERSION/'live'),
        activation_file=str(BASE/'feedback_validation_authorization_20261022_v1/activation.json'),
        original_schedule=str(SOURCE/'SCHEDULE.json'),schedule=rows,config=config,financial_baseline=fin,
        public_price_table_identity=old['public_price_table_identity'],immutable_files=files,
        historical_started_hashes=starts,old_stop_hashes=stops,approval_required=approval,analysis_rules=rules,
        contexts=r.read(out/'MATERIALS.json')['contexts'],material_count_audit=count_audit,
        limits=dict(max_calls=20,cumulative_cap=305,active_capacity=349,proposed_capacity=369,
            active_trial_usd='3.15',stage_usd='2',trial_usd='3.65',shared_usd='20',native_single_reserve_usd='.786432',
            fixed_calls=16,supplemental_max=4,logical_slots=24,new_generation=0,natural_updates=0),
        semantics=dict(initial_score_reused_as_baseline=True,independent_arms=False,final_usable_U_requires_local_evidence_review=True,
            no_average_or_minimum_reward=True,unknown_is_null=True,final_evaluation=False,
            different_owners_from_old_task_reference=True,independent_fact_families_certified=False,
            automatic_error_detection_unverified=True,old_stop_release=False))
    pr['identity']=r.digest(pr)
    r.save_new(out/'protocol.json',pr)
    r.save_new(out/'PENDING_EXECUTION_SCOPE.json',dict(status='PENDING',protocol_identity=pr['identity'],**approval))
    r.save_new(out/'PROPOSED_AMENDMENT_NOT_APPLIED.json',dict(applied=False,protocol_identity=pr['identity'],
        old_capacity=349,proposed_capacity=369,old_trial_usd='3.15',proposed_trial_usd='3.65',
        execution_authorized=False,capacity_rationale='305 stage maximum + 59 acceptance + 4 recovery + 1 reserve; none of those future calls authorized'))
    r.save_new(out/'budget.json',dict(financial_baseline=fin,stage_cap_usd='2',proposed_trial_usd='3.65',
        shared_usd='20',native_reserve_usd='.786432',native_sum_for_twenty='15.728640',
        latest_joint_mean_usd='.00803585625',twenty_at_old_joint_mean_usd='.160717125',
        long_audit_and_supplement_cost='unknown; historical joint mean is not a forecast guarantee',
        max_prior_settled_for_next_stage_call_usd='1.213568',
        effective_new_trial_headroom_usd=str(Decimal('3.65')-Decimal(fin['trial_accounted_usd'])),
        stage_can_end_early=True,capacity_is_not_execution_approval=True))
    text=f'''# 有限用途反馈验证：一次启动范围（待批）

协议：{w.VERSION}；身份：{pr['identity']}。
本包已经完成离线实现，不代表执行批准。当前285/349，API试验已记账$1.602273，未结责任0。

固定4个既有train来源组、8个OFF/ON终点，RS/MP/MS/ME各一对。只有7份不同完整输入：V4_ME的OFF/ON回复及来源相同。
两槽仍独立派发、保留资源成本差；分数差不能解释成内容改善，不缓存合并、不选新题替换。旧清单unique_replies=8按终点数记录的口径另作纠正说明。
选取与原始绑定沿用v5；不新生成，不读封存。
按原轮换顺序做8次联合初评、8次自动审查；初评也是比较基线，不另付8次。
若模型unknown、审查关系uncertain或发现未决/错误，按固定初评顺序最多补核4条，每条一次。
故24个可追踪逻辑槽（含8个条件槽），真实请求最多20次，累计硬停305。未触发/额度未覆盖的补核另记，不填0。

请求确认的新增费用及未结责任上限$2，API试验累计线3.15→3.65，容量349→369，共享$20不变。
每条原生预留$0.786432，已结算阶段支出超过$1.213568即放不下下一条；不保证跑满20次。
$0.160717125只是按旧联合评分均价乘20的量级，审查/补核更长，不能据此承诺费用。

接收方仍为DeepSeek官方Flash/high。启动时只读核验公开映射/价格，GET /models和/user/balance各一次；
进程内读取指定env的DEEPSEEK_API_KEY，不持久保存。旧服务映射V4.1-Flash-1017必须重新确认，别名不是权重锁。
外传：原合法来源、回复、稳定ID及固定提示；审查增加同条本轮preliminary_score完整final，补核再增加同条machine_audit完整final。
这些是可能出错的机器材料，不是来源。字段示意：{{"preliminary_score":{{"status":"scored","q":"本轮原值","assessments":"本轮原项"}},"machine_audit":{{"check":"本轮核查","findings":"本轮理由"}}}}。
不发送人工答案、人工参照、分析者复核、历史其他候选输出、预期赢家、封存材料或密钥。

语义错误/复核歧义记为结果并继续，模型unknown缺测；技术/来源绑定/服务漂移/截断/usage责任不明硬停。
新规则仅适用于本诊断，旧STOP不解除。无自动重试；已开始无完整回执不重发。
只有完整封存且结算的请求边界可以从下一未开始槽接续；管理请求不重复。
补核得出数字仍是提案，不自动变成正确奖励。整批无PPO更新，原始分数不覆盖。

本地复核提案最多8条初始+4条补核、120分钟，以已有来源和独立作答身份分别记录；本包不派发人评。
尚未落实独立人类核验，不把分析者或机器同意算金标。是否安排这部分工作可以在真实结果后集中决定。

判读依次为：技术/来源合法、关系与读法核查、后果和q依据、数值覆盖、OFF净收益/排序/幅度、费用。
沿用已提出的开发推进底线（仍待批）：至少3/4配对在上限内获得可辩护候选；在不同来源有具体修复；无新增已证实错误被作为有效反馈。
这不是零总体误差资格门槛。只修好一处仅报局部机制；初评全对则无法判别增益，不追加抽样。
混合结果：记录修复与新错/拒判/幅度变化，不选净分数赢家。
失败出口：自动审查漏检/误指控则定位核查；正确核查后分级依据仍不成立则定位评分映射；合理双读则研究数值处置。
覆盖太少或基线已正确可判无法区分，不追加抽样。本轮不赋资格、不启用奖励或训练、不启动C或微调。

完整研究仍保留四头顺序获取、BC真实起点、OneShot/NoText等比较及多种子独立评价。
原完整研究成本估算单评约$26.60/$38.94，若普遍双调用约$51.60/$76.29；本包没有批准或削减那些规模，也不承诺装进$20。
80J/44G/$3、旧容量369/累计$4.25随机32诊断提案仍被搁置；本包369是新提案，不继承旧授权。

离线入口：119_run_feedback_validation.py --check；真实入口：--live --approval 明确批准文件。
只能在收到真实启动指令后另存授权及启用对应额度修订。本包只有PENDING及applied=false。
'''
    with (out/'START_REQUEST_ZH.md').open('x') as handle:handle.write(text)
    return dict(preparation=str(out),identity=pr['identity'],status=pr['status'],new_model_calls=0,credentials_read=False)


if __name__=='__main__':
    os.umask(0o077);ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=OUT)
    print(json.dumps(prepare(ap.parse_args().out),ensure_ascii=False,indent=2))

#!/usr/bin/env python3
"""Close out completed pilot artifacts, cost, provenance and technical limits."""
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
OUT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'
DATA=PROJECT/'outputs/pm_rl1/source_and_capacity_20260928_v1'


def read(p):return json.loads(p.read_text())


def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


def main():
    a=read(OUT/'measurement_analysis.json');v=read(OUT/'typographic_parser_v2/analysis.json');cost=read(OUT/'measured_cost_update.json')
    ip=read(OUT/'indexed_transport_smoke_pointer.json');irun=Path(ip['run_dir']);it=read(irun/'summary.json')
    assert sha256_file(irun/'summary.json')==ip['summary_sha256'] and len(it['rows'])==5
    old=read(Path('/home/tokkio/PM_RL1_接手审计_20260928/repository_snapshot.json'))['dirty_file_sha256']
    changed=[f for f,h in old.items() if sha256_file(PROJECT.parent/f)!=h]
    assert not changed
    assert sha256_file(Path('/home/tokkio/PM_RL1_单轮资源选择与执行_环境及训练实施方案_20260928.md'))=='7888613fac3a0820db2be012d9f85b59eb0dbb0a22d373a68eaaa3b6acb94a6b'
    tree=ET.parse(OUT/'validation/tests.xml');suites=list(tree.getroot().iter('testsuite'))
    tests=sum(int(s.get('tests','0')) for s in suites);fails=sum(int(s.get('failures','0'))+int(s.get('errors','0')) for s in suites)
    assert fails==0
    assert read(OUT/'validation/review_form_browser_test.json')['test_values_removed']
    for runtime_path in list((OUT/'judge').glob('*/runtime.json'))+list((OUT/'indexed_transport_smoke').glob('*/runtime.json')):
        r=read(runtime_path)
        # Runner/model identities are preserved, including unsuccessful startup.
        assert r['output_token_cap'] is None and r['serving_context']==r['native_context']
    genp=read(OUT/'generation_pointer.json');grun=Path(genp['run_dir']);gs=read(grun/'summary.json');assert len(gs['rows'])==24
    missing=read(OUT/'coordinator_only/controls_and_missing.json')['missing']
    indexed_counts=dict(Counter(r['measurement_status'] for r in it['rows']))
    review_copy=Path('/home/tokkio/PM_RL1_独立盲评卷_20260928.html')
    if review_copy.exists() and sha256_file(review_copy)!=sha256_file(OUT/'independent_review.html'):
        raise RuntimeError('home review copy already differs; preserve it')
    shutil.copyfile(OUT/'independent_review.html',review_copy)
    for src,name in [('/tmp/rl1_joint_measurement_numeric.log','judge_v1.log'),('/tmp/rl1_indexed_smoke.log','indexed_transport_smoke.log'),
                     ('/tmp/rl1_pilot_prepare.log','pilot_prepare.log'),('/tmp/rl1_pilot_generation.log','pilot_generation.log'),('/tmp/rl1_capacity_full.log','full_capacity.log')]:
        f=Path(src)
        if f.exists():shutil.copyfile(f,OUT/'technical_attempts'/name)
    valid=a['measurement_status_counts'].get('measured_candidate',0);valid2=v['status_counts'].get('measured_candidate',0)
    rows=[]
    for condition,name in [('OFF','真实 OFF'),('ON','真实 ON'),('damage','单点损伤'),('style','轻量风格')]:
        d=a['distributions'][condition]
        normalized=[r for r in v['rows'] if r['condition']==condition and r['repeat']==0]
        rows.append(f"| {name} | {d['total']} | {d['status_counts'].get('measured_candidate',0)} | {sum(r['q'] is not None for r in normalized)} |")
    t=v['repeat'];changed_repeats=sum(r['delta_q']!=0 or r['delta_m']!=0 for r in t['rows'])
    penalty_disagreement=t['abs_utility_delta_gt_full_resource_penalty']
    transport_valid=indexed_counts.get('measured_candidate',0)
    cond_rates=cost['combined_34_pair_scenarios']
    expected=[r['batch_usd'] for r in cond_rates if r['assumed_output_per_pair'] in (512,1024)]
    native=[r['batch_usd'] for r in cond_rates if r['assumed_output_per_pair']==16384]
    g=a['generation'];jc=a['judge_compute'];freeze=read(DATA/'dataset_freeze.json')
    report=f'''# PM-RL1：首轮测量试跑、来源冻结与后续推进

本轮已完成真实回复生成、首轮联合评分、重复测量、失败归因及新接口技术检查。**现有 J 仍不能冻结为正式训练奖励。** 已经有新的考卷、候选评分标准、完整合法评审证据和可填写的独立复核表；尚无返回的独立复核答卷，不能写成“新裁判已通过 A/B 人评”。

**实际完成的工作。** 固定 12 个 train owners 各一条前缀后，每题生成 OFF 与预先指定的一个头的 Top-1 ON；RS/MP/MS/ME 各 3 题，B=2048，12 个 ON 均合法。共得到 24 条真实回复，23 次新增生成、1 次完全一致的既有缓存命中；24 条均自然结束，输出 token 范围 {g['output_tokens']['min']}–{g['output_tokens']['max']}。没有沿用 60/256 的任务输出上限。该小卷不证明资源有效，也没有训练 LoRA 或 PM。

损伤控制只在实际 OFF 有合适可查证断言时做一个事实修改，保留原文、改动区间及来源。可构造 9 条，另 3 条保留不适用；风格控制 12 条，只展开缩写并调整断句，不增添事实/建议/确定性。由此实际为 45 个回复评分，加 10 个预选的不同随机 seed 重测，共 55 次。2 个预选重测因条件缺失而没有替换。独立复核实际 10 对，原定另 2 对损伤控制缺失；没有按结果换题。

**第一版 J 的实测结果。** 本地 Qwen3.5-9B 通用 thinking 配置，完整合法历史、原生 262144 context、自然 EOS/EOT、温度 1、4 并发；没有人工任务输出 token cap。900 秒 watchdog 和重复循环 guard 属技术失败处理。本轮结束状态：`{a['finish_counts']}`。严格解析得到 {valid}/55 个有数值的候选评分；状态明细 `{a['measurement_status_counts']}`。自然结束不等于成功形成合规评分。

| 条件（不含重测） | 实际回复数 | 严格解析有数值 | 仅字形/空白规范化后有数值 |
|---|---:|---:|---:|
{chr(10).join(rows)}

离线解析 v2 只规范直/弯引号及空白，在指定的同一 source ID 或同一回复内匹配；不改词、不换证据编号、不补理由、不改 q/m，原始输出和严格结果均保留。它额外恢复 {v['recovered_from_strict']} 条，合计 {valid2}/55 条有数值。未能通过的仍是缺失，不能补为零，也不能把这部分剔除后声称完整效果。

失败尤其集中于损伤控制：9条中严格可用仅1条，字形规范化后也仍只有1条。因此缺失不是可以忽略的随机噪声；只保留可解析答案，会系统性漏掉本来最需要检查的错误案例。33条严格失败中，17条是引文不匹配、2条来源编号不存在、3条缺必需证据、5条错误索引不一致，其余为JSON/结构/分数内部矛盾。字形规范化只能恢复其中4条，不能替代接口修复与语义校准。

在该规范化解析视图下，10 个实际重测中有 {t['valid_pairs']} 对前后都有效；其中 {changed_repeats} 对 q 或 m 改变，{penalty_disagreement} 对效用差绝对值超过用满预算的资源惩罚 0.05。这里改变了预定采样 seed，测的是含采样在内的稳定性，不是同 seed 确定性。分母很小且有选择性缺失，不能用它宣布稳定或人类一致。

q 一档为 0.25，是全部资源成本 0.05 的五倍；m 的分档也可造成更大改变。因此评分接口与相邻档判据必须先可用、可解释，再向 PPO 提供 reward。损伤例为本次编码助手构造的诊断材料，不能称独立人类 gold；错误被标出还须检查是否标到了被修改的事实，而非另一处误报。轻量风格控制不能证明没有冗长偏好。当前自然题中很多需求可由当前前缀直接回应，不能凭本卷推断 LoRA、资源使用或序贯选择的优劣。

**已落实的技术修复及其边界。** 引文编号接口 v2 让模型选择已有 response sentence/source turn ID，程序再从绑定原文恢复引文和字符位置；未知 ID、q/m 类型/范围错误、严重性矛盾仍拒绝。准备了同一批 55 个请求，并在原始结果独立保存后追加 5 次技术检查，覆盖 OFF/ON/损伤/风格及一条既有重复条件，按固定 hash 选样。新接口状态 `{indexed_counts}`，其中 {transport_valid}/5 条形成有数值候选评分。实际追加模型调用为 5，总计本轮 J 调用 60；不把这 5 条并入首轮成功率。

这仍不是新版 J 的完整测量验收。编号引用粒度为回复句子和来源整轮，机械引用正确不能证明语义蕴含，也不能证明 q/m 准确。质量锚点未因此调成更有利的分数。下一次若执行新版全卷，应直接重评这批相同回复，单独保存完整版本；不用重生成，不挑得分好的旧新记录混成一个结果。

**来源、分组与预算。** 已按原 hash 保留 12/3/3 owner split，隔离共享源会话 `esc1198` 在 p13/p18 两支及全部后继前缀。重建 owner 平衡名单为 train=96（每人8）、dev=18（每人6）、test=48（每人16）。dev 从24降为18是合法来源数量约束，不是按效果抽样。原 12 题 pilot 全部包含在新 train 名单中。

通过重建旧 v2 完整历史参考及核验 SHA，确认新 test 中 32/48 个切点所属完整会话（包括该切点之后的内容）已出现在旧开发评审材料。它们可作“未参与本轮参数拟合”的历史暴露 benchmark，不能称研究者从未见过的 sealed test。其余项也不能因缺少完整历史匹配就自动视为未暴露；旧 QA/Summary 可能涉及局部事实。来源 ID、完整/空白规范化 transcript 和已知派生关系已核对；语义改写事实家族不作穷尽保证。需要未见确认集时，应新增来源家族，不能重新命名这些 owner。

162 个前缀 × 3 档预算共 486 组真实 tokenizer 完整渲染检查已完成。1024/2048/4096 下可行计划数中位数分别为55/69/70；2048 下最少16、最多70，低数量同时可能来自资源库存少。保留最初的 B=2048，未用模型质量分数调 B。主实验用同一预算和合法计划域。

后续训练还新增了来源绑定更严格的 generation v2 身份：prefix/cutoff、完整库存及其来源、retrieval、规范计数、完整 prompt、执行器/runtime/draw 一起绑定。不同来源即便文字相同也不会共用训练请求；不同 GET 顺序得到同一规范计划则可复用。旧试跑保留 v1 身份和重放入口，不能悄悄改名成 v2；该封装已通过 CPU 合约测试，尚未宣称做过 v2 执行器真模型试跑。

**费用与时间。** 本轮新增付费 API 为 **$0**，原账本 SHA 不变；继承的预算期仍为目标 $10、硬上限 $20，不重置。G 的23次新增解码累计 {g['new_generation_seconds']:.1f} 秒，成功加载 {g['successful_load_seconds']:.1f} 秒；首轮55次 J 的 engine wall 为 {jc['engine_wall_seconds']/60:.1f} 分钟，成功加载 {jc['successful_load_seconds']:.1f} 秒。并发请求的 latency 有重叠，不能直接求和当运行时长。5 次新版技术检查另有 engine wall {it['engine_wall_seconds']/60:.1f} 分钟、加载 {it['load_seconds']:.1f} 秒。

首个 vLLM 启动因本地库不接受 UUID 设备写法而失败，确认请求账本为0条后，改用已核验 A6000 的数字编号。失败日志保留；该失败全过程时长没有完整持久化，不能把成功耗时声称为全部工程时间。source/capacity runner 耗时包含 CPU 渲染和 GPU 持有期，不能当纯 GPU kernel 时间。没有提供电价或租价，所以没有把本地算力折成虚构美元值。

dev 数量调整后，原计划六个核心阶段调用从8496降为8244；另外还要列 OFF、测量、修订、独立评审、训练与重试等成本。若将本轮每次 J 的实际 engine 吞吐直接用于3096次后续 J，约需 {cost['conditional_downstream_J_only_hours']:.1f} 小时；这只是相同任务/配置/并发下的规划外推，不含 T_X/V_X、OFF、加载、训练、重试等，也不是已承诺总工期。当前 J 尚未合格，不应据此直接批量开跑。

可选 GPT-4o 模型复核仅作价格场景，未选定/调用：本轮10对完整消息内容实数 token 并加 framing reserve 后约164825输入 token。按每对512–1024输出 token 的**长度预测**，标准接口约 $0.46–0.51、Batch约 $0.23–0.26；按原生16384输出额度预留的 Batch liability约 $1.03。输出长度预测不是人为终止上限。加24对尚未生成的正式复核，Batch预测约 ${min(expected):.2f}–{max(expected):.2f}，原生输出预留场景约 ${min(native):.2f}–{max(native):.2f}；正式题输入仍为情景估计，实际账单以usage为准。[官方价格](https://developers.openai.com/api/docs/pricing)、[模型上限](https://developers.openai.com/api/docs/models/gpt-4o)、[Batch规则](https://developers.openai.com/api/docs/guides/batch)。这不证明 GPT-4o 适合担任最终裁判，也不构成付费调用批准；付费路径仍须先完成继承账本的原子预留/结算接入。

**现在怎么推进。** 先完成新版引文协议的整卷测量和独立复核，再决定 q/m 哪部分有足够支持。独立答卷必须明确是个人、多人共议还是模型，不能把模型 B 写成第二位人类。若只有事实误用可稳定测量，就先收缩结论范围；不能照样宣称已优化帮助性。测量支持后，再进入96 train /18 dev 的 T_X/V_X 样本制作及 LoRA；冻结 X_l 后完成共同监督初始化与 OneShot，然后才做 E0 三 seed 真更新验收和受限 PPO。当前训练更新为0。

评审者若参与独立复核，应先填写盲卷再阅读逐题诊断。10对题附148个合法过去会话、3647个证据 turns，约64357个英文源词；完整证据用于查验，不应把十对题误说成十段短句。尚未测量人工用时。离线表单已验证填写、保存、重载和JSON导出，测试值已清除，未生成伪人评记录。

**可复查材料。** [可填写盲卷]({review_copy})；[严格测量结果]({OUT/'measurement_analysis.json'})；[仅字形规范化视图]({OUT/'typographic_parser_v2/analysis.json'})；[逐题回复及裁判记录，协调端材料]({OUT/'coordinator_only/measurements_with_replies.json'})；[失败引文诊断]({OUT/'coordinator_only/failure_diagnostics.json'})；[来源与预算冻结]({DATA/'dataset_freeze.json'})；[费用清单]({OUT/'measured_cost_update.json'})。

代码验证：{tests} 项相关 CPU 测试通过；网页真实 Chromium 保存/重载/导出通过；{len(old)} 个接手时已有修改文件及用户原方案未被改动。新产物为本地文件，没有提交或推送远端。
'''
    doc=PROJECT/'docs/PM_RL1_MEASUREMENT_PILOT_RESULTS_20260928_ZH.md';doc.write_text(report)
    save(OUT/'closeout.json',dict(status='FIRST_PILOT_COMPLETE_MEASUREMENT_NOT_REWARD_READY',
        generator_new_calls=23,generator_exact_cache_hits=1,first_judge_calls=55,indexed_transport_smoke_calls=5,
        total_judge_calls=60,strict_valid=valid,typographic_valid=valid2,indexed_transport_valid=transport_valid,
        source_grouped_prefixes=162,split_counts=freeze['split_counts'],independent_reviews_returned=0,
        training_updates=0,paid_api_usd=0,tests=tests,test_failures=0,preexisting_files_preserved=len(old),
        report_path=str(doc),report_sha256=sha256_file(doc),review_copy=str(review_copy),review_sha256=sha256_file(review_copy),
        script_sha256=sha256_file(Path(__file__)),
        artifacts={str(p.relative_to(OUT)):sha256_file(p) for p in [OUT/'measurement_analysis.json',OUT/'typographic_parser_v2/analysis.json',
            OUT/'indexed_transport_smoke_pointer.json',OUT/'measured_cost_update.json',OUT/'validation/tests.xml',OUT/'validation/review_form_browser_test.json']},
        new_code_sha256={str(p.relative_to(PROJECT)):sha256_file(p) for folder in [PROJECT/'src/metacom_pm/rl1',PROJECT/'scripts/rl1'] for p in sorted(folder.glob('*.py'))}))
    print(json.dumps(read(OUT/'closeout.json')|dict(new_code_sha256='recorded',artifacts='recorded'),ensure_ascii=False,indent=2))


if __name__=='__main__':main()

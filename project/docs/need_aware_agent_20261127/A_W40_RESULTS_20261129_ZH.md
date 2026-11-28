# A：W4-0 终局评分与联合申请会签（2026-11-29，日本时间）

按输出前冻结的 `naa-wp4-reply-mcq-policy-v1` 评分，未改题目、选项、答案、历史、分母或 parser。执行 manifest 与 A 原冻结逐字段相同；五个 sealed 预测文件、ledger snapshot、原题及政策 hash 全部验证。公开回执在 `response_receipts/W40_AGGREGATE.json`，原始回复/逐题记录仅留本机。

## 1. 真实结果

五臂各预定且完成 272 题，14 个完整 owner/history-family cluster。无结构缺失、执行失败、重试、未执行或长度截断；完成率均 100%。严格格式失败仍在分母内。

| 条件 | 正确 / 272 | 准确率 | 严格格式失败 | owner-macro 准确率 |
|---|---:|---:|---:|---:|
| U0 原模型＋合法历史 | 110 | 40.44% | 1 | 40.31% |
| U1 记忆使用规则 | 103 | 37.87% | 2 | 38.44% |
| U1+ 主体/服务对象规则 | 101 | 37.13% | 1 | 37.45% |
| No-memory | 67 | 24.63% | 0 | 25.32% |
| Options-only | 93 | 34.19% | 0 | 34.27% |

四个格式失败均缺少协议要求的冒号，属于模型未遵循输出格式，不是程序漏识别；未放宽评分。固定分母敏感性与完成样本准确率相同。独立直接计算全部 1,360 个答案与 scorer 的计数一致。

预定次要比较均用相同的 272 个完整配对、14 个 cluster。下面是冻结 bootstrap 的描述性 95% 区间；不把次要比较升级为主检验，也不作未校正显著性宣称。

| 比较（右侧方法相对参照） | 修复 / 退步 | 差值 | owner/family cluster CI |
|---|---:|---:|---:|
| U0 − No-memory | 61 / 18 | +15.81 pp | [+10.17, +21.53] pp |
| U1 − U0 | 10 / 17 | −2.57 pp | [−6.43, +1.83] pp |
| U1+ − U1 | 5 / 7 | −0.74 pp | [−3.35, +1.86] pp |
| No-memory − Options-only | 21 / 47 | −9.56 pp | [−13.17, −5.86] pp |

结论限于此开发集和 modified MCQ 协议：长期历史有实际价值；当前规则未展示稳定总体增益。Options-only 高于 No-memory 提示选项风格/问题条件化等捷径风险，但这个比较不能单独定位机制，亦不能证明历史无价值。只有 14 个 cluster；不将区间跨零称为等效。U1−U0 的区间低于既定 −5pp 非劣界限，不能确认其总体非劣。原主要比较 **U3−U2 尚未运行**，不改变其身份。

预定类别的正确数如下（类别重叠，不可相加；others 仍只是未验证的元数据标签）：

| 类别 | n / cluster | U0 | U1 | U1+ | NoMem | OptOnly |
|---|---|---:|---:|---:|---:|---:|
| who:others | 29 / 11 | 3 | 8 | 7 | 7 | 3 |
| forget / updated | 58 / 14 | 19 | 16 | 17 | 15 | 15 |
| sensitive | 19 / 10 | 5 | 5 | 7 | 5 | 7 |

规则在 others 子组有局部修复，同时在 self 上退步；不凭局部方向声称稳定第三方能力。敏感与遗忘错误仍多。updated 与 forget 在这里是同一组，不能解释成一般时序更新能力。

## 2. 已完成的后台数据与 WP3

`joint_release/JOINT_DONE.json` 已完成，FREEZE `297c752d…`：实际 **234 fit / 47 tune**，分别 92 / 19 个 owner，原 owner 划分保持不变；fit 有核查负例 2 行，tune 1 行。全体 4,000 原候选及未知项继续保留。

fit 的正例组成：204 条窄筛选弱监督建议、27 条当前请求支持的通用回复、3 条实际送达历史支持的个性化候选。这个分布不说明其他官方回复错误，而说明本次来源审核和实际证据供给下，能用来检验历史理解的监督很少。不能把 234 条都称为记忆依赖训练样本。

原 review50 中 11 个可用相对排序候选，5 个属于 development，始终禁止训练；3 个 fit 候选所核查证据未完整送达；剩 2 fit / 1 tune。不会为凑比例把这八个直接放入训练。原 50 题核查结论与数据版本保持不动。

WP3 已由上一轮独立 CPU subscriber 完成封存评分，产物在 `a_response/wp3_terminal`，交接事件 `A_W3_SCORED_FOR_B.json`。B1→E0 +3.57 pp，CI [−2.14,+9.29] pp，Holm p=1；E0→E0s −7.14 pp，bootstrap CI 不跨零，但精确 McNemar p=.0639、预定 Holm p=.2557，不能据此称校正后显著下降。C→C+noise 在共同 131 题下降 19.85 pp，Holm p=.0000646；合法背景可能包含冲突/撤回，不能当作纯无关噪声。Direct 差距不等于可学习收益。

A 本次确认继续采用 **全角色 dense @8192、Qwen native 计数**作为 WP4 可部署供给：E0 未建立对 B1 的可靠优势，CPU 重排成本高；保持训练/评测一致。此为本次记录的会签意见，不伪称早于 W4-0 的另一次人工审核。WP3 双 tokenizer 的 B1 与本版预算身份分开保留。

## 3. 联合训练申请意见

已阅读 B `59962cc2` 的新增成本句。U0 272 题实测生成累计 **583.05 s**，加载 **36.80 s**；约 540 s 是中位数乘任务数，不是实际累计时间。两个适配模型的粗略同长度参考约 1,240 s，尚不包含已实测的 LoRA 开销或 64-token 最坏输出。支持保留申请的 3,500 s 主 MCQ 上限作为有余量候选，不能把 base-G 实测当作适配模型硬保证。

**会签：数据/执行/评价接口与资源核算已核验；不建议原样启动当前 U3−U2 主比较。** 两个 fit pair 仅占 0.85%，且绝大多数正例不要求历史。当前 30 步实验最多是小规模回复 SFT 迁移探索，不能支撑“排序监督无效”或“已学会记忆理解”。保留 U3−U2 原主要比较，U2−U0 仍是预定次要比较，不能因这些结果事后换主指标。

下一项有价值的 CPU 工作是对训练侧实际送达的官方正/负回复补充有限、逐项的语义支持与相对排序标注，优先修复训练信号缺口。只用原 fit/tune owner；不能按这 272 道开发题的错误挑训练样本，不能强凑“30%”而制造负例，也不再改写动作模板。数据变化需保存新版本和实际 token 检查，U2/U3 使用完全相同的正例、样本顺序、权重和更新数。

B 的书面决定要求训练后的 NoMem/OptOnly 诊断。已增加显式 `manifest-adapted --diagnostics-only` 候选块及严格 scorer 身份支持；默认仍只有 544 个主请求。诊断独立生成 1,088 请求，不重复主块，也不自动获得 GPU 批准。原 W4-0 政策不改；诊断仅描述各模型同题历史收益、NoMem/OptOnly 准确率及 cluster 配对区间，不新增主检验。

84 个完整 Agent 合同的实际 episode/技能来源适配、MP/ME 遥测、真实开放回复和有限审查仍待完成。MCQ 成绩和单元测试不替代完整陪伴 Agent 评价。不启动训练、不占 GPU、不解封正式测试集。

## 4. 可复现命令

```bash
export PYTHONPATH="$PWD/project/src" CUDA_VISIBLE_DEVICES=''
P=/opt/tokkio-data0/tokkio_envs/naa-cpu-py311/bin/python
S=/opt/tokkio-data0/naa/20261128/a_response
B=/opt/tokkio-data0/naa/20261128/agent_b
"$P" project/scripts/need_aware/finalize_w40.py \
  --material "$S/development_frozen" \
  --sealed "$B/runs/w40-v11/seal" --manifest "$B/manifests/w40-v11" \
  --original-manifest "$S/joint_release/development/MANIFEST.json" \
  --out /new/private/w40-score
"$P" -m pytest -q project/tests/test_need_aware_*.py
```

既有输出目录拒绝覆盖。此次评分无工程失败；四个模型格式错误完整保留并计错。公开材料只有代码、统计和 hash；原始回复、答案、逐题标注和 owner 身份不上传。

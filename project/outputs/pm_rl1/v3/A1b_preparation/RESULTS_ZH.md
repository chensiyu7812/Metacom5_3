# A1b bank-v0 真实迁移与读取准备结果（待 C0 正式冻结）

代码、真实 bank、原生 tokenizer 全量读取及跨线测试已运行；**不宣布 A1/A1b completed**。integration 仍未冻结 C0，因此在 detached worktree 准备两项独立提交，没有继续 PR #5、没有新建正式工作分支/PR、没有修改全局状态。A1 准备提交为 `69a850c5`，对应结果见 A1_preparation/RESULTS_ZH.md。

## 四头实际条目与可读取比例

| head | bank 实际条目 | 至少一个 B0 前缀合法 | 实际被 top-1 读取的不同条目 | GET 成功 / 4119 | 可得率 / GET 成功率 | 实际正文 token 范围 |
|---|---:|---:|---:|---:|---:|---:|
| MP | 387 | 343 | 169 | 3610 | 87.64% | 31–325 |
| ME | 1525 | 1461 | 500 | 4108 | 99.73% | 55–341 |
| MS-RAW | 401 | 383 | 352 | 4119 | 100% | 266–1264 |
| RS 完整案例 | 875 | 875 | 316 | 4119 | 100% | 354–2502 |

3188 条中 3185 条 unverified、3 条 development_reviewed；没有 independent/professional approved，没有 verified-world-fact 或 positive_eligible=true。MS 没有 SUM；RS 没有虚构方法卡。875 是本次从合法来源得到的完整对话案例数，**不是独立策略或已验证方法数**。

全部 4119 个固定 B0 前缀 × 4 头共 16476 次真实 GET，15956 成功（96.8439%）；每次还重复调用核对确定性。520 次失败均为 `unavailable:no_legal_candidates`（MP 509、ME 11）；没有空 ReadingView、超容量成功、截断或成功序号推进。126 条 bank 记录在这组固定前缀中从未合法可得，主要因为缺少该会话之后的前缀；这不等于全局不可用。可得率/成功率不衡量语义相关性或自然支持质量。

原生 Gemma tokenizer 的 4 个小文件 SHA 与固定资产审计一致，100 条旧 A0 请求的完整 token ID 全部复现；没有读取模型权重。原生容量配置 262144 tokens；本次每个完整输入都实际计数并在超限时整条拒绝，运行数据中没有容量拒绝。容量负例另由明确标记 test-only 的小容量 tokenizer fixture 验证，不伪称原生容量实测失败。全量读取 CPU 实际耗时 316.51 秒，不是 GPU 推理吞吐。

## 旧资产转换，严格区分统计层

`ASSET_CONVERSION_SCORECARD.json` 区分已存在、来源核验、映射进入 bank、至少一个前缀可得、实际读取。RS 多对一/多对多派生层不可相加为独立样本。

- 713 MP 全部核验来源：387 正常迁移，2 条按既有修复证据转为 ME，324 保持隔离；因此旧 MP 映射新记录总数为 389，而新 MP 头为 387。
- 1523 ME 全部核验来源：1522 正常迁移，1 条证据修复；加上两条 MP→ME，新 ME 为 1525。普通旧 ME stage=unknown，不把旧时态标签升级成完成或因果。
- 401 MS-RAW 全量原文迁移，保留角色、顺序、来源跨度和 RAW 身份；没有使用 `evo_emo.json` 的评测 summaries。个人会话时间与 ready_at 逻辑边界见 A1 说明。
- 11590 策略保留到 823 个完整来源案例的映射；13172 treatments 保留 source_card_ids、atomic_card_ids、所有父来源及到 875 个案例的映射。treatment 只通过父来源/family 谱系门，未把归纳方法文本声称为逐句来源/语义核验通过，其 scorecard source_verified=0、lineage_verified=13172。
- 旧 12 个案例保持 6 repair、6 quarantine；3 方法草稿全部 quarantine，均未接入读取。
- 既有六类 EvoEmo 特权/评测字段另在最终 scorecard 登记排除数量，runtime 完全不导入其正文。
- 迁移 ledger 粒度汇总：2310 migrated、3 repaired、24762 adapted_lineage、333 quarantine、6 repair；这些混合粒度不能相加当成独立有效资源。源级另拒绝 84 overlap family + 341 非 train。

### 713→388 的逐条解释

旧 `42_build_multi_view_candidate_census.py:290` 使用完整历史终点；旧 candidate_adapter 按 owner+profile_slot_key 仅保留最高 source_session_rank 的值。实际重建此投影，与旧池 388 MP 集合完全相同。没有进入旧池的 325 条全部存在同 owner、同 slot 的后续版本；每条的 replacement_ids、原始 SHA、来源与原因保存在 migration.jsonl。

这 325 条**不因跨度通过而自动恢复 MP 召回**：324 留在隔离台账；写作班这一条仅因研究者明确要求处理的既有证据修复，被单独迁移成 ME。旧最新值规则只用于解释旧池，不用它宣称最新画像一定为真；当前读取仍按严格过去过滤，并以过去自报而非当前事实表达。

三条修复原 ID 及引用全部保留。挂电话和写作班改为 ME/attempted，在线社区条目保留 stage=unknown、主观帮助与社区支持的分开观察；不升级为因果、康复或持续有效。均为单次既有开发审阅，独立审核仍 pending。

## 过滤、身份与跨线接口

A1 source 版本：`sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02`。

bank：`bank:02d0a4b1e62fd033c02b4fdc8e76d8796b285aa058cb59201aacde2c13ce8dd9`。

index：`index:227cca582de991e1ef823e0122e842be7316bf4339acc73c88992870ff1846f3`。

先 source/owner/严格过去/ready_at/family/train/review 过滤，再合法前缀末三轮词面排序；一次 GET 交付一条完整记录，不按容量偷偷替换低排名结果。全量候选比较记账为 owner 拒绝 8964751、future_source 拒绝 290985、通过 3875636（每前缀×bank record 粒度，不是不同资源数）。所有 84 重叠 family 已在 source build 阶段拒绝；esc1198 的 p13/p18 关联及同折保持。未确认关系不能进入 v0 读取图。

调用示例、B5 无业务修改接入、token 账与完整提示长度的区别见 **B_INTERFACE_ZH.md**。可调用 `source_registry.build/load`、`bank_v0.build/load`、`retrieve.search/read`、Reader.availability/action_mask/terminal_key/replay。ReadFailure 明确区分空 bank、无合法候选、容量、非法动作和完整性/错误版本；失败不改变调用方状态。

REAL_REPLAY 为真实 p1/esc245/cut=1 的四头读取，实际顺序 MS→ME→MP→RS 与规范化顺序均保存；完整提示实际 1949 tokens。完整 TerminalKey 已绑定 owner/prefix context/bank/index/renderer/Step-2/G/decode。B5 实测能读四头并重放身份；STOP 没有 Generator 输出时保持 PendingTerminal，不填零奖励或假回复。

## 验证、失败及修复

- A1：16 项通过；A1b：21 项通过（包含参数化版本隔离）；全部 V3 跨线 324 项通过，零 skip/xfail。32 份 C0 Schema 一致性与 compileall 通过。
- 完整当前 CPU：2156 passed / **1 failed** / 1 历史 tokenizer 环境 skip / 11 GPU deselected，501.20 秒。全部 V3 在该完整运行中也通过。唯一失败是 integration 已记录的 `test_ci_never_runs_local_gpu_tests_on_github_cpu_runner`：独立 V3 CI 命令遗漏 `-m "not gpu"`。本轮 WS-A 未改 workflow 或弱化测试，等待集成负责人修复及冻结。
- 首次 RS 迁移比较 strip-only 文本失败。核对旧 adapter 后，确认它压缩所有空白，现按该确定性规则核验旧响应与原轮次，同时保存原始字节跨度；6410 exact + 5180 legacy_whitespace_normalized，零剩余不匹配。
- 第一版测试 fixture 误写不存在的 p2_conv_23，并把 823 个策略来源误认为 875。改为从真实 registry 选合法前缀，分别验证两类真实数量；B 的代码、正式验收和断言未动。初次失败 XML/log 与最终通过结果均保留，详见 diagnostics/REPAIRS.json。
- PR CI **未运行**：C0 正式冻结条件尚未满足，遵照用户指示未创建新功能分支/PR。不可用 integration 旧 CI 或本地绿灯冒充新 PR CI。

没有实现 A2–A4 的 v1 编译、A5 BGE/BM25/RRF、关系传播或新 Generator 输出。没有 GPU、生成、实验训练或付费调用；CPU 回归包含既有合成优化器单元自检。未修改 H0、状态表、B0/B1/B2/B5 业务或历史产物。没有召回质量改善或回复质量收益结论。

## 重建与下一步

```bash
export PYTHONPATH=project/src
export CUDA_VISIBLE_DEVICES=''
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
python project/scripts/rl1v3/a1_build_source_registry.py --out /tmp/registry-v0
python project/scripts/rl1v3/a1b_build_bank_v0.py --registry /tmp/registry-v0 \
  --out /tmp/bank-v0-replay --tokenizer-model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3
python project/scripts/rl1v3/a1b_finalize_scorecard.py --measured /tmp/bank-v0-replay \
  --out /tmp/bank-v0-scorecard.json
```

此环境为 `/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python`。后两条分别实际测量与汇总固定审计中的隔离源字段；不会重新扫描全部模型资产。MANIFEST 固定输入、代码、bank/source/index、结果、tokenizer 小文件及 SHA；耗时字段作为实测日志，不要求重放完全相同。

B 现在可在独立准备树复现真实 bank 读取与 B5 身份回放。**正式 B1/B2 依赖放行**仍须集成负责人修复 CI、冻结 C0；之后从最新 integration 新建工作分支，移入 A1/A1b 独立提交、提交新 PR 并通过 PR CI/集成验收。不能在冻结前以本准备报告宣布任务 completed。

准备阶段 manifest 的 code_sha 是施工起点提交，实际运行代码由逐文件 SHA 绑定；独立任务提交 SHA 以 Git 历史和最终交接为准。首次失败日志/XML 保留 pytest 原始字节（包括行尾空白），全路径 diff --check 因这些原始日志空白报警；源码、说明和配置另行检查通过，不改写失败证据。

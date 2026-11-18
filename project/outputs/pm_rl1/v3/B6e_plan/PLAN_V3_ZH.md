# B6e 工程预检方案 v3：预注册的覆盖诊断选样（只是方案，未执行，未获授权）

- 证据等级：engineering_only。
- 配置：`configs/rl1v3/B6e_preflight_plan_v3.yaml`；规则写在代码里：`evaluate/b6e_select_v3.py`。
- 结果文件：`v3/SELECTION.json`、`v3/PLAN_V3_FROZEN.json`、`v3/REAL_KEYS_CHECK.json`。
  - `selection_sha256 = db44a509…612f`；
  - `plan_sha256 = bef7ad23f62babebbbd7a5dee3efcf19b0d99a6075c63e1aa49bf06b829cddf3`；
  - 规则 `rule_sha256 = 7410bd6c…`；代码 `0700794b`。
- v1（`PLAN_ZH.md`）和 v2（`PLAN_V2_ZH.md` 及其配置）原样保留。
- 本轮**没有**任何 G0、J1、J2、GPU 或付费调用。

## 1. 为什么修改

- v1/v2 的规则按可达数从高到低选，在真实回放下只会选中第 1–4 折、可达数为 16 的前缀。"MP 无合法候选、只有 8 个终点"的情形和第 5 折因此永远得不到检验。
- 研究者决定改为**工程覆盖诊断**：固定 7 个四头都可读的前缀（R16），加 1 个 MP 无合法候选的前缀（MP8）。
- 这**不是**自然分布抽样，不能用来估计自然分布。

## 2. 预先固定的规则（`rule_sha256` 见 `PLAN_V3_FROZEN.json`）

- **候选**：`coverage_sample_v1` 中第 1–5 折的 20 个 NeedCard 试点前缀，并且在正式 integration B5 回放（`320a33d1`）中通过；第 6 折不用。
- **分类**：
  - R16：可达 16 个子集，且没有不可达的头；
  - MP8：可达 8 个子集，且唯一不可达的是 `MP: unavailable:no_legal_candidates`；
  - 其他情况不可选。
- **约束**：
  - 恰好 7 个 R16 加 1 个 MP8；
  - 每个 owner 最多 1 个，每折最多 2 个；
  - 第 1–5 折每折至少 1 个。
- **顺序**：按 `sha256("pmrl1v3|b6e-preflight-v3|" + prefix_id)` 升序，相同时按 prefix_id。
- **选择**：在这个顺序下取第一个可行集合（字典序最小）。具体做法是依次检查每个候选：加入它之后仍能补成可行集合，就保留。任何约束无法同时满足时，**直接停止并报告**，不放宽约束。
- **输入**：只读回放事实（可达性、折、owner）。不读取任何生成、判官或质量字段；有测试验证，加入质量字段或打乱顺序后结果不变。

## 3. 选样结果

| 序 | 前缀 | 折 | owner | 段 | 类别 | 终点 |
|---:|---|---:|---|---|---|---:|
| 1 | 01c44f464e0e | 4 | p15 | late | R16 | 16 |
| 2 | fa14cf4451df | 2 | p16 | mid | R16 | 16 |
| 3 | b60fe830cb1b | 2 | p13 | late | R16 | 16 |
| 4 | ac45ce97a037 | 3 | p2 | late | R16 | 16 |
| 5 | f310c0e490b1 | 5 | p8 | mid | R16 | 16 |
| 6 | 74a7a964cc18 | 1 | p11 | late | R16 | 16 |
| 7 | 6ce6b7faa301 | 3 | p5 | mid | R16 | 16 |
| 8 | ab3d17407ca4 | 4 | p3 | early | MP8 | 8 |

- 折的覆盖：1 / 2 / 2 / 2 / 1。owner 共 8 个，互不重复。共 **120 个终点**。
- 如实记录的偏差：
  - 段分布为 late 4、mid 3、early 1，唯一的 early 前缀就是那个 MP8；
  - 三个 MP8 候选中只有第 4 折这个可行：第 2、3 折的折名额和 owner 已被前面的 R16 占用。

## 4. 调用上限（由选样结果计算，不重复计 NeedCard 额度）

| 环节 | 上限 |
|---|---:|
| NeedCard writer | 0（这 8 个都在已申请的 20 个试点中） |
| 检查表 | 0（确定性的模板 v3） |
| G0 生成 | 120（7×16 + 1×8，每个终点贪心生成 1 次） |
| J1 | 360（每个终点最多 3 次：完整、完整重问、缺项重问） |
| J2 / 付费 API | 0 / 0（GSC 保持 pending，pending 绝不记为 0） |

## 5. 身份绑定（由代码计算并写入 `PLAN_V3_FROZEN.json`）

- **来源与读取**：
  - sources `c6ad9b15…`、bank `02d0a4b1…`、index `227cca58…`、renderer `e7678cc1…`；
  - Step-2 `none-v0-read-replay`；
  - 读取端口为 WS-A PrefixPort。
- **NeedCard**：试点计划 `plan_sha256`，writer v2 的身份，RS-v0 类别目录。
- **评价协议**：
  - 检查表模板 v3、判官 v3（首次调用前固定 `JudgeIdentityV3.id`）、聚合 v3；
  - ER-v3（附预登记哈希）、评价协议 v2；
  - 终点登记 v1、B8e 接口 v1。
- **G0 与 decode：仍缺**，需要 WS-A 交付带版本的初始 G0（权重 SHA、请求渲染器、解码配置）。

## 6. 真实 key 核对（CPU）

`REAL_KEYS_CHECK.json` 的做法：
- 用原生 Gemma tokenizer 和 WS-A 正式端口，重建 8 个前缀全部可达子集的 TerminalKey 与 ExecutionTrace；
- 要求每个 trace 都能重现对应的 key，并且 key 与正式 integration 回放中的 key 完全相同；
- 没有生成，也没有奖励。
- **结果：120/120 个 key 与正式回放相同。**

## 7. 启动前提（现在不满足，**不能启动**）

1. 本 WS-B S3 分支经集成负责人审核并合入；
2. NeedCard 试点在单独授权下完成，这 8 张卡核查结论为 valid（试点证据错误率 ≤ 10%）；
3. 这 8 个前缀的 v3 检查表在任何 G0 调用之前冻结；
4. WS-A 交付带版本的初始 G0 身份和请求渲染器；
5. A0 在 A6000 上实测 G0 和 Qwen 的吞吐与显存峰值；
6. 研究者明确授权，并且 A6000 空闲 ≥ 30 GiB、WS-A 当时没有占用。

**不能据此得出的结论**：
- 对自然分布的估计；
- 在同 8 个前缀上训练又测试的结果，不能用来声称泛化能力，也不能说明 PPO 更优。

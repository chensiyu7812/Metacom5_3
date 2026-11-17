A1、A1b 与 B5 已在真实 integration 提交 `16644abb3cc28aa1a2f16b0309b84402ac854d5c` 验收通过。本记录只确认工程能力；B1/B2 的真实模型与判官任务仍未完成，S1 没有整体完成。

| 集成事件 | SHA / 证据 |
|---|---|
| 起始 integration | `8bcd326e5158482e3e4ad1760f82b117a58d1e2c` |
| PR #8，审阅 HEAD ca4db1a3 | merge `b591863e4439014872dd076c72b20b99983a52e4` |
| PR #9，同步 HEAD 59607355 | merge `16644abb3cc28aa1a2f16b0309b84402ac854d5c` |
| 两项合入后的实际 push CI | [run 44188379179](https://github.com/chensiyu7812/Metacom5_3/actions/runs/44188379179)，success；integration-base 实际执行成功 |
| C0 | pmrl1v3-contracts-0.2.0 / pmrl1v3-json-1，34 个共享文件（含32 Schema）与原冻结 SHA 一致 |

PR #8 已先行合入，B 在原工作分支普通 merge integration，PR #9 改 base 并转为 ready 后合入。B 同步后的差异仅 46 个 B-owned 文件，无 A 文件重复引入。两个 PR 的最新 HEAD CI 均通过。PR #7 未重复处理；main、PR #4、H0、研究者采用状态和旧失败/原始输出均未改动。

| 真实 integration 验收 | 结果 |
|---|---|
| 本地严格 V3 + verify_v3_junit | 466 passed，0 fail/error/skip/xfail |
| 本地完整 Paper-1/RL1/V3 CPU | 2299 passed，1 历史 skip；11 GPU 测试排除 |
| 实际 push CI 严格 V3 | 466 passed，0 fail/error/skip/xfail；与本地测试身份集合一致 |
| 实际 push CI 完整 CPU | 2231 passed，63 历史 skip；0 fail/xfail，1 GPU 测试排除 |
| GPU 隔离保护 | 单项通过 |
| Schema / integration-base | 32 份一致；本地及 CI integration-base 通过 |
| B5_real_replay_v2.py --port a | 24/24；21 个前缀有16子集、3个有8子集；360终点、1413合法读取顺序 |
| B1_A1_cross_check.py | 401会话、4119前缀，内容/前缀/覆盖差异均为0 |
| B1_needcard_cpu_preflight.py | 20/20 ready；3739–27009 token；0截断、0 writer调用 |

B5 读取身份、正文、token、可达性与此前 173bed 报告完全一致；两次独立磁盘加载和24/24容量压力、失败不推进状态均通过。21条 `ready_at == cutoff` 边界合法。24个覆盖前缀的合法性检查未发现未来、跨 owner、跨 family 的违规读取；非法/超容量请求被拒绝且不推进状态。全部真实 STOP 终点仍为 pending，未填零。来源适配器的 license/provenance/URI/split 各401处元数据标注差异按设计单独记录，内容零差异；85条 ESConv 派生个人会话对应84个重叠 family，含 esc1198 多 owner。

本地/CI 的历史 skip 逐项保存在 `validation/VALIDATION_RESULTS.json` 与 `code_ci/ATTESTATION.json`。CI 缺本地研究输入、旧 tokenizer、rg 和 sentence_transformers；这些跳过不计作完整覆盖。完整 CPU 范围已运行，不等于所有历史环境分支都被覆盖。

首次 Schema 命令从 project 工作目录运行且未给 --out，产生 FileNotFoundError。集成负责人修正的是验收包装器的调用路径：显式指向现有32份 Schema，检查通过；未改共享代码、Schema 或测试。原始失败日志、命令收据和 v1/v2 包装器均保留（`HARNESS_INVOCATION_FAILURE.json`、`validation/guards/`、`validation/guards_retry/`）。除此之外，无代码测试、CI或真实跨线验收失败，未 skip/xfail 绕过。

| 已集成资源 | 实际数量 / 状态 |
|---|---|
| 来源 registry | 1276：401 MS-RAW 会话 + 875合法 ESConv train 来源 |
| bank-v0 | 3188：MP387、ME1525、MS401、RS875 |
| 质量状态 | 3185 unverified，3 development_reviewed；非研究级事实认证 |
| MP/ME 迁移 | 713 MP / 1523 ME逐条映射保留；324 MP隔离、2 MP转ME、1 ME修复 |
| RS-v0类别目录 | 8类、7类可选；unknown/unverified，875案例映射，不是A4正式方法卡 |

source/bank/index 在合入前内存重建身份一致；未重复生成或覆盖旧资产。完整输入哈希见 INPUT_MANIFEST，读取接口可直接使用 `bank.v0_port.make_port_factory(root=repo)`；返回 PrefixPort 使用 `read(head, acquired=...)`，actual token before/after 和 TerminalKey/ExecutionTrace 由回放绑定。本轮未执行 A5，GET 成功或工程回放通过不能证明检索准确率或回复收益。

| 正式任务状态 | 当前结论与后续依赖 |
|---|---|
| C0 / B0 | 保持 completed；原冻结记录不变 |
| A1 / A1b / B5 | completed，绑定本次真实 integration 验收 |
| A0 | in_progress；CPU准备可继续，GPU吞吐/显存/时间仍缺，另行授权后才能实测 |
| B1 | in_progress；A1b来源与目录依赖已满足，可做CPU准备；真实NeedCard生成需另行GPU/模型授权 |
| B2 | in_progress；v2代码/协议已合入，仍待真实B1需求卡、检查表及判官验收；未放行模型或付费调用 |
| B6e / B8e | pending；B6e仍待A0、B2与完整G0/终点输入身份，B8e依赖真实B6e；不得用pending STOP填表 |

本次 GPU、模型推理、Generator、Judge、实验训练、付费调用均为0；仅CPU回归（含既有测试fixture）和原生 tokenizer 计数。G0仍未冻结，g0_identity/scale_tier/lambda_main未自行设置。

本报告绑定已验收的代码合并 SHA；随后状态与报告记录提交还须检查其自身 HEAD 的 push CI。该最终 HEAD/CI 凭据通过本轮 PR 交接评论与最终汇报提供，避免将中间提交的成功冒称最终 HEAD 成功。

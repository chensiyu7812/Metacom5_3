# WS-A G0e / A0 CPU / 开发诊断验收收据

实现基线为 integration `320a33d1d871199d171f998300ce926b341ca1a8`。代码提交：G0e `9f29fc8d`、A0 有界准备 `07dee4bc`、相关性诊断 `d8939403`。PR：<https://github.com/chensiyu7812/Metacom5_3/pull/10>，目标 integration，未合并。

该代码 HEAD `d893940357c0539f2c4b8166cf0b34fc29c0ecea` 的 GitHub CI 已成功：<https://github.com/chensiyu7812/Metacom5_3/actions/runs/44200339100>。本收据提交后的最终 HEAD CI 通过 PR checks / PR 描述核对，避免把此处代码提交的成功冒充之后提交的成功。

| 验证 | 实际结果 |
|---|---|
| 新增有针对性的 CPU 测试 | 24 passed |
| 本地全部 V3 严格测试 | 490 passed，0 skip / xfail / failure |
| verify_v3_junit | 通过，490 个 testcase |
| GitHub 全部 V3 | 490 passed，0 skip / xfail |
| GitHub Paper-1 + RL1 + V3 完整 CPU 命令 | 2255 passed，63 skipped，1 GPU deselected |
| 32 份冻结 C0 Schema | 全部一致 |
| 本地及 GitHub integration-base | PASS，GitHub 对应 step 实际执行 success |
| GPU CI 隔离保护断言 | 完整 CPU 套件内通过，未改断言或 workflow |
| G0e binding 重建 | build_config 与提交 JSON 精确相等；未扫描或加载权重 |
| 受保护资产 | 141 个文件与基础提交逐字节一致 |
| 未授权运行的真实命令检查 | 在 authorize 阶段拒绝，未访问 GPU / 导入模型 / 创建运行目录 |

完整 CPU 命令不代表旧测试的完整覆盖。GitHub 63 个历史跳过分别是：sentence_transformers 缺失 1、冻结 Llama tokenizer 缺失 1、rg 不在 PATH 1、缺少旧本地 engine/relation inputs 32、缺少旧 engine/task inputs 28。逐项原因在 `validation/ci-code/SKIPS.json` 和原始 JUnit。V3 没有任何 skip/xfail。这里固定的是已完成的 GitHub 全 CPU 证据；额外本地全套运行单独保留日志，不用未完成运行计入此收据。

四个真实请求的原生输入 token 为 OFF=418、ME=668、RS=1658、ALL=2771；全部保留 320 输出预算。16 子集/65 顺序身份检查通过。B 的未修改有限域环境与新端口联合检查 20 个开发前缀：17×16 + 3×8 = 296 个终点身份、1153 条顺序，全部 STOP pending。与旧 B5 的 24/360/1413 不同是因为本轮排除 fold 6 的 4 个前缀，仅用于 G0e 开发输入；没有替换原 B5 结论或 B6e 采样。

source/bank/index 身份保持：

- `sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02`
- `bank:02d0a4b1e62fd033c02b4fdc8e76d8796b285aa058cb59201aacde2c13ce8dd9`
- `index:227cca582de991e1ef823e0122e842be7316bf4339acc73c88992870ff1846f3`

三项 manifest 已校验，输入路径以仓库根为基准；在仓库根调用 C0 `io.verify_manifest(..., root=repo)` 可核验。原始失败/初始候选另存 preparation_failures，未覆盖历史审计或原实验输出。

- G0e：`0fb948738d01dd3fad8da4cf2c51a0f4af3360ed96f888404c70d02274d4addf`
- A0 CPU proposal：`fcdd4cf9e10bde528ea6d077b0ffd320c160b74c1474f4d97997f526c3245318`
- 相关性诊断：`e6ce61a5aed97b68bc32101a1257c5515319fd1912f1885c277ee6b4ab86a0e1`

诊断中的 12 项并非 12 个独立来源，112 个来源跨度引用包含复用，不作总体准确率计算。Gemma 准备的测速输入主要覆盖原 OFF 和四个资源条件，不能未经长度分层验证就将吞吐外推到所有长终点。新执行器显式固定解码参数，原 100 OFF 的 messages / 原生 token IDs 保持原样；A0 probe 与 G0e 正式终点缓存身份隔离。

## B6e 交付与剩余依赖

B 可从 PR #10 调用 `generator.g0e_port.make_port_factory`、`port.request_packet`、`port.replay`；新 G0e key 和旧 tokenizer-only B5 key 并存。正式集成由 integration owner 进行，A 不改 B-owned 代码或全局状态。

B6e 仍缺：独立 GPU 授权与 A6000 独占窗口；A0 实际 backend/容量/吞吐校验；B 对 120 G0 / 最多360 J1 调用清单的固定（当前基线 B 配置为128/384）；真实 NeedCard/Checklist/J1 输入和真实回复。若同一项已在 B 的新分支推进，以 B 的正式合入证据更新依赖，不能从本轮 CPU 接口推定完成。

G0e 是 no-plan、batch=1 的初始工程版本，不是 A7 正式研究 G0。A0 全任务仍未完成；未完成 A4/A5/A6/A7/G1；模型生成、GPU、实验训练和付费调用为 0。H0、main、PR #4、EXECUTION_STATE 均未修改。

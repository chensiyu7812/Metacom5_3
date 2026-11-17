# RS-v0 策略类别目录：未验证的工程输入

协议 `pmrl1v3-rs-v0-strategy-catalog-1`，Schema `rs-v0-catalog-1`。目录身份 `pmrl1v3-rs-v0-strategy-catalog-1:7323c7f40e7b99cff5b7e7bcc10354c9360b7a0a6016a3495ee13124998d344f`。输入 Schema 在 `project/schemas/rl1v3_rs_v0/StrategyCatalog.schema.json`，没有修改冻结的 C0 32 份 Schema。

来源为现有 bank 内 875 个 ESConv train 完整案例；逐条比对原始 JSON 中 supporter 话语、角色、turn 和 strategy annotation，与 A1 source ID、family 及 SourceSpan 绑定。84 个 EvoEmo 重叠 family 未进入本目录。原始 emotion/situation/survey/全轨迹评价字段均不进入 writer 输入。

实际核验 12,403 个 supporter 标签：Question 2,568；Affirmation and Reassurance 1,953；Self-disclosure 1,149；Providing Suggestions 1,991；Others 2,252；Restatement or Paraphrasing 706；Reflection of feelings 976；Information 808。8 个来源标签，7 个可选择类别；Others 不可选择。当前 admitted 来源中 unknown=0；实现遇到未识别/缺失标签时保留 unknown，不能猜测。

旧 11,590 个 strategy ID、13,172 个 treatment ID 在 cases 中保留映射，不把它们相加成独立方法。12,403 是原始 supporter 标注数，与旧策略池过滤后的行数口径不同。旧 guidance 与 treatment 正文不会成为目录描述。所有 definition=unknown、quality=unverified、is_a4_method_catalog=false，使用范围仅 engineering_needcard_input_only。

```python
from pathlib import Path
from metacom_pm.rl1v3.bank.v0_port import load_bank
from metacom_pm.rl1v3.bank.rs_v0_catalog import load
root = Path('/path/to/Metacom5_3')
bank, _ = load_bank(root)
catalog = load(root/'project/outputs/pm_rl1/v3/A1b_crossline_20261118/RS_V0_STRATEGY_CATALOG.json', root=root, bank=bank)
# B v1 needs.protocol.build_pack(ctx, catalog.for_needcard_writer())
# B v2 可消费 catalog.selectable / entries / as_dict()；类别 ID 保持 snake_case。
```

目录包含私有 provenance；`for_needcard_writer()` 和 `as_dict()` 仅输出标签、未知定义和明确的未验证说明，不向 writer 传递案例正文或来源 ID。B 现有 v1 writer 输入协议已经实际构造 24/24 个 ready 输入包（B1_INPUT_PACKS_24.jsonl）；未运行 writer、未生成 NeedCard、未授权 GPU。

首轮目录测试曾因测试使用 decode_contract 时传入 dict 而失败，已改为契约要求的规范 JSON 字符串；仍逐条验证全部12,403个来源跨度，未弱化断言。初始失败日志保留。42项 bank/port/catalog 针对测试通过；完整回归与 PR CI 在总报告记录。

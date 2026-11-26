# GE2 评价侧严格来源坐标核查

起点 `5440d422110c57cba6567fca216383cd86e838de`。本核查在新G回复阅读前完成，只读冻结 `source-bundle-v2`、`cpu-final-v1` 与既有隔离来源cache。未修改任务、EvalSpec、排名、控制器、执行器或已批准运行包；没有模型、权重、GPU或API调用。

**未发现数据身份损坏，无来源身份阻塞。** 29个旧参考实例、20个规范历史引用实例均核对到原会话与原话轮；96个既有CPU条件的旧substring计数完整复现。将匹配条件收紧为同record、同原话轮、同speaker及同Unicode片段，并对当前出现文字作具名助手开发审阅后，96个CPU条件和5个Direct条件的原子覆盖数本次均未变化。这是本批数据的检查结果，不表示原全文substring谓词一般安全。

## 1. 核查范围和坐标含义

来源cache及registry首先匹配冻结配置SHA；合法池的完整source_refs再与该cache逐项相等。每个历史引用要求 `record_id/owner_id/session_id/turn_index/speaker/start_char/end_char/exact_quote` 同时一致，原话轮SHA正确。offset按原Unicode字符串字符计，不按UTF-8字节、不trim、不在同record其他话轮补找相同文字。官方来源的upstream `original_idx` 与运行时 `ordinal_turn/turn_index` 分别保留，不能把前者当后者。

实际供应只认receipt中的原话轮区间；某句话出现在同record的另一个speaker或另一个turn，不能代替被要求的原坐标。充分组继续按原定义OR组、AND组内片段；多话轮问答组须同时供给其上下文和回答。范围内未知、欠定reference及没有正向组的项仍为unknown。

|题别名|通道|必答原子|历史引用实例|当前匹配实例（按原子）|当前内容的有限身份|
|---|---|---:|---:|---:|---|
|G01|事实|2|2|0|提问，不供给所问具体事实|
|G02|事实|2|4|0|提问，不给出所问时间；原日历推理假设保留|
|G03|事实|1|0|0|提问，原范围内未知不能被当成现实否定|
|G04|自然支持|0|0|1|当前用户自述；offer不能升级为已完成帮助|
|G05|自然支持|0|8|0|当前另有自述，但不供给所列可选历史原子|
|G06|自然支持|0|2|0|问候、简短近况和反问；历史执行及事件同一性仍未知|
|G07|构造联合|2|2|1|明确回忆引文；可回答所引决定，当前未给出另一必答细节|
|G08|构造联合|2|2|2|笔记引文；可回答笔记所述安排和时间，不能推成实际执行|

G08两原子共用同一段出现文字，故共4个按原子出现实例实际对应3个独立出现位置；不按独立样本计。8题的12个可见话轮均已审阅，评审者为 **Codex /root/rs**，身份是参与过任务/评价开发的助手来源审阅者，不是独立真人或通用Judge。本核查不包含新生成回复，也不是随后固定8输出的回复审阅。

当前自述、引用、提问、假设分别保留。引用并非一概无效：当原任务明确要求说明给定引文的内容时，它可以成为有界的任务前提；这不使它成为新的独立现实经历或执行证据。无具名绑定审阅时，当前文字匹配返回unknown，不自动通过。历史取得与当前可见是两条供证路径，合并时OR去重。

## 2. 旧计数与严格计数并列

下表为冻结BM25诊断，8题共9个必答原子，其中1个原本没有正向充分组。自然任务另有可选背景，未强加必答回忆。Direct仅适用于5个事实/联合题；其9个必答原子与前述9个同源，不增加独立样本。

|原条件|旧全文匹配覆盖|严格覆盖|严格历史供应覆盖|当前有界前提覆盖|未知|
|---|---:|---:|---:|---:|---:|
|仅当前可见|3/9|3/9|0/9|3/9|1/9|
|首个检索单元|5/9|5/9|5/9|3/9|1/9|
|首轮Top4窗口|7/9|7/9|7/9|3/9|1/9|
|同query第二轮|7/9|7/9|7/9|3/9|1/9|
|首轮Top4完整父会话|8/9|8/9|8/9|3/9|1/9|
|全合法池（可用性诊断）|8/9|8/9|8/9|3/9|1/9|
|Direct原recipe|8/9|8/9|8/9|3/9|1/9|

历史与当前列有重叠，不能相加。全池条件不表示预算可达或合法策略；原每条件capacity与token计量照录，没有重排或重算排名。旧time-lexical的必答列相同；其完整父会话可选背景覆盖与BM25不同，详见101行公开并列表。可选背景被供给也不要求在自然回复中复述。

供证不等于蕴含成立、实质回答、支持适切或任务成功；日历推理假设没有因坐标正确获得语义资格。全部 `task_success/formal_reward=null`。未知保留，没有借负结果停跑或重选题。

## 3. 实际运行后的复用接口

新增纯CPU模块 `ge2_source_coordinate_audit.py` 不导入模型或冻结执行器：

```python
strict_supply(
    evaluation['required_atoms'], pool['records'],
    receipt['read_intervals'], task, current_review,
)
# DirectEvidence：先 direct_intervals(receipt['source_recipe'])
```

`current_review` 从私有 `CURRENT_SOURCE_SEMANTIC_REVIEW_PRIVATE.jsonl` 按task_id选择，绑定完整task及EvalSpec SHA。函数返回逐原子历史坐标供应、当前任务范围供应和合并三值结果；公开报告只输出计数/别名/哈希。调用者必须先验证实际receipt、请求payload与合法池身份，并确认实际渲染到G输入。该函数不能把自报区间变成实际输入证明；本轮CPU条件也不能冒充未来真实政策轨迹。

## 4. 验证与产物

新增13项CPU测试全部通过，包括同文字错speaker、同speaker错turn、错record、Unicode字符/字节混淆、布尔坐标、组内上下文缺失、unknown保留、当前提问与引文区别及审阅身份绑定。合成反例中旧substring会误计供证，新严格函数拒绝；没有修改旧谓词或旧分数。

复跑：`PYTHONPATH=project/src python -m pytest -q project/tests/test_rl1v3_journal_ge2_source_coordinates.py`。源核查CLI为 `project/scripts/rl1v3/journal_audit_ge2_source_coordinates.py`，参数 `--bundle/--cpu/--current-review/--out`，out要求新目录。冻结输入、代码和私有产物SHA见同目录 `SOURCE_COORDINATE_MANIFEST_PUBLIC.json`；101条件计数见 `SOURCE_COORDINATE_COMPARISON_PUBLIC.jsonl`。私有完整引用、原坐标和具名语义理由留在运行根，未复制到公开仓库。

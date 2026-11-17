# C0 统一契约施工结果

2026-11-17；级别 engineering_only；状态：代码完成、待 B 审阅与集成冻结。基线 75689002846996555724307039649c656f3c1e71，分支 pmrl1-v3/ws-a，独立工作树 /home/tokkio/Metacom5_3-ws-a。PR #4 开工核对仍 open；H0、adopted_by_researcher 与 EXECUTION_STATE 未改。

已实现全部要求对象及可见 Observation/VisiblePrefix，25 个 frozen dataclass、25 个 JSON Schema、规范 JSON/SHA256、严格编解码、只写一次/同字节恢复和输入/代码/输出 manifest 校验。SourceSpan 精确核对 Unicode 偏移、原话、角色、owner/session/rank、turn hash、source_key；时间语义、未知、建议阶段、RS 风险与负例、私有字段拒绝有约束。共享字段解释和待 B 审阅点见 INTERFACE_ZH.md。

针对性 pytest：**104 passed，0 failed，0 skipped**。包含 25 种契约正例、33 个错误样例，额外检验所有 schema 拒绝未读内容字段、所有 TerminalKey 字段变更失效、时间更正不冒充事实有效期、legacy prefix 适配、manifest 防篡改、未知值和 Unicode。可回放 fixtures.json → replay.json：25 accepted / 33 rejected。所有例子都是确定性契约 fixture，不是生成的研究用户或模型结果。

完整 CPU Paper-1/RL1/V3 suite 在提交时仍运行，结果后续另行追加；不预报 CI 成功。CI workflow 只增加 test_rl1v3_*.py 纳入原阻塞测试命令，不禁用任何旧测试。

实际问题与修复：文档默认 paper1-judges-py312 无 pytest；paper1-py311 有 pytest 但缺 jsonschema。使用已存在的 pmrl1_validation_vendor_20261103（含 cp311 rpds）通过 PYTHONPATH 提供依赖，未安装/升级冻结环境。旧 PrefixSpec 实际字段为 cut_after_turn_index，适配器按实际字段写并通过测试。没有 GPU、模型加载、推理、训练、付费或人工评价。

复核命令（仓库根目录）：

```bash
export PYTHONPATH=project/src:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103
PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
$PY -m pytest -q project/tests/test_rl1v3_contracts.py -o addopts=
$PY project/scripts/rl1v3/c0_export_schemas.py --check
$PY project/scripts/rl1v3/c0_replay_contracts.py --input project/outputs/pm_rl1/v3/C0/fixtures.json --out project/outputs/pm_rl1/v3/C0/replay.json
```

manifest.code_sha 记录施工起点，code 数组逐文件 SHA 精确绑定本次实际代码，避免自引用 commit hash。manifest 不包含运行中的全套日志；最终日志完成后另写验证记录。来源为现行主方案、RESOURCE_SPEC 与交接文档；未消费任何评测 gold 或旧禁用合成资料。

下一步：B 审阅 C0，集成负责人合入；A 在等待期间完成 A0 CPU 盘点与 OFF 吞吐请求准备。依交接门槛，A1/A1b 尚未开工，后续 source registry / bank-v0 接口不能标完成。

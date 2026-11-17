# WS-A C0/A0 最终 CPU 验证

2026-11-17。被测代码 HEAD=`fa52e74d622b7456d43b543c78dac087082612e7`；本提交仅追加完成的验证证据，不改代码。

完整本地命令：

```bash
PYTHONPATH=project/src:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103 \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest -q -m 'not gpu' \
project/tests/test_paper1_*.py project/tests/test_rl1_*.py project/tests/test_rl1v3_*.py -ra -o addopts=
```

实测结果：**1950 passed，0 failed，1 skipped，11 deselected，469.22秒**。唯一skip为原测试依赖的 `/home/chenzhi/paper1_runs/frozen_tokenizers/llama31_8b_instruct_tokenizer.json` 不存在；11个GPU标记按既有non-GPU命令排除。新C0为104项、A0为13项，全部通过。首次全套2失败及第一次不完整修复2失败原日志均保留，最终没有禁用这些断言；修复说明见上级 VALIDATION_REPAIR_ZH.md。

另已通过：新模块/脚本 compileall；现有 integration_base/outcome_lock 检查（failed_checks=[]、outcome_calls=0）；25 Schema 与代码完全一致；C0/A0最终交付manifest校验；100条OFF请求实际重建SHA=`de354844a41ac5de6ae58040507af3416db91d33923abd51f32f2cbbc8c71070`，与交付字节相同。代码/配置/Schema的git diff --check通过；原始pytest失败日志内的trailing whitespace按原字节保留，没有为了格式化改写证据。

独立提交：C0 `50c9ade0`；A0 CPU `92368ec8`；历史测试工作树适配 `fa52e74d`。提交审阅入口为 PR #5，目标integration。C0首个CI run 44038668594已通过；后续head状态以GitHub Actions为准，不用前一个run冒充新head。

B现在可调用共享冻结候选类型、strict JSON编解码、SourceSpan.verify、PrefixSpec.from_legacy/visible、SHA与manifest接口；还可复用A0候选模型身份和100条真实OFF请求。**source_registry/bank-v0/search/read/request_packet未交付。** 按STARTUP_HANDOFF §2–3，C0需B审核并由集成负责人合入，之后A才开工A1→A1b；当前没有这个合入事实，因此没有跨越依赖。C0字段仍为初次提交版本，未擅自冻结或改变。

A0的GPU吞吐/峰值显存/QLoRA测试与规模选择仍未完成。真实资产为既有EvoEmo隔离runtime、P1 train/dev前缀和本地Gemma/Qwen/BGE文件；没有新编译来源库，也没有生成、训练或付费。A0第一次分词失败和Mapping修复复跑分别保留，最终报告在A0/repair_1/ENV_REPORT.json。

PR #4未合并；H0、adopted_by_researcher、全局EXECUTION_STATE、Paper-1冻结资产均未修改。下一可推进动作是B的C0审阅/集成；新的100请求GPU吞吐执行才需要研究者对明确范围授权及临近执行的指定卡占用检查。

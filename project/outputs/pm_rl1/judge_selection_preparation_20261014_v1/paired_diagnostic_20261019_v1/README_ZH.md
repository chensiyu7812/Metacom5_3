# PM-RL1 八题配对诊断离线交付

当前120次；准备已完成，真实运行未授权。协议 `paired-source-check-v1-20261019` / `f871e7eaacab4382a322646f915f3103e3674816ffba44f4bf095e2041f33e0c`。

1. [执行协议与一次启动申请](START_APPLICATION_ZH.md)：主要阅读入口。
2. [八题核对清单](package/CHECKLIST_ZH.md)：原人评不改；英文、原答与来源分别保存在配套JSON及sources。
3. [34项mock测试回执](tests/test_receipt.json)与[预算回执](package/budget_receipt.json)：工程覆盖和不能保证的部分。
4. [独立验证元数据](VALIDATION_METADATA_ZH.md)：库存和暴露边界。

实现文件 paired.py、live.py、prepare.py 是既有runner的版本化扩展，复用原transport、预算账本、v2最终schema/解析器和外层接口。第一步接口新增；旧运行文件不改。包内不含密钥、未公开新验证文本或封存答案。

home副本用于阅读与审阅；实际执行必须使用仓库中的固定路径，以验证原始来源和旧代码的哈希。此包不包含旧大仓库，不能作为脱离仓库的独立运行环境。

离线验证（无需密钥/网络）：
```sh
cd /opt/tokkio-data0/tokkio_projects/Metacom5_3/project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/paired_diagnostic_20261019_v1
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python paired.py
```

真实运行只在研究者批准本协议后，由后续任务保存链接本次批准的APPROVED.json，再使用 `paired.py --live --approval <批准文件路径>`。不要把PENDING文件自行当作授权，不使用旧D剩余额度。

预计新增调用0（当前）；测试内24请求均为临时目录里的合成数据，不计真实账本。前后历史校验另见provenance/final_verification.json。原始人评、补充解释和分析者核查始终分开；不需研究者重填。

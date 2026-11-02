# 离线复算与测试

工作目录`/home/tokkio/Metacom5_3`。以下准备命令只加载已有本地tokenizer，真实模型、BGE编码、G/J、优化器及人评均不执行。输出路径须为新目录，不能覆盖旧回执。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 \
PYTHONPATH=/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929:project/src \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -u \
project/scripts/rl1/138_prepare_organized_policy_interface.py \
--output project/outputs/pm_rl1/organized_policy_interface_NEW_REPRODUCTION

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -ra \
project/tests/test_rl1_organized_policy_interface.py \
project/tests/test_rl1_resource_organization.py \
project/tests/test_rl1_resource_evidence_views.py \
project/tests/test_rl1_observation_features.py \
project/tests/test_rl1_learning_preparation.py \
--junitxml=/tmp/pmrl1-organized-interface-20261102-tests.xml
```

实际准备目录`project/outputs/pm_rl1/organized_policy_interface_20261102_v1/`，退出0；完整输出、代码与来源hash都在其manifest中。54项测试通过，退出0；公开目录保留pytest.xml和验证记录。

轨迹中的6个MS只是工程探针，不是读取上限或正式Fixed-Dev策略。114条逻辑轨迹分别在顺序、预承诺程序、NoText三路重放；没有三个不同质量结果，也不计为新的研究训练样本。720块只是编码输入，未有720次BGE调用。

`organized_interface_handoff_20261102_v1/`保存10个已用RS的来源缺口和S/A开发材料交集：采用旧审计允许的canonical alias/split/stage材料以及已隔离dev前缀，按完整(role,text)序列匹配；未读原始混合语料、sealed或金标。其`INPUT_HASHES_PRIVATE.json`绑定所有输入，`OUTPUT_MANIFEST.json`绑定结果；内容材料不随公开报告上传。

可确认的结果为：准备和测试通过；真实模型及训练因本轮范围未执行；J资格因独立参照未回收、真实验证未执行而仍未成立。不能用这三个不同状态互相替代。

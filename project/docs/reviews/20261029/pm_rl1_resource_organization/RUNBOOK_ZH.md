# 资源组织原型：执行与复查

唯一计划入口：[PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md](../../../PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md)。实现范围与研究限制见[组织修订](RESOURCE_ORGANIZATION_ZH.md)。原始结果留在本机私有输出，不复制到公开仓库。

## 本轮实际命令

在 `/home/tokkio/Metacom5_3` 执行：

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/131_prepare_resource_organization.py \
--output project/outputs/pm_rl1/resource_organization_20261029_v1 \
--tokenizer-dir /opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -q \
project/tests/test_rl1_resource_organization.py \
project/tests/test_rl1_temporal_evidence_ledger.py \
project/tests/test_rl1_environment.py \
project/tests/test_rl1_representation.py \
--junitxml=/tmp/pmrl1-organization-tests.xml

python -m py_compile project/src/metacom_pm/rl1/resource_organization.py \
project/scripts/rl1/131_prepare_resource_organization.py

git diff --check
```

准备入口退出0，主体41.36秒；这是离线CPU、tokenizer、文件读写和检索时间，不是新G/J推理时延。完整日志为 `/tmp/pmrl1-organization-v1.log`。53项定向测试通过、无skip。最初一次单文件测试9过1失败，是断言`source-a`误匹配了指导语中的`source-attributed`；改为检查完整引号包围的ID后通过，不是数据或模型能力失败。

重跑必须给新输出目录，拒绝覆盖旧目录。默认只读取上轮 `reorganization_20261029_v4` 的登记输出及其输入allowlist；相关hash不符立即失败。缺私有材料时不能运行完整数据准备，但合成测试不需要它们。没有任何模型下载、推理或付费回退。

## 文件用途

私有根目录：`project/outputs/pm_rl1/resource_organization_20261029_v1/`。

| 文件 | 复核用途 |
|---|---|
| `RS_LIBRARY_PRIVATE.json` | 13,172条共享动作及8类目录，一份库、多前缀引用；没有新fit/reward标签 |
| `catalogs_private/<prefix>.json` | 前缀身份、RS引用、MP/ME/完整MS记录及私有目录/结构边；不能直接传入actor |
| `CATALOG_MANIFEST.json` | 114个实例身份、逐head数量、额外MS位置数和完整/部分来源覆盖 |
| `CONSTRAINT_ABLATION_PRIVATE.json` | 1,704个旧候选位置的2×2可达性对照，同旧renderer；不含奖励 |
| `RETRIEVAL_TRACES_PRIVATE.json` | 固定head离线读取轨迹与读后检索变化；不是策略rollout或模型回复 |
| `PROFILE.json` | 汇总与限制，公开副本字节一致 |
| `INPUT_HASHES_PRIVATE.json` | 所有实际读取输入的hash；无mixed/test/sealed输入 |
| `SOURCE_CODE_HASHES.json`、`OUTPUT_MANIFEST.json` | 复算代码身份、122个产物hash |
| `PROTECTED_HASHES.json` | 旧执行合同、费用账本、人评原件前后不变 |

共享RS库中没有预先计算的未来适用性；全库查找只在检索/构造侧。`OrganizationSession.observe()`只返回公开前缀、已取正文和实际用量，不返回目录或未取证据。`receipt()`属于审计域，不能作为网络输入。

读取流程可以直接按地址跳到MS候选，也可以用`get(head)`触发基于当时公开/已取信息的词项检索。正文永不截断，超出原生上下文时报明确错误并保持取得状态不变，不静默换成较短候选。旧BGE相似度保留在独立字段，新排序绝不伪装成BGE。

## 历史尝试登记的使用

[ATTEMPTS_ZH.md](ATTEMPTS_ZH.md)列32条主要路线；[ATTEMPT_REGISTER.json](ATTEMPT_REGISTER.json)给出来源hash、25条原时间线、保留/关闭/未运行状态与重新尝试的证据要求。登记覆盖机制和阶段，不声称逐请求重审了历史全部运行。

后续修改先引用相关route ID，例如J13关系参照、J15实际请求合同、O01资源可达性；明确变化和成功/失败出口。只修代码的工程回归无需新人工问卷；开放式语义能力不得由同一实施者无独立参照自证。既有有效分项可以保留优化，不因未解决全部评分问题而否决。

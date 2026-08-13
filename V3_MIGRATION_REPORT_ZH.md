# MetaCom V3 独立工作区迁移报告

日期：2026-08-13
目标：`/home/tokkio/metacom_workspace/metacom_v3`

## 迁移结果

V3 已从当前最新工作树 commit `ef318c3e35982e277883e06c5ec25cc7392eab67` 建立为独立 Git clone，分支为：

```text
work/v3-research-program-20260813
```

新工作区没有修改或删除 snap 源目录，没有复制源 `.git`、5.2GB virtualenv、缓存、secrets 或完整 3.3GB ignored outputs。

## 迁移方式

- Git：`git clone --no-hardlinks --no-checkout` 后 checkout 精确 source commit；
- remote `origin` 指向 `chensiyu7812/Metacom5_3`，旧 review remote 保留为 `legacy-review`；
- 最新有效 private evidence 选择性复制到 `private_evidence/current_20260813/`，并由 `.gitignore` 禁止上传；
- private evidence 共 12 个目录、29 个文件、1,994,348 个文件内容字节；确定性组合 SHA-256 为 `355203e7ef433c469a921cb81ca29115131b077cd5821b96bd3cc5407afa5282`；
- 对源和目标执行 `rsync --checksum` dry-run，结果为零差异。

## 可运行性

在 V3 clean clone 中，使用原 Python 3.13.2 依赖环境但强制 `PYTHONPATH=src`：

- V4 response program；
- external treatment stress test；
- MS pre-decision；
- source-aware Risk；
- MP rule/profile delta；
- MS/MP V1.1 gate

共 39 个 active tests 全部通过。

另有14个ESC-RANK strict-parser/runtime-overlay测试和11个V3 authority、evaluation-freeze、official-benchmark、public-1427、same-stack reference、margin-phase与private-evidence consistency测试通过；合并验证为64 tests passed。

完整 legacy pytest 不能作为 clean-clone release gate：它读取大量未提交历史 outputs、已消费人评包和阶段性 materialization。缺失路径导致大量预期失败和 11 个 setup errors；这说明旧测试缺少 active/replay 分层，不说明 V3 path relocation 破坏代码。

## 未直接迁移

- 失败、空白或方法失效的人评包；
- 未跟踪的旧 HTML report；
- 旧 virtualenv；
- 旧 outputs 全树；
- secrets；
- caches。

历史证据仍可从 snap 或 artifact vault 追溯；V3 authority 不再依赖它们作为当前运行前置条件。

## 新入口

- 总方案：`project/docs/V3_MASTER_RESEARCH_PROGRAM_ZH.md`
- Evaluation plan：`project/docs/V3_EVALUATION_BENCHMARK_PLAN_ZH.md`
- Evaluation freeze audit：`project/docs/V3_EVALUATION_FREEZE_AUDIT_20260813_ZH.md`
- Dataset cards：`project/docs/V3_DATASET_AND_EVIDENCE_CARDS_ZH.md`
- 机器权威：`project/data/v3_authority/v3_research_authority_v1.json`
- Evaluation 硬门：`project/data/v3_authority/v3_evaluation_freeze_contract_v1.json`
- 迁移矩阵：`project/data/v3_authority/v3_asset_compatibility_manifest_v1.json`
- 验证器：`project/scripts/v3/00_validate_v3_workspace.py`
- 可审阅总报告：`project/reports/v3_master_research_program_20260813/report.html`

# 离线复算与交付文件

本轮目录与脚本只用于当前已批准的 train/dev 离线范围。不得为了补缺失文件去打开 mixed/test 原始容器，不得自动调用 embedding/G/J。公开仓库没有私有输出时，合成测试可跑，实际审计会明确失败关闭，不能用公开统计代替逐条原文。

## 已执行命令

工作目录 `/home/tokkio/Metacom5_3`，实际解析为 `/opt/tokkio-data0/tokkio_projects/Metacom5_3`。现存 Python 环境是 `/tmp/pmrl1-publication-20261022-venv/bin/python`；使用其 tokenizer 库，没有安装依赖或下载模型。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python \
project/scripts/rl1/130_audit_resource_opportunities.py \
--output project/outputs/pm_rl1/reorganization_20261029_v4 \
--tokenizer-dir /opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=project/src \
/tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -q \
project/tests/test_rl1_temporal_evidence_ledger.py \
project/tests/test_rl1_environment.py \
project/tests/test_rl1_representation.py \
--junitxml=/tmp/pmrl1-reorganization-tests-final.xml

git diff --check

python -m py_compile \
project/src/metacom_pm/rl1/temporal_evidence_ledger.py \
project/src/metacom_pm/rl1/resource_opportunity.py \
project/scripts/rl1/130_audit_resource_opportunities.py
```

实际审计 stdout/stderr 保存于 `/tmp/pmrl1-reorganization-20261029-v4.log`。第一次失败及 v2/v3 中间成功均保留；最终 v4 为报告统计源。**复跑必须另给一个不存在的新 output 目录**，已有目录会退出，不覆盖旧运行。缺输入时先写 `FAILURE.json` 并非零退出；不能把它解释成该研究方法失败。

另以 Python `subprocess.run` 执行两项 CLI 失败关闭检查：`--project <新建空目录> --output <新建目录>/missing --tokenizer-dir <不存在目录>` 应在读取首个合同阶段退出 1、记录 FileNotFoundError；`--output <现存v4目录> --tokenizer-dir <不存在目录>` 应在任何读取/加载前退出 1，报告不可覆盖。两项均符合预期，属于通过的错误路径检查，不是两个研究运行失败。随后核对245个输出文件、8个源码文件和3个保护文件 hash，全部一致；结果记入 `VALIDATION.json`。

## 输入边界

入口显式读取冻结的 `outputs/pm_rl1/completion_20260930_v2/P1` 库存/容量/投影，P2 common_pool 请求与 raw 回复，P3 common_evidence 的 42 份合法 train/dev 证据、已打开开发人工记录和根因 case 引用，以及当前方案/预算/预备材料。`INPUT_HASHES_PRIVATE.json` 给出逐文件 SHA256；freeze manifest 和输入读前/读后检查失败立即停止。

脚本不打开 `es_memeval_public_sanitized_runtime_artifact_v1.json` 或 sealed/test 标签。完整原文覆盖缺口不补加载。tokenizer 仅 `local_files_only=True`、`trust_remote_code=False`，核对固定 tokenizer SHA 与 active renderer identity；无 AutoModel、BGE 或服务回退。

## 输出与审阅位置

以下文件位于 `project/outputs/pm_rl1/reorganization_20261029_v4/`，含原文的文件保持私有。候选和回复的引用通过 prefix/request/hash 关联，不按文件名猜测同一实验。

| 文件 | 用途 |
|---|---|
| `PROFILE.json` | 汇总、边界、实际时长；公开副本与私有字节一致 |
| `CANDIDATE_LEDGER_PRIVATE.json` | 1,704 个候选位置，库存 pointer、来源核对、成本/可达性、未核验字段 |
| `CAPACITY_PRIVATE.json` | 每个前缀的 70 数量计划、库存可用性、fits 与逐步 reachable；未测效用不出现 |
| `RESPONSE_LEDGER_PRIVATE.json` | 586 个请求/原文路径、绑定、人工对照引用；q/m 保持 null |
| `MATCHED_CONTRASTS_PRIVATE.json` | 593 条单候选增量对照边；未认定质量效应 |
| `DOMINATED_PRIVATE.json` | 52 个同评分内容更高成本计划及较便宜已测参照 |
| `EXECUTOR_PAIRS_PRIVATE.json` | 53 组 base/LoRA 同输入身份；不充当金标 |
| `CASE_LEDGER_PRIVATE.json` | 历史 11 项来源 hash、本轮 3 项案例及逐条证据表指针 |
| `SHARED_SPANS_PRIVATE.json` | 47 组共享精确跨度；语义等价未核验 |
| `OWNER_SUMMARY.json` | 逐 owner/分 split 覆盖和阻塞；不用 prefix 数替代 owner 数 |
| `ledgers_private/`、`queries_private/` | 114 个时点绑定索引和示范来源定位；仅构造域，不能给 actor 未取正文 |
| `J1_READINESS.json` | 22 条初评重建状态、原预算提案、动态请求/资格/人工缺口 |
| `INPUT_HASHES_PRIVATE.json`、`SOURCE_CODE_HASHES.json` | 读取的输入与复算代码 SHA256 |
| `PROTECTED_HASHES.json`、`OUTPUT_MANIFEST.json` | 执行合同/账本/原人评包未变，以及输出文件完整性 |

公开 companion [audit.ipynb](audit.ipynb) 从最终私有账本重新核对计数、MS 阻塞例子和 GET 后合法分支，不显示私人原文。其单元已按顺序用 Python 执行并保存输出；未依赖或启动 notebook kernel/model 服务。`VALIDATION.json` 和 JUnit 摘要记录实际结果。

## 新模块接口

`TemporalEvidenceLedger(prefix, turns, provenance_identity=...)` 创建时检查合法输入；`span`/`locate_quote` 验证精确来源；`add_claim` 只映射有依据的现有记录，语义默认未核验；`lookup` 返回定位和独立词项排名；`export` 生成内容身份。图关系 schema 保留但本轮真实实例关系为 0，不能宣称实现了自动事件链理解。

`resource_opportunity.capacity(spec, renderer)` 与既有环境逐步可达性一致；`candidate_capacity` 将单候选假设成本与现规则必须先取得的累计成本分开；`measured_contrasts` 只接受同前缀/G/renderer/J依据的单候选增量；`dominated_same_input` 不填任何未合格分数。

全部新文件是旁路。当前 `schema.py`、环境、主 renderer、G/J 配置、measurement freeze 和 execution_contract 未修改。

## 四类状态

1. 已运行且通过：v4 全覆盖机械审计、原池身份/token 核对、确定性索引/查询、22 初评构造、定向合成测试、输出/保护 hash 核对。
2. 运行失败：v1 原始 turn ID 与盲化位置混用的审计适配错误，保留失败；修复后唯一引文定位通过，但原始 ID 映射仍未验证。
3. 因输入缺失未完成：194 个 memory 位置原文核验、top4 外 BGE 排名重建、完整语义金标、新人评回收。
4. 因授权范围未运行：新模型加载/编码/生成/评分，任何训练，人评扩张，sealed/test 揭封，主版本替换，P4、merge/ready。

交互期间 mixed JSON 输出事件是额外研究暴露记录，见 [EXPOSURE_INCIDENT.json](EXPOSURE_INCIDENT.json)；不能用“脚本不读 test”掩盖该事件。实际代码验证结果与研究资格/收益结果分开报告。

# A 线 WP2 评价实现与执行交接

评价规则在查看真实模型输出前由 `629d20f7` 冻结，SHA256 为 `18d863f6f9547040c7d11aab85c4a68e501560dd7e0fa113962f7e1d40474cd3`，见 [WP2_EVALUATION_RULES.json](WP2_EVALUATION_RULES.json)。本文件记录已执行的实现和命令；2026-11-28 已完成真实模型终局评分与结果审查，见 [A_WP2_RESULTS_ZH.md](A_WP2_RESULTS_ZH.md) 和 [完整数表](wp2_results/statistics.md)。1,618/1,788 个可执行位置完成，1 次失败、169 个未执行、132 个结构性位置分别保留。

## 实际实现

`evaluate_wp2.py` 验证原数据冻结、执行 manifest、逐请求/模型/运行身份、导出文件 SHA256 和账本封存头，随后调用未改变的 PersonaMem 官方 MCQ 解析器。每个条件必须交付全部 240 个槽位，包括结构性不可评价和未执行位置。原单条件 scorer 已修复 C/D `not_evaluable` 合法空 request hash 被误拒的问题。

报告同时给出完成准确率、预定可评价分母、完成率、超时/运行错误/返回校验失败/中断/未执行/容量错误、解析失败、有效错误答案及固定分母敏感性。失败和结构性缺失的正确性为 unknown；只有固定分母敏感性将技术未完成计为零成功。长度停止仍按官方解析评分，另给 EOS-only 结果，不宽松修复答案。

A/B 全 240、四臂共同 207、Direct 缺失 33 分开；180 代表性和 60 困难层及其 Direct 交集分开。跨条件/模型只比较同一任务集合，记录完整配对、修复、退步、persona bootstrap 95% CI 和固定 8 组的 Holm 校正 McNemar p 值；类别为描述性分析。另有四臂/八单元共同完成表与未完成结果的上下界，避免仅比较完成样本的边际准确率。

`evidence_audit.py` 从实际合法历史核对每个送达 source id/hash，并把 B 的参考缺失按 user/nonuser 分开；不从覆盖率推断回答能力。`report_wp2.py` 仅接受真实 model 聚合结果，拒绝 plumbing 作为模型报告。原始预测、逐题评分及请求变更映射仅写本地私有目录。

`review_wp2_errors.py` 仅接受终局 model 封存，重新验证已评分记录，按冻结规则生成全部 C/D 错误与 B→C、C→D 正误变化的任务并集。私有审查材料含合法 Direct 原文、坐标、实际 D 请求和原始输出；公开输出只含可观察的解析/有效错误及转移计数。语义原因必须另经原文审阅，程序不会按关键词推断归因，也不会修改主评分。

## 与 B 的实际版本核对

[A_WP2_JOINT_RECEIPT.json](A_WP2_JOINT_RECEIPT.json) 对照原 CPU manifest `9839c088…` 与执行 v2 `c370103c…`：487 个冻结文件逐字节 hash 全部保持，240 题、答案、选项排列、历史、Direct 207/33 均未变；两模型内的任务/条件次序不变，模型运行先后改为 Qwen35、G0e。新预算为 57,600 秒总计、每模型 28,800 秒、1,920 次物理尝试，两模型各自前 16 次技术烟测计入预算。

B 的 speaker/subject、更新适用范围和遗忘指代修复符合 D 的既定投影+指导构念。公共 RAW 增加说话人说明还改变了 A 的 170/480、B 的 94/480 槽位所选记录；全部 A/B/C 可执行请求 hash 相应变化。这项变化已明确记录，不能声称只有 D 请求变化。A 在启动前建议保留原 RAW 行，但检查账本元数据时 v2 已开始执行，因此保持实际运行条件，不在中途修改。该变化未改原始题目、历史、检索方法或共同 8192 evidence budget；它是最终 v2 的公共渲染版本差异。

实际核对 v2：两模型的 B 在 207 个 Direct 可定位任务中仍全部保留用户参考记录，但 **207/207 均缺其他说话人的参考记录**。C/D 的送达 ids/hash 与原完整合法 Direct 坐标一致，D 的 414 个可执行请求有新 hash，旧请求文件保留。B→C 同时改变非用户上下文和无关信息量，不能仅凭此对照将差异因果归为“噪声”或“检索遗漏”。

A 已通过 PR #31 评论及共享 `handoff/A_WP2_EVALUATION_STATUS.json` 交接评价冻结和导出契约。B 独占 GPU 运行职责；A 未加载模型、未调用 API、未训练或打开正式测试。另已向 B 指出 session 终局计时写在 worker close 前的成本遗漏，最终成本需计入 teardown；不回写旧账本。

## 已执行验证与可复跑命令

本地原数据/新评价回归 33 passed；`8de35594` 的 [NAA CPU CI](https://github.com/chensiyu7812/Metacom5_3/actions/runs/46026871974) 与 [PM CI](https://github.com/chensiyu7812/Metacom5_3/actions/runs/46026871951) 通过。一次真实冻结材料与原 B plumbing 导出的接口联调处理 1,920 槽位、1,788 plumbing 完成、132 结构性位置，8 个主比较的配对数为 240、240、207、207、207、207、207、207；11.659 秒。随后已用实际 v2 plumbing 哈希链跑通封存→评价完整接口，1,788 次 plumbing 调用对应 1,920 完整槽位。两次都是接口验证，没有模型能力成绩，也没有重复 GPU 资格验证。

`seal_wp2_export.py` 不依赖 B 改动当前运行器：只读账本、校验 hash chain、取首个有效结果，保留 timeout/invalid/interrupted/unattempted 和所有失败尝试。附实际 token/生成时间/内部首 token 计时及账本 GPU 秒；未知延迟不填零，v2 teardown 未计入部分明确单列限制。`watch_wp2_evaluation.py` 已作为独立 CPU 后处理启动，禁用 CUDA；等待 B `RUN_SUMMARY` 后才封存/评分/生成本地表格，中途只输出技术完成计数。它不启动 GPU、不修改推理、不给训练授权，也不自动对外发布。该 CPU 后处理已在 B RUN_SUMMARY 后完成；本轮研究解释与唯一 WP3 建议已提交结果报告。旧 PROGRESS 中 accuracy_inspected=false 仅描述运行期间技术监测状态，不描述最终研究审阅。

以下命令在 A worktree 的 `project/` 中运行。私有材料根目录记为 `NAA=/opt/tokkio-data0/naa/20261127`；普通 Python 环境为 `$NAA/venv/bin/python`。

```bash
PYTHONPATH=src "$NAA/venv/bin/python" -m pytest -q tests/test_need_aware_data.py tests/test_need_aware_wp2_evaluation.py

PYTHONPATH=src "$NAA/venv/bin/python" scripts/need_aware/audit_wp2_freeze.py \
  --artifacts "$NAA/artifacts" \
  --policy docs/need_aware_agent_20261127/WP2_EVALUATION_RULES.json \
  --old "$NAA/agent_b/manifests/wp2-final" --new "$NAA/agent_b/manifests/wp2-exec-v2" \
  --out "$NAA/evaluation_wp2/joint-audit-v2"

# 下列评分命令须使用 B 完成封存的 export；不能指向正在写入的结果。
PYTHONPATH=src "$NAA/venv/bin/python" scripts/need_aware/evaluate_wp2.py \
  --artifacts "$NAA/artifacts" --manifest-dir "$NAA/agent_b/manifests/wp2-exec-v2" \
  --export-dir "$SEALED_EXPORT" --out "$NEW_EVALUATION_OUT" --kind model \
  --policy docs/need_aware_agent_20261127/WP2_EVALUATION_RULES.json
```

实际未通过的检查也保留：第一次版本审查把两模型整体执行顺序误作必须不变，因 Qwen35 优先而报错；改为核对各模型内部冻结顺序并明示模型调度差异。预执行 RAW 一致建议不作为新增审批门；最终审核以用户要求的原任务/答案/选项/历史不变、合法证据及四条件构念为边界。评价指标、官方解析、预定样本和预算没有根据模型答案调整。

错误审查新增回归首次执行漏设 `PYTHONPATH=src`，collection 报 `ModuleNotFoundError: metacom_pm`；使用上面的完整命令重跑后 33 项通过，没有删除或跳过测试。

当前未执行边界：170 个可执行位置因 Gemma 预算终止未完成，其中 1 个尝试失败、169 个从未调用；开放生成评价、WP3 推理/训练未执行。严格评分、失败分解、跨模型配对及单一 WP3 建议均已交付。B 报告中的未完成计数及 EOS 边际比较纠正已通过 PR #31 评论和本地 handoff 发送；A 终局结果以本次封存与配对表为准。


## 已执行的真实终局后处理

自动 CPU 后处理使用以下参数（输出目录已经存在且封存，复跑时必须换新目录，禁止覆盖）：

```bash
NAA=/opt/tokkio-data0/naa/20261127
FINAL="$NAA/evaluation_wp2/automatic-v2-terminal-final"
PYTHONPATH=src CUDA_VISIBLE_DEVICES= "$NAA/venv/bin/python" scripts/need_aware/watch_wp2_evaluation.py \
  --artifacts "$NAA/artifacts" \
  --policy docs/need_aware_agent_20261127/WP2_EVALUATION_RULES.json \
  --manifest-dir "$NAA/agent_b/manifests/wp2-exec-v2" \
  --ledger-root "$NAA/agent_b/runs/wp2-exec-v2-model/model" --out "$FINAL"

PYTHONPATH=src "$NAA/venv/bin/python" scripts/need_aware/review_wp2_errors.py \
  --artifacts "$NAA/artifacts" --manifest-dir "$NAA/agent_b/manifests/wp2-exec-v2" \
  --export-dir "$FINAL/sealed" --scored-dir "$FINAL/scored" \
  --out "$NAA/evaluation_wp2/error-review-v2"

PYTHONPATH=src "$NAA/venv/bin/python" scripts/need_aware/check_wp2_format.py \
  --export-dir "$FINAL/sealed" --upstream "$NAA/upstream/PersonaMem-v2" \
  --out "$FINAL/FINAL_FORMAT_DIAGNOSTIC.json"

PYTHONPATH=src "$NAA/venv/bin/python" scripts/need_aware/close_wp2.py \
  --manifest "$NAA/agent_b/manifests/wp2-exec-v2/MANIFEST.json" \
  --aggregate "$FINAL/scored/aggregate.json" \
  --ledger-dir "$NAA/agent_b/runs/wp2-exec-v2-model/model" \
  --out "$FINAL/TERMINAL_RECEIPT.json"

PYTHONPATH=src "$NAA/venv/bin/python" scripts/need_aware/report_wp2.py \
  --aggregate "$FINAL/scored/aggregate.json" --out "$FINAL/MODEL_STATISTICS_FINAL.md"
```

结果：watcher 收到 STOPPED 终局后封存并评分；175 个源审查包生成成功，重新核验冻结材料及逐题评分无差异；1,618 条真实输出与官方方法解析一致；终局重算 1,619 次物理尝试、1,618 次完成、132 个结构性位置。所有发布统计与本地原文件 SHA256 一致。[终局回执](wp2_results/terminal_receipt.json) 明确披露 Gemma 单模型计时超额至少 0.532 秒及 teardown 上界，不用总预算合规掩盖单模型超额。格式诊断和报告新增展示未修改冻结 scorer、分母、样本或 CI 方法。

审查材料 `ERROR_REVIEW.private.jsonl`、逐题 `SOURCE_AUDIT.private.jsonl` 以及各模型 `scored.*.private.jsonl`、封存预测均在 `$NAA/evaluation_wp2/` 下。公开只提交聚合表与校验摘要；不发布 raw gold/history/output 或逐题身份。原 240 任务仍由已有 FREEZE 引用，未重生成。

最终提交前新增终局成本回归后，本地数据/评价测试为 **34 passed**。该回归明确区分已失败与从未尝试，检验即使总预算足够也如实报告单模型超额，并拒绝 pending 计数不一致。

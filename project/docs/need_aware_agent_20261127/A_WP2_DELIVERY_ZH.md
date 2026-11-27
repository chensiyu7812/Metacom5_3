# A 线 WP2 评价实现与执行交接

评价规则在查看真实模型输出前由 `629d20f7` 冻结，SHA256 为 `18d863f6f9547040c7d11aab85c4a68e501560dd7e0fa113962f7e1d40474cd3`，见 [WP2_EVALUATION_RULES.json](WP2_EVALUATION_RULES.json)。本文件记录当前已执行工作；最终模型统计与 WP3 决策尚待 B 封存输出，不能用 CPU/plumbing 结果替代。

## 实际实现

`evaluate_wp2.py` 验证原数据冻结、执行 manifest、逐请求/模型/运行身份、导出文件 SHA256 和账本封存头，随后调用未改变的 PersonaMem 官方 MCQ 解析器。每个条件必须交付全部 240 个槽位，包括结构性不可评价和未执行位置。原单条件 scorer 已修复 C/D `not_evaluable` 合法空 request hash 被误拒的问题。

报告同时给出完成准确率、预定可评价分母、完成率、超时/运行错误/返回校验失败/中断/未执行/容量错误、解析失败、有效错误答案及固定分母敏感性。失败和结构性缺失的正确性为 unknown；只有固定分母敏感性将技术未完成计为零成功。长度停止仍按官方解析评分，另给 EOS-only 结果，不宽松修复答案。

A/B 全 240、四臂共同 207、Direct 缺失 33 分开；180 代表性和 60 困难层及其 Direct 交集分开。跨条件/模型只比较同一任务集合，记录完整配对、修复、退步、persona bootstrap 95% CI 和固定 8 组的 Holm 校正 McNemar p 值；类别为描述性分析。另有四臂/八单元共同完成表与未完成结果的上下界，避免仅比较完成样本的边际准确率。

`evidence_audit.py` 从实际合法历史核对每个送达 source id/hash，并把 B 的参考缺失按 user/nonuser 分开；不从覆盖率推断回答能力。`report_wp2.py` 仅接受真实 model 聚合结果，拒绝 plumbing 作为模型报告。原始预测、逐题评分及请求变更映射仅写本地私有目录。

## 与 B 的实际版本核对

[A_WP2_JOINT_RECEIPT.json](A_WP2_JOINT_RECEIPT.json) 对照原 CPU manifest `9839c088…` 与执行 v2 `c370103c…`：487 个冻结文件逐字节 hash 全部保持，240 题、答案、选项排列、历史、Direct 207/33 均未变；两模型内的任务/条件次序不变，模型运行先后改为 Qwen35、G0e。新预算为 57,600 秒总计、每模型 28,800 秒、1,920 次物理尝试，两模型各自前 16 次技术烟测计入预算。

B 的 speaker/subject、更新适用范围和遗忘指代修复符合 D 的既定投影+指导构念。公共 RAW 增加说话人说明还改变了 A 的 170/480、B 的 94/480 槽位所选记录；全部 A/B/C 可执行请求 hash 相应变化。这项变化已明确记录，不能声称只有 D 请求变化。A 在启动前建议保留原 RAW 行，但检查账本元数据时 v2 已开始执行，因此保持实际运行条件，不在中途修改。该变化未改原始题目、历史、检索方法或共同 8192 evidence budget；它是最终 v2 的公共渲染版本差异。

实际核对 v2：两模型的 B 在 207 个 Direct 可定位任务中仍全部保留用户参考记录，但 **207/207 均缺其他说话人的参考记录**。C/D 的送达 ids/hash 与原完整合法 Direct 坐标一致，D 的 414 个可执行请求有新 hash，旧请求文件保留。B→C 同时改变非用户上下文和无关信息量，不能仅凭此对照将差异因果归为“噪声”或“检索遗漏”。

A 已通过 PR #31 评论及共享 `handoff/A_WP2_EVALUATION_STATUS.json` 交接评价冻结和导出契约。B 独占 GPU 运行职责；A 未加载模型、未调用 API、未训练或打开正式测试。另已向 B 指出 session 终局计时写在 worker close 前的成本遗漏，最终成本需计入 teardown；不回写旧账本。

## 已执行验证与可复跑命令

本地原数据/新评价回归 28 passed；`fc9f92b8` 的 [NAA CPU CI](https://github.com/chensiyu7812/Metacom5_3/actions/runs/46010175563) 通过。一次真实冻结材料与原 B plumbing 导出的接口联调处理 1,920 槽位、1,788 plumbing 完成、132 结构性位置，8 个主比较的配对数为 240、240、207、207、207、207、207、207；11.659 秒。该检查只验证接口，没有模型能力成绩，且没有重复 GPU 资格验证。

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

当前未完成：B 封存真实模型输出后的严格评分、失败归因、跨模型配对结果及基于真实错误的单一 WP3 修复建议。尚无训练决定或训练执行。

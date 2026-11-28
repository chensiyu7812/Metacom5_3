# A：官方回复监督实施交付（2026-11-28）

本次是研究者对 v1.1 的实施修订，不改 NAA 名称、三个 RQ 或完整陪伴 Agent 目标。独立工作树 `Metacom5_3-naa-response-data` / `work/naa-response-data-20261128` 从 B `5c332bec` 建立，已包含 A PR34；四份研究入口与权威 `65424fd8` 一致。没有重复合并 PR30/31、reset、force 或改动 B 正在使用的工作树。

原 1,591 组 / 4,772 条动作模板保持原文件和身份，新增本机 `HISTORICAL_RETIREMENT.json` 标记为历史构造诊断，禁止作为本轮主要训练材料。冻结 WP3 的规则和数据继续有效。本次新回复监督不使用 USE/IGNORE/CLARIFY 目标。

## 已经落地的真实材料

本机根目录 `S=/opt/tokkio-data0/naa/20261128/a_response`，私人材料不提交 GitHub。

* `official_source/CANDIDATES.private.jsonl`：实际 4,000 条原请求、原 correct_answer、12,000 条原 incorrect_answers，以及已有合法历史路径/hash。125/26/26 owner 原划分不变，对应 2,907 fit、570 tune、523 development 原题。每条历史已核验；未导出 hidden persona。
* `review50/`：预先按 task ID hash 固定的 50 道训练侧 others、完整定位原文、合法全历史入口、逐题 speaker/holder/beneficiary、正例与负例关系。实际可辩护 11/50（22%）、歧义 25/50（50%）、证据不足 6/50（12%）、不适合训练 8/50（16%）。只 9 题归为明确的第三方情境；另有写作身份未定、邮件收件人可能为用户、公共文本、合理替代和自他重叠。11 题有经核查的相对排序候选，仍须核验这些证据实际送达。不是独立人评，不把有限关键词全历史检索当作语义穷尽证明。
* `support96/`：在同一次正例制作中固定抽取 fit/tune 的 96 个非敏感、非 forget 的 self 候选，23 个支持候选、64 个证据不足/歧义、9 个不适合；不估计总体发生率，不另开资格实验。允许原文中的隐含偏好，不要求第一人称明示。未经核查的诊断、地点、日程、AI 个人经历不强行学习。
* `development_frozen/`：26 development owner 共 523 题中，按预定 owner hash 顺序、完整组能放入 280 上限才选，实际 14 个完整 owner / 272 题。实际请求、四选项、答案、历史和评分政策已冻结，未读取新模型输出。旧 240 题、WP3 140 题和 60 题衔接材料未改。
* `agent_system/`：复用 PM 原开放 60 题与 J06 24 题，合计 84 个系统评价合同；J06 的 memory_only / RS_only / both / neither 各 6 题、6 个 owner，保留实际合法 ES-MemEval AsOf 来源和已有 Support Skill 的进入/退出条件。60 个有限回复抽检槽位已固定（24 J06 + 36 PM），尚不冒充已经取得或人评的新系统回复。

自动供给与终结程序使用全角色 dense B1@8192、Qwen 原生 tokenizer、完整话轮和原顺序。只用原请求检索，不读选项、答案、who、Direct 坐标。`supply/runtime/` 与 `release/supervision/`、`release/development/evaluation/` 物理分离。程序完成时生成 `FINALIZE_DONE.json`、实际 fit/tune 数据、原生编码、1,360 个五臂请求、精确 token/配对数、资源候选及 SHA 冻结；未完成时不能把这些预定数量当作已验收的训练数据。此提交的 `OFFICIAL_SOURCE.json` 是供给合并前的真实原始候选快照，最终验收以 `release/CPU_RECEIPT.json` 为准。

## 正式集独立性发现

仅用 Arrow 投影 `persona_id` 与 `chat_history_32k_link`：正式 benchmark 5,000 行 / 200 owner / 200 history path，与 train/val 均重叠 **1 owner / 1 history path**。该 owner 不在 177 个训练侧或 140 个 WP3 中，而在后续 60 个 WP4 保留名单中。保留原名单，单独隔离这 1 个，当前最多 59 个可以声称路径级独立；不偷偷补抽。精确身份只在本机交接，公开只给计数。

原 CSV 作为不透明文件 chmod 600 封存，Python 只取得两列分组元数据；答案没有投影、没有评分，没有正式模型调用。此核查只证明路径/owner 关系，不证明未打开的正式历史不存在语义或字节重复。

## 监督与评价实现

`data/response_data.py` 保留全部官方回复及未知项。自动准入仅限很窄的非断言型建议筛选，明确是弱官方监督，非语义真值；涉及个人断言、医疗、外部时间事实、敏感/forget 的未知项保留 mask。审查的个性化正例还须其核查来源确实送达。Direct 命中本身不能准入。普通合理替代不会被自动当成错误或有害。

`data/reply_objective.py` 实现普通回复 SFT（U2）及同正例 SFT + `0.1 × softplus(0.5 − lp(y+) + lp(y−))`（U3）。lp 为完整回复 token 平均 logprob；每个已核查正例只用预定第一个合格负例，未知负例不进损失。正例前向复用，仅 U3 的合格负例增加前向；额外 token 和次数单列。原生推理前缀完全一致、Qwen turn-end 248046、不静默截断、拒绝目标控制 token。

候选统一 Qwen3.5-9B 固定 revision、q_proj/v_proj/in_proj_qkv、r8/alpha16、dropout0、同 seed/顺序/权重/步数、一个 epoch、accumulation8、lr1e-4、固定终点，不给 U3 额外类别权重。B 需将该接口接入有界训练器，按 accumulation group 归一化已核查 pair；旧 `train-v11` 仍是动作目标，不能直接喂新文件。A 没有启动训练或创建授权。

`agent/reply_protocol.py` 提供竞争性 U1 记忆使用规则和 U1+ 主体/服务对象匹配规则；三证据臂原文逐字相同，均不静默屏蔽第三方。No-memory 留问题/选项，Options-only 连问题一起移除。`evaluation/wp4_mcq.py` 使用严格短答案 **modified protocol**，不能与官方原协议混算。以 owner/history-family 连通分量聚类，报告共同完成配对、修复/退步、micro 与 owner-macro 差异/CI、预定分母、完成率、解析/技术失败及失败纳入分母敏感性、未知区间。主要 U3−U2，次要对照预先固定；+5pp 实际意义、总体 −5pp 非劣，不将不显著叫等效。others 元数据类别不冒充已验证第三方；updated/forget 重合不代表一般时序更新。

`evaluation/agent_system.py` 检查需求处理、合法取史/技能、实际回复、历史落盘和后续交互的 trace 身份/顺序。事实短语检查只提供可复算观察，未出现不直接判事实错误，出现也不直接判帮助充分。仍需实际开放回复的帮助质量、误用及任务完成检查；缺少独立评审则如实记单人审查。当前完整 Agent 接线、新回复和 MP/ME 遥测仍是 B 联合缺口，不把 84 个合同当作完成系统实验。

## WP3 和联合资源交接

初次查看 B 时仍在 CPU 供给阶段，未取得终局账本；不据此编造 WP3 分数，也不持续查 GPU。`finalize_wp3.py` 是 B 运行结束后的一次 CPU hook：验证原冻结、终局 hash 账本、封存、按预定 confirm/bridge 身份拆分、十格聚合与跨模型/旧协议配对。修复通用 exporter 对新臂仍硬编码 A/B/C/D 的成本表问题；不改历史 scorer 或成功定义。

本机 `handoff/A_RESPONSE_TO_B.json`、PR33 的实际评论同步了新输入合同、50 题结果和 formal 分组重叠。自动终结程序生成一份 `JOINT_RESOURCE_CANDIDATE.json`：五臂基线 8,000 GPU 秒、U2/U3 各 10,800 秒、训练后 MCQ 与有限开放评价 16,000 秒，总候选 45,600 秒，包含加载/烟测/重试/保存/退出；这是待 B 接线和研究者批准的同一份具体申请，**不是已获联合签认或训练授权**。不把旧短输入 0.21 秒外推成 8k 输入时间上界。若两方法未到同一步数，不报告公平训练比较。当前 WP3 运行不受此候选阻塞。

## 复现与状态

从本分支根目录：

```bash
export PYTHONPATH="$PWD/project/src" CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1
S=/opt/tokkio-data0/naa/20261128/a_response
R=/opt/tokkio-data0/naa/20261127
CPU_PY=/opt/tokkio-data0/tokkio_envs/naa-cpu-py311/bin/python
NATIVE_PY=/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python

"$CPU_PY" -m pytest -q project/tests/test_need_aware_*.py
python project/scripts/need_aware/prepare_response_data.py \
  --source "$R/source" --training "$R/artifacts/training" \
  --allocation "$S/ALLOCATION.json" --out "$S"
"$NATIVE_PY" project/scripts/need_aware/supply_response_data.py \
  --runtime "$R/artifacts/training/runtime" --out "$S/supply" \
  --reuse /opt/tokkio-data0/naa/20261128/agent_b/train_diag --threads 4
"$NATIVE_PY" project/scripts/need_aware/finalize_response_data.py \
  --root "$S" --source "$R/source" --training "$R/artifacts/training"
```

现有目的地不得重跑覆盖；supply 支持严格身份匹配的恢复，release 已存在则拒绝，失败目录保留再用新根目录修复。后台脚本独立执行，机器可定时检查自己的 completion 文件；AI 不持续等候或每分钟轮询。

真实工程失败：首次 shell `nohup` 启动未存活，日志为空，没有模型调用；改用 Python `subprocess.Popen(start_new_session=True)`、绝对 PYTHONPATH 和私有日志后确认存活。原始失败日志保留。CPU 测试、训练候选准备、scorer fixture 和 BGE 编码均不是 Generator 能力结果。

公开仅实现、测试、无文本统计及 hash；原始历史、官方回复、逐题标注、预测、sealed 文件、权重、密钥均留本机。公开回执见 `response_receipts/`，运行完成/失败事件见本机 `FINALIZE_DONE.json` / `FINALIZE_FAILED.json`。

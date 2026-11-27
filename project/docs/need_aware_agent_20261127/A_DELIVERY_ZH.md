# A 工作线实际交付：数据、官方 MCQ 与 CPU 回执

日期：2026-11-27（JST）。本文件是执行结果，不改变 MASTER_PLAN。代码/聚合回执见本 PR；原文、答案、逐题记录、模型权重均仅在实验服务器。**没有模型能力结果，没有 GPU、训练、付费 API 或正式测试集解封。**

固定起点 `3dded9b28606d670dc0ed57bcaf8197a7926f4fd`；独立分支 `work/naa-data-20261127`；独立 worktree `/opt/tokkio-data0/tokkio_projects/Metacom5_3-naa-data`。按追加通知以 fast-forward 整合 `5c7195984af60ebc84cc12cdd0b16ae550cbdc30` 的 30 个恢复源码。旧 worktree、main、历史实验和授权未修改。首次在 home 创建 worktree 因根分区不足失败；Git 已清除失败检出，改用数据盘和 sparse checkout，未删除历史输出。

实现提交 `2615ffec`（共享契约）、`4bb5b7dc`（真实数据及 CPU 路径）和 `e146812f`（WP2 / native stop / 来源保护）；最终交付以 PR head 为准。[PR #30](https://github.com/chensiyu7812/Metacom5_3/pull/30)。可机读的完整聚合统计、来源/材料哈希、模型文件哈希及成本见 [A_CPU_RECEIPT.json](A_CPU_RECEIPT.json)。

## 1. 数据已经取得，官方划分存在实质偏差

[PersonaMem-v2 数据](https://huggingface.co/datasets/bowen-upenn/PersonaMem-v2/tree/ed956dea41521fc4499acbc63f966e0fd3c053ba) 固定 HF revision `ed956dea41521fc4499acbc63f966e0fd3c053ba`，数据卡声明 CC BY 4.0、LLM 合成。作者/来源归属保留；本 PR 不再分发源数据。

| 项目 | 实物结果 |
|---|---:|
| text train CSV | 18,549 行，800 persona / 800 history family |
| text val CSV | 2,061 行，735 persona / 735 history family |
| train–val persona / history 交集 | 735 / 735 |
| 两分区完全相同行交集 | 0 |
| 各分区完全重复行、重复 persona+query | 均为 0 |
| 下载且成功解析的所需 32k history | 477 / 477 |
| 这些 history 的消息总量 | 110,232 |
| 这些 history 完整内容重复文件 | 0 |
| history 中含非 role/content 杂键的消息 | 8 |
| benchmark_text | 元数据服务列 5,000；未下载/打开标签，未做固定 CSV 实物 census |

这不是主方案引用的 18,500 / 2,600，也不支持 train/val persona-disjoint 的假设。保持官方原始分区身份；本次另行排除冻结开发 persona 才构造训练候选。不能把官方 val 的未来训练后结果自动称为独立用户泛化。benchmark 的 persona 独立性仍未验证，不能由卡片推断。

字段 census（pref_type / who / updated / sensitive_info / conversation_scenario）、各 persona 行数分布、缺失/重复、类别交叉统计全部保存在聚合回执。train 缺 `short_persona` 13、`incorrect_answers` 1；val 缺 `short_persona` 2；`prev_pref` 的空值恰为非 updated 行。缺少 persona 描述不影响 runtime，因为这些标签不进入输入。所选任务的四个选项均有效。此 revision 的 updated 全部对应 ask_to_forget，**不能把它当成一般偏好更新的独立覆盖**；也没有可靠的显式/隐式二元真值，困难层中的 implicit_scenario_proxy 仅按实际对话场景预定义。

8 条杂键消息仅导出原始 `role/content`，内容和顺序不改；原始 JSON、其文件哈希和归一化副本哈希分别保存。这是解析兼容修复，不是丢弃题目。没有下载 128k、multimodal histories 或 raw persona 文件。

## 2. 冻结材料是实际文件，不是空 manifest

本机根目录：`/opt/tokkio-data0/naa/20261127/artifacts`。种子 `20261127`，`FREEZE.json` 绑定 487 个文件；实际重算 487 个哈希，0 差异。冻结哈希：`f29ad02de12c73d341d44d7e0fc8295889ec8f284db6d73b46b8ed0a5fb5eae5`。

| 路径（相对上述根目录） | 内容 |
|---|---|
| `runtime/tasks.mcq.jsonl` | 240 个真实 val MCQ，240 个 persona |
| `runtime/tasks.generation.jsonl` | 另外 60 个 val 开放任务，另外 60 个 persona，完全没有 options/gold |
| `runtime/histories/` | 300 个开发 persona 的合法历史副本，只含 owner/family/messages |
| `evaluation/tasks.mcq.jsonl` | 240 个 EvalTask：答案映射、参考、类别、相关片段、合法证据坐标 |
| `evaluation/tasks.generation.jsonl` | 60 个开放评价 sidecar；没有产生生成质量分数 |
| `evaluation/selection.json` | 精确原始行号、180/60 分层、开放及训练选择 |
| `direct/direct.jsonl` | 300 条 C/D-only 诊断定位状态；仅源坐标及哈希，没有答案或黄金偏好 |
| `training/runtime/tasks.jsonl` | 4,000 个真实 train 候选输入，177 个 persona，与上述 300 persona 零交集 |
| `training/candidate_provenance.jsonl` | 4,000 条来源/定位记录；`target_materialized=false` |
| `source_manifest.json` / `census.json` | 实际源文件 SHA-256/字节数、完整实测 census |

240 的构成为：按 pref_type/who/updated/sensitive_info 比例最大余数分配 180 题、在层内优先不重复 persona；另外 60 题依次选忘记/updated、第三方、敏感、隐式场景代理各 15 题，行不重叠。抽样不读取模型输出，不按 Direct 成功与否筛选。代表层近似原始分层组成；persona 平衡和困难层均须披露，不能将合并 240 的比例估为自然发生率。开放任务与 MCQ 的 persona/行均不重叠。训练按 persona 成组选择，最后一个组只取到 4,000 行。

## 3. Direct 证据检查的实际结果

只接受**同 persona、cutoff 前、同角色、连续完整原话、唯一匹配**。坐标是 message_index 和完整消息字符范围；source_id、文本 hash、源文件 hash 均可追溯。时间只有原始消息顺序，不编造日期。`validity=unknown`，不把说话者 role 自动等同于偏好主体，也不宣称定位就证明充分性。

| 材料 | 唯一完整定位 | missing | ambiguous |
|---|---:|---:|---:|
| MCQ 240 | 207（86.25%） | 33 | 0 |
| 开放 60 | 54 | 6 | 0 |
| train 候选 4,000 | 3,579 | 421 | 0 |

MCQ 缺失具体为 31 个 sensitive_info 和 2 个 ask_to_forget。进一步核查：31 个敏感题的 snippet 中没有一个消息能在 history 按角色+原文逐条匹配，空白归一化也不解决；2 个 forget 题仅能匹配 4 条中的 3 条。因此没有用黄金偏好、reference 或拼出的“证据”补洞，没有把部分片段冒充完整定位。A/B 仍执行全部 240；C/D 对这 33 题每模型各保留 not_evaluable，占两模型逻辑位置 132 个。Direct 是带离线任务信息的条件性诊断，不是可部署检索或严格 Oracle。

## 4. 官方 MCQ 已复现；开放评价分开

取得并检查 [官方源码 commit d29d91d](https://github.com/bowen-upenn/PersonaMem-v2/tree/d29d91d016add354e459dfeb0d24af08bc402e2a)：`inference.py`、`prompts.py`、`inference_utils.py`、`verl_custom/data_preprocess_rft.py` / `data_preprocess_sft.py` 的相关输入、构造、解析和目标路径。根目录无软件 LICENSE；`MemAgent/LICENSE` 只覆盖其子项目，不能外推。公开代码为独立兼容实现；上游源码留本地，不运行其 provider、训练、数据生成或 Docker 入口。

- `data/prompts.py` 提供无 gold 的官方题面/recall suffix/消息次序；`evaluation/mcq.py` 提供同选项打乱、同优先顺序解析及按选项文本判分。裸 `A` 不被接受、`A.` 被接受、boxed 优先等不寻常行为照实保留。
- 官方默认 row_seed 使用 Python 进程 hash，未固定 PYTHONHASHSEED 时跨进程不稳定。本次显式种子 `20261127+原始行号`，冻结实际选项排列；所有模型/arms 共享同一排列。检索接口只有 query/current_messages，不能用选项找答案。
- 对全部 2,061 val 行，以 AST allowlist 仅执行上游三个纯方法进行确定性对照：选项/题面 0 差异，30,915 次解析+判分比较 0 差异。没有导入 QueryLLM。
- 已知答案和无效文本分别走实际 scorer CLI：240/240 应通过、0/240 应通过，均明确 `result_kind=plumbing`。**这些是 scorer 检查，不是任何模型 accuracy。**
- scorer 拒绝重复/未知 task_id，保留 missing/失败分母；aggregation 支持按 persona 聚类的 paired bootstrap、repair/regression、代表层与困难层分报。plumbing/model 来源不能混合，聚合输出也携带该标记。
- 开放任务只有 history + query；上游开放 scorer 需要 LLM 调用，本轮不执行。没有生成、人评、reward 或开放质量结果。

官方训练预处理与 inference 不完全相同：训练 MCQ 用小写 boxed、42+index 和截取前四选项，且有 thinking 指令；SFT 以 correct_answer 作为 assistant target 并清除该 thinking 指令。已记录差异，不把训练 parser 等同于 inference scorer，也不把人工 distractor 当成真实人类偏好数据。

## 5. B 接口、隔离和 CPU 执行

`data/contracts.py`: RuntimeTask / EvidenceRecord（严格拒绝额外字段）；`data/history.py`: HistoryResolver；`evaluation/contracts.py`: EvalTask。JSONL 接口 schema 为 `naa-v1`。B 使用 `RuntimeTask.from_dict()` 或 `load_runtime()`，`HistoryResolver(runtime_root).resolve(task)`；仅 C/D 可调用 `resolve_direct(task, diagnostic, arm)`。retrieval 不读 evaluation/source；source_family/persona_group 仅用于隔离/分组，不能作预测特征。证据附加的结构与适用性由 B 在其 own package 中实现，不能覆盖原文坐标。

已运行 Linux bubblewrap 真实隔离进程：只挂载源码、runtime 与单独输出目录，网络隔离，不挂载 source/evaluation/training/direct。实际 resolve 240 MCQ + 60 generation 成功，用时约 0.89s；不含检索、tokenizer 或推理耗时。目录隐藏断言在进程内部验证。此隔离不能替代 B 对其后续 GPU runner 的同等边界落实。

13 个 NAA 数据/评价测试通过：extra gold、option 正确标记、错 owner、越界 cutoff、路径逃逸、hash、source role、不完整/歧义 Direct、A/B 禁用 Direct、无选项开放输入、解析异常、完整分母、plumbing 来源保护、PrefEval 隐式标签排除、聚类配对。另加独立 NAA CPU CI job，不删除/跳过/放宽旧测试。旧依赖恢复及剩余 CI 由 B 核验，A 不将旧套件写成已通过。

同 PR 的交接评论及本机 `/opt/tokkio-data0/naa/20261127/handoff/A_TO_B.json` 已交付真实路径。**截至本回执，尚未收到 B 的接口回签、最终 renderer/runner commit、强固定检索选择及其 240 题 CPU 输入统计；联合验收仍未完成。** A 没有代写 B 的 Agent/记忆模块，也不将自己的 resolver 检查冒称 B 的检索实验。

## 6. 外部数据实际核查

| 来源 / 固定代码版本 | 实测与处置 |
|---|---|
| [PrefEval](https://github.com/amazon-science/PrefEval/tree/50795054b5ff5f418d2b768a331d71e480f93331) | CC BY-NC 4.0；非商业科研范围。显式/choice/persona 各 20 topic、各 1,000 行，三条件共享 1,000 case family，不是 3,000 独立用户。各读取并转换 10 个真实样本，共 30，经过同 RuntimeTask/HistoryResolver。MCQ 目录 21 文件/1,052 行，额外 `travel_hotel copy.json` 52 行不当作新题；核心 20 topic 为 1,000。没有现成 benchmark train/val/test 划分，局部 val 仅标识 loader 已暴露样本。generation evaluator 需 API，未调用。 |
| [OP-Bench](https://github.com/yulinlp/OP-Bench/tree/44e7d0e526152997b04208218a8ad7362174dae4) | 实物 10 conversation families、20 users，irrelevance 318+100、sycophancy 400、repetition 20 组共 897 queries，总 1,715；不是 README 的 1,700/882。官方默认只用每组第一个 persona，20-user 复现须显式启用双方。普通项为 API judge，重复项为组内回答 embedding cosine；不能拆成独立单轮结果。NOTICE 明说尚未声明软件许可，LoCoMo 再分发条款待核实。仅做实物检查，未接入主干/正式考卷。 |
| [ENPMR-Bench](https://github.com/xingqwq/ENPMR-Bench/tree/f46921bc42c14c1cc57d68a364bee7a3a7dcc1d2) | 实物 50 persona、2,692 dialogues、11,846 memories。memory 有 date，但全部 2,692 目标对话缺结构化时间；只见 README/data/assets，没有可执行 evaluator 或明确 LICENSE。许可与目标前时间界限未解决，blocked admission，不阻塞 PersonaMem。 |

没有拓展为三套 benchmark 同时开发；ES-MemEval/ESC-Eval 保持现有实现，fold6/历史正式评价未重开。

## 7. 已核实模型与一次 WP2 候选包

| 本机 checkpoint | 固定 revision / 许可 | native tokenizer 实测 |
|---|---|---|
| G0e：Gemma-4-12B-it | `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`，[官方卡片 Apache-2.0](https://huggingface.co/google/gemma-4-12B-it/blob/707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7/README.md) | GemmaTokenizer；native context 262144；实际文件 SHA 已重算，约 23.92 GB 权重 |
| Qwen3.5-9B | `c202236235762e1c871ad0ccb60c8ee5ba337b9a`，[官方卡片 Apache-2.0](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md) | Qwen2Tokenizer；native context 262144；4 个现有权重 shard 实际 SHA 已重算 |

使用已有不同家族、通用 instruction model 作能力参照，没有按本次题目效果挑模型，也没有选择弱模型证明方法。两者 GPU 装载兼容性仍须授权后的真实运行确认。只读 nvidia-smi 显示 A4500 20GB 与 A6000 48GB；拟顺序使用一张 A6000，并在正式运行时重验可用性，不抢占/杀其他作业。

native tokenizer 实际处理了两模型 × 300 任务：A 的容量探测消息保留完整来源原文并标注角色，完整历史在 Gemma 为 37,772–48,507 tokens、Qwen 为 36,848–47,349；全部超过 12,000。261 个成功定位任务的 Direct 最大分别为 1,682 / 1,634。该统计是 A 的消息容量探测，**不是 B 最终请求 token 统计，也不是完整历史模型成绩**。

Qwen 对 240 个 MCQ 的官方末尾 system 消息报模板错误；B 需要统一前置任务指令并把历史作为引用数据，保留选项文本、recall suffix 与官方评分契约。原始官方构造接口仍保留供复现。两种模型都固定 greedy / thinking=false；建议 input cap 12,000、max output 1,024、backend context 16,384，任何长度截断单列失败。G0e 原生 stop ids `[1,50,106]` / suppress `[258883,258882]`；Qwen text-config EOS=248044 与 tokenizer EOS=248046 不同，显式接受二者，避免依赖配置默认值导致不停止。NAA decode 是新身份，不复用旧 run authorization。

**实际 WP2 逻辑清单**位于 `wp2_v2/logical_requests.jsonl`（相对 `/opt/tokkio-data0/naa/20261127`），1,920 个唯一逻辑位置，任务顺序与 arms 交错固定，模型顺序固定。1,788 个可运行位置（最终请求精确去重前），132 个 not_evaluable。`actual_request_sha256` 明确等待 B 物化；logical hash 不冒充 exact-cache key。旧初稿 `wp2/` 保留，v2 加入实际 native stop tokens。

提交给 B 联合完成的**单次候选上限**：1 张 A6000，两模型顺序加载，1,920 次物理终局尝试上限（包含失败/重试；未去重时最多 132 次重试余量），GPU 占用总 43,200 秒/12 小时（含加载、索引中若使用 GPU 的部分、重试、等待本作业占用）。前 16 个实际可运行请求是同包技术烟测，成功即继续；只重试失败的同一请求，成功结果不择优重跑；到时间/次数硬限停止并报告缺口。12 小时是上限而非吞吐承诺。

60 个开放任务已经物化，其后续最多 180 个 A/B/方法生成请求**没有计入**上述 1,920 MCQ，本申请候选的开放实际请求数为 0，需后续明确配额。没有生成式 Writer 或训练费用隐藏其中。零付费、零外传、无训练、无正式 test。需要 B 回填最终 runner/消息 hash/实测输入/强基线及共同确认后，才是一份可批准的联合 WP2 申请；当前所有授权字段均为 false。

## 8. WP2 后唯一训练实施路径（未训练）

只有在真实 WP2 显示“C 已供合法证据而 G0e 仍错、第二 G 能修复”等利用能力缺口时，才从已冻结的 4,000 train 候选中构造一次 grounded SFT/LoRA 修复。当前有 3,579 条完整可定位候选，满足 3k–5k 量级，但它们不是已经合格的训练真值。

输入仅 train 合法历史/源坐标 + query；target 可用该 train 行的官方 reference，黄金偏好只用于离线监督审核，不塞入用户消息；MCQ distractor 不当作人类偏好对。先按实际失败类型过滤、人工/弱监督抽查 reference 是否被合法证据支持、主体/忘记/时序是否正确；拒用/偏好改变对照若缺少合法观测监督，就明确缺标签，不从 category 造“最佳行动”。敏感题的定位缺口意味着不能用这批 grounded 子集宣称覆盖全部敏感保护。保留 train persona 内部的独立审核小组，开发 300 persona 禁入训练；未来确认 val 还须排除训练 persona，不能回用官方整张 val 假称独立。

训练建议先做一个 NAA 新 LoRA checkpoint（不覆盖 G0e），rank 16、1 epoch、有效 batch 16、同一 native cap；teacher forcing 只在 assistant target 上计 loss。先比较固定 prompt/rules 与适配 G + fixed evidence；训练目标和预算待真实瓶颈后一次提交。候选训练上限可提出 1 张 A6000、4 GPU 小时、单一 seed/单一配置，具体可行性以实际 backend 内存和计时为准；**这不是授权，也未启动训练/GRPO/PPO**。按主方案 WP3 只修一个最大瓶颈，无可靠增量就停止该方案。

## 9. 可重跑命令、失败与未完成项

以下命令在独立 worktree 执行；原始文件不会写入 Git。复跑 prepare 使用新的 output-root，已冻结目录会拒绝覆盖。

```bash
git fetch origin research/need-aware-agent-20261127
git worktree add --no-checkout /opt/tokkio-data0/tokkio_projects/Metacom5_3-naa-data work/naa-data-20261127
git sparse-checkout init --cone
git sparse-checkout set project/src project/scripts project/tests project/configs project/docs/need_aware_agent_20261127 .github
git checkout
git merge --ff-only 5c7195984af60ebc84cc12cdd0b16ae550cbdc30

export PYTHONPATH=project/src
python project/scripts/need_aware/prepare_personamem.py --source-root /opt/tokkio-data0/naa/20261127/source --output-root /opt/tokkio-data0/naa/20261127/artifacts
python project/scripts/need_aware/verify_official_mcq.py --upstream /opt/tokkio-data0/naa/20261127/upstream/PersonaMem-v2 --source /opt/tokkio-data0/naa/20261127/source --output /opt/tokkio-data0/naa/20261127/logs/official_conformance.json
python project/scripts/need_aware/run_cpu_isolated.py --runtime-root /opt/tokkio-data0/naa/20261127/artifacts/runtime --output /opt/tokkio-data0/naa/20261127/logs/cpu_isolated
python project/scripts/need_aware/run_plumbing_score.py --artifacts /opt/tokkio-data0/naa/20261127/artifacts --output /opt/tokkio-data0/naa/20261127/logs/scorer_plumbing_v2
python project/scripts/need_aware/prepare_prefeval.py --repo /opt/tokkio-data0/naa/20261127/upstream/PrefEval --output /opt/tokkio-data0/naa/20261127/prefeval
python project/scripts/need_aware/audit_external.py --upstream-root /opt/tokkio-data0/naa/20261127/upstream --output /opt/tokkio-data0/naa/20261127/logs/external_audit.json
CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/need_aware/model_inventory.py --artifacts /opt/tokkio-data0/naa/20261127/artifacts --output /opt/tokkio-data0/naa/20261127/logs/native
python project/scripts/need_aware/prepare_wp2_manifest.py --artifacts /opt/tokkio-data0/naa/20261127/artifacts --models /opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json --output /opt/tokkio-data0/naa/20261127/wp2_v2
/opt/tokkio-data0/naa/20261127/venv/bin/python -m pytest project/tests/test_need_aware_data.py -ra -o addopts=
```

单独评分入口：`score_mcq.py --runtime ... --evaluation ... --predictions ... --kind model|plumbing --output ...`；每次输入一个 model/arm，Prediction 需 task_id/output/status/result_kind，真实模型另需 run_id/model_id/request_sha256。`aggregate_mcq.py --left ...scored.jsonl --right ...scored.jsonl --output ...` 生成配对统计；不混 benchmark 分母。

真实失败与修复保留在本机 logs：home 空间不足改数据盘；第一次历史 URL 误删 `data/` 前缀导致 404，保留官方完整 ref 后成功；8 条杂键消息使严格 parser 拒绝，审计后只投影 role/content；默认 Python 无 pytest、随后缺 pydantic，在单独 venv 安装普通依赖后继续；初步 tokenizer 探测把返回字典长度误当 token 数，已改为 native rendered text 的 encode 长度，初步值未用作任何容量结果；Qwen 尾部 system 不兼容已记录并准备前置/引用形式的容量探测；Google 独立 LICENSE 文件和 Qwen generation_config 获取返回 404，分别用固定官方卡片 license 声明、实际 config/tokenizer EOS 处理，未擅改已有模型文件。

尚未完成：B 共同接口回签与真实检索/materialization 接入、最终 exact-request 清单和联合 WP2 批准就绪申请；实际 GPU 推理与模型分数；训练；开放生成人评；MemAgent/强 full-history 模型复现；正式 benchmark 标签 census/测试；OP/ENPMR 许可及 ENPMR 时间边界。没有将上述事项写成已完成，也没有为它们开旧锁或复用旧授权。

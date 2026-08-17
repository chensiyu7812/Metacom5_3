# Paper 1 Brev A6000 -> 本地 RTX 2070 迁移交接（2026-08-17）

状态：`MIGRATION CHECKPOINT / NO EXPERIMENT EXECUTED`

本文件记录 2026-08-17 服务器退租时的可恢复状态。GitHub 是 source of truth；旧 Brev 磁盘不应成为任何后续研究步骤的依赖。

## 1. Git checkpoint 与工作区身份

### A：Paper-1 integration

- 服务器路径：`/home/shadeform/Metacom5_3`
- branch：`work/paper1-rq1-integration-20260816`
- 本次迁移开始时的 audited HEAD：`46d4e1f64cc4f0c05b2c09d262f47a5432ff60e9`
- 该 HEAD 在审计时与 `origin/work/paper1-rq1-integration-20260816` 相同。
- 最终 migration commit 是包含本文件与 2026-08-17 semantic-compiler amendment 的该 remote branch tip。Git commit 不能把自身 SHA 写进自身内容；clone/fetch 后以 `git rev-parse origin/work/paper1-rq1-integration-20260816` 取得最终 exact SHA，并与本次 leader 最终验收回执核对。

### B：memory lane

- 用户给出的预期路径 `/home/shadeform/Metacom5_3-B` 在服务器上不存在。
- 实际 B30 checkout：`/home/shadeform/Metacom5_3_b30`。它是 A repository 的 linked worktree，不是独立 clone。
- branch：`work/paper1-memory-rq2-b30-final-20260817`
- exact HEAD / remote tip：`7f63f1a1060d97d9407d2007cdffe72ebe4302ff`
- parent / 已合入 A 的 memory baseline：`b8883dfdbe30104cd9aa05c186d20b185c13b325`。

### Merge 关系

- B memory commits through `b8883dfdbe30104cd9aa05c186d20b185c13b325` 已由 merge commit `e0e86e3` 集成进 A，A 随后用 `4b4ed18` 与 `46d4e1f` 刷新 M2 provenance。
- B30 Part A `f556f9d609b7049743afd4fc67c7d79e9438c39b` 未合入 A。它只保存 stable-kinship regex 规则缺失的历史 blocker；研究者批准的 semantic-compiler amendment 已使该 blocker 成为 `pre-semantic-compiler diagnostic / not ontology ceiling / not active learnability evidence`。
- B30 Part B `7f63f1a1060d97d9407d2007cdffe72ebe4302ff` 未合入 A。它物化 K=5/seed=0 folds，但先前审计仍要求补全 missing/extra target-set fail-closed invariants、修正 Part-A `basic_info` provenance 表述并提交 build reports。退租不是盲目 merge 的理由；该提交由 remote B30 branch 完整保留，后续应基于新 A tip cherry-pick/重做并审计，而非直接合并整条旧 blocker branch。
- 旧 remote branch `work/paper1-memory-rq2-20260816` 仍指向 `b8883dfdbe30104cd9aa05c186d20b185c13b325`；不 force-push，不用 B30 改写其历史。

## 2. Outcome lock、M2 与已禁止的运行

- `project/data/paper1_authority/integration_base_validation_v1.json` 记录 `status=PASS`、`outcome_calls=0`。
- outcome lock 仍为 `LOCKED_PRE_ZERO_OUTCOME_FREEZE`：formal effect calls、formal training、formal benchmark outcomes 全部禁止。
- `project/data/paper1_authority/paper1_m2_decision_packet_draft_v1.json` 仍是 `PRE_OUTCOME_DECISION_DRAFT_NOT_A_FREEZE_NOT_AN_UNLOCK`，`formal_outcome_calls=0`，不是 M2 freeze，也没有 unlock。
- 旧 M2 draft 的 memory census / stable-kinship recommendation 已被新 amendment 定点 supersede。该 draft 必须在新的 semantic compiler artifact 与 census 冻结后重建；不能继续把 MP=3/ME=3 当 ontology ceiling 或 learnability evidence。
- 本次迁移阶段故意没有运行：任何 paid API call、Semantic Compiler smoke、formal outcome、PM training、ESC-Eval、ES-MemEval 正式结果、模型下载。四头 ontology、Route A、L2 learner、0.5 threshold 与研究主张均未改变。

## 3. 2026-08-17 active implementation amendment

以下新 authority 已加入根 `AGENTS.md` 的必读和 scoped precedence：

- `project/docs/PM_PAPER1_SEMANTIC_MEMORY_COMPILER_AMENDMENT_20260817_ZH.md`
- `project/data/paper1_authority/paper1_semantic_memory_compiler_amendment_20260817_v1.json`

其关键冻结是：

- Qwen `qwen3-235b-a22b-instruct-2507` 只作为 Alibaba Cloud Model Studio OpenAI-compatible API 上的 non-thinking semantic factual extractor + verifier；Generator 仍为 NVIDIA hosted NIM `meta/llama-3.1-8b-instruct`。
- structured output 是 JSON object mode + local strict schema/Pydantic validation；不得声称 provider strict JSON Schema enforcement。
- semantic factual/ontology judgment 合法；utility/helpfulness/transferability/worth-opening/should-open/ON-OFF/effect judgment 禁止。
- regex/string compiler 与 lexical Jaccard 仅 diagnostic/baseline；BGE-M3 是四头 formal similarity encoder。
- 总 API hard budget 是 USD 2.00；成功 cache/resume、per-attempt usage/cost ledger、pre-call cap guard、无 silent retry。当前 formal semantic compiler calls = 0。

## 4. 下一机器的恢复顺序

### 4.1 Semantic Compiler

1. 先读根 `AGENTS.md` 与其中列出的全部 active authority。
2. 基于 amendment 实现 typed schema、prompt identity、deterministic grounding、content-addressed atomic cache、显式 retry ledger 与 USD 2 pre-call guard。
3. 先读并把 `project/scripts/v1_5/51_me_semantic_extraction_pilot_v1_5.py` 的 third-party action、future-plan-as-action、purpose-as-outcome 变为 regression fixtures；旧 regex 不得成为正式证明。
4. 修复/绕开现有 API client 两个风险：调用级 `retries=1`，以及 fail-closed 绑定 `enable_thinking=false`，不能依赖当前 config loader 的 provider default。
5. 冻结 endpoint/region、request parameters、schema/prompt hashes、timeout、允许 retry 类型和当时的官方价格快照。
6. 只有研究者再次允许开始调用后，按 owner 内 `(timestamp, session_id)` 先做前 20 sessions smoke；缓存成功结果后直接继续 381，不重付费。之后冻结全量 output hash，再做 official annotation-relative audit。

当前服务器没有 DASHSCOPE secret file；本地恢复时只在 shell/session secret store 中 export，env var name 可由实现 contract 指定，但 key/value/path 不得进 Git、cache 或日志。不要把 key 写进命令历史；推荐在权限 `0600`、repo 外的本地 secret 文件中保存 `export DASHSCOPE_API_KEY='...'`，需要时以 `set +x; source /absolute/private/path; set -x` 加载，并用只输出“是否存在”的 probe 验证。

### 4.2 BGE-M3

- 在首次正式物化前冻结 exact Hub revision、文件 hashes、pooling、normalization、query construction 与 artifact identity。
- 现有 local environment attestation 记录了 commit-addressed PR-130 snapshot 与官方 RAG runtime工程证据，但没有冻结 upstream main 等价性，也没有把它冻结为最终 RS variant。
- 将 BGE-M3 接入 RS/MP/MS/ME formal similarity；Jaccard 留作 diagnostic。不能把 embedding score 解释成 utility。

### 4.3 RS

- 保留已集成的 public-only、leave-current-dialogue-out RS census/runtime evidence。
- 在 M2 freeze 前完成 Strategy Bank universe、RS Top-1 encoder exact identity、renderer/token boundary、matched-random 与 task anchor 的剩余 freeze；不能用 family-match diagnostic 代替效果。
- Generator/Step2 full-stack manifest 仍需绑定 `meta/llama-3.1-8b-instruct`、supporter prompt、temperature 0、max output tokens 256、provider seed null 及 resource-block hash。

### 4.4 MP / MS / ME

- 以 semantic compiler 从全部 401 EvoEmo sessions 重建三头 candidate census；official annotations 只能在 primary output hash 冻结后做 audit/reference。
- 报告真实 MP/MS/ME counts、owner/target coverage、type distribution、cross-turn ME、conflict/supersession、verifier rejection、grounding failure、tokens/cost 与旧 compiler 的 candidate-yield/eligibility 差异；无 denominator 时不称 recall。
- 保持 MP=Profile only、MS=strict-past cross-session continuity、ME=strict-past user action -> user-observed outcome；不使用 synthetic rescue，不因稀疏缩小 ontology。
- B30 K=5/seed=0 materialization 先按上面的未合并原因加固与审计，再集成；semantic links 不得改变 primary exact-mechanical grouping。

### 4.5 M2 之后

semantic compiler 与 BGE-M3 identities、candidate census、candidate-dependent features/bundles/folds 全部冻结后，重建 zero-outcome M2 decision packet；研究者批准 M2 freeze 并显式解锁后，才进入 paired effect construction、四头 training 和 official benchmark。

## 5. 服务器环境 identity

- OS：Ubuntu 22.04.5 LTS，kernel `6.8.0-90-generic`，x86_64。
- GPU：NVIDIA RTX A6000，49140 MiB，compute capability 8.6。
- driver：580.126.09；`nvidia-smi` 报 driver-supported CUDA 13.0。
- 系统没有 `nvcc`；这不表示 PyTorch CUDA 不可用。
- 正式 Conda env：`/home/shadeform/miniconda3/envs/metacom-paper1-py311`。
- Python 3.11.15；PyTorch 2.3.1+cu121（compiled CUDA 12.1）；`torch.cuda.is_available()=true`，识别 RTX A6000。
- 关键包：transformers 4.57.6、sentence-transformers 5.1.0、scikit-learn 1.9.0、numpy 2.4.6、pandas 2.3.3；`pip check` 无 broken requirements。
- `metacom-pm 4.0.0` 是 editable install，指向 A 的 `project`。在 B/新 clone 测试时必须先 `cd` 正确 checkout 并显式设 `PYTHONPATH=project/src`，避免 editable install 串到 A。
- env lock SHA256：`00fb80a1086db247be93e02d77ec4de4dc0a0dd041a766075b216261e1e08071`。
- 可恢复入口：`project/environments/paper1-py311.yml`、`project/environments/requirements-paper1-py311.lock.txt`、`project/scripts/paper1/10_create_paper1_environment.sh`、`10_attest_paper1_environment.py`。

## 6. Tests / validator checkpoint

- A 最终 suite：`379 passed`；integration validator PASS、全部 checks true、`outcome_calls=0`；`git diff --check` PASS。
- B30 最终 suite：`329 passed`；validator PASS、全部 checks true、`outcome_calls=0`；`git diff --check` PASS。B 测试使用该 checkout 的 `PYTHONPATH=src`，已解耦 A editable install。
- 两边运行的都只是静态/单元/integration validation；没有打开 outcome、调用模型或执行 benchmark。

## 7. 可丢弃与不可丢弃项

可安全随服务器删除、以后重建：

- Conda env（约 5.9 GiB）与 Miniconda 安装；
- `/ephemeral/cache` 下 pip/uv cache（约 3.1 GiB）；
- `.pytest_cache`、`__pycache__`、`.pyc`、editable `.egg-info`、VS Code server/extensions；
- 未来按冻结 revision/hash 重新取得的公开 tokenizer/BGE snapshots。当前服务器未发现 Hugging Face model snapshot cache 或 repo 外 `.safetensors/.gguf/.onnx/.pt/.ckpt` 权重。

不能按目录整体当 cache 删除：`project/outputs` 含 518 个 Git-tracked historical output files；它们由 GitHub 恢复，应以 `git status`/tracked identity 而不是目录名判断。

审计结论：除最终 commit/push 前正在编辑的 amendment/handoff/guide 外，A/B 无 nonignored untracked research artifact；ignored 文件仅 pyc/pytest/egg-info 等可重建缓存。没有发现 GitHub 无法恢复、但 Paper-1 后续仍需要的研究 artifact。API secrets 不在 repo，也不在当前服务器预期 secret path。

## 8. Clone 后的最小验收

```bash
git fetch --all --prune
git switch --track origin/work/paper1-rq1-integration-20260816
git rev-parse HEAD
git rev-parse origin/work/paper1-rq1-integration-20260816

cd project
conda run -n metacom-paper1-py311 env PYTHONPATH=src pytest -q tests/test_paper1_*.py
conda run -n metacom-paper1-py311 env PYTHONPATH=src python scripts/paper1/00_validate_integration_base.py
git -C .. diff --check
```

需要 B30 provenance 时只 fetch/read remote branch，不要覆盖 A：

```bash
git fetch origin work/paper1-memory-rq2-b30-final-20260817
git log --oneline --decorate origin/work/paper1-memory-rq2-b30-final-20260817 -2
```

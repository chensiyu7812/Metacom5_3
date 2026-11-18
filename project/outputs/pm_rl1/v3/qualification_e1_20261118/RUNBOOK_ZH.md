# CPU 复跑与 WS-B 核查入口

所有输出写入新目录；不要覆盖本目录、旧 65 快照或旧实验。没有 Generator/Judge/训练执行命令。

## 独立检查，无 A/B 代码或分词器依赖

```bash
python project/scripts/rl1v3/check_e1_exports_standalone.py \
  --bundle project/outputs/pm_rl1/v3/qualification_e1_20261118/cpu_v3 \
  --sources project/outputs/pm_rl1/v3/A1_preparation/final/registry/sources.jsonl \
  --out /new/path/check.json
```

请 B 自己实现/检查 `SNAPSHOT_HASH_SPEC_ZH.md` 与 `HASH_TEST_VECTORS.json`，并用自己的 RAW oracle 对齐 8 个 B6e prefix。A 提供的 checker 只作参考；执行它本身不构成独立 B 确认。`DUAL_HORIZON_READINGS.json` 给出同一 prefix 两个 horizon 的实际原生 Reader 结果。

## 从固定 Git 对象重新导出

须已有 #12 `8ba20d21da4bdcbb552946241563bd41dbe46c6c` 和 #16 `a9cf0cca0fecd044a5a4e2a4066355a9a8123dc5` 的 Git 对象。脚本按 SHA 读对象，不按活动分支名、不合并候选。

```bash
git fetch origin pull/12/head:refs/remotes/origin/e1-input-pr12 \
  pull/16/head:refs/remotes/origin/e1-input-pr16
CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONPATH=project/src \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/prepare_e1_qualification.py --out /new/path/export
```

默认 tokenizer 使用固定本地 Gemma 文件；不同环境可以准备相同小文件与相同 transformers/tokenizers 版本。只允许 AutoTokenizer，未加载模型权重。需核对 `GENERATOR_BASELINE.json` 的 config/tokenizer/template SHA。不要因为模型目录不在本机而下载/加载权重或把此步骤当成模型运行授权。

```bash
CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONPATH=project/src \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/verify_e1_dual_readings.py \
  --bundle /new/path/export \
  --model /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 \
  --out /new/path/dual-readings.json
```

## 独立合成机制 fixture

```bash
CUDA_VISIBLE_DEVICES='' PYTHONPATH=project/src \
  /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  project/scripts/rl1v3/e1_synthetic_fixture.py --out /new/path/synthetic.json
```

这是手写 synthetic source，含 `RELATION/UPDATE`、known/ready/valid 三时间、七阶段及其他 owner；不导入真实 RAW，也不进入 E1。请 B 用它检查 #16 RELATION 适配器缺口，不能把 synthetic 中的测试 approval_ref 当真实人评。

## CPU 测试

项目既有 py311 CPU 环境及只读 jsonschema vendor 路径见 VALIDATION_RECEIPT。运行目录为 `project`：

```bash
CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH=src:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103 \
  /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest \
  -q -m 'not gpu' tests/test_paper1_*.py tests/test_rl1_*.py tests/test_rl1v3_*.py \
  -ra -o addopts= --junitxml=/new/path/full-cpu.xml
```

其中历史确定性优化器/环境单元测试不生成研究检查点；不启动研究 SFT/PPO。V3 严格套件另用 `tests/test_rl1v3_*.py -o xfail_strict=true`，并通过 `verify_v3_junit.py` 检查。跳过原因必须保留，GPU 用例排除，不算通过。

## B 审阅时应单列的决定

1. 8 个 B6e join 键、cutoff、source frontier、源跨度和 owner 是否完全一致。
2. 两 horizon 相同历史 snapshot 与实际读取是否相同；变更整文件 hash 或未来文本不应影响历史绑定。
3. hash 是否按规范独立重算，不把 B 转换后的 records 摘要当 A snapshot hash。
4. 新 preview 的 G 可见字段只含固定系统提示、当前前缀和本条件选定内容；没有私有 ID、评估标签、未读/未来正文。隔离 MP/ME 的预览不代表可执行 Reader。
5. 原 54/100 OFF、旧 key/token/result/reward、五项人工待审、324 MP 和 source/bank/index 不变。
6. QH 背景须由合法 RAW 独立构建，不由实验处理决定；Q0/QH/F 评分规则及身份等待 B 提案和研究者批准。旧曝光不自动排除评价资格。

所有研究批准和 B 收据在获得前保持 pending。此 PR 的父分支是 #15，只为避免重复 diff；**不得把本 PR 合入 #15 工作分支**。未来如获合并授权，应先处理依赖与跨线验收，再由 coordinator retarget 到真实 integration 并重新核查最终 HEAD CI。

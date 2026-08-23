# Paper-1 ESC-RANK 云端资格运行手册

本手册只用于 official ESC-RANK runtime qualification，不是正式 ESC-Eval。必须使用单卡可见显存不少于 24576 MiB 的隔离环境；本地 RTX 2070 不满足条件。

## 固定顺序

1. 将 ESC-Eval checkout 固定到 `9ad46e7b5e247e824dae4633910eaa82be668beb`。
2. 将 `internlm/internlm2-chat-7b` snapshot 固定到 `c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2`，目录名使用该 revision。
3. 将 `haidequanbu/ESC-RANK` snapshot 固定到 `450bf2eb5376c79e371aaf432925810243de1527`，目录名使用该 revision；七个 `_en` adapter 必须齐全。
4. 在独立 CUDA 12.1 环境安装 `torch==2.3.1`、`transformers==4.41.2`、`peft==0.11.1`、`accelerate==0.31.0`。
5. 先运行资产 attestor，生成 run-local resolved manifest；它只计算 hash，不加载模型：

```bash
python project/scripts/paper1/34_attest_esc_rank_cloud_assets.py \
  --esc-eval ESC_EVAL_CHECKOUT \
  --rank-path ESC_RANK_SNAPSHOT_REVISION_DIR \
  --base-path INTERNLM2_SNAPSHOT_REVISION_DIR \
  --template project/data/paper1_authority/paper1_esc_rank_24gib_patch_manifest_20260820_v1.json \
  --out RUN_DIR/esc_rank_resolved_manifest.json
```

6. 再运行 pinned harness：

```bash
python project/scripts/paper1/26_qualify_esc_rank_runtime_24gib.py \
  --esc-eval ESC_EVAL_CHECKOUT \
  --rank-path ESC_RANK_SNAPSHOT_REVISION_DIR \
  --base-path INTERNLM2_SNAPSHOT_REVISION_DIR \
  --qualification-dialogues project/data/paper1_authority/paper1_esc_rank_runtime_smoke_dialogues_20260820_v1.jsonl \
  --patch-manifest RUN_DIR/esc_rank_resolved_manifest.json \
  --out RUN_DIR/esc_rank_runtime_qualification.json \
  --repeats 2
```

输出只用于验证 load peak VRAM、cold/warm latency、七维 parse 和重复性。不得换 rubric、prompt、base model、adapter mapping 或 parser；不得把 qualification dialogues 替换成 PM arm、Top-k 或 confirmatory items。完成后等待 researcher review，不自动调用其他 judge，也不运行正式 ESC-Eval。

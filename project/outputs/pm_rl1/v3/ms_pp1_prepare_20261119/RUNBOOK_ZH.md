# CPU 复跑

从仓库根目录执行；输出必须是新目录。构建读取固定 Git 对象 #12/#13/#17/#18，未在当前分支合入它们。复核者需能读取这些提交；无法读取即停止，不自动换 HEAD。原生分词只读取本地 tokenizer/config/template，不打开权重张量或 GPU。

```bash
CUDA_VISIBLE_DEVICES='' HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
  project/scripts/rl1v3/prepare_ms_pp1.py --out /tmp/ms-pp1-new-export

PYTHONPATH=project/src /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  project/scripts/rl1v3/check_ms_pp1.py \
  --out project/outputs/pm_rl1/v3/ms_pp1_prepare_20261119/cpu_v2
```

构建的 13 个文件（包括 manifest）干净重跑逐字一致。`INPUT_PINS.json` 保留输入 Git SHA、文件 SHA、准备代码 SHA；`MANIFEST.json` 是文件字节 SHA。JSON 对象 hash 沿用既有 `io.object_sha256`：UTF-8、sort_keys、ensure_ascii=False、紧凑分隔符、不加换行；不是 RFC8785 的泛化承诺。

人工/AI 解释报告不是自动语义真值；`OWNER_AUDIT_SAMPLES` 的 first/RET/latest/current 抽样可重现，`OWNER_CONSISTENCY_REVIEW.json` 的解释由 WS-A 明确署名并引用原文，不会自动批准或改变资源。B 应用自己的 hash/RAW/payload 检查实现签收，不能只执行 A 的脚本。

本目录没有 GPU 执行入口。`ProcedureLog` 是 CPU 参考状态机，验证拟议的一次调用/停止规则，不是已经通过独立验收的持久执行器。未来 GPU runner 必须在获准的真实 integration 上绑定最终代码身份、保护流程和申请，不可将本准备脚本或原 A0 批次作为运行许可。

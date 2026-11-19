# CPU 复跑与未来执行环境

本轮只执行 check / CPU tokenization / pytest / read-only SHA；不执行 run。现有 #19 以及 #10/#12/#18/#20 的候选都不是已合并或 H0 采纳。

所有输出必须是新的目录。示例 DATA 路径需替换为实际数据盘目录；不更改 HOME/CODEX_HOME，不删除旧材料：

~~~bash
export PMRL1_JOB_ROOT=/opt/tokkio-data0/tokkio_projects/pmrl1-validation/new-job-with-unique-name
mkdir -p "$PMRL1_JOB_ROOT/tmp" "$PMRL1_JOB_ROOT/cache" "$PMRL1_JOB_ROOT/logs"
export TMPDIR="$PMRL1_JOB_ROOT/tmp" TMP="$PMRL1_JOB_ROOT/tmp" TEMP="$PMRL1_JOB_ROOT/tmp"
export HF_HOME="$PMRL1_JOB_ROOT/cache/hf" HF_HUB_CACHE="$PMRL1_JOB_ROOT/cache/hf/hub"
export TRANSFORMERS_CACHE="$PMRL1_JOB_ROOT/cache/transformers" XDG_CACHE_HOME="$PMRL1_JOB_ROOT/cache/xdg"
export TORCH_HOME="$PMRL1_JOB_ROOT/cache/torch" TORCHINDUCTOR_CACHE_DIR="$PMRL1_JOB_ROOT/cache/inductor"
export TRITON_CACHE_DIR="$PMRL1_JOB_ROOT/cache/triton" CUDA_CACHE_PATH="$PMRL1_JOB_ROOT/cache/cuda"
export PYTHONPYCACHEPREFIX="$PMRL1_JOB_ROOT/cache/pycache" PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export PYTHONPATH=project/src CUDA_VISIBLE_DEVICES=''

/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/rl1v3/limited_g0e_run.py check \
  --plan project/outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/A0_MIN_PLAN.json
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/scripts/rl1v3/limited_g0e_run.py check \
  --plan project/outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/PP1_PLAN.json
~~~

重建 CPU 材料使用 prepare_runprep.py --executor-head 575011b43947f4aaf73d6bb31f376bf4c36405fc --out 新仓库内目录。路径是 plan 身份的一部分，所以换目录的 plan hash 会不同；messages/input_ids、选择与 renderer identities 可独立比对。文件 SHA 是原始 UTF-8 文件字节；对象 SHA 使用 rl1v3.io.canonical_json 的排序键、无多余空白、ensure_ascii=false、allow_nan=false；不要把包含尾换行的文件 SHA 当成对象 SHA。

CPU 测试：

~~~bash
PYTHONPATH=project/src:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103 \
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python -m pytest project/tests/test_rl1v3_*.py \
  -m 'not gpu' -q -o addopts= -o xfail_strict=true -p no:cacheprovider \
  --junitxml="$PMRL1_JOB_ROOT/logs/v3.xml"
python project/scripts/rl1v3/verify_v3_junit.py "$PMRL1_JOB_ROOT/logs/v3.xml" \
  --out "$PMRL1_JOB_ROOT/logs/v3-gate.json"
~~~

未来运行需要研究者另行签署对应模板，最终 checkout HEAD、plan SHA、G0e 路径、执行器独立验收须一致。PP1 还需 A0 的真实成功收据以及 B 协议/背景/人员工具门禁。run 子命令只在这些证据齐全后由获准执行者使用；内部 worker 不应独立启动。模板 boolean 不是数字签名系统，签署证据须由负责执行的人核对，不能把任何人手工填写的 true 自动当作研究者许可。

事件日志使用 SHA 链和 O_EXCL，包含 RUN_START、MODEL_BYTES_VERIFIED、LOAD_START/OK、REQUEST_START、REQUEST_RETURNED、REQUEST_VALIDATED、STOP、SUMMARY。进程被外部硬杀或磁盘无法写入时可能只有未决 START；按 pending/不可重试处理，保留现有文件。禁止覆盖、断点续发、用旧请求结果填充本作业或把诊断 fixture 写进研究结果。

# 已完成阶段的复核入口

本轮实际执行已封存，不重跑旧输出目录的prepare/run/closeout。独立核验只读取来源、tokenizer和生成记录，不加载模型权重或调用API：

```bash
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python project/docs/reviews/20261105/pm_rl1_slight_positive_path/verify.py
```

15项定向测试：

```bash
env PYTHONPATH=project/src OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -q project/tests/test_rl1_slight_path_recovery.py
```

执行入口及本次用途：

- `171_probe_slight_positive_path.py`：固定N23的5个动态MS停止位置，复用2条，仅准备3个缺失请求；首次执行在加载前拒绝。原脚本和协议保留。
- `172_resume_slight_path_preload.py`：记录一次加载前接续，用局部低利用率容差执行原3个请求，旧公共检查器和失败记录保留。
- `173_replay_complete_frozen_ms_rank.py`：核验全部24个前缀旧MS分数覆盖，对N23完整旧语义排序执行一次MS，绑定G01旧偏好。不重训检索器、不推广为当前主线排名。
- `174_measure_reused_pair_g_latency.py`：2预热＋4配对，共10次固定G生成；仅量G首token/完成，不做Tokkio端到端声明。
- 本目录`closeout.py`：一次性分析并封存两个产物目录；`verify.py`独立复核。

新请求仍用原候选Gemma运行身份`cf84d46eccfb00133963f0b31e80eb323c0fa3c58ba64455b215c1a7dbcf0b3e`。所有G自然EOS结束；同输入回复可精确复用，计时重复不增加独立人评样本。费用、新训练及新人评均0。

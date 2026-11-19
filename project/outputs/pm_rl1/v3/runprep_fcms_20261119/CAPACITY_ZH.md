# 根盘和数据盘只读调查

精确采样时点、字节数、inode、GPU UUID/空闲及进程快照见 CAPACITY_READONLY.json。本次 root 和 /tmp 同属 /dev/sda2，可用 208,904,192 bytes（约 199 MiB）；数据盘 /opt/tokkio-data0 可用 327,303,786,496 bytes（约 304.8 GiB），约 5,960 万 free inodes。容量持续变化，不能把本次快照当作未来保证。

结合上一轮 /tmp 已发生 Errno 28，拟议执行器要求 root 至少保留 1 GiB、数据盘至少 4 GiB/1000 inodes。当前 root 不满足，运行必须停止在模型加载之前。已把 worktree、CPU 测试临时目录、日志和材料放在数据盘；这不能替代 root 储备修复。没有擅自删除任何旧文件，也没有清理其他人的缓存。

A6000 当时查询为 49,140 MiB 总量、48,551 MiB free，没有 compute PID；A4500 仅被只读列出，不允许回退使用。未来首次加载前重新检查 A6000≥40 GiB 空闲、无其他 compute PID；运行时若出现其他任务或空闲低于 4 GiB，只停止本作业子进程。没有占用/预留 GPU，没有停止任何其他任务。

TMPDIR/TMP/TEMP、HF_HOME/HF_HUB_CACHE/TRANSFORMERS_CACHE、XDG_CACHE_HOME、TORCH_HOME、TORCHINDUCTOR_CACHE_DIR、TRITON_CACHE_DIR、CUDA_CACHE_PATH、PYTHONPYCACHEPREFIX 与工作日志都必须在该作业的数据盘根目录。PYTHONDONTWRITEBYTECODE=1、离线加载、固定模型路径；不下载、不安装依赖。具体环境模板见 RUNBOOK_ZH.md。

需要磁盘负责人恢复至少拟定储备并提供新容量快照；本轮只调查，不替用户作删除决定。engineering_ready=false（运行环境），research_qualified=false，authorized=false。

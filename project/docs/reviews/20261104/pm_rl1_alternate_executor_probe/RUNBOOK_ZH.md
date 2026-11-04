# 复核与冻结边界

工作目录`/home/tokkio/Metacom5_3`。结果目录`project/outputs/pm_rl1/alternate_executor_probe_20261104_v1`。

已执行脚本`project/scripts/rl1/167_probe_alternate_executor.py`的prepare/run/analyze。prepare在首次成功冻结前修复了transformers新默认返回对象和本机没有accelerate的环境元信息读取；两次CPU预检均未进入模型加载或G调用。冻结后执行脚本未改，1次模型加载、36次生成全部自然结束，无自动重试。原生非思考模板仍有1次channel/字样泄漏，不能把自然结束等同于全部内容合格。

不可在已有目录重跑prepare/run/analyze或prepare_review；它们采用一次性写入，失败/原始输出不覆盖。原脚本及依赖哈希记录在PROTOCOL.json。新模型本地原件、36条消息、token、选取资源、原旧缓存均绑定；CARDS继承的原token计数仍属于旧G，新G真实token在REQUESTS/raw中，勿混用。

只做CPU复核，不重新生成或训练：

```bash
env HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
 project/docs/reviews/20261104/pm_rl1_alternate_executor_probe/verify.py
```

已有相关测试在本轮运行一次：

```bash
env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=project/src \
 /tmp/pmrl1-publication-20261022-venv/bin/python -m pytest -o addopts= -q \
 project/tests/test_rl1_environment.py \
 project/tests/test_rl1_local_backend.py \
 project/tests/test_rl1_resource_comparison_analysis.py
```

43 passed，退出0。HTML的内嵌JS经`node --check`和内存DOM/storage模拟验证默认未答、保存重载、导出study标识及答案；测试答案只在内存，未写人评文件，也没有真实浏览器视觉测试。

CONTENT_REVIEW_PRIVATE记录逐卡原文锚点、合法来源和观察；HUMAN_PAIRS_PRIVATE是盲评映射。浏览器答案只存在该浏览器localStorage，需导出或在对话中报告后方可接收；空表/测试数据绝不能当新人评。旧答案原则可复用，新输出不继承旧q/m。技术失败C未替换为事后看来更好的E。

本轮无付费请求、无模型下载、无PM或G训练。API旧账本SHA256仍为`e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417`。OUTPUT_MANIFEST冻结本轮产物；后续收到答案须另写追加文件及新收口，不改写本轮“尚未收到”的时点快照。

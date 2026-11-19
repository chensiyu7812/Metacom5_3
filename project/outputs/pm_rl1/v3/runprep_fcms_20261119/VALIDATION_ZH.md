# CPU 验证与失败记录

验证代码 HEAD：575011b43947f4aaf73d6bb31f376bf4c36405fc。所有测试使用 CUDA_VISIBLE_DEVICES 为空、离线模型资产、PYTHONDONTWRITEBYTECODE=1、数据盘 TMPDIR；没有真实 backend 调用。CPU fake 生成的是明确标记的机制 fixture，不进入研究材料。

| 检查 | 实际结果 | 限制 / 原因 |
|---|---|---|
| 初始定向测试 | 38 passed | 添加 family 约束前 |
| 加入 family 检查后 | 32 passed / 7 failed | 新实现误要求历史 family 等于当前 family；合法历史还包括祖先 family 闭包。失败 XML 原样保留 |
| 修正闭包、添加越界 family 回归 | 40 passed，14.68 s | 无跳过；没有改样本、问题或原协议 |
| 完整 V3 严格 CPU | 637 passed，126.97 s，0 failed/error/skip/xfail | JUnit gate PASS；新增 40 项，其余为本分支原 V3 |
| PP1 原生输入重分词 | 16/16 完全一致 | 不更改旧 input_ids/payload/顺序 |
| A0 原生输入重分词 | 4/4 完全一致 | 70/877 token 各重复两次，无输出 |
| renderer 对照 | 32 个新预览；旧 renderer 的 16 项与 PP1 精确相等 | 8×2 renderer×OFF/MS 夹具；不是 DP 的人工选取 |
| renderer 安全编码 | 30 项通过 | 含全部 24 个原生 special tokens、闭合标签、引号、反斜杠、HTML 实体、换行/控制字符；仅编码边界，不是模型注入行为证明 |
| DP 交互 | Node DOM harness PASS | 8 前缀、无结果声明门禁、none 草稿、切换清空、textContent/CSP；没有浏览器视觉验收 |
| 权重/非权重 SHA | 7/7 相同；170.53 s | 流式读文件字节，0 model/tensor load；未来每次获准作业仍必须重算 |
| 既有材料保全 | 见 PRESERVATION.json | #19 基础上只新增文件；实际旧路径逐字节核对 |

机制覆盖：授权为空/跨 A0-PP1/错误 plan SHA 拒绝；内部 worker 拒绝独立启动；首次超时/空回复/中断停止且保留 START；第三次 length 停止，截断和尾项保持 pending；A0 首次截断/重复差异停止；自己的 CPU dummy 子进程超时强制退出；O_EXCL 防覆盖；加载缺失权重拒绝；ROOT 容量不足拒绝；DP 跨 owner/family/未来/RAW 篡改拒绝，未确认正式样本拒绝，无材料不伪装 DP，冻结只一次。没有用 GPU 验证 worker 加载兼容性，仍需独立获准 A0。

初始构建仅使用短执行器 commit 名；为最终申请固定完整 SHA，在新 cpu_v2 重建。初版完整保留于 /opt/tokkio-data0/tokkio_projects/pmrl1-validation/runprep-20261119/cpu_short_head_superseded，不覆盖任何旧冻结证据。保全脚本一次因 git 未使用 -z 而把中文文件名的转义文本误当路径，改为 NUL 分隔后复核；这不是旧文件缺失，也未修改旧文件。

新 Draft PR 最终交付 HEAD 的 hosted CI 以 PR 上实际 workflow 和逐 step 回执为准，提交时仍 pending；不借用父 #19 或较早代码 HEAD 的绿色结果。公共 CPU 工作流之外的全仓 tests/ 不在本轮伪称全绿：B #20 对照仍有 99 旧失败；A #19 上轮本地完整检查的磁盘失败与复测证据保留。此次新运行执行器相关的完整 V3 已通过，公共 CPU 全量由本 PR CI 再验。

本轮跳过真实 GPU/Generator/Judge/训练，是研究者明确未授权；不是测试 PASS。研究质量和授权均未因此升级。

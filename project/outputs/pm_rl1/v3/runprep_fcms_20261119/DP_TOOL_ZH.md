# DP-MS 人工选择工具与资格条件

入口 cpu_v2/DP_SELECTOR_8.html 可离线打开；包含原 8 个固定前缀及全部 87 份合法历史 RAW，按历史时间排列。输入是 #19 完整 DP_REVIEW_POOLS，无 RET 排名、Generator 回复、Judge 分数或比较结果。原 8 个 DP_PENDING proposal_id 仅作溯源，不替换成新的已选状态。

界面只显示当前合法前缀、过去完整会话及其日期和会话标识。可选一份完整会话、没有适合材料或无法确定。必须填写选择者、当前需求、材料如何满足需求（或为何没有合适材料），并声明尚未看过此 prefix 的 Generator 比较结果。不得为了正面结果换样本。选取者的声明不是对外部行为的技术证明；人员隔离及不接触结果仍由研究负责人落实。

浏览器下载的是待冻结草稿，不上传数据、不写仓库。CLI 冻结重新检查 pool/bundle/source hash、时间、owner、family 闭包、完整 RAW 覆盖，写 UTC 冻结时点、原声明时点及来源 SHA。对每个 prefix 固定一个 O_EXCL 文件名；重复提交（包括相同选择）拒绝，不能无声重选。receipt 仍标 human_choice_recorded_pending_researcher_confirmation，research_qualified=false、authorized=false。两个目录手工复制、伪造声明或外部看过结果不是工具可单独排除的行为；正式数据由指定保管者统一冻结目录，B 对其 SHA 复核。

~~~bash
# 环境按 RUNBOOK 设置；只需 CPU
python project/scripts/rl1v3/dp_ms_select.py freeze \
  --bundle project/outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/DP_SELECTOR_BUNDLE_8.json \
  --draft /DATA/actual-human-choice.json --out /DATA/frozen-dp
~~~

本轮没有代填任何真人选择，未创建真实人审 receipt。测试中的 synthetic-test-only / UNIT_TEST_NOT_A_HUMAN 仅存在 CPU 测试临时目录，绝不作为资格证据。

## 正式 90 条与导出

B INITIAL_SCREEN_90 仍是候选。研究者确定前缀清单后，在 FORMAL_SAMPLE_TEMPLATE.json 填 owner_id/session_id/cut_turn/prefix_id 的顺序列表、prefixes_sha256、签署人和决定证据。样本资格不因以前被查看过而自动排除；应记录选样、调参及结果使用历史，不能用待报告结果反向调样。

prepare 仅接受 researcher_confirmed=true 的固定清单；从 registry 构造 MS_RAW-only as-of snapshots 和 SourceFrontier，同时形成独立的 lexical-v0 RET 审计包。RET 材料不展示给选择者：

~~~bash
python project/scripts/rl1v3/dp_ms_select.py prepare \
  --sample-manifest /DATA/researcher-fixed-screen90.json --out /DATA/screen90-dp
~~~

导出前必须每个 prefix 有一次冻结选择（包括 none/uncertain），并为全实验传入一个 renderer：legacy 或本轮 candidate 的完整 renderer_id。

~~~bash
python project/scripts/rl1v3/dp_ms_select.py export \
  --bundle /DATA/screen90-dp/SELECTOR_BUNDLE.json \
  --receipts /DATA/frozen-dp \
  --ret-audit /DATA/screen90-dp/AUDIT_RET_NOT_FOR_SELECTOR.json \
  --baseline project/outputs/pm_rl1/v3/ms_pp1_prepare_20261119/cpu_v2/BASELINE.json \
  --renderer renderer-fcms:e675b43535843b6d0a9f0410d14294249572290c60325a11f8081678c61880dc \
  --out /DATA/fc-ms-candidates.jsonl
~~~

输出 OFF / DP-MS / RET-MS 用同一 prefix、G、decode、renderer，均带新 FC-MS-preview 身份、原生 input_ids/hash 和容量结果，runtime_callable=false。无适合历史的 DP 或 RET 没有 model_input，不能伪装为成功 OFF。DP 来源选择与 RET 审计独立；即使恰好选同一会话也保留两份独立选择证据，不更名。候选先交 B 核查，正式人审确认/协议采用及后续运行授权另行决定。

HTML 将载荷 base64 编入脚本，再用 textContent 插入 DOM；没有 innerHTML 或网络请求。CSP 禁止连接、外部内容和表单提交。编码测试不能证明选择者语义判断正确。RAW 人物自述、第三人经历、建议/意图/执行/结果和跨阶段变化仍需逐案判断。原五项人工标注 pending 不变。

# FC-MS 人工 DP v2：字段、角色、冻结时点与请求绑定

新工具为 `project/scripts/rl1v3/dp_ms_select_v2.py`，新协议 `pmrl1-dp-human-selection-2`。原 `dp_selection.py`、旧界面、旧冻结receipt和已签收#23执行器不变；不把旧receipt重标成v2。没有新增Generator prompt，renderer仍是#21的line-quote-1 `renderer-fcms:e675b435…`。

## 选择与语义字段

界面只展示当前前缀及完整合法过去会话，按时间排序。它不展示筛查标签、检索排序、评分、Generator回复或Rule-DP选择。人工可选selected、none_suitable或uncertain；不强制选会话、不拼接伪会话、不换样本。

| 字段 | 规则 |
|---|---|
| `single_session_coverage` | full / partial / none；描述所选单一会话，不是历史库总体覆盖 |
| `missing_need` | partial/none必填；full必须为空，避免自相矛盾 |
| `staleness_issue` / `staleness_detail` | 显式布尔；true时必填说明，UI允许将无法排除的疑点标true |
| `stage_issue` / `stage_detail` | 显式布尔；true时必填说明，区分想做、尝试、完成、失败、拒绝与更新 |
| 原字段 | 当前需求、理由、selector、declared_at、完整来源、snapshot/source/receipt SHA继续保留 |
| 盲态声明 | 未看Generator结果/比较分数、未看检索排序；必须分别确认 |

none_suitable/uncertain必须无source，coverage=none，并说明缺失或无法确认之处。它们保留为没有可执行DP材料的pending行，不伪装成OFF或RET。partial允许保留所选完整会话，同时保留未覆盖需求；不会自动追加第二会话。

## 角色与时间

资料负责人提供角色登记：`sample_identity`、`people`（人员代码→同一人的稳定person_id）、`assignments[prefix_id]`（selector以及Q0/QH/F各自reviewers）、signed_by/evidence/frozen_at。当前版本在冻结选择时要求登记完整；未分配人员保持pending，不代填真实人员。检查按person_id比较，不能靠给同一人两个代码绕过隔离。

冻结时核查角色、完整来源和必填语义字段；系统写入frozen_at并用固定prefix路径O_EXCL一次写入。声明时间不得晚于冻结；角色登记先于选择冻结。receipt包含角色登记SHA和全部语义字段，因此改理由、来源、时间、覆盖或人员会破坏原绑定。人工真实行为与人员代码的真实性仍需协调人落实，程序不能证明选择者在其他渠道没有看过结果。

## 真实筛查与正式计划

`prepare`必须提供研究者已确认的sample manifest及B核验过的真实筛查ledger封套。封套字段为：`simulated=false`、`verified_by`、`verification_evidence`、`frozen_at`、`labels`、`labels_sha256`；labels采用B现有replan的四字段prefix_id/owner_id/group/need。manifest另绑定`screening_receipt_sha256`及frozen_at。真实核验出处必须指向B验证过的人工最终导出；仅改simulated标志不能证明人工来源。

工具拒绝模拟、未确认、hash不符、重复、含outcome字段或未在真实筛查中得到S1/S2/S0标签的正式样本。它不选择样本数量、不重新排序筛查标签、不依据模拟标签提前固定正式90条或其子集。B的S7/unclear处理仍留在正式设计中，不偷偷纳入已解决的DP比较样本。

`export`只生成同一renderer的OFF/DP-MS/RET-MS候选和`PLAN_BINDING.json`。计划固定sample/screening/bundle/roles SHA、每个prefix的选择receipt SHA、全部请求及有序request IDs；明确列出无材料的pending项。它不包含Rule-DP生成臂，也不产生运行授权。

`check-start`重算全部绑定，在未来FC-MS作业第一次持久START之前核验：选择冻结早于计划冻结，且选择与计划均严格早于该次START。它使用当前机器时间，输出`generation_started=false, authorized=false`，不是可提前保存后重复使用的运行票据。未来FC-MS执行入口必须在写第一个START前调用`check_start`；当前没有正式FC-MS作业/执行器集成，因此不声称已经实测生成阶段门禁。已签收A0/PP1执行器不受影响。

`check-reviewer`供审阅包构建入口检查实际prefix/channel/assignee，重新核对选择receipt与角色登记，拒绝选择者本人或别名。B仍须在真实审阅包构建时调用并独立验证，不能仅核对一份纸面角色表。

## 命令与输出边界

- `prepare --sample-manifest ... --screening ... --out ...`：真实筛查后产生合法选择池；只向选择者交付SELECTOR文件，AUDIT_RET由协调人保管。
- `freeze --bundle ... --draft ... --roles ... --out ...`：冻结一次人工选择；只打印receipt SHA。
- `export --bundle ... --receipts ... --roles ... --ret-audit ... --baseline ... --sample-manifest ... --screening ... --out ...`：CPU原生tokenizer，生成候选请求和计划绑定，不加载G。
- `check-start --plan ... --requests ... --bundle ... --receipts ... --roles ... --sample-manifest ... --screening ...`：将来的FC-MS START前检查。
- `check-reviewer --plan ... --bundle ... --receipts ... --roles ... --prefix-id ... --reviewer ... --channel Q0|QH|F`：审阅包分发前检查。

产生文件的命令要求输出位于数据盘且不在任何Git checkout内，防止误把原文包写入公开仓库。本轮只提交工具源码、纯合成测试和不含原文的准入记录；没有生成真实DP包、实际选择或正式样本。

## 验证与待办

21项纯合成CPU测试覆盖字段、none/uncertain、一次写入、别名角色冲突、真实/模拟筛查准入、plan/receipt/request篡改、START先后和Rule-DP拒绝。离线界面另用真实headless Chrome验证字段与下载逻辑，GPU禁用；收据与合成页面留数据盘。首次浏览器启动因TMPDIR路径过长失败，保留失败日志，改用本作业自己的短数据盘临时路径；未删除或清理他人文件。

最终测试数字、CI与B交接在PR回执补记。B须对v2工具、真实screening封套对接及未来实际DP/RET请求重新验收；已签收E6不扩大到DP。engineering_ready只指验证范围，research_qualified=false、authorized=false。

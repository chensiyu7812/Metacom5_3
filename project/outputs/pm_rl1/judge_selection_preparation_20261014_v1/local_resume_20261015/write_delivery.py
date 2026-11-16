"""Write local-only review artifacts from completed immutable records."""
from pathlib import Path
import sys,datetime,hashlib
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent))
import selection as s
from resume_engineering import now

r=s.read(OUT/'results_private.json');audit=s.read(OUT/'final_integrity_audit.json')
plan=s.load_plan();stamp=now();rows=r['all_eight_slots']
root=s.HERE/'live_runs';c1=root/'continuations/engineering_AB_resume_20261015_01';c2=root/'continuations/engineering_AB_resume_20261015_02'
def write_new(path,text):
    with Path(path).open('x') as f:f.write(text)

review=dict(time_jst=stamp,scope='diagnostic reading of completed final text only; no score repair, new draw, human calibration or qualification',
    item_key='dev02B',evidence_identity=plan['items']['dev02B']['evidence_identity'],
    current_source_anchors=plan['items']['dev02B']['evidence']['current_prefix'],
    bound_outputs=[dict(configuration=x['configuration'],request_id=x['request']['request_id'],
        response_artifact=x['artifacts']['response'],formal_measurement=x['measurement'],
        final_content_sha256=hashlib.sha256(x['final_output']['content'].encode()).hexdigest()) for x in rows if x['started']],
    observations=[
      'Both completed final answers retain an outer Markdown json fence; unchanged strict parsing fails. No fence removal or numeric score recovery was applied.',
      'Both final rationales attribute the wish to help others and vulnerability to the current seeker/user and cite C:T006. That turn supports the stated motivation; this does not cover the separate friend-versus-assistant subject trap in dev15B.',
      'A labels R001-R003 supported with C:T006; B labels all five units non_factual. R003 contains a specific claim about the user motivation mixed with general support. B says it reflects stated motivation while denying it asserts a personal fact; this conflicts with, or at minimum fails to explain compliance with, the frozen mixed-claim inspection instruction. This diagnostic issue is not converted to m or U.',
      'A and B here judged the same reply, not the distinct dev37A/dev37B equivalent pair. No conclusion about equivalence stability is possible.'],
    subject_trap_dev15B='not_dispatched_after_STOP',equivalence_dev37A_dev37B='not_dispatched_after_STOP',
    dev35='not covered; remains in original development list',q=None,m=None,U=None,reward_eligible=False,
    new_independent_human_reviews=0,semantic_revision_delta=0)
s.save(OUT/'semantic_diagnostic_private.json',review)

table=['|原顺序|配置|题号|状态／未派发原因|正式 q / m / U|输入 tokens（实际；未派发为预检）|',
       '|---:|---|---|---|---|---:|']
for x in rows:
    state='已开始；完整输出解析失败，配置停止' if x['started'] else '未派发：该配置首项失败，保留 STOP'
    n=str(x['actual_input_tokens'])+'（实际）' if x['started'] else str(x['preflight_input_tokens'])+'（预检）'
    table.append(f"|{x['order']}|{x['configuration']}|{x['item_key']}|{state}|null / null / null|{n}|")
tele=['|配置|单次耗时 s|生成路径 s|输出总 tokens|thinking / final / format|峰值 allocated / reserved bytes|自然结束|',
      '|---|---:|---:|---:|---|---|---|']
for x in rows:
    if x['started']:
        t=x['tokens'];tele.append(f"|{x['configuration']}|{x['elapsed_seconds']:.6f}|{x['gpu_seconds']:.6f}|{t['total_output']}|{t['thinking']} / {t['final']} / {t['format']}|{x['peak_allocated_bytes']} / {x['peak_reserved_bytes']}|是，EOS 106|")
checks=[]
for folder in (c1,c2):
    for f in sorted(folder.glob('gpu_check_*.json')):checks.append((f,s.read(f)))
checktable=['|接续／检查|开始—结束（JST）|空闲 MiB|利用率|可见 PID|结果／拒绝原因|',
            '|---|---|---:|---:|---|---|']
for f,x in checks:
    gpu=x['selected_gpu'];name=f.parent.name[-2:]+'/'+f.stem.split('_')[-1]
    times=x['start_jst'][11:23]+'—'+x['end_jst'][11:23]
    pids=','.join(str(p['pid']) for p in x['visible_processes']) or '未列出'
    reason=', '.join(x['rejection_reasons']) or ('通过加载前原空闲条件' if x['own_pid'] is None else '通过驻留模型进程检查（仅本进程）')
    checktable.append(f"|{name}|{times}|{gpu['free_mib']}|{gpu['utilization_percent']}%|{pids}|{reason}|")
bind=[]
for x in rows:
    if x['started']:
        bind.append(f"- {x['configuration']}：request `{x['request']['request_id']}`；配置 `{x['request']['configuration_identity']}`；原始输出文件 [{x['configuration']} raw](../live_runs/{x['candidate']}/{x['request']['request_id']}.raw.json)，完整原生解析输出与理由／引用 [{x['configuration']} response](../live_runs/{x['candidate']}/{x['request']['request_id']}.response.json)。")
post=s.read(OUT/'post_run_read_only/gpu_check_0001.json')
report=f'''# PM-RL1 原 Gemma A/B 首轮接续结果

生成时间：{stamp}。本轮已停止，等待研究者审阅。**原 8 项中 A/B 各开始 1 项，共 2 次；两次均为完整输出的严格 JSON 解析失败，余下 6 项按既定 STOP 未派发。累计 66＋2＝68/140。** 原批准的新增 8 次／累计 74 次上限未提高、未重置。

## 接续身份与工程边界

仓库真实路径 `{s.REPO}`，分支 `{audit['branch']}`，HEAD `{audit['head']}`。四配置 plan `{r['plan_identity']}`；原实现 `{r['original_implementation_identity']}`；独立工程接续代码 `{r['engineering_resume_sha256']}`。原合同 SHA256 `{audit['contract_sha256']}`。原 608 个交付文件、上轮 30 个回执文件、既存 9 个工作文件均哈希不变。

原阻塞阶段 `live_runs/engineering.AB.stage_result.json`（SHA256 `427fdec76f0b6d81f854e0baf9f705f5520ae6713de1a8c10126164dbee7944b`）保留。接续 `_01` 保存诊断中断历史，`_02` 保存这两次实际执行；二者均绑定原父阶段、批准、请求清单，后者还关联前者。没有新实验、新抽样或新增额度。原 8 项仍属于各配置原 40 次开发清单。

模型 `google/gemma-4-12B-it`，revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`，A `enable_thinking=False`，B `True`。共用已校验权重，BF16、SDPA、greedy、原环境、单卡 A6000 UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4` 均不变；未重下载、未安装依赖、未量化、未改提示或评分。实际输入长度分别 28,187／28,185，与先前完整原生模板回执相同；上下文 262,144、最少输出预留 32,768，未静默截断。各配置完整参数在 `results_private.json` 的 planned/executed_configuration 中；冻结配置里的旧 readiness 描述仍保留，实际可运行状态以本次 artifact_preflight 与结果为准。

## 八项完整状态

{chr(10).join(table)}

未知运行失败、超时、输入／输出截断均未观察到；正式解析失败 2 次，未派发 6 项单独列出。没有正式语义分数，不能把缺测当 0，也不能把未派发项计为模型失败。失败请求保留 started/raw/response/result 四件记录，未重试；两个 STOP 均保留。

## 完整输出、计量与绑定

{chr(10).join(tele)}

两次最终内容都以字面量 Markdown ` ```json ` 围栏起始，以围栏结束；原生处理器成功分离通道并自然结束，但冻结的 `judge_completion.parse_completion` 对完整 final 严格 `json.loads`，报 `Expecting value: line 1 column 1 (char 0)`。失败归类为解析失败，并非超时、输出未完或语义不确定。没有去围栏、截取内层 JSON、填补分数或修改解析器。原文内任何数字均未写成正式 q/m/U。

{chr(10).join(bind)}

两项共用 dev02B 输入／回复绑定：messages `{rows[0]['messages_identity']}`，schema `{rows[0]['schema_identity']}`，回复 SHA256 `{rows[0]['reply_sha256']}`，合法来源 `{rows[0]['evidence_identity']}`。全部 8 个完整 request/config/input/reply/evidence 身份与原始文件哈希见 [results_private.json](results_private.json)；可直接查看的逐项表见 [eight_slots_private.csv](eight_slots_private.csv)。原始完整来源保留在固定 plan，不向外发送。

生成路径耗时 A 102.091279 秒、B 133.002148 秒，合计 **235.093427 秒**；共享加载一次 **10.235682 秒**，从共享加载入口至阶段完成的驻留窗口 **251.159757 秒（约 4.186 分钟）**。这是 runner 实测墙钟区间，包含相应前处理／查询／同步开销，不是 CUDA 内核活跃时间或利用率积分；共享加载与驻留时间不按 A/B 重复相加。最大 allocated 约 37.108 GiB，reserved 约 41.594 GiB。校正后的进程整体墙钟 285.492392 秒（含文件核验、前检与退出），退出码 0。

本轮新增 API／付费调用费用 **0 美元**，下载流量 **0**；上一轮唯一下载的 23,951,746,871 字节不重复计费。未提供本机 GPU 电价或租赁单价，不能把 GPU 时间换算成实际货币成本；能耗未测量。既有共享付费账本仍为 1.50724291 美元、未结责任 0，账本哈希不变。旧两轮请求／原始输出／测量重新核对各 33；新池真实 started 恰为 2，无孤立记录、无重复派发。详见 [最终完整性审计](final_integrity_audit.json)。

## GPU 守卫与诊断

未改变加载前空闲显存至少 45,000 MiB、利用率恰为 0% 的条件。原 `selection.py` 一次查询和笼统拒绝缺少日志；新独立入口精确匹配 UUID，并保留每次 GPU CSV、计算进程 CSV、完整 NVIDIA XML 的原始 stdout/stderr、退出码、时间、进程与明确拒绝原因。查询失败、解析失败、进程信息不可见与成功空列表分开处理。

{chr(10).join(checktable)}

原只读等待窗口从 **11:15:26.427950** 到 **11:20:26.427950 JST**，校正后在 **11:18:39.062832** 完成通过检查，未重置 5 分钟。初版新增辅助 `/proc/1/ns/pid` 检查时错误地把 PermissionError 设为拒绝；这不是 NVIDIA 进程查询失败。该工程错误已纠正为单列可见性限制，第一版代码和全部 7 个检查不删除。只对明确匹配的本轮自有等待进程 PID 618955 发出 SIGINT，发生在无模型请求的 sleep 间隔；同学和其他用户进程未被操作。见 [工程修复记录](ENGINEERING_REPAIR_ZH.md) 及 `diagnostic_interrupt_receipt.json`。

12 次执行检查的 36 条 NVIDIA 查询全部成功；初始空列表仅代表查询当时未列出进程，不证明不存在隐藏／瞬时／随后出现的任务。加载后 4 次只列出本轮模型 PID 619502；驻留阶段沿用原排除其它进程的守卫，模型自身显存和负载不重复按加载前阈值检查。没有以“未列出进程”推断 2% 负载的来源，也没有放宽阈值。

退出后另做一次只读结尾观察（不用于派发，也不是新的等待窗口）：{post['start_jst']}，空闲 {post['selected_gpu']['free_mib']} MiB、利用率 {post['selected_gpu']['utilization_percent']}%，进程查询成功且未列出进程，按原空闲规则仍会拒绝此时加载；本轮模型进程已退出。原始回执在 `post_run_read_only/gpu_check_0001.json`。执行前检的全部原始输出在两个 `live_runs/continuations/.../gpu_check_*.json`；本报告不把结尾观测覆盖到执行前的事实。

## 语义复核范围与下一步

仅查看两次已完整结束的 final 文字，作为本地诊断；不修复正式解析、不把思考片段当评分，也不计为新独立人评。两者均把帮助他人的动机与脆弱感归给当前 seeker/user，并引用 C:T006；该条直接支持这两点。但 dev02B 不覆盖 dev15B 的“朋友／历史支持者／新 AI”主体陷阱。dev15B 未派发，主体陷阱检验仍待原清单。

可见的诊断问题：A 将 R001–R003 标为 supported 并引用 C:T006；B 将全部五个单元标为 non_factual。R003 同时包含一般支持和对用户个人动机的具体陈述，B 的理由一方面承认其反映用户已表达的动机，另一方面否认个人事实断言；这与冻结的混合断言检查要求存在不一致，至少缺少按该要求展开的解释。它只是一条已观察到的语义诊断，不转化为 m/U，也不据此排名。完整锚点和绑定见 [semantic_diagnostic_private.json](semantic_diagnostic_private.json)。

dev37A/B 等义对照均未派发，不能以本次 A/B 同一回复的差异冒充等义测试；第 35 题及其它风险留在原开发清单，没有临时加题。工程上已证实权重／环境／指定 GPU 可以加载并完整生成，尚不具备按冻结接口持续得到正式评分的条件。两配置停止，奖励资格未建立，不能宣称准确或获胜；DeepSeek C/D 未运行，不作四配置排名。

**最小下一步是先审阅这两份完整格式失败记录，决定是否另行批准仅针对外层格式的接口修正及其后续执行范围。** 本轮未实施该修正、未解除 STOP、未重算这两次分数，未运行任何恢复请求。工程守卫修订与裁判语义修订分别记录：本轮语义修订增量 0，总数仍为 1。余下开发、冻结、封存 24 对、12 次复评、自然任务训练和两层联合训练均未启动。没有提交、推送或上传任何材料。

测试：先于实际模型请求完成 53 项离线测试（20 项接续／守卫，33 项原 runner），覆盖阻塞后接续、跳过已开始／已完成、孤立输出保守计数、不可覆盖、失败配置停止而同伴可继续、同学计算／图形进程导致阻塞、查询异常与可见性、阈值不变及 5 分钟上限；日志 [tests_corrected.log](tests_corrected.log)。工程入口与测试位于上级 `resume_engineering.py`、`test_resume_engineering.py`，不修改原执行器或裁判。
'''
write_new(OUT/'RESULTS_ZH.md',report)
status_path=s.REPO/'project/docs/PM_RL1_CURRENT_STATUS.md'
old=s.read(OUT/'baseline.json')['current_status_before']
assert status_path.read_text()==old
write_new(OUT/'PM_RL1_CURRENT_STATUS_before_resume.md',old)
status=f'''# PM-RL1 当前状态

更新：{stamp}（Asia/Tokyo）。**Gemma A/B 原首轮接续已停止：各开始 1 项，均因最终输出带 Markdown 围栏而被冻结的严格 JSON 解析器拒绝；余下 6 项按原 STOP 未派发。累计评分尝试 68/140，等待研究者审阅。** 本文件仅含可分享摘要，私人来源、标注、完整输出和诊断留在本地忽略目录。

长期目标是分别用 RL 学习资源获取及资源使用／回复策略，再研究两层协同。当前阶段仍是既有有界监督适配后冻结执行器，仅训练 GET／STOP；不设计或启用未来 Step 2、不联合训练。完成标准是环境、奖励、训练与对照可信，不保证 PPO 获胜，SFT 完成不证明资源使用正确。见[路线澄清](PM_RL1_TWO_STAGE_ROUTE_20261015_ZH.md)。

真实仓库 `/opt/tokkio-data0/tokkio_projects/Metacom5_3`，`/home/tokkio/Metacom5_3` 为链接。分支 `work/paper1-rq1-integration-20260816`，HEAD `{audit['head']}` 未变化；既存 9 个工作文件及原合同、修订历史保留，未提交或推送。

[控制合同](pm_rl1_completion_20260930_v2/execution_contract.json) SHA256 `{audit['contract_sha256']}`；当前四配置协议 `{r['plan_identity']}`，原实现 `{r['original_implementation_identity']}`。新增独立工程接续代码 `{r['engineering_resume_sha256']}`；模型、提示、评分规则、请求身份均未变，裁判语义修订增量 0（累计仍为 1）。原 608 个交付文件、上轮 30 个回执文件校验通过。

本次接续关联原 GPU 阻塞回执，重建 started/result/raw/response 的真实账本，已有尝试不可重派，旧记录不覆盖、不删除、不清零。先完成 53 项离线测试，再在原 5 分钟只读窗口内于 11:18:39 JST 满足指定 A6000 空闲 48,551 MiB、利用率 0% 的条件。每次保留原始查询与拒绝原因，空进程列表仅作可见性观察。新增辅助命名空间诊断曾误拒绝，已单独记录修正，窗口未重置、原显存／0% 阈值未放宽。未操作同学或其他用户进程。

固定模型 `google/gemma-4-12B-it` revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`，A thinking=False、B=True；BF16、SDPA、greedy、原环境与单卡部署不变。复用上一轮已下载并校验的共享权重，未重下载或安装。两次完整原生输入 28,187／28,185 tokens，与预检一致，输出预留符合原要求，均自然结束。正式 q/m/U 为 null，没有去围栏补分或重试。

旧账本重新核验 33＋33＝66 次，本轮新增 2 次失败尝试，新池累计 2/8，总计 **68/140**；本轮累计上限 74 不变。共享模型加载一次 10.236 秒，生成路径合计 235.093 秒，驻留窗口 251.160 秒；最大 reserved 约 41.59 GiB。新增 API 费用 0 美元、下载 0；共享付费账本仍 1.50724291 美元、未结责任 0。GPU 时间为实测墙钟区间，未换算货币成本。

工程加载与完整生成已验证，冻结输出接口仍有格式阻碍。完整 final 的诊断还发现对混合个人断言的分类分歧；这不产生正式分数或奖励资格。主体陷阱题和等义对照题因 STOP 未覆盖，第 35 题等仍留原开发清单。DeepSeek C/D、剩余开发、恢复、冻结、封存、独立复评及自然任务训练均未执行，不作四配置排名，不将 Du 派生记录视为独立人评。

待审阅事项：两份完整格式失败记录，以及是否另行批准仅针对外层格式的接口修正和后续范围。本轮未改解析器、未解除 STOP、未追加模型请求。原状态快照和原阻塞报告保留；只准备文档，不推送。

详细结果：`project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/local_resume_20261015/RESULTS_ZH.md`。同目录 `results_private.json`、`eight_slots_private.csv` 包含 8 项状态、完整绑定、计量和本地原始文件路径；`ENGINEERING_REPAIR_ZH.md`、`final_integrity_audit.json` 记录工程变更与核验，原始 GPU 回执在上级 `live_runs/continuations/`。
'''
status_path.write_text(status)
print('Wrote RESULTS_ZH.md, semantic_diagnostic_private.json, prior status snapshot and current shareable status; no execution.')

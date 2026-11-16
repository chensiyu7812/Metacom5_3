from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import selection as s
from resume_engineering import now

r=s.read(HERE/'results_private.json');p=s.read(HERE/'protocol.json');stage_dir=s.HERE/'live_runs/output_interface_v1/stage';stage=s.read(stage_dir/'stage_result.json')
def qm(m):return '—' if not m else ' / '.join('null' if m.get(k) is None else str(m[k]) for k in ('q','m','candidate_utility'))
table=['|顺序|配置／题号|原严格接口|新接口离线派生|本轮新实时|未派发／停止说明|','|---:|---|---|---|---|---|']
timing=['|配置／题号|实际输入|总输出|thinking / final / format|单次墙钟 s|生成路径 s|allocated / reserved bytes|','|---|---:|---:|---|---:|---:|---|']
notes=[]
for x in r['rows']:
    old=x['previous_strict_result'];derived=(x['offline_derived_result'] or {}).get('measurement');live=(x['new_live_result'] or {}).get('evaluation',{}).get('measurement')
    oldtxt='解析失败；'+qm(old) if old else '未开始'
    derivedtxt=qm(derived)+'（派生）' if derived else '无'
    livetxt=(live['measurement_status']+'；'+qm(live)) if live else '未派发'
    review=x['source_review'];reason=x['not_dispatched_reason'] or ('语义硬停' if review and any(review[k] for k in ('material_source_proven_error','critical_unknown','unexplained_equivalence_difference')) else '本项完成；范围结束后停止')
    if live and live['measurement_status'] not in s.VALID:reason='技术失败，配置停止；校验阶段 '+x['new_live_result']['evaluation']['validation_stage']
    if x['previous_started']:reason='旧请求不重派；原失败/null/STOP保留'
    table.append(f"|{x['order']}|{x['label']} / {x['item_key']}|{oldtxt}|{derivedtxt}|{livetxt}|{reason}|")
    if x['new_live_started']:
        t=x['new_live_telemetry'];tokens=t.get('token_accounting',{})
        timing.append(f"|{x['label']} / {x['item_key']}|{t.get('input_tokens')}|{tokens.get('total_output')}|{tokens.get('thinking')} / {tokens.get('final')} / {tokens.get('format')}|{x['new_live_result']['elapsed_seconds']:.6f}|{t.get('gpu_seconds')}|{t.get('peak_allocated_bytes')} / {t.get('peak_reserved_bytes')}|")
    if review:notes.append(f"- {x['label']} / {x['item_key']}：{review['explanation']} 来源检查、完整引文及该次原始响应哈希见对应 `.review.json`，以及 results_private.json 的 source_review。")
checks=[s.read(f)|{'file':str(f)} for f in sorted(stage_dir.glob('gpu_check_*.json'))]
gpu=['|检查|开始—结束（JST）|空闲 MiB|利用率|可见 PID|结果／拒绝原因|','|---:|---|---:|---:|---|---|']
for g in checks:
    v=g['selected_gpu'] or {};visible=','.join(str(z['pid']) for z in g['visible_processes']) or '未列出'
    gpu.append(f"|{g['check_index']}|{g['start_jst'][11:23]}—{g['end_jst'][11:23]}|{v.get('free_mib')}|{v.get('utilization_percent')}%|{visible}|{', '.join(g['rejection_reasons']) or '通过（加载前空闲／加载后仅本进程）'}|")
idle=s.read(stage_dir/'idle_wait_result.json');receipt=s.read(HERE/'process_receipt.json')
configs='\n'.join(f"- {cfg['label']}：`{cfg['identity']}`；原 `{cfg['original_configuration_identity']}`。" for cfg in p['configs'].values())
report=f'''# 输出外层接口适配与原清单接续结果

时间：{now()}。本轮已完成获准范围并停止。新增真实尝试 **{r['new_live']['started']}**，累计 **{r['history']['cumulative_calls']}/140**；原 8 槽跨版本共 {r['history']['started_or_evidenced']} 次开始／已有证据，未超过 8，累计未超过 74。没有 dev02B 重派、自动重试或新实验。新增 API 费用 **0 美元**。

## 三类结果分别报告

|来源|请求／记录数|机械校验有效|技术失败|调用增量|含义|
|---|---:|---:|---:|---:|---|
|原严格接口 dev02B A/B|2|0|2|已计入原68|正式 q/m/U 仍 null，不改称首试成功|
|同两份 final 的新接口离线派生|2|{r['offline_derived']['valid']}|{2-r['offline_derived']['valid']}|0|开发派生；独立样本增量0，原输出和失败不改|
|本轮获准剩余6槽的新接口实时|{r['new_live']['started']}|{r['new_live']['mechanically_valid']}|{r['new_live']['technical_failed']}|{r['new_live']['started']}|另有{r['new_live']['not_dispatched']}槽未派发；语义问题独立于机械校验|

这些类别不合并成“新接口首试成功率”，也不把派生恢复当新抽样。机械校验通过不是语义正确、奖励合格或后续阶段许可。

## 原八槽完整状态

表内数字依次为 q / m / U；null 为缺测，— 表示不存在该类记录。

{chr(10).join(table)}

所有原／新 request_id、原槽位映射、完整配置、提示／schema／回复／来源哈希、实际 final、评分理由与引用、耗时、token、显存以及原始文件路径见 [results_private.json](results_private.json)；可筛选表见 [eight_slots_private.csv](eight_slots_private.csv)。完整原始输出只存本地 `../live_runs/output_interface_v1/<candidate>/`；两份旧 dev02B 原始文件仍在原 candidate 目录，派生记录在 `derived/`。

## 接口身份与不可变部分

原仓库 HEAD `0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28`，分支 `work/paper1-rq1-integration-20260816`。原四配置 plan `{p['original_plan_identity']}` 未回写。本轮独立协议 `{p['identity']}`；接口 `{p['interface']['version']}`，身份 `{p['interface']['identity']}`，代码 SHA256 `{p['interface']['code_sha256']}`。四项完整新配置均包含同一接口及新编排身份，C/D只登记、不执行：

{configs}

适配器只接受完整裸 JSON 对象，或整个 final 恰好一个 json／无标签三反引号围栏；仅去外层界定符，内部文本不改。禁止解释文字里搜 JSON、选择多块、补全或修改字段、数值、来源。只读取原生 final/content；thinking 永不作为答案来源。先严格检查完整 JSON，再验证原 schema、原严格解析及来源证据；schema有效只证明结构与引用ID机械合法，不保证所引来源蕴含模型理由。

原模型／固定revision、A/B thinking、BF16、SDPA、greedy、原生模板、消息、评分规则及 q/m/U 均未变化。实际输入逐条与原清单预检 tokens 相等，完整合法来源未截断，仍保留至少32,768输出空间。未安装依赖；使用环境已有 jsonschema 4.26.0。历史语义修订仍为1，本轮增量0。

76项离线测试通过（23新增＋53既有），覆盖完整裸JSON、合法围栏、额外文本、多块、截断、非法JSON、重复键、schema／证据失败、非自然结束、thinking隔离、四配置同规则、重复执行和跨版本计数／硬停。初次测试发现 CRLF 关闭换行解析多保留回车，已在派生和真实推理前修正，失败与成功日志均保存。实际两份旧输出也重复执行过离线重解析，派生文件哈希不变、调用数不变。见 [接口修订](OUTPUT_INTERFACE_AMENDMENT_ZH.md)、`tests_v1_corrected.log`、`offline_idempotence_check.json`。

## 语义与关键题复核

两份 dev02B 派生结果均为 q=4、m=0、U=1，这是原模型判断经新接口读出，不是人工替模型修分。B把含个人动机的R003整句标成 non_factual，仍作为混合断言分类／覆盖理由问题保留；C:T006直接支持所述动机，未证明本处造成错误主体、事实或严重度结论，因此没有据此认定实质错误硬停，也没有认定问题已解决。A对一般“勇气”支持语的supported分类同样保留解释局限。五个回复单元逐项对照、原判断和来源引文见两份 `derived/*.review.json`；不把它们当新增独立人评。

{chr(10).join(notes) or '本轮没有新增完整输出可做语义复核。'}

15题依据是 C:T005明确旧大学朋友、C:T009朋友的鼓励、C:T013聊天改变论文视角；新AI不能把朋友变成历史支持者，更不能把这份帮助归自己。37A/B只有“I’m / I am”差别、合法来源相同；C:T014计划稍后思考、C:T016感谢倾听。是否覆盖、实际 q/m/U 与差异理由按上表和逐条 review 报告，未派发项不能推定一致。第35题未加测，仍留原开发清单。

新输出每次保存完整记录后才进行来源复核；来源可证明的实质错误、关键unknown或无依据等义差异不会被格式适配解除。阶段阻塞记录：`{stage['blocked']}`。原 STOP 一直保留；关联的 `continuation_authorization.json` 只解除两次外层格式失败导致的阻塞，不抹去其历史。新 STOP（如有）独立保存。

## 耗时、显存与GPU诊断

{chr(10).join(timing)}

本轮生成路径墙钟合计 **{r['new_GPU_generation_path_seconds']:.6f} 秒**；共享加载记录 `{r['shared_loads']}`，共享驻留 **{r['new_shared_GPU_residence_seconds']:.6f} 秒**。驻留含加载、进程检查及来源复核等待，不按A/B重复计一次加载；生成路径含前处理／同步等开销，不是CUDA内核活跃秒数。整个本轮runner墙钟 {receipt['wall_seconds']:.6f} 秒，退出码 {receipt['exit_code']}。前一轮两次dev02B的235.093427秒生成路径和251.159757秒驻留是历史成本，不重复计成本轮实耗。离线重解析没有模型GPU请求。

复用既有权重、环境、指定 A6000 UUID `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`，没有下载／换卡／量化。加载前只用一次最长300秒只读窗口，本次等待 {idle.get('elapsed_seconds',0):.6f} 秒；显存>=45,000 MiB且0%利用率条件保持。每条查询的原始stdout/stderr/退出码、时间和进程可见性在阶段 `gpu_check_*.json`。

{chr(10).join(gpu)}

NVIDIA成功空列表仅表示此次未列出进程，不能证明不存在隐藏或瞬时任务；辅助/proc命名空间不可读的限制单列，不冒充查询失败。加载后检查只允许本轮模型PID，原驻留进程守卫不把自身显存／负载当加载前空闲失败。未操作同学或其他用户进程，没有以少量非零利用率自行放宽条件。

共享付费账本哈希 `{r['paid_ledger_sha256']}` 不变，仍1.50724291美元、边界后新增0、未结责任0。本轮 API费用0、下载0；没有本机租价／电价和能耗测量，不虚构GPU货币成本。新 started（包括失败）全部入账；原66、前轮2、本轮{r['new_live']['started']}严格相加，未派发不计。初始保存的 {r['original_files_unchanged']} 个文件哈希不变；原失败结果、null、STOP、原协议和修订均保留。

## 当前边界

输出接口的工程结果与裁判语义结果分别报告；即便本轮剩余项全部机械有效，也不足以宣布奖励合格、准确率获胜或四配置冠军。DeepSeek、剩余开发、恢复批次、最终冻结、24对封存、12次独立复评、自然PPO与未来Step2均未启动。没有提交、推送或上传私人材料。当前停止等待研究者审阅；若继续需要修改提示、评分标准或内部输出，应先另行决定，不能在本次格式批准下扩大。
'''
with (HERE/'RESULTS_ZH.md').open('x') as f:f.write(report)
print('Detailed local report written.')

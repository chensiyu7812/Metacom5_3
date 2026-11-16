from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import selection as s
from resume_engineering import now
r=s.read(HERE/'results_private.json');p=s.read(HERE/'protocol.json');a=s.read(HERE/'final_integrity_audit.json')
path=s.REPO/'project/docs/PM_RL1_CURRENT_STATUS.md';old=s.read(HERE/'baseline.json')['current_status_before']
assert path.read_text()==old
with (HERE/'PM_RL1_CURRENT_STATUS_before_interface_v1.md').open('x') as f:f.write(old)
hard=sum(bool(x['source_review']) and any(x['source_review'][k] for k in ('material_source_proven_error','critical_unknown','unexplained_equivalence_difference')) for x in r['rows'])
text=f'''# PM-RL1 当前状态

更新：{now()}（Asia/Tokyo）。**本轮输出外层适配、两份旧输出离线复核及原清单接续已结束，停止等待研究者审阅。新增真实尝试 {r['new_live']['started']} 次，累计 {r['history']['cumulative_calls']}/140；未开启下一阶段。** 本文件仅为可分享摘要，来源、标注、逐题结果和完整输出留在本地忽略目录。

长期目标仍是分别用 RL 学习资源获取与资源使用／回复策略，再研究两层协同。当前第一阶段只在有界监督适配后冻结执行器，训练 GET／STOP；本轮不设计或启用 Step 2，不联合训练。SFT 完成不证明资源使用正确，初版不保证 PPO 胜出。见[路线说明](PM_RL1_TWO_STAGE_ROUTE_20261015_ZH.md)。

真实仓库 `/opt/tokkio-data0/tokkio_projects/Metacom5_3`（`/home/tokkio/Metacom5_3` 为链接），分支 `{a['branch']}`，HEAD `{a['head']}` 未变化；未提交、推送或清理既存工作文件。原[控制合同](pm_rl1_completion_20260930_v2/execution_contract.json)、历史修订、旧失败与 STOP 均保留。

原四配置协议 `{p['original_plan_identity']}`；本次独立输出接口协议 `{p['identity']}`，接口 `{p['interface']['version']}`，身份 `{p['interface']['identity']}`。A/B/C/D的新完整配置均绑定相同接口版本，实际只运行获准A/B；原配置身份不冒用，原清单槽位跨版本去重。原严格解析器、schema、提示、q/m/U、奖励与资格门槛不改；语义修订本轮增量0、历史总数仍1。

适配仅接受完整裸 JSON 对象，或独占整个 final 的单层 json／无标签围栏；只移除外层包装，内部文本不改，再执行原完整校验。不从 thinking 提取答案，不搜索解释文字中的JSON，不修复内容或截断。76项离线测试通过，实际离线重复执行也验证派生记录不覆盖、计数不变。旧材料 {a['old_files_hash_verified']} 个文件哈希核对通过。

三类结果分开记账：原严格接口的2次请求仍是解析失败，正式q/m/U全部null；同两份完整final经新接口离线重解析均得到开发派生分数，调用和独立样本增量均0；本轮原剩余6槽中实际开始{r['new_live']['started']}，机械有效{r['new_live']['mechanically_valid']}，技术失败{r['new_live']['technical_failed']}，未派发{r['new_live']['not_dispatched']}。不把派生成功混成旧首试成功或新独立样本。

本轮来源复核记录的硬停止数为{hard}。已覆盖的主体归属和等义对照按原证据逐项复核；混合个人断言分类及相邻质量锚点的理由问题仍需保留，机械通过与本轮个案表现不构成奖励资格。详细数值、引用、差异和局限留在本地结果报告。未加测其它题目，不重做人评，不将派生记录计为独立人评。

复用固定 `google/gemma-4-12B-it` revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`、原环境和指定A6000；A thinking=False、B=True，BF16、SDPA、greedy及完整输入不变，未下载／安装／换卡。加载前一次最多5分钟只读等待，原≥45,000 MiB及0%条件未放宽；查询原文、进程可见性限制与拒绝原因完整保存，未操作同学或其他用户进程。模型进程已退出。

本轮生成路径墙钟 {r['new_GPU_generation_path_seconds']:.3f} 秒，共享GPU驻留 {r['new_shared_GPU_residence_seconds']:.3f} 秒（含加载、检查及来源复核等待），不按A/B重复计算。新增API费用0、下载0；共享付费账本仍1.50724291美元、未结责任0。旧66＋前轮2＋本轮{r['new_live']['started']}＝{r['history']['cumulative_calls']}；原8次额度和累计74上限未提高。未给本机GPU时间虚构货币成本。

DeepSeek、其余开发、恢复批次、最终冻结、24对封存、12次独立复评、自然PPO及未来Step2均未执行。不作四配置排名，不宣称裁判准确或奖励合格。后续开发或其它阶段仍待研究者审阅与另行授权；本轮没有修改提示、评分标准或内部输出来追求通过。

本地详细结果：`project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/outer_format_v1_20261015/RESULTS_ZH.md`。同目录 `results_private.json`、`eight_slots_private.csv`、`OUTPUT_INTERFACE_AMENDMENT_ZH.md`、`continuation_authorization.json`、`final_integrity_audit.json` 分别保存三类结果、八槽表、版本变更、条件接续和最终核验。原状态及原报告保留；只准备文档，不推送。
'''
path.write_text(text)
print('Current shareable status updated; previous version preserved.')

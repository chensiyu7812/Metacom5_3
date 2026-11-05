2026-11-05 N23实际路径与旧偏好接续完成：原动态词语重合检索的0～4MS共5个停止位置已齐，复用2条、新增3条自然回复，2MS和4MS均无追问但没有对应完整旧人评，不移植G01标签。发现该情境完整4段MS的旧BGE排名原把目标排第1；在单独标识、全MS分数完整才允许的静态对照中实际一次GET_MS，输入/回复/当前及所取历史与G01精确对应，可复用原“略好”，无需重评。24个train前缀共248个MS位置，仅85个保留旧分数、6个前缀覆盖完整，未静默丢弃新增资源或替换主检索。已完成该旧人评对的2预热＋4配对生成计时，10次原文/token序列全复现；ON减OFF的G首token中位+0.110秒、完整生成−0.085秒，仅G组件，非Tokkio有效语音/3秒判定。累计本轮新G13次/实际加载2次；首次2%利用率加载前拒绝保留，局部≤5%容差接续仍排除其他进程和查询异常。15项测试及独立来源/token/偏好/计时检查通过；45条参照、1018个P2文件、453历史文件、账本保持。新人评/API费用/训练均0，原24次成本负对照PPO保持；局部帮助方向已接上实际短路径，综合效用反馈与完整等待尚未齐备。下一步补全统一语义索引和检索/决策延迟，优先复用旧判断。详见[实际路径、小收益复用与计时](reviews/20261105/pm_rl1_slight_positive_path/RESULTS_ZH.md)。下方为历史时点。

2026-11-05 V01已收到：研究者认为A/B相当，沟通导师和先应对身体不适都是可接受策略。已精确绑定候选G实际4MS路径与OFF、完整当前及4段历史；原44条参照保持，增量为45条（34配对/8单回复q/m/3补充）。N06保留“资源可取得、采用并改变建议”的机制观察，但没有帮助性偏好，不作为正收益样本，也不触发此前以正收益为前提的计时/训练；相当不写成精确零质量或PPO奖励。G01/G07的略好仍保留；本轮进一步重放N23/N05实际4/10MS路径并核对44个同G缓存，原人评都是单独目标输入，实际多资源路径均无精确缓存，偏好不可直接迁移。下一步优先补较短N23路径输出并检查旧参照可复用性，不继续围绕V01寻找必须胜出的说法。独立来源/呈现/路径核验通过；本轮新问题、模型/API、费用及训练均0，既有24次成本负对照PPO保持。详见[V01收口及旧小收益接续](reviews/20261105/pm_rl1_incremental_help_human_review/RESULTS_ZH.md)。下方V01待答为历史状态。

2026-11-05 信息增量与反馈复查完成：44条人评参照保持，复用8组旧裁判对照；新裁判实测4次（1自然、3超时），G01完整结果与研究者偏好反向且夸大差别，完成当前双顺序尝试后主动提前停止，其余12次未执行、不计准确率，未赋奖励。24个train情境的完整MS路径及9条候选来源核查完成，187条已有程序来源/呈现核验通过；9条目标中动态加入已读全文后6条位置不变、3条更晚，没有据此替换检索。N06/N13固定2情境×4条件×2G：复用5条原G、新增3原G＋8候选G，16条件回复全部自然结束。N06候选G在目标单独呈现和真实4MS路径均采用保留开心活动的约束、询问灵活研究安排；原G没有这一调整。N13两G仍未体现降低反复解释负担的目标机制。实际帮助未判，唯一新V01比较已发送待回收，旧8题不重发。25项测试与独立来源/token/路径/人评绑定核验通过；1018原P2文件、453历史文件和账本保持。API费用、新训练均0，既有24次成本负对照PPO保持；候选G未推广，Tokkio配对实际等待尚待。详见[本轮结果与后续判定](reviews/20261105/pm_rl1_feedback_and_opportunity/RESULTS_ZH.md)、[核验](reviews/20261105/pm_rl1_feedback_and_opportunity/CHECKS.json)。下方为历史时点。

2026-11-05 替代G盲评已全部收到：8个原始答案逐项绑定实际HTML呈现、完整证据和回复。6个新G C/OFF比较为读资源2略好、4相当；原计划第7对N18 C格式失败继续单列，非零收益。2个新旧G OFF比较为新G 1略好、1相当（G06的B是新G）。G01偏好主要涉及避免过早推进，G07涉及自然衔接；保留实际小收益，不擅自归因为历史信息。N21已采用互留休息仍相当，因此其增益不足不能再只解释为旧G未采用历史。原36条参照保持并追加8条，共44条；85/95不转q/m，相当不填精确零奖励。当前是1位研究者、7个情境的开发判断，不能证明新G普遍更强或资源无价值。独立解盲/来源核验通过；新增API/G/训练/问卷均0，既有24次成本负对照PPO保持。接下来优先复用参照检查反馈、核验合法历史是否改变可接受支持及GET可达性，不继续以引用率为目标扩大SFT。详见[完整解盲与研究判断](reviews/20261105/pm_rl1_alternate_executor_human_review/RESULTS_ZH.md)。下方人评待答为历史状态。

2026-11-04 相同输入跨G诊断完成：改用已有本地Gemma4-12B-it，36去重输入/41卡/8个已暴露train情境全部自然结束，1条格式泄漏单列；未改原提示、未替换正式G、未赋奖励。新G在N21能采用互留休息，N18不再因无关失恋资源转移主题，但N21无资源回复已建议同类行动，帮助增益未定；N19/N23仍未明确采用目标历史，不能推出资源无价值。原计划7对C/A中6对进入新盲评、1对技术失败保留，加2对预定OFF比较，共8对新回复，非旧8对重发；新人评待答。额外等待超过3秒记为研究者暂定约束，不定λ；本轮G组件耗时不冒充Tokkio有效语音延迟。43项相关测试、完整输入/token/来源独立核验及表单保存导出检查通过；旧1018个P2文件、453历史文件和账本保持。新增API费用/PM及G训练更新均0，既有24次成本负对照PPO保留。详见[对照结果与Claude分析](reviews/20261104/pm_rl1_alternate_executor_probe/RESULTS_ZH.md)、[复核入口](reviews/20261104/pm_rl1_alternate_executor_probe/RUNBOOK_ZH.md)。下方继续小样本SFT的安排已由本轮诊断优先顺序替代。

# PM-RL1：首批工程结果

2026-09-28。研究方向及差异见 [实施范围](PM_RL1_SCOPED_IMPLEMENTATION_20260928_ZH.md)，价格、假设和预算见 [费用重估](PM_RL1_COST_REASSESSMENT_20260928_ZH.md)。

## 已落地

- `src/metacom_pm/rl1/schema.py`：私有 prefix/库存与公共 observation 分开；actor/critic 不接收 owner、来源 ID、未 GET 正文、未来回复或评分。
- `data.py`：真实 seeker 后、supporter 前切点，沿用方案的 owner hash split 与上一轮审计的确定性 cut hash；先 as-of 过滤再构造 MP/MS/ME。
- `render.py`：RS→MP→MS→ME 规范渲染，所有已取证据完整保留；RS 允许合理不采用；真实 tokenizer 计算完整资源块和 chat context。
- `env.py`：固定 GET/STOP、最多四次 GET、非法动作报错、状态校验、重放、初始共同可达计划 mask、精确 token 差分成本；STOP 等待真实生成和评分。
- `generation.py`：新本地自然结束接口，原生上下文剩余量、真实 EOS/EOT 分类、技术异常单列；不依赖旧 60/256-cap HTTP 服务。
- `cache.py`：SQLite 事务抢占单次生成请求，完成缓存按完整身份复用；RUNNING/FAILED 不自动再调用。

## 已执行的验证

36 项新环境及相关旧模块测试通过；包含 341 条 GET 序列→70 个规范终值、观测泄漏、首条超预算不能跳到下一条、非单调 token 成本、wrong-owner/future、源 session 从 0 开始编号、无评分不填零、EOS 恰在边界结束、恢复与重复 claim。测试中的模拟 score 仅是程序夹具，没有进入真实数据或训练。

真实来源 census 有 383 个合法 memory sessions，预选 96 train / 24 dev / 48 test。它仍标为 DEVELOPMENT_CENSUS_NOT_FROZEN：跨 owner 同源 `esc1198` 出现在 p13/train 与 p18/dev，历史暴露与事实家族及其后继材料尚需整理，不能把这 48 个 test 前缀直接宣称全新未暴露测试集。

按训练前缀原始文本 tokens 的最短、中位、最长，预先选三条（4 / 218 / 720 tokens）；选样先于新回复，不依据收益。重新编码当前完整前缀，从 13,172 个去重 RS treatments 及三条前缀共 230 个不同合法记忆候选检索；RS 按完整 lineage 排除了已识别 EvoEmo seed。既有 BGE 权重 hash 和运行环境在加载时核验。没有复用旧 QA/Summary 的 query ranking。

| 真实前缀 | 1,024 资源预算可达计划 | 2,048 | 4,096 |
|---|---:|---:|---:|
| 最短 | 55 | 66 | 69 |
| 中位 | 55 | 68 | 70 |
| 最长 | 55 | 69 | 70 |

这是三条开发 probe 的完整渲染结果，不代表全部 168 前缀的最终容量或最优预算。三条实际 GET/STOP 轨迹均通过状态保存/重放检查。

每条 train prefix 做 OFF 与固定机械 GET_MS→GET_MP 路径各一次，共六次 Llama 本地生成；该路径是服务测试，不是训练出的策略。A4500 上六条均真实以 EOT `128009` 结束，输出 34 / 41 / 39 / 52 / 50 / 43 tokens，合计 259 tokens。实际生成段共 11.216 秒，峰值 allocated 15.321 GiB；模型校验/加载另记 108.476 秒。六条都为 `pending_score`，没有 J 调用、reward、训练更新或 test 生成。不能据六次短回复外推整项研究的 J/LoRA 工期，也没有据此证明新方案质量改善。

成功的 BGE/容量构建运行历时 187.723 秒。此前一轮在新环境的 session 序号检查处失败：旧数据从 0 编号，新检查误按 1 起始，已修复并新增回归用例；首轮失败已消耗 BGE 计算，其时长没有完整持久记录。因此上述成功轮时长不能作为本次全部 GPU 工作量。新 RS 向量缓存已绑定文本与向量文件 hash，后续同身份可直接复用。

工作开始前的 70 个已有 dirty/untracked 文件逐项 hash 保持不变；旧 1,924 条生成、旧 JSON authority、旧服务、原账本均未改写。新增 API 支出 0。

## 产物与复算

产物目录：`project/outputs/pm_rl1/engineering_20260928_v1/`。

- `census.json`、`prefixes_private.json`：初步来源 census 与候选 prefix。
- `retrieval_manifest.json`、`episode_specs_private.json`：真实检索身份与私有库存。
- `capacity_probe.json`、`mechanical_traces.json`：预算域、公开 observation、GET/STOP 重放。
- `generation_smoke_pointer.json` 指向本次真实 G 的 runtime、request、raw response、episode 和 SQLite cache。
- `cost_reassessment.json`：独立复核/QA/旧收口的分项报价与原预算余额。
- `test_results.xml`、`validation.json`：自动测试和旧文件保护检查。

环境为已有 `paper1-py311`，没有安装或更新软件。三个脚本依次为 `01_prepare_engineering_probe.py`、`02_reprice_plan.py`、`03_smoke_natural_generation.py`。01/03 绑定单张卡、只读本地模型，示例：

```bash
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=GPU-bb27e322-0c2a-fe7f-35a8-3ec5944fd243 HF_HOME=/opt/tokkio-data0/tokkio_models/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/01_prepare_engineering_probe.py
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/02_reprice_plan.py
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=GPU-bb27e322-0c2a-fe7f-35a8-3ec5944fd243 HF_HOME=/opt/tokkio-data0/tokkio_models/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/03_smoke_natural_generation.py
```

## 后续顺序与当前状态

R00 已有接手审计；R01 schema/cache 已实施，共同付费预算 broker 未接线；R02 census/as-of/小型容量已运行，完整分组与预算尚未冻结；R03 环境及机械测试已实现，尚非完整正式数据验收；R04 真实 G 已接通，J 测量与服务恢复未完成。

下一步依次完成：来源/暴露分组与全量容量 census；固定 X_b/X_g 指导、完整 J 证据及解析合同；12 个 train/dev 前缀的小型测量检查（48＋12 scores，独立复核分开）；再生成执行器弱监督数据并训练 LoRA；最后进行共同计划监督/E0 与受限 PPO。没有训练 PM 或 LoRA 的结果，不提前写作完成。

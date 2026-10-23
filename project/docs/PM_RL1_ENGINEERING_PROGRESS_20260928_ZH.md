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

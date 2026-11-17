# A1：过去研究资产复用清单实测结果

本轮完成资产复用审计代码、配置、逐项机器台账、来源/跨度/family 核验和模型文件 SHA 复测。**这是冻结前的资产审计，尚未建立 V3 source registry / bank-v0，也没有运行读取、生成或训练。** C0 0.2.0 待 B 复审和集成；按本轮指示不提前施工 A1b。

入口：`project/scripts/rl1v3/a1_audit_asset_reuse.py`；实现：`rl1v3/sources/asset_reuse.py`；配置：`project/configs/rl1v3/asset_reuse_v1.json`。

机器产物为 `ASSET_REUSE_MANIFEST.json`（809 个实际文件，共 64,160,011,522 字节）和 `ASSET_ITEMS.jsonl`（27,420 个条目，包含多种粒度，**不能相加宣称独立样本数**）。每条有路径、旧 ID、内容 SHA、可用的 owner/family/时间、分类、原因、目标入口；文件条目还包含原版本和结构计数。缺少 ready_at、许可或语义审核时明确记录缺口。41 个模型权重/tokenizer/配置文件本轮实际读取并计算 SHA，与既有记录全部一致；未把权重装入模型。55 条旧人评登记重新计数，保留 historical_only，不能成为新独立测试证据。

## 四资源及原始来源

| 资产 | 实际数量 | direct_reuse | adapt | repair | quarantine |
|---|---:|---:|---:|---:|---:|
| MS 原始完整会话 | 401（18 owners） | 401 原文来源 | 0 | 0 | 0 |
| 历史编译 MP | 713 | 0 | 711 | 2 | 0 |
| 历史编译 ME | 1,523 | 0 | 1,522 | 1 | 0 |
| RS 旧策略卡 | 11,590 | 0 | 11,590 | 0 | 0 |
| RS canonical treatments | 13,172 | 0 | 13,172 | 0 | 0 |
| 11/15 完整案例候选 | 12 | 0 | 0 | 6 | 6 |
| 11/15 方法草稿 | 3 | 0 | 0 | 0 | 3 |

这里 direct_reuse 表示原始来源字节可以复用，不表示已经生成合法的 V3 阅读资源。adapt 是具备迁移基础，仍需新 schema、全部依赖闭包、ready_at、许可/风险和逐前缀合法性过滤；任何旧归纳都不自动标记事实已验证。RS 策略/treatment 是同源的不同派生层，不得相加当成 24,762 个独立案例。

- 旧候选池实际是 **388 MP / 1,523 ME / 401 MS**，与编译层的 713 MP 不同。325 个 MP 没进入该旧池，不得因此丢弃历史版本；逐条 `in_old_eligible_pool` 已登记。
- 2,236 条编译单元的原文引文、字符偏移、角色、原始 turn idx、owner/session/rank/报告时间均实测通过。原始 idx 与零基 ordinal 显式映射，不把 `idx=1` 静默当成 ordinal=1。精确引文不等于语义正确。
- 已知修复 ID：MP `mvu_2a73b2853cdd499d576e2ab5`（挂电话行为不能归纳成稳定回避偏好）、MP `mvu_785a6f6f9e719c52ef13fc57`（参加写作班及主观帮助不是稳定画像）、ME `mvu_c8da36ab41b1d4da5464dd8d`（主观结果不能丢失/升级为因果）。已有修复 sidecar 原样保留，尚未导入新 bank。
- 实际 ESConv 原始数据为 1,300 会话，split 为 934 train / 186 validation / 180 test。按 family 先排除 84 个与 EvoEmo 重叠的来源（其中 train 59、validation 14、test 11），再排除其余 341 个非 train，余 **875 个候选来源**。机器计数见 SOURCE_GATE_COUNTS.json。旧 11,590 策略和 13,172 treatments 的所有来源均通过 train/family 检查，拒绝数均为 0；这只证明谱系门，不证明方法正确性。
- 从 EvoEmo 会话 ID 实际推导的 84 个 ESConv family 与 split manifest 的排除集合完全一致；`esconv:esconv_1198` 确实由 p13/p18 共享。family 别名 `esc1198`、`esconv_1198`、`esconv_dialogue:esconv_1198` 规范化为同一身份；多祖先任一重叠即拒绝。
- `evo_emo.json` 的 basic_info 18、event_experience 446、social_relationship 150、summaries 125、questions 355 组、subsequent_topics 34，均作为特权/全轨迹/评测字段隔离，不拿来补 runtime 事实。**summaries 在这里是评测问题资产，不是已完成会话的 MS-SUM。** 本次没有找到可直接冒充 V3 SUM 的产物；A2 仍须建立逐命题来源与父 RAW 回查。
- FailedESConv 在本次盘点的 `project/data/external` 下实存匹配文件为 0；这是明确搜索范围的结果，不宣称全机器/互联网上不存在。未下载新数据，不能把文献中的数量写成本地已可用资产。

## 其他复用资产及边界

- 时间证据 ledger、旧组织/渲染/反馈/生成代码、BGE dense encoder、既有索引/census、回归测试逐文件登记。既有未验证关系只能保留索引来源，不能传播新事实。旧 `organized_encoding` 属于可见状态编码，不能叫资源检索。
- BGE revision `9a0624b896d81da7492a910ffa53731274b6cf3d`；原 dense 接口是 CLS、1024 维、L2、8192 token 上限。当前只确认文件身份与接口；没有本轮 Dense/BM25/Hybrid 召回结果，A5 仍须公平比较。
- Gemma、Qwen、Llama、历史 P2 adapter 和各自 tokenizer/config 保留实际文件哈希。A0 的 100 条真实 OFF 请求/原生 tokenizer 检查保持可复用；没有新的 GPU 时延、峰值显存、生成吞吐或 QLoRA 结果。历史 adapter 不自动升级为 G1，也不自动冻结新 G0。
- 人评 55 条、旧 Judge、11/11 QA 输出及旧实验日志可作历史回放/工程开发依据；不自动迁移其标签、不产生新独立证据。本轮不把旧任务分数用作新的自然支持奖励。
- B0 的曝光登记及 folds 已从 `b664ea07b032740486741ce95ce5447a11f7aadf` 固定到 inputs，原文件字节 SHA 记录在 manifest。旧文件有曝光或无法确认独立性时，一律不标为 untouched。
- 许可按原来源保留；缺少可绑定的许可证证据/方法域适用性时记为待迁移条件，不自行宣称部署许可。退役合成 intake 只登记禁止路径，未打开其中的源文件。

## 测试、回放及未完成项

17 项 A1 定向测试通过，覆盖 family 别名/多祖先/非 train、空来源、跨 owner、报告时间、缺失/错位/重复跨度、角色错误、全部 2,236 单元和不可覆盖输出。C0 全量另有 2,018 passed，详见 C0_revision/full_cpu。

首轮测量保留于 initial_measurement；随后补齐文件结构计数、逻辑路径、历史人评数量及模型旧 SHA 比对，重新实际运行最终盘点；没有覆写历史结果。交互式查看旧修复 sidecar 时曾误按 dict 处理其 list 根节点，出现 AttributeError；正式脚本按 JSON 实际结构读取，不把该探索错误伪装成成功运行。两次正式盘点退出码均为 0；最终旧 SHA 不匹配 0，缺失已登记输入 0。

重建命令（仅 CPU 读取文件，约 64 GB SHA 扫描，不加载模型）：

```bash
PYTHONPATH=project/src python project/scripts/rl1v3/a1_audit_asset_reuse.py \
 --history-root /opt/tokkio-data0/tokkio_projects/Metacom5_3 \
 --out /tmp/a1-reuse-replay \
 --extra-file project/outputs/pm_rl1/v3/A1_reuse/inputs/exposure_registry.jsonl \
 --extra-file project/outputs/pm_rl1/v3/A1_reuse/inputs/folds.json
```

B 当前可调用 C0 0.2.0 的前缀、读取结果、检查表、终点/执行轨迹契约和验证函数；资产侧可调用 `verify_unit` / `esconv_family` / `rs_rejection` 核验。**retrieve.read / bank/index manifest 尚未交付**，bank-v0 各头写入数均为 0，读取成功率为 null（未运行），没有伪造空 bank 或超预算结果。

下一项是 B 复审/集成冻结后的来源 registry 与 A1b 迁移：先复用已验证原始跨度和 RAW，再处理 3 条已知语义失真，保留其旧 ID 映射；RS 从 875 个合法 train 来源绑定上下文、许可及风险。A1b 真正完成后才交付读取成功率、四头数量和回放。GPU 推理/训练/付费仍需研究者另行明确授权；CPU 审计不新增授权请求。

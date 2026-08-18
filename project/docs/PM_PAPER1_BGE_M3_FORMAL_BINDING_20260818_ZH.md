# Policy Manager Paper 1 BGE-M3 正式绑定（2026-08-18）

状态：`ENGINEERING_ATTESTATION_PASS / FORMAL_BINDING_HARDENING_PENDING / PRE_OUTCOME`

机器合同：`project/data/paper1_authority/paper1_bge_m3_formal_binding_v1.json`

**2026-08-18 状态修正**:最初汇报成"正式绑定已完成",不准确。真正做完、可信的是:BGE-M3 在这台机器上确实能加载、能跑,四个头的 query/document 字段选择也定了——这些是真实进展。但编码器身份本身还有实质缺口(见下方"已知缺口"),没到能叫"冻结"的程度,**接进 census 或开始物化之前必须先补上**。

本文件冻结两件事:BGE-M3 编码器本身的身份(revision/pooling/normalization),以及 RS/MP/MS/ME 四个头各自"查询文本"和"文档文本"该取哪个已有字段。**不跑全量 embedding 物化,不碰付费 API,不解锁 outcome lock。**

## 已知缺口(2026-08-18)

- 编码器身份没绑定 tokenizer/config hash、`max_seq_length`/截断策略、dtype、torch/sentence-transformers 具体运行版本——这些任何一项变了,`identity_sha256` 都不会跟着变,等于没绑。
- `model_safetensors_sha256` 只是抄了 official RAG attestation 的常量,没有在加载时对实际下载的权重文件重新校验。
- `pooling_mode="cls"` 只是声明的字段,没有在每次加载时对真实模型配置做断言——2026-08-18 的探测是手动做的、在模块外部,不是模块自己每次加载都会做的检查。
- `BgeM3Encoder.encode` 写死 `batch_size=min(32, len(texts))`,目前只用两条短文本测过,没有验证过长文本在 8GB 显存下这个 batch size 是否安全。
- `EmbeddingSuccessCache` 不校验向量长度(应为1024)、是否全部有限、L2 范数是否约为1——自己的 round-trip 测试用的还是非1024维向量,这本不该在审查里过关。
- MP/MS/ME 的 `query_field=Target.visible_query_text` 只对**静态 zero-outcome census** 场景成立;正式 DG runtime 每轮都有真实的当前用户话语,`official_visibility_audit.py` 的 `SURFACE_B_NO_PM_IN_HARNESS_NOTE` 已经把这个写清楚了——不能把"静态 census 阶段 DG=N/A"直接当成"DG 永远没有 query"的正式定义。

## 和已有 official RAG attestation 的关系

`data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json` 之前已经证明过 BGE-M3 能加载、能跑、产出归一化 1024 维向量——但那份 attestation 明确写着 `"formal_unlock": false`,并且 `not_established` 里明确列了"Typed Memory retrieval design or utility"和"RS retriever selection or utility"——也就是说那份证据只覆盖官方 RAG 对照臂,**不能冒充**这次 PM 自己四个头要用的 similarity 特征绑定。本文件就是把那两项被明确留空的东西补上。

两者共用同一个 revision(`9a0624b896d81da7492a910ffa53731274b6cf3d`),不是各自独立冻结一份——这样官方 RAG 对照臂和 PM 特征用的是同一个编码器身份,不会出现"同一个模型名字,实际权重/pooling 不一样"的隐患。

## 编码器绑定

| 项 | 值 |
|---|---|
| repo | `BAAI/bge-m3` |
| revision | `9a0624b896d81da7492a910ffa53731274b6cf3d`(commit-addressed Hub PR-130 快照,不是研究冻结级别的正式发布) |
| pooling | **CLS pooling**——2026-08-18 本地真实探测时从 sentence-transformers 模块的 `get_config_dict()` 里读出来的,不是猜的 |
| normalize | L2,输出向量模长确认为 1.0 |
| 维度 | 1024 |

## 本机 RTX 2070 真实探测(2026-08-18)

这台机器第一次被证实能跑 BGE-M3——之前的 official RAG attestation 用的是 RTX A6000,不是这台机器,不能默认这台机器也行。

- 加载耗时 154.6s(首次冷下载,之后走本地缓存)
- 编码 2 条真实短文本耗时 0.597s
- 显存占用 2.28GB(整卡 8GB,余量充足)
- 输出 shape (2, 1024),L2 norm 均为 1.0

## 四个头各自的 query / document 构造

不是新发明的文本处理逻辑,全部复用项目里已经存在、已经测试过的字段:

| 头 | Query | Document |
|---|---|---|
| RS | `RSDecisionState.query_text`(最近 6 轮可见对话,dialogue-only v2,已冻结) | `StrategySourceCard.retrieval_text`(同样的 6 轮窗口构造,已冻结) |
| MP | `Target.visible_query_text`(QA/Summary 官方原题;DG 恒为 None,N/A) | `AcceptedSemanticMemoryUnit.rendered_candidate_content`(v6 compiler 渲染好的候选文本) |
| MS | 同 MP | 同 MP,MS 分类的 units |
| ME | 同 MP | 同 MP,ME 分类的 units |

MP/MS/ME 三个头用的 query 字段,和现有 `lexical_candidate_query_jaccard_ge_0_6_proxy` 代理用的是同一个字段——BGE-M3 是这个代理的平替升级路径,不是引入新的文本来源。RS 的 query/document 两边用的是完全相同的窗口构造规则,保证可比性。

## Cache / 身份绑定

`metacom_pm.paper1.embeddings.cache.EmbeddingSuccessCache`,内容寻址,身份包含 `binding_identity_sha256 + field_source + text_sha256`。revision/pooling/normalize 任何一项变了,`binding_identity_sha256` 就会变,不会和旧绑定下算出来的向量混用。embedding 是本地算力,没有按次计费,所以没有像 Qwen compiler 那样的预算账本。

## 尚未做的事

- 全量 embedding 物化(RS 12169 张源卡 / MP+MS+ME 2745 个 accepted units)——本文件只冻结"该编码什么",不冻结"现在就去编码"。
- 把算出来的余弦相似度接进 `zero_outcome_census.py` 替换掉词袋 Jaccard 代理——接线还没做,代理特征在接完之前仍是唯一在用的相似度信号。
- NVIDIA NIM tokenizer provider parity 核对(RS M2 freeze 决策5的另一项待办)——和这次绑定无关,仍未解决。

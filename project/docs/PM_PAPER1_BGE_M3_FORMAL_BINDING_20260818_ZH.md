# Policy Manager Paper 1 BGE-M3 正式绑定（2026-08-18）

状态：`FORMAL_BINDING_HARDENED_V2 / MATERIALIZATION_NOT_STARTED / PRE_OUTCOME`

机器合同：`project/data/paper1_authority/paper1_bge_m3_formal_binding_v1.json`

**2026-08-18 状态修正**:最初汇报成"正式绑定已完成",不准确,当时有 6 个真实缺口(见下)。**2026-08-19 全部 5 个编码器硬化缺口已修复并实测**,第 6 个(DG 动态 query)不是编码器硬化范围内的事,保持标注为"仍未解决的范围边界",不算进硬化完成度。**同一天的第二轮复查又发现前 5 项里有两处只写了注释要求调用者自觉遵守,代码本身并未强制**——runtime identity 没有真正进 cache key、8192 token 上限只在加载模型时断言过一次、从未在编码真实文本时检查——这两处已经补上代码层面的强制,见下方"2026-08-19 第二轮"。

本文件冻结两件事:BGE-M3 编码器本身的身份(revision/pooling/normalization/max_seq_length/truncation/dtype),以及 RS/MP/MS/ME 四个头各自"查询文本"和"文档文本"该取哪个已有字段。**仍然没有跑全量 embedding 物化,不碰付费 API,不解锁 outcome lock。**

## 2026-08-18 发现、2026-08-19 修复的 6 个缺口

1. **编码器身份不完整**——已修复:`max_seq_length`(8192)、`truncation_side`(right)、`dtype`(torch.float32)现在是冻结字段,真实值从本机加载的模型读出来的,不是猜的;`identity_sha256` 覆盖了这几项。torch/sentence-transformers 版本故意不做成冻结字段——升级不该靠人去改常量才能被发现,而是每次加载时实时读取,进独立的 `BgeM3RuntimeIdentity`。
2. **权重 hash 没有运行时校验**——已修复:`BgeM3Encoder._load_model` 每次加载都用 `huggingface_hub.scan_cache_dir` 找到本地真实缓存文件重新算 hash,和声明值不一致直接抛错。
3. **pooling 等字段没有加载时断言**——已修复:pooling_mode、max_seq_length、truncation_side、dtype 现在每次加载都对真实模型配置做断言,不一致直接抛错,不再是"探测过一次就当作永远成立"。
4. **batch_size 写死、没测过长文本**——已修复:按文本长度自适应(4/16/32 三档),CUDA OOM 会自动减半重试。真实测过一条 5440 字符的长文本(超过 4000 字符档位),本机 RTX 2070 编码成功。
5. **cache 不校验向量**——已修复:`EmbeddingSuccessCache` 现在校验维度(必须1024)、是否全部有限值、L2范数是否约等于1,写入和读取都会拦。专门补了"非1024维/NaN/Inf/未归一化"四种拒绝的回归测试。
6. **MP/MS/ME 的 query_field 只对静态 census 成立,不是永久 DG=N/A 规则**——**仍未解决**,不是这轮硬化的范围。正式 DG runtime 每轮都有真实的当前用户话语,`official_visibility_audit.py` 的 `SURFACE_B_NO_PM_IN_HARNESS_NOTE` 已经把这个写清楚了。

## 2026-08-19 第二轮:把"注释要求"改成"代码强制"

第二轮复查(另一个 codex)指出上面第 1、5 条其实还没真正闭环——只是把该记的信息算出来了,但没有强制接到实际会用到的地方。已修复:

7. **cache key 之前只绑定了 `binding_identity_sha256`,`runtime_identity_sha256` 只是模块文档里的一句"调用者以后记得合并进去",代码没有任何地方强制**——已修复:`EmbeddingCallIdentity` 现在把 `runtime_identity_sha256` 定义成必填字段,torch/sentence-transformers 版本变化会直接改变 cache key,不可能绕过。回归测试:`test_cache_key_changes_when_runtime_identity_changes`。
8. **`max_seq_length=8192` 只在模型加载时对模型自身配置断言过一次,从来没有对着真正要编码的候选/文档文本检查过**——如果某条文本的真实 token 数超过 8192,`sentence-transformers` 会按 `truncation_side="right"` 静默截断,不会报错。已修复:`BgeM3Encoder.encode` 现在会先用真实 tokenizer(不做截断)量出每条文本的真实 token 数,超过上限直接抛错拒绝编码,不再静默丢内容。回归测试(真实 GPU):`test_encode_fails_closed_on_text_that_would_be_silently_truncated`。

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

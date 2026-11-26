# 独立申请：DYNAMIC88 的 DR1–DR4

**状态：CPU 准入及最终冻结执行器复跑已通过；未获运行授权，未启动 GPU。** 起点 `f2d59f1c42de672c0785e034dbbd76e424f5529e`。本申请落实此前八题六臂提案，不使用原剩余 220 次，不增加研究任务或训练。

申请四个独立作业，每作业两个同来源、不同目标任务，完整保留六臂配对。每作业最多 **22 次实际 start、1 次加载、0 warmup、0 retry、1200 秒全局硬限**；四包合计最多 **88 次、4 次加载、4800 秒硬上界**。22 次包含 12 次终局 G、2 次 OneShot、最多 8 次逐轮 ToolAgent；控制调用和失败 start 计入预算。模型每次加载子限 600 秒、请求子限 300 秒均受剩余全局限约束。停止/失败不自动恢复或补齐。

模型保持本地 `gemma-4-12B-it-707f0a3`，revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`；唯一原指定 GPU 为 `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`。设备忙则守卫拒绝，不干预别的项目、不换设备。旧 G0e/E6/A0 身份直接复用，不重新签收。

## 固定身份

活动包：`/opt/tokkio-data0/tokkio_runs/pmrl1-j-dynamic-20261126/packages-v2`。

- `CATALOG.json` **文件 SHA256**：`b2d8e16eb33fcbf304b3b5b314cb8240bfcc085ea0847d5cb8fe88893e50ccac`
- 全局比较 scope **对象 SHA256**：`3a501ba86118c10828fb4ee45bad8de53cec35dab3ab8a9a43d965ebbff942de`
- 执行器文件清单 **对象 SHA256**：`6116fbc4056c1da2d90cf54d04213515bada29c35447d101d2afe53f5837540c`
- 共同控制协议 **对象 SHA256**：`fc233716b33d90f3a4a14848026ed38d74a74b9a09d433ddd8f3391bba4b7f02`
- 计时协议 **对象 SHA256**：`89633f55ffd6f1d0e0fec1183f8fdacfb45bbbe5cb7025351cc4b44ef5d10431`

|作业|计划对象 SHA256|动态请求范围文件 SHA256|
|---|---|---|
|DR1|`a2c20cf956fba952703101e386eedce4a7f7bf61ba8d44f1ac9c2423032b747c`|`2571e844d4b747326a76c9858ff56fac062fa1d9f796057c7aa7ba5f4467a213`|
|DR2|`bc801c28be6753d081f0946e483cd3acd34b872d3c96ba14b4da2df1fd6b1d3e`|`19e556906f4b97aa0832cf2a92424e5da23bf059d575e533f4967c4b7a4a5bcf`|
|DR3|`48b55379ed7c4b97600e2588c342cb62518df6a14852bdde9eb356427e9655b2`|`cd35c6db727bac4d4f7e475a1b876e3216c060988733dc0ab869e81ce78bf8df`|
|DR4|`3596397b6dcc30982c3174a1021831c4db9e57c4b0c8dda664ff27f6724f51f5`|`635a90fe4cb662c99eb5cffd7b89eaa435b5d3e9a261e7315efa2dc1a77d08c4`|

逐包计划文件、初始控制器文件 SHA 和可公开目录信息见 [DYNAMIC88_CATALOG_PUBLIC.json](dynamic_v1/DYNAMIC88_CATALOG_PUBLIC.json)。计划对象 SHA 使用仓库 canonical JSON 方法，不能用漂亮打印后的文件 SHA 代替。

动态后续 payload 尚未产生，不能预称其内容已经冻结。这里冻结的是任务、来源、评价、动作/观察构造器、共同控制协议、初始提示、模型、执行器和每个终局 slot/角色调用上限。每次真正已读观察及由此生成的下一请求，在调用前保存实际 bytes/对象 SHA 并绑定返回。原 32 个确定臂请求与原 16 个控制器初始 messages 均保留；CPU 已验证确定臂输入一致。

## 明示变化与不变项

终局 G 的 system、decode、任务和严格评价不变。新控制器共同使用 XGrammar 0.1.21、`no_repeat_ngram_size=0`；OneShot 上限 768 tokens，ToolAgent 最多四轮、每轮 192，其他基础 decode 沿用。两者在同一模型和四获取原语域比较；grammar 不输入 gold、正确动作或答案。协议/状态非法、控制器 length、有限合法 logits 为空或非有限异常立即技术停机，0 重试、不清洗、不放松 mask。

六臂为 STOP、FixedTop4Macro、LLMOneShot、LLMToolAgent、SequentialRule、SequentialNoText。Top4 保留五原语的强实践基线身份；NoText 是透明规则，不是同一 LLM 消融。原顺序和冻结政策保留，elapsed-time 暂不进入策略。

为取得实际执行延迟，关闭精确端点缓存；同 payload 也各自实际生成，不把离线缓存作为在线优势。被动 streamer 不改终局 tokens/logits 配置，但会增加观察开销，该开销在实际 wall 中保留。worker 首非空文字并不等于客户端首文字；client TTFT 和 Tokkio 语音指标当前未测。

技术停止保留实际 start、输出、错误 wire、部分区间和 pending。终局 length 保留技术未完成，第三次 length 停整包；来源、设备、存储、模型身份、总 deadline 沿原守卫执行。来源配对的持久 claim 防止换新目录或审批文件隐式重试。任一包被停机后不自动追加、重排或补跑；其他包无自动调度链。

## CPU 就绪证据与运行后判读

最终冻结模块已用 native tokenizer、真实合法来源、实际检索/展开回放全部 48 路径；88 次 fixture 分发明确标为测试替身，真实模型调用为 0。32 个确定输入逐字相等；429 项 CPU 测试通过。原输出/评价 hash 保持。新协议有限 token 回放证明所测路径可执行，不保证真实模型规划成功，也不保证 1200 秒内一定完成整包。

获批后每包仍先独立准入并检查设备；保存冷启动、实际调用、内部首文字、PM、工具、终局和完整本地 Agent wall。按事实/自然支持、来源情境、六臂完整配对报告，评价未知保留。运行数量、来源覆盖、格式合法、tokens 少或速度快均不直接成为任务成功或正式 reward。

若真实动态控制延迟或技术失败耗尽硬限，保留未完成与原因，不增预算、不改模型/样本/提示词追求正结果。结果只用于这一有限开发机制比较；首次 STOP 冷推理、固定臂序、小样本尾部和来源相关性都必须报告。

本轮研究者明确要求所有执行重新批准，因此这里只提交具体可审阅包。审批模板仍为 `authorized:false`，没有以历史授权替代。批准后才依据真实批准文本建立独立审批记录并启动对应作业。

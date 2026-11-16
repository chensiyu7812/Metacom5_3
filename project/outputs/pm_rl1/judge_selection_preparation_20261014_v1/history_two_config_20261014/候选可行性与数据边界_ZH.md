# 候选可行性、输入长度与第三方边界

核查日期2026-10-14。查询官方网页和HF公共JSON元数据，没有请求推理、下载权重、安装包或读取真实封存材料。SHA是查询到的HF仓库revision；DeepSeek服务别名不能替代不可变SHA。

| 候选 | 官方依据与版本 | 本机结论 | 本轮决定 |
|---|---|---|---|
| DeepSeek V4.1-Flash / high | 官方`deepseek-flash`目前映射V4.1-Flash；1,048,576上下文，393,216最大输出；high是推理强度。服务协议授权使用API，不是本地权重许可。 | 无需本地GPU；旧项目有官方endpoint配置。账户、余额、服务返回身份尚未访问核验。完整开发输入16,120—92,797 UTF8字节；本候选精确token数尚未知，估算约4.3k—31.2k。 | 优先API候选，需费用、数据权限及账户回执；尚未实测。 |
| google/gemma-4-12B-it | SHA `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`；Apache-2.0；`Gemma4UnifiedForConditionalGeneration`；262,144上下文；11,959,730,224 BF16参数。 | 官方权重文件23,919,549,408 bytes≈22.28GiB；A6000约47.4GiB当时可用。现有Transformers5.17.0、torch2.7.1+cu128、tokenizers0.23.2、safetensors0.8.0可导入对应模型/processor类；不需要为`.to(cuda)`安装accelerate。现有vLLM0.19.1未确认支持此新架构，故不沿用旧vLLM。 | 优先本地候选；权重/本模型tokenizer未在已核查模型根目录发现，需单独批准约24GB下载。真实加载、全文token长度、吞吐仍未验证。 |
| Qwen/Qwen3.8-27B | SHA `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`；Apache-2.0；`Qwen3_5ForConditionalGeneration`；原生262,144上下文。 | 全模型BF16参数27,781,427,952，仅权重≈51.75GiB，超过A6000；普通TP=2每卡约25.87GiB，又超过20GiB A4500。现有vLLM有Qwen3_5注册，但本checkpoint的配置/加载尚未验证；不等于已可运行。权重未找到。 | 本轮不入池。非对称切层、CPU卸载或量化可能另行可行，但目前没有验证过的方案及耗时证据；不能凭理论总显存相加宣称可承担，也不为第三名增加工程路线。 |
| PatronusAI/glider | SHA `5639434e21faee47a8d3a092cd3105ab051c8b01`；CC-BY-NC-4.0；Phi3架构；官方模型卡说明适用序列8192，作者测试到12k。 | 3.821B参数F32约14.23GiB，显存本身不是主要问题。底座config写131072不等于该裁判已支持完整长评分；开发最长源在旧Qwen下约27.5k tokens，另须留输出。本模型tokenizer精确长度未测；8k/12k适用条件没有被满足或证实。原生接口还是自定义评价，直接套q/m也未验证。 | 条件不满足，本轮不入池；不宣称已用它的tokenizer严格证明每题超长。不能删合法历史凑8k、分段多数投票或用底座128k冒充裁判验证长度。未来若重新提出，属于替换/新审批，不能偷偷扩池。 |

官方模型来源：[Gemma模型卡](https://huggingface.co/google/gemma-4-12B-it)、[Gemma固定revision文件树](https://huggingface.co/google/gemma-4-12B-it/tree/707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7)、[Qwen模型卡](https://huggingface.co/Qwen/Qwen3.8-27B)、[Glider模型卡](https://huggingface.co/PatronusAI/glider)。HF固定revision的config和tokenizer_config均已读取；未读取权重内容。`gemma_public_file_metadata.json`保留官方文件大小、Git blob及LFS SHA256，可用于下载后检验。

Gemma显存估算：按48层中40层1024滑窗、8层全局，FP16/BF16 KV、局部8 KV头×256维、全局1 KV头×512维，保守把K/V分别存储，滑窗缓存约0.31GiB，全局在32k/64k/262k时约0.5/1/4GiB。加22.28GiB权重和假设4—12GiB激活/框架空间，约27—39GiB，有单卡可行余量。此数不是峰值测量；SDPA预填充、实际缓存实现及长输出可能改变峰值，OOM算技术失败。不会自动缩证据、换卡、卸载或量化。固定GPU UUID在configs.json；启动前要求该卡空闲且≥45000MiB可用。

本地环境检查只导入模型类，没有实例化权重、初始化推理或执行forward；因此“离线检查通过”仅指接口/导入可用。安装环境已有对应实现，也不证明24GB新checkpoint能完成此任务。`runtime_receipts.py local`准备好下载后的文件身份、原生模板精确计数和32k输出余量检查；这次未运行该项。32k是输入准入余量，不是生成截断线；实际生成允许直到原生总context边界，达到边界或超时均拒收。

## DeepSeek接口与复现限制

固定POST `https://api.deepseek.com/chat/completions`，字段为model、messages、thinking.type=enabled、reasoning_effort=high、top_p=1、response_format.type=json_object、max_tokens=393216、stream=true、stream_options.include_usage=true。不传无效temperature或假seed；不用自动重试。原v2提示已有JSON/schema说明，本地解析器照常严格检验，不靠JSON模式放宽内容规则。[官方思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)、[Chat参数及返回schema](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)

保存每个SSE原始块、最终content及reasoning_content、id、created、model、system_fingerprint、usage及finish_reason，以及本地请求/配置/提示/解析器哈希。usage.completion_tokens已含思考，不能再加reasoning_tokens而重复计费。服务/model/fingerprint变化时停下核查；没有fingerprint时如实记录可观察性缺口。执行前另获批准读取`/models`的name/context/max_output及账户balance；这两个管理读取不是J推理，不包含项目对话。[官方Models接口](https://api-docs.deepseek.com/api/list-models/)

只有不可变本地revision能绑定下载文件。服务名、返回别名、high、甚至稳定fingerprint都不能保证供应商权重绝对不变；禁止把本API称为不可变权重版本。文档支持与账户实际返回分开记录。还需记录执行前官方价格复核时间，不在未知新价格下继续用旧预留。

## 拟对外发送什么、尚缺什么授权

接收方仅DeepSeek官方API（杭州深度求索体系），用途仅为开发裁判评分。JSON仅包含原v2系统评分提示、新AI任务契约、当前日期、当前前缀、该前缀合法过去完整对话（说话角色、原文、稳定来源ID）、一条待评回复和回复单元ID。四个变体若阶段获批也仅发送其待评文本和同一合法来源。

不发送：Chen/Du姓名、偏好、风险标签、私人备注、答案映射、策略名、预期评分、审核表、密文、密钥、其它文件。原始响应和诊断记录只保存本机，不上传。Gemma权重若获批下载，接收方HF仅收到公开仓库下载请求，不会收到这些对话。

来源是已冻结ES-MemEval公开数据及ESConv种子关系；项目说明明确其包含虚拟人物/扩展轨迹，不是真实18用户纵向随访。ESConv官网限制学术研究用途；本轮查到的ES-MemEval根目录/README没有明确独立LICENSE，故不能从“公开可下载”推断任意第三方传输授权。[ESConv官方说明](https://github.com/thu-coai/Emotional-Support-Conversation)、[ES-MemEval官方仓库](https://github.com/slptongji/ES-MemEval)

DeepSeek开放平台协议要求使用者拥有输入所需权利并处理终端数据权限；公开隐私说明没有为本账户提供可核验的零保留、固定保留期或不训练承诺。隐私政策的开放平台账户数据说明也不能代替对下游对话数据的专项约定。不能借通用消费产品条款推断该API会/不会训练。[开放平台协议](https://cdn.deepseek.com/policies/zh-CN/deepseek-open-platform-terms-of-service.html)、[公开隐私政策](https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html)

因此API首阶段仍需用户确认：这批完整公开研究对话可交由该第三方处理的权限依据，以及是否接受目前未核实零保留/不训练约定的服务条件。若不能确认，API继续阻塞，可独立决定是否只批准本地Gemma准备；不要求粘贴密钥。此项不影响本轮离线实现和mock验证。

# 两模型、四配置支持情况与数据边界（2026-10-15）

本页替代同名旧两配置说明；旧版保留于history_two_config_20261014。没有继续审查或扩充模型名单。仅读取公共文档/文本模板和本地代码，不下载权重、不推理。

| 项 | 文档支持 | 离线实现/检查 | 真实状态 |
|---|---|---|---|
| Gemma A/B | 固定revision原生`enable_thinking=False/True`；同一原生模板 | 公共Jinja模板实测：ON写入think控制标志，OFF预闭合空thought通道；解析器支持带原始prefix解析；两项greedy/BF16/SDPA完全相同 | 约24GB权重未在既定目录存在；真实token计数、加载、显存/吞吐均未验证 |
| DeepSeek C/D | `thinking.type=disabled/enabled`；ON额外high | C temperature=1.0且不发effort；D top_p=1且不发temperature；两项同JSON/最大输出/零重试；mock有效 | 未读取账户、未发研究对话；实际服务及计费未验证 |

[Gemma固定模型卡](https://huggingface.co/google/gemma-4-12B-it/blob/707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7/README.md)、[固定聊天模板](https://huggingface.co/google/gemma-4-12B-it/blob/707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7/chat_template.jinja)、[DeepSeek原生模式](https://api-docs.deepseek.com/guides/thinking_mode/)、[Chat参数](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)。本轮再次核对官方当前页面：temperature在thinking无效；top_p仅thinking有效0.95–1，关闭时固定1并忽略传值。不能用同名无效参数冒充相同有效解码。

Gemma卡和元数据声明Apache-2.0，11,959,730,224参数，权重23,919,549,408字节≈22.28GiB；262144上下文。指定A6000 49140MiB总显存，最新只读快照48551MiB空闲、1%利用率，不视为未来空闲保证。权重+KV+预估框架/激活约27–39GiB，仅为估算，长prefill/OOM尚未实测。现有Transformers5.17.0/torch2.7.1+cu128/tokenizers0.23.2/safetensors0.8.0，固定直接.to(cuda)不需额外安装accelerate。不换卡、量化或卸载来绕过失败。需批准一次约24GB固定版本下载后，对两模式分别用原生模板验证全部40输入+32768输出余量；实际生成自然终止，不将余量当截断值。

DeepSeek服务名deepseek-flash目前映射V4.1-Flash，原生上下文1048576、最大输出393216。关闭默认8K、开启默认64K，因此两项显式设原生384K上界，不利用不同默认值缩短某一项。它是动态服务，不是不可变权重SHA，high也只是模式参数。保存model/id/created/fingerprint/日期、请求配置哈希和每个SSE块；两模式共享观测身份，漂移停止核查。即使fingerprint一致也不能保证权重完全不变；字段缺失须记录。启动前另获准GET /models和/user/balance共2次管理请求，0次J，不发送研究对话。

usage.completion_tokens包括思考；reasoning_tokens是其中子集，不再重复收费。若服务没有返回细分，thinking/final保持null，保留总输出与原始文本，不根据字符数猜token。Gemma按实际生成ID分成思考/最终/格式控制符，保留输入和总生成数。只有自然结束才接收评分；超时/length/不完整SSE不是低奖励。此轮只能证明接口和守卫离线可用。

## API数据范围与仍未解决的权限

接收方仅DeepSeek官方API，开发评分用途。拟发送原v2评分提示（含当前新AI任务契约）、一条原回复或获准变体、全部合法当前/过去来源（角色、原文、日期和稳定ID）及回复单元。绝不发送Chen/Du标注、私人备注、预期分数、别的配置输出、复核意见、密文/密钥或无关文件。Gemma公开下载只向HF请求文件，不传项目对话。

原数据许可审查继续有效：ESConv说明限学术研究；现有ES-MemEval目录/README未查到明确独立许可，公开可下载不能推定此次第三方处理授权。此轮没有发现能补足该缺口的新许可材料。[ESConv来源](https://github.com/thu-coai/Emotional-Support-Conversation)、[ES-MemEval来源](https://github.com/slptongji/ES-MemEval)。需有可核对的文件/许可条款或权利方授权依据；笼统同意无法代替。

既有[开放平台协议](https://cdn.deepseek.com/policies/zh-CN/deepseek-open-platform-terms-of-service.html)与[公开隐私政策](https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html)审查没有给本账户建立可验证的零保留、固定保留期或不训练专项承诺。不能推断该API必然训练或必然不训练。执行前须核对适用账户条件并记录接受范围；数据权限与服务条件是两项独立缺口。

当前有效授权只覆盖离线修订与验证。API需要具体数据许可证据、服务条件、账户/余额/账外责任核对、费用与8次实测授权；本地需要固定权重下载及A/B各4次实测授权。其余144次、恢复、59验收、提高140额度仍另行批准。可先完成本地8次工程门，在阶段结束停止，API保持阻塞。

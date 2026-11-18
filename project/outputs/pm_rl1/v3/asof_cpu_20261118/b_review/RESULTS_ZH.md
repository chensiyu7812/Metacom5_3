# B 独立 CPU 联合审阅结果

基线：integration `320a33d1d871199d171f998300ce926b341ca1a8`。审阅对象按 [RECEIPT.json](RECEIPT.json) 中文件 SHA 绑定；当时尚未提交，不把基线 SHA 冒充新实现 SHA。最终提交必须包含相同已审字节，否则重验。

**结论：新 sidecar 的本轮机械接口检查通过；仅为 engineering_only。** 独立 B AI 审阅不代表人评、原 WS-B owner 正式采纳或 H0 变更。

- 独立解析 A1 RAW Registry，对 p1 / p15 / p18 的全部 65 个真实切点分别核对 source membership、owner / family / transcript SHA、known / ready 边界；切点分别31 / 21 / 13，没有伪造最后会话后的 prefix。
- 独立测试共 **93 passed，0 failed / skipped / xfailed**，9.25秒。第一轮81项及第二轮93项原始日志和 JUnit 均保留。
- 验证未来追加和整个语料文件 SHA 变化不改变过去 snapshot；batch / stream 一致；持久 append 幂等；延迟 ready / 晚获知旧事件 / 当前会话阻断；真实 esc1198 同文同 family 不能跨 p13 / p18 owner；建议不得标为执行；unknown 主体隔离；未审更正不生效；冲突 GET 拒绝；rejected 在 C0 内以 unknown 阶段加明确正文保留。
- 对新 renderer 核对原始证据逐字保留、当前 prefix 相同、OFF 不加资源块、私有绑定不进 messages、篡改/未购买材料被拒及 G/decode/Step-2 改动产生新请求身份。新请求仍不可执行，token IDs / result 为 null，不继承旧 reward。
- C0 contracts / io、32份 Schema 和全局 EXECUTION_STATE 与基线逐字相同。

静态审阅提出并由 A 修复四项：事实日期使用了知识rank比较器；pending ID可进入内存ledger；冲突读取只呈现最后条目；内部审阅状态出现在阅读正文。对应回归均通过。修复发生在测试运行前，未虚构失败测试次数。

仍未验证：真实人工语义批准、模型抽取/摘要、Generator 阅读效果、资源增量质量、RS 方法适用性/疗效、原生新请求分词、真实异步 Writer 与用户等待。测试中的 `human_approved` 均明确为 synthetic mechanism fixture，不是对真实语句的人评。

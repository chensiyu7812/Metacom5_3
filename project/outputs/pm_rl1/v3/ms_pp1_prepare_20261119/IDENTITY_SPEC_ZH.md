# PP1 身份、可见性和原输入保全

文件 SHA256 对文件原始字节计算，包含文件结尾换行；`MANIFEST.json` 列出的文件 hash 是首选传输校验。对象 SHA256 使用现有 `io.object_sha256`：Python JSON、递归键排序、UTF-8、ensure_ascii=False、分隔符 `,` 和 `:`、不加换行。数组保留顺序，不做 Unicode 归一化。浮点数沿用 Python JSON 的有限浮点表示（来源审计中的原 lexical score）；不声称通用 RFC8785。B 可以先对原始字节 SHA 独立复核，再用自己的等价实现重算对象。

三层身份不能互换：

1. **原请求**：`legacy_request_id` 是 #12 G0e 的 `sha256({protocol, terminal, binding, payload})`，其中 protocol 为 `pmrl1v3-g0e-request-packet-1`、terminal 为原 TerminalKey 的对象 SHA、binding 为 BASELINE.spec 的对象 SHA、payload 为 messages/input_ids/decode。16 条原请求和 TerminalKey 字段逐项保留在 `LEGACY_INPUTS_16.json`。原研究 job 在 `plan_job_id` 旁路引用。
2. **PP1 admission**：`PP1-admission:` 加 SHA，字段由 `compile/ms_pp1.py:admission_identity` 的固定列表定义，绑定 protocol、condition、owner/prefix/context、snapshot/frontier、原请求/terminal、payload/token hash、四项 G/renderer/decode/Step-2、来源绑定 hash。它仅用于本次许可和新日志空间，不能把旧请求结果/reward 搬进来。plan SHA 再绑定 16 条顺序和请求 JSONL 文件 SHA、预算、runtime、停止规则；研究者许可必须引用完整 plan 与实际 executor/integration SHA。
3. **DP pending slot**：`PP1-DP-pending:` 只标识前缀、候选池、基线和独立选择规则。由于选择未完成，最终内容 request_id/model_input/token IDs 为 null；不能执行、不能当已合格 DP、不能用 RET 的结果填入。正式 DP 选择与人工确认后另建内容请求，若与 RET 最终字节相同，未来是否共享一次物理请求由获准协议决定，本轮没有共享结果。

Generator 唯一预定可见对象是 `model_input` 的 messages/input_ids/decode。owner、family、prefix/snapshot/frontier ID、条件标签、候选排名、来源文件、审查状态、DP 池、许可和评价字段全部属于外侧审计。`audit_projection` 重建原 G0e 白名单，HTML 转义完整 RAW 后逐字比较；重新原生分词逐 token 比较。它是 A 的独立实现自检，不改变被测试的原 renderer 身份，也不冒充原 B 的独立验收。

旧 bank/request 身份仍含全局 registry/bank 依赖，因此只声明**固定 16 条原载荷保全**，不声明重新编译旧 bank 后其请求键未来不变。双 horizon 的不变性对象是 #18 的局部来源 snapshot/frontier/RAW/readings；在线 B binding/cache 的 R1 风险在集成报告中继续保留。

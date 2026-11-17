# B5 准备状态（未完成，等待 C0 冻结）

- 证据等级：engineering_only；无模型、GPU 或付费调用
- 已完成的部分不依赖契约形态：`project/src/metacom_pm/rl1v3/env/finite_head.py`
  - Phase-1 动作 STOP/GET_RS/GET_MP/GET_ME/GET_MS。每个头最多读一次；终点只取决于已取子集（规范头序 RS, MP, ME, MS）
  - mask：已读、空头、超出原生容量、超出 GET 预算和 STOP 之后的动作都会被屏蔽；如果仍被执行，抛出 `IllegalAction`，状态不变
  - GET 只调用注入的 reader（WS-A `retrieve.read`），不调用 G/J；STOP 才查版本化终点表；缺失的终点抛出 `PendingTerminal`，不算 0
  - Observation 由注入工厂构造；record_ids 只交给执行器，不进入观察
  - 精确 DP（含平局集合、可达终点、步进成本、可用头与预算限制）、暴力枚举核验、区间 DP（重叠时不声称精确最优）
- 测试：`project/tests/test_rl1v3_b5_env_core.py` 16 项通过。DP 与 300 张随机表的暴力枚举一致；按 DP 策略执行能达到 DP 值；回放确定；观察中没有私有 id 和未读正文
- 尚缺（依赖 C0 冻结，见 `../C0_review/C0_REVIEW_WSB_ZH.md` R1–R3）：接入 C0 Observation/TerminalKey（domain_id、规范路径、按动作分组的 record）、真实 bank v0 reader（A1b）、终点表文件格式与 B6e 对接

# B 最新提交的独立联合验收补充

施工期间 B 从 `0af8d35e` 推进到 PR #11 的 `10fccdf623c2336ee8245e586bfd0830f472e85d`。A 保留第一次验收，然后在独立工作树把该 B 提交与 A 代码 `c4c9db1e2a8c957921a7f4702a14b661f16d3db4` 合成 **`87d5e8709702a896a7ce825174cc4897430ef8aa`**。这个合成提交仅本地验收，不推到 integration，不计正式集成。

实际运行 B 自己的 `project/scripts/rl1v3/B6e_g0e_binding_addendum.py`，没有修改该脚本或 B-owned 实现。原生 Gemma tokenizer，CPU only，无权重加载/forward/生成。完整结果在 `b_latest/`，原始stdout在 `validation/b-latest.log`。

- 状态 passed，8/8前缀；7×16+1×8 = **120**终点、**471**合法读取顺序。
- B 的完整 B5 replay 检查通过，包括owner、严格过去、family、来源跨度、原生token、容量压力、顺序一致、A replay(key)及独立reload。
- 原生payload、key/trace、decode、计费和容量均一致；检查2427条可识别未来话语无泄漏，5条与合法已见原话完全相同的未来重复话语单独计数。检查了NeedCard/Checklist/Judge特权标记和私有ID。
- 旧 renderer / Step-2 / g_id / decode_id 与新版本不同，bank/index未变；旧资源组、正文及token数相同。旧key表放入测试诱饵奖励0.5，仅用于验证新key查表仍为PendingTerminal；该值不是生成/判官结果，没有写入真实终点。
- A与B独立材料的120组 `(prefix, subset)` 全部相同，旧key SHA、新key SHA、request SHA逐一相同，见 `A_B_EQUALITY.json`。
- 原B冻结plan/selection/REAL_KEYS_CHECK未改写；B addendum协议 `pmrl1v3-b6e-g0e-binding-addendum-v1`，object SHA **`c1acae9f83e708953b73ac23ef88398ef3d9877b946386049ca09418323fa2a6`**。
- 最新合成代码V3 **588 passed / 0 fail / 0 skip / 0 xfail**，严格JUnit gate通过；上一合成代码570项结果也保留，不覆盖。均为CPU测试；测试内fixture优化器检查不是真实模型训练实验。

B最新J1容量诊断作为依赖记录在 `inputs/B_CAPACITY.json`：部分真实协议结构的fixture输出可能超过原800 token上限；B提出前缀定额/最多4096等方案，尚未批准。A没有改判官协议/解码，也没有把NeedCard的800 token测速当成J1吞吐。真实J1输入、decode身份和预算需要B/研究者在调用前固定。

## 给 integration owner / B 的衔接

1. 保留 PR #10 HEAD `73fdb12f` 及其成功CI；由integration owner合入。
2. PR #12 是独立补充，暂base为PR #10工作分支，仅用于避免重复diff；**不要合入PR #10分支**。父PR合入后将base改为integration，再做真实集成HEAD验收。B PR #11按其依赖同步。
3. B6e新生成manifest引用本补充的完整G0e六字段和B addendum SHA，不能仅填旧plan中的G0/decode占位字段。旧冻结记录继续保留。
4. A0补充plan须研究者单独授权；B6e120个真实终点生成仍是B的单独授权工作。G0e不是A7，A0没有GPU实测完成声明。

# Policy Manager 版本索引

更新时间：2026-07-15

本仓库中的 PM 研究现在按三个版本管理，避免原始 V1、后补诊断和 V2 重设计相互混用。

## PM-v1：原始冻结研究版本

分支：[`pm-v1-frozen`](https://github.com/chensiyu7812/metacom-v33-review/tree/pm-v1-frozen)

冻结提交：

```text
c16608343fe60e92e57c622fdc24738efe57d08c
```

用途：

- 保存原 V3.3 / PM-v1 方法、结果和六条件 EvoEmo 主实验；
- 不包含后补 `ME+R0`、forced-swap 或 PM-v2；
- 该分支应保持只读。

## PM-v1.5：PM-v1 的补充诊断版本

分支：[`pm-v1.5-supplemental`](https://github.com/chensiyu7812/metacom-v33-review/tree/pm-v1.5-supplemental)

主要文档：

- `project/docs/PM_VERSIONING_AND_BRANCHES_ZH.md`
- `project/docs/PM_V1_5_SUPPLEMENTAL_ANALYSIS_ZH.md`

用途：

- 保持 PM-v1 checkpoint 和选择规则不变；
- 汇总 OOD、semantic split、margin/epsilon sensitivity；
- 汇总同预算 `ME+R0` 和 forced-swap 结果；
- 修正 Overall、claim boundaries、Discussion 和 Limitations；
- 不构成新训练模型或重新选择后的 confirmatory method。

## PM-v2：实质性重设计

分支：[`pm-v2-redesign`](https://github.com/chensiyu7812/metacom-v33-review/tree/pm-v2-redesign)

用途：

- 新数据、标签、模型和 multi-objective selection；
- explicit M0/R0 gates；
- human label calibration；
- internal cost-matched reportability gate；
- 必须重新训练、冻结和外部评价。

## Main 分支

`main` 当前作为整合与审查入口，包含多个版本的文档和代码。论文复现或引用时不要只写 `main`，应明确指定：

- `pm-v1-frozen`；
- `pm-v1.5-supplemental`；
- 或 `pm-v2-redesign`。

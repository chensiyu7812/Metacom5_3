# MetaCom Policy Manager 版本与分支边界

更新时间：2026-07-15

本文档用于防止 PM-v1、后补诊断和 PM-v2 重设计相互混用。

## 1. PM-v1：原始冻结版本

GitHub 分支：

```text
pm-v1-frozen
```

冻结提交：

```text
c16608343fe60e92e57c622fdc24738efe57d08c
```

PM-v1 表示原始 V3.3 研究链路，包括：

- 原始监督式 pre-retrieval Policy Manager；
- 16 个 memory × strategy 资源动作；
- Synthetic development supervision；
- ESConv Strategy RAG diagnostic；
- EvoEmo fixed-input 六条件外部比较；
- 原始 V4 response evaluation；
- sampled/stress selected-context audit；
- observed latency diagnostic。

PM-v1 不包含：

- 后补的同预算 `ME+R0` response comparison；
- forced-swap PM vs `ME+R0` probe；
- 后补的 margin / epsilon sensitivity；
- semantic-family split robustness diagnostic；
- PM-v2 数据、模型或训练代码。

`pm-v1-frozen` 只用于保存原始研究版本。不得在该分支上继续追加实验或修改结果口径。

---

## 2. PM-v1.5：同一 PM 的补充诊断版本

GitHub 分支：

```text
pm-v1.5-supplemental
```

基线提交仍为：

```text
c16608343fe60e92e57c622fdc24738efe57d08c
```

PM-v1.5 **不是重新训练后的新 PM**，也不是一个新的主要方法。它保持 PM-v1 checkpoint、动作空间和原始外部生成不变，只增加原研究冻结后的补充分析：

- EvoEmo OOD 与 TF-IDF coverage 诊断；
- semantic-family split 复核；
- top-1 / top-2 score margin；
- epsilon sensitivity；
- 同预算固定动作 `ME+R0`；
- forced-swap 顺序稳健性 probe；
- 对 `Overall = Emotional Support` 的指标修正；
- 更新后的 claim boundaries、Discussion 和 Limitations。

因此，版本关系为：

```text
PM-v1.5 = PM-v1 frozen method + post-freeze supplemental diagnostics
```

不能将 PM-v1.5 描述成经过 `ME+R0` 结果重新调参后的模型。任何根据 EvoEmo 补充结果修改 epsilon、阈值、训练目标或 checkpoint 的版本，都不再属于 PM-v1.5，而应进入 PM-v2 或新的预注册实验。

---

## 3. PM-v2：实质性重设计版本

PM-v2 是独立的重新设计与重新训练研究，包括：

- 新的 longitudinal development data；
- user / semantic-family / normalized-text 三重隔离；
- 完整 16-action sweep；
- 删除 LLM `overall` 字段；
- 多 judge family 与人工标签校准；
- 新特征表示、uncertainty 和 OOD；
- 显式 M0/R0 benefit gates；
- direct quality-risk-cost utility；
- internal cost-matched reportability gate。

PM-v2 不是 PM-v1.5 的简单补丁，结果也不能与 PM-v1/V1.5 混成同一个 confirmatory experiment。

---

## 4. 论文使用边界

### 使用 PM-v1 主实验时

可以使用原六条件主表，重点回答：

- 资源是否应 always-on；
- Context Only、focused session retrieval 和 full history 的非单调关系；
- PM 相对高资源 structured/full-history baselines 的资源节省；
- coarse source routing 与 item-level evidence filtering 的区别。

但必须：

- 将原 `Overall quality` 改名为 `Support Rating`；
- 不声称 PM 已证明优于所有同预算 fixed actions；
- 不声称 PM 已经学会 M0 或 Strategy-off；
- 不声称 quality、risk、cost 已被完整联合优化。

### 使用 PM-v1.5 补充分析时

推荐放在：

- Discussion；
- Limitations；
- Appendix / Supplement；
- failure analysis。

主表是否放入 `ME+R0` 由版面与论文叙事决定，但正文必须保持与补充结果一致的谨慎主张。

---

## 5. 分支管理原则

1. `pm-v1-frozen` 永久只读，保存原研究快照。
2. `pm-v1.5-supplemental` 只接收与 PM-v1 同一 checkpoint 有关的后补诊断和论文边界修正。
3. PM-v2 代码、数据和新 checkpoint 不提交到 PM-v1/V1.5 分支。
4. PM-v1.5 不允许根据外部测试结果重新选择模型或阈值。
5. 任何正式论文应在 Methods 或 Reproducibility 中标明使用的是 V1、V1.5 supplement，还是 V2。

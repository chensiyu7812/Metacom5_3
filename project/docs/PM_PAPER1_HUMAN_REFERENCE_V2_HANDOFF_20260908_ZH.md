# Paper-1 V2 人评交付说明（2026-09-08）

状态：空白卷已生成；等待两名评审独立完成。研究者已授权本次 V2 证据修订和制卷，详见同目录 `PM_PAPER1_HUMAN_REFERENCE_V2_AMENDMENT_20260908_ZH.md`。

## 分发和填写

产物目录：`project/outputs/paper1_pairwise_teacher/human_sheets_v2/`。

| 评审 | 专用分发包 | 解压后打开 |
|---|---|---|
| A | `paper1_rater_a_v2.zip` | `paper1_pairwise_teacher_rater_a_sheet_v2.html` |
| B | `paper1_rater_b_v2.zip` | `paper1_pairwise_teacher_rater_b_sheet_v2.html` |

每个包只包含本人 HTML、原始空白 JSON 和操作说明。只发给各评审自己的包；`coordinator_only/` 留给研究负责人。推荐电脑浏览器打开本地 HTML，页面无外部依赖，不会自动上传。

1. 阅读页面顶部说明；按照本人卷的顺序独立填写，不与另一位评审交流，不让模型代评。
2. 每题选一个判定，并写 1–3 句理由，中文或英文均可。更长、更温暖、更多记忆本身不加分；没有实质净差异选 equivalent，证据不足无法可靠判断选 uncertain。
3. DG 题先读可见对话和相关历史摘录；需要核查其他记忆或当前状态时，使用完整历史的关键词搜索、日期索引。摘录没有提到不等于事实为假；注意 seeker/supporter 角色和时间变化。
4. 每人共 96 题，允许分次完成。休息前点击“导出进度”，下次在本人网页中“恢复进度”；同时浏览器会尽可能保存本机进度。保留下载文件作为备份。
5. 全部完成后点击“导出完整答卷”，将下载的 `*_rated.json` 交回研究负责人。原始空白卷保持不变。

旧 V1 仅保留溯源，新人评统一使用 V2。如已有旧版评分，应另外归档，不能无版本区分地混入。

## 接收与后续

接收时先做只读完整性校验（在 `project/` 下运行，Python 环境须含当前 `metacom_pm` 依赖）：

```bash
python scripts/paper1/62_validate_human_reference_v2_submission.py --rated-file /path/to/paper1_pairwise_teacher_rater_a_sheet_v2_rated.json
```

检查进度备份时可加 `--allow-partial`；不加时必须 96 题都有有效 verdict 与非空 rationale。工具校验 rater/version、所有原题及参考不可变字段、题序、重复 JSON 键、规范卷哈希，只输出状态、计数及提交 SHA-256，不修改文件或自动判分。对 B 同样执行。

两份完整答卷封存后，先按原始评分计算双评一致性和反序稳定性，再依预先确定的共识规则单列处理分歧。共识在查看 Gemini verdict 前封存，无法形成可靠共识则 uncertain；不覆盖原始评分。

下一步是单独授权的 Gemini teacher qualification，使用本次已绑定的相同参考与 prompt。再推进真正的 RS/MP/ME/MS amount/top-k calibration；冻结 k*、容量、折分隔离、完整生成栈和调用计划后，才生成正式 effect labels 并训练 PM。本轮人评是测量参照，不直接充当 PM 训练标签，也不代表另行设计的 natural-turn appropriateness 样本。

新版制卷完成不代表正式链路已全部就绪。2026-09-07 审计指出的 Summary equivalent 编码与现行契约不一致、teacher 目标与后续验证的隔离、正式 DG 调用预算重算等问题，仍须在相应 calibration/effect/正式调用前处理；本次仅修订人评证据及对应 teacher 接口。

## 可复核材料

- 规范清单：`data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json`。
- 当前流程：`data/paper1_authority/paper1_pairwise_teacher_qualification_plan_v3.json`。
- `python scripts/paper1/61_materialize_human_reference_v2.py --check` 离线重构并逐字节验证已交付包，无写入。
- 本次保留全部 142 条已有回复、80 个基础 pair 和 16 个反序；新增模型调用、API 花费、formal outcome、PM training 均为 0。

答卷和生成文本位于被 Git 忽略的 outputs 中；仓库只跟踪实现、方法说明和无回答文本的哈希/来源清单。

# 原生 token 与条件可执行性

分词器：冻结 Gemma-4-12B-it-707f0a3；transformers 5.17.0 / tokenizers 0.23.2；仅 CPU。HF 上下文 16,384，每条额外保留 320 输出 token；无截断。

| 条件 | 已分词 / 8 | 最小–最大输入 token | 材料状态 |
|---|---:|---:|---|
| OFF | 8 | 137–795 | 输入准备；运行未授权 |
| MP-direct | 7 | 328–991 | p3 无候选；其余仅审阅预览 |
| ME-direct | 8 | 320–982 | 仅审阅预览；资格待审 |
| MS-RAW-direct | 8 | 977–1598 | 机械完整 RAW；适用及许可待审 |
| MS-SUM-direct | 0 | N/A | 无合格摘要 |
| RS-R0 | 8 | 137–795 | 输入准备；运行未授权 |
| RS-F-resident | 8 | 373–1031 | 仅审阅预览；资格待审 |
| RS-METHOD | 8 | 302–960 | 仅审阅预览；资格待审 |
| RS-METHOD+CASE | 8 | 691–1349 | 仅审阅预览；资格待审 |

63 条均 fits。9 条缺材料没有空文本假成功、没有 token IDs。新原生 IDs 从新 preview_messages 重算；旧 54/100 OFF 不迁移。所有 72 条 runtime_callable=false、research_qualified=false、result/reward=null。

MP/ME Preview 的主体/阶段仍为 unknown，显式显示 source speaker 与 reported 日期，避免把建议当用户执行。CASE 标明是其他人。只向模型投影 messages/input_ids/decode；此轮没有模型调用。

FINAL_EXECUTABILITY_MATRIX.jsonl 绑定 AI 语义预审处置；cpu_v3 的 token 化预览保留原样，隔离条目不会因预览可分词而放行。

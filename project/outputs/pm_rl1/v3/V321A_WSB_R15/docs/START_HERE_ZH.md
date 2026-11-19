# 从这里开始：R15 人工筛查与评审交接

**交接目录**（在仓库外，按人分文件夹）：`/opt/tokkio-data0/tokkio_projects/pmrl1-validation/wsb-v321a-handover-r15/`

含原文的文件只放在这个目录里，不进公开仓库。各文件的 SHA 见同目录的 `SHA256SUMS.txt`。

## 先记住三条规则

1. **不要把任务 HTML 整个上传给 ChatGPT。**
   - 要上传的是 `00_TRANSLATE/batches/` 里的小文本批次，每个约 3,000 词，最大 25 KB。
   - 任务页里有锁定、校验和盲态逻辑，必须保持原样。译文由本地命令逐行检查后，放进已经验证过的页面。
   - 中文优先、英文可展开、逐句对照的显示方式，页面已经内置。
2. **翻译由两名整理者交叉操作，R1 和 R2 不操作。**
   - CUR1 上传 `CUR1_操作/` 里的批次，内容是 CUR2 组人物的会话。
   - CUR2 上传 `CUR2_操作/` 里的批次，内容是 CUR1 组人物的会话。
   - 原因：谁操作翻译，谁就会读完这些人物的全部历史。
     - 如果 R1 或 R2 读了，Q0 就不再是“没看过历史”，QH 也不再只看到“此刻之前”的历史。研究者本人是 R1，所以不操作。
     - 如果整理者读自己组的人物，就会在标注较早的前缀之前，先读到同一人物较晚的会话。
   - 交叉操作的结果：正式 90 条没有一条受影响。11 条交叉复核和 PP1 的 8 条会提前读到同一人物较晚的会话，已在 `EXPOSURE.json` 中登记。
3. **PP1 生成后的候选回复，由 CUR2 操作翻译。** CUR1 看得到条件对应关系，R1/R2 在锁定前不能看到生成结果，所以都不操作。

## 现在能下载什么、给谁

| 给谁 | 文件 | 用途 |
|---|---|---|
| R1 | `R1/00_练习_R1_评审第一部分Q0（模拟）.html`、`R1/REVIEWER_GUIDE_ZH.md` | 练习，模拟材料 |
| R2 | `R2/00_练习_R2_评审第一部分Q0（模拟）.html`、`R2/REVIEWER_GUIDE_ZH.md` | 练习；左右位置与 R1 镜像，译文完全相同 |
| CUR1 | `CUR1/00_练习_CUR1_筛查（模拟）.html`、`CUR1/CURATOR_GUIDE_R15_ZH.md`、`CUR1/DP_PREP_ZH.md` | 练习与说明 |
| CUR1 | `00_TRANSLATE/CHATGPT_转换说明_ZH.md`、`00_TRANSLATE/试跑_模拟/B00.txt`、`00_TRANSLATE/batches/CUR1_操作/`（29 个批次） | 翻译 |
| CUR2 | `CUR2/00_练习_CUR2_筛查（模拟）.html`、`CUR2/CURATOR_GUIDE_R15_ZH.md`、`CUR2/DP_PREP_ZH.md` | 练习与说明 |
| CUR2 | `00_TRANSLATE/CHATGPT_转换说明_ZH.md`、`00_TRANSLATE/batches/CUR2_操作/`（26 个批次） | 翻译 |
| 只给 CUR1 | `CUR1/COORDINATOR_只限CUR1/` | 题号对照、审计映射、DP 模板、PP1 生成后的构建清单 |

**正式任务页**（中文版）现在还没有。对应批次译完并通过检查之后，`zh` 命令会自动生成。

## 怎样得到最终中文 HTML

1. **试跑一次**（模拟句子，约 10 分钟）。
   - CUR1 新开一个 ChatGPT 对话，上传 `CHATGPT_转换说明_ZH.md` 和 `试跑_模拟/B00.txt`，说“按说明翻译这个批次”。
   - 把返回的文件存为 `B00.zh.txt`，然后运行：
     ```
     cd /home/tokkio/Metacom5_3-ws-b/project
     export TMPDIR=/opt/tokkio-data0/tokkio_runs/wsb_v321a/tmp
     PY=/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python
     $PY scripts/rl1v3/V321A_r15.py dryrun --returned <B00.zh.txt 的路径>
     ```
   - 打开生成的 `00_TRANSLATE/PRACTICE_DRYRUN.html` 看看效果。
2. **翻译正式批次。**
   - 每个批次开一个新对话，上传转换说明和一个批次文件。
   - 返回的文件按批次号命名，例如 `B01.zh.txt`，放进 `00_TRANSLATE/returned/`。
   - 如果 ChatGPT 中途停下，回复“继续”，后面的部分存为 `B01.part2.zh.txt`。
   - **顺序**：CUR1 先做 B01–B10，CUR2 先做 B11–B16（这是各自交叉复核需要的批次）。之后 CUR2 做 B17–B36，CUR1 做 B37–B55。
3. **运行 `zh`。**
   ```
   $PY scripts/rl1v3/V321A_r15.py zh
   ```
   - 有服务器权限的人都可以运行。输出只有状态，不显示内容。
   - 某个批次没通过时，`00_TRANSLATE/fix_requests/Bxx.fix_request.txt` 只列出要重译的行。同一操作人把它交给 ChatGPT，结果存为 `Bxx.fix1.zh.txt`，再运行一次 `zh`。
   - 一个任务包需要的批次全部通过后，中文页面会出现在 `CUR1/` 或 `CUR2/` 下，例如 `CUR1/CUR1_01_CROSS6.html`。这些页面都已通过检查；检查不通过的页面不会生成。

   | 页面 | 需要的批次 |
   |---|---|
   | `CUR1_01_CROSS6`（6 条） | B01–B10 |
   | `CUR2_01_CROSS5`（5 条） | B11–B16 |
   | `CUR1_02_SCREEN40`（40 条） | B11–B36 |
   | `CUR2_02_SCREEN50`（50 条） | B01–B10、B37–B55 |
   | `CUR1_03_PP1_S8`（8 条） | 全部 55 个 |

4. **页面被改过的情况。** 如果有人用 ChatGPT 或手工改过页面外观，发出前必须运行：
   ```
   $PY scripts/rl1v3/V321A_r15.py check --file <页面> --e2e
   ```
   任何一项显示 FAIL，就不能用于真实评审，改用 `zh` 生成的原页面。
5. **分发与收件**：见 [OPS_ZH.md](OPS_ZH.md)。所有导出文件都交给 CUR1。

## 必须等以后才能准备的材料

- **PP1 的 R1/R2 盲评页**：要等 A0 通过、PP1 单独授权并完成 16 次生成之后，由 CUR1 按 `PP1_AFTER_GENERATION_ZH.md` 构建。现在只有练习页。
- **DP 选材**：要等正式 S 标签冻结、样本确认之后。在此之前，A 需要先修好 PR #26 选材页的默认选中问题（见 DP v2 回执）。
- **正式 FC-MS 回复评审页**：要等生成之后。

## 两点注意

- 使用 ChatGPT 网页版是研究者在 R15 指令中的决定。建议在 ChatGPT 的数据控制设置里关闭“改进模型”。批次和译文文件不转发、不公开。
- `_英文源文件_不分发/` 里的英文页面只用来核对身份，不发给任何人。收件命令会拒绝这些页面的导出。

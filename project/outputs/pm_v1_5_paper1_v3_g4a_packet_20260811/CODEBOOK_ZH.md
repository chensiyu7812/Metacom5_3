# G4A 非排他资源适用性审核手册

本包只判断：**这个组件的 actual Rank-1 候选，是否适合用于当前下一条 supporter 回复。**

每个条目只属于一个 component。不要在 MP、MS、ME 之间选赢家；你看不到其他 component 是刻意的。
同一个底层 state 可以在另一个 component 包里再次出现，而且 MP/MS/ME 可以同时全部 SUITABLE。

## 唯一主决定

- `SUITABLE`：候选能在当前边界内实现该 component minimum，并带来当前未见的具体用途。
- `NOT_SUITABLE`：冻结材料已足以确认不应使用；选择一个最主要的负 reason code。
- `SEMANTIC_ABSTAIN`：冻结可见 state 与候选不足以解决 bounded 判断。它不是低信心分数，也不能默认改成 NOT。

四项 checklist 只表示你已经考虑：target/entity/function、nonredundant increment、component minimum、
current boundary。不要分别输出四个 YES/NO/UNKNOWN；旧四轴量表已经停用。

## 组件边界

- MP：必须静默改变约束、现实细节、framing 或必要前提。只念 profile、当前已说出、装饰性提及或刻板推断均 NOT。
- MS：严格过去的原子 user evidence 必须改变理解、一个问题、约束或当前 option。寒暄、感谢、current echo、
  wrong event、stale/resolved、同主题但无 response change 均 NOT。
- ME：过去 action-result 必须能作为 tentative user-owned evidence 或可拒绝 option。typed/完整不自动为正；
  当前不需要行动、不可迁移、已尝试/已拒绝或边界禁止均 NOT。

## 提交格式

只提交 review_item_id、decision、primary_reason_code、visible_span_ids、candidate_span_ids、
checklist_attested=`ALL_FOUR_CONSIDERED`。证据只用包内预编号 V/C span ID，不复制长文本。

不要判断 response quality、risk、cost、未来 generator 是否会执行，也不要猜 PM 或实验臂。

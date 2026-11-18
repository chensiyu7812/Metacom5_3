# 三位 owner 的逐时点快照与差异

以下65行对应真实下一会话首个 seeker→supporter 切点。RAW 逐会话累积；last session只提交，无虚构的下一会话快照。新增条目可能包含待审MP/ME或unusable SUM；这些不是已验证事实。旧 latest 差额仅诊断池成员选择，不恢复旧隔离MP。

| owner | cutoff | 合法已完成源 | 新增ledger条目 | 移除 | 旧全历史latest丢失早期成员数 | 快照 |
|---|---:|---:|---:|---:|---:|---|
| p1 | 1 | 1 | 1 | 0 | 3 | [53a0bad0b04c](cpu_v3/snapshots/p1-r01.json) |
| p1 | 2 | 2 | 1 | 0 | 1 | [7d838667abd9](cpu_v3/snapshots/p1-r02.json) |
| p1 | 3 | 3 | 1 | 0 | 0 | [e754469e9f44](cpu_v3/snapshots/p1-r03.json) |
| p1 | 4 | 4 | 1 | 0 | 0 | [0c163867bddd](cpu_v3/snapshots/p1-r04.json) |
| p1 | 5 | 5 | 1 | 0 | 0 | [51367b4aa1ec](cpu_v3/snapshots/p1-r05.json) |
| p1 | 6 | 6 | 1 | 0 | 0 | [7043011d3efe](cpu_v3/snapshots/p1-r06.json) |
| p1 | 7 | 7 | 1 | 0 | 0 | [c37d3d287899](cpu_v3/snapshots/p1-r07.json) |
| p1 | 8 | 8 | 1 | 0 | 1 | [dca9f4b7a6b5](cpu_v3/snapshots/p1-r08.json) |
| p1 | 9 | 9 | 1 | 0 | 0 | [b1e6863438d8](cpu_v3/snapshots/p1-r09.json) |
| p1 | 10 | 10 | 1 | 0 | 0 | [5826177a62d0](cpu_v3/snapshots/p1-r10.json) |
| p1 | 11 | 11 | 1 | 0 | 0 | [af9da0f12a87](cpu_v3/snapshots/p1-r11.json) |
| p1 | 12 | 12 | 1 | 0 | 0 | [6bf7c082640a](cpu_v3/snapshots/p1-r12.json) |
| p1 | 13 | 13 | 5 | 0 | 4 | [09cb9dc83091](cpu_v3/snapshots/p1-r13.json) |
| p1 | 14 | 14 | 1 | 0 | 4 | [ad596f6bc9d7](cpu_v3/snapshots/p1-r14.json) |
| p1 | 15 | 15 | 1 | 0 | 2 | [88f56fd52895](cpu_v3/snapshots/p1-r15.json) |
| p1 | 16 | 16 | 3 | 0 | 2 | [3ba0c2438485](cpu_v3/snapshots/p1-r16.json) |
| p1 | 17 | 17 | 1 | 0 | 0 | [9399df550bc1](cpu_v3/snapshots/p1-r17.json) |
| p1 | 18 | 18 | 1 | 0 | 0 | [011365bb1c58](cpu_v3/snapshots/p1-r18.json) |
| p1 | 19 | 19 | 1 | 0 | 0 | [3d29c8d5fd25](cpu_v3/snapshots/p1-r19.json) |
| p1 | 20 | 20 | 3 | 0 | 0 | [01bf322f2d3c](cpu_v3/snapshots/p1-r20.json) |
| p1 | 21 | 21 | 1 | 0 | 0 | [fe561dd797b3](cpu_v3/snapshots/p1-r21.json) |
| p1 | 22 | 22 | 1 | 0 | 2 | [6e90ccc2e161](cpu_v3/snapshots/p1-r22.json) |
| p1 | 23 | 23 | 1 | 0 | 2 | [57c1c2696460](cpu_v3/snapshots/p1-r23.json) |
| p1 | 24 | 24 | 1 | 0 | 2 | [2987eeb42793](cpu_v3/snapshots/p1-r24.json) |
| p1 | 25 | 25 | 1 | 0 | 2 | [cd3c95a3622b](cpu_v3/snapshots/p1-r25.json) |
| p1 | 26 | 26 | 1 | 0 | 3 | [e766d82021ba](cpu_v3/snapshots/p1-r26.json) |
| p1 | 27 | 27 | 1 | 0 | 3 | [f0aa6a41251f](cpu_v3/snapshots/p1-r27.json) |
| p1 | 28 | 28 | 1 | 0 | 3 | [f9a0711d5cd6](cpu_v3/snapshots/p1-r28.json) |
| p1 | 29 | 29 | 1 | 0 | 3 | [0a991e65d22f](cpu_v3/snapshots/p1-r29.json) |
| p1 | 30 | 30 | 1 | 0 | 1 | [d40e54c553ae](cpu_v3/snapshots/p1-r30.json) |
| p1 | 31 | 31 | 1 | 0 | 0 | [98fa6591d20b](cpu_v3/snapshots/p1-r31.json) |
| p15 | 1 | 1 | 1 | 0 | 1 | [c5315e2fd126](cpu_v3/snapshots/p15-r01.json) |
| p15 | 2 | 2 | 1 | 0 | 2 | [366656bb3ee8](cpu_v3/snapshots/p15-r02.json) |
| p15 | 3 | 3 | 1 | 0 | 2 | [b68aa47ad72a](cpu_v3/snapshots/p15-r03.json) |
| p15 | 4 | 4 | 1 | 0 | 2 | [8f274205ef26](cpu_v3/snapshots/p15-r04.json) |
| p15 | 5 | 5 | 4 | 0 | 2 | [1da0bb3e033f](cpu_v3/snapshots/p15-r05.json) |
| p15 | 6 | 6 | 1 | 0 | 2 | [442dd4440397](cpu_v3/snapshots/p15-r06.json) |
| p15 | 7 | 7 | 1 | 0 | 2 | [3fe584e16d2d](cpu_v3/snapshots/p15-r07.json) |
| p15 | 8 | 8 | 1 | 0 | 2 | [7ff88aff501c](cpu_v3/snapshots/p15-r08.json) |
| p15 | 9 | 9 | 1 | 0 | 2 | [4e6408deb0bb](cpu_v3/snapshots/p15-r09.json) |
| p15 | 10 | 10 | 1 | 0 | 2 | [6c52d87a658e](cpu_v3/snapshots/p15-r10.json) |
| p15 | 11 | 11 | 1 | 0 | 1 | [4d23fa85c2e8](cpu_v3/snapshots/p15-r11.json) |
| p15 | 12 | 12 | 1 | 0 | 1 | [b20d5c0c0182](cpu_v3/snapshots/p15-r12.json) |
| p15 | 13 | 13 | 3 | 0 | 1 | [57469e7d7a01](cpu_v3/snapshots/p15-r13.json) |
| p15 | 14 | 14 | 1 | 0 | 2 | [26cab57622c4](cpu_v3/snapshots/p15-r14.json) |
| p15 | 15 | 15 | 1 | 0 | 2 | [f9a24d12c9a6](cpu_v3/snapshots/p15-r15.json) |
| p15 | 16 | 16 | 1 | 0 | 2 | [01fceba6b2ac](cpu_v3/snapshots/p15-r16.json) |
| p15 | 17 | 17 | 1 | 0 | 2 | [28dfc45fb3c4](cpu_v3/snapshots/p15-r17.json) |
| p15 | 18 | 18 | 1 | 0 | 2 | [a73d17f30a81](cpu_v3/snapshots/p15-r18.json) |
| p15 | 19 | 19 | 1 | 0 | 2 | [44bf3fe85699](cpu_v3/snapshots/p15-r19.json) |
| p15 | 20 | 20 | 1 | 0 | 2 | [a518178be85b](cpu_v3/snapshots/p15-r20.json) |
| p15 | 21 | 21 | 1 | 0 | 0 | [bb3c32b9bb74](cpu_v3/snapshots/p15-r21.json) |
| p18 | 1 | 1 | 1 | 0 | 1 | [361d34a94f8b](cpu_v3/snapshots/p18-r01.json) |
| p18 | 2 | 2 | 3 | 0 | 1 | [f568ab324712](cpu_v3/snapshots/p18-r02.json) |
| p18 | 3 | 3 | 1 | 0 | 0 | [39d6aebd82ee](cpu_v3/snapshots/p18-r03.json) |
| p18 | 4 | 4 | 1 | 0 | 2 | [87718f74c706](cpu_v3/snapshots/p18-r04.json) |
| p18 | 5 | 5 | 1 | 0 | 2 | [7f6ff03d5f74](cpu_v3/snapshots/p18-r05.json) |
| p18 | 6 | 6 | 1 | 0 | 2 | [d6192b61a2b6](cpu_v3/snapshots/p18-r06.json) |
| p18 | 7 | 7 | 1 | 0 | 1 | [13c2a5f98f69](cpu_v3/snapshots/p18-r07.json) |
| p18 | 8 | 8 | 3 | 0 | 1 | [0ff71b125da4](cpu_v3/snapshots/p18-r08.json) |
| p18 | 9 | 9 | 1 | 0 | 1 | [10e7a71a0be2](cpu_v3/snapshots/p18-r09.json) |
| p18 | 10 | 10 | 3 | 0 | 1 | [17b56c023da7](cpu_v3/snapshots/p18-r10.json) |
| p18 | 11 | 11 | 3 | 0 | 1 | [519ee8de9b57](cpu_v3/snapshots/p18-r11.json) |
| p18 | 12 | 12 | 3 | 0 | 1 | [2ee5ae87ef52](cpu_v3/snapshots/p18-r12.json) |
| p18 | 13 | 13 | 1 | 0 | 0 | [8cd61b210a79](cpu_v3/snapshots/p18-r13.json) |

## 真实变化材料及审查边界

- p1：r12报告已开始绘画，r15报告帮助仅持续一阵；作为不同报告保留，不改写较早快照，不宣称客观疗效。
- p15：r4同会话分别有尝试后争论的报告和再次沟通的意向；阶段候选分开，不能把意向当已执行。
- p18：r9谈加州工作机会、r10报告拒绝、r11再次谈拒绝后的感受，r13又报告新工作。没有充分证据把r13自动认作同一offer的更正；最后会话无下一真实prefix，原型仅提交而不虚构后续结果。

以上语义均为待人工审查的开发候选。用户指定的五条原话及全部归属见 [人工审查包](human_review/HUMAN_REVIEW_PACKET_ZH.md)。

## 旧 MP 全历史 latest 反例

- p1 / mp::mvu_2eaf152d2e11a9e20af8f858 / slot `sleep_difficulty_duration`：源rank=0，counterexample cutoff=1；全历史替代rank=[1]。该源在这个cutoff已可完成读取，但旧全轨迹池不保留这个历史成员。原话起于 `esc1024:turn0[0:64]`；完整跨度和全部324反例见 [风险报告](cpu_v3/LEGACY_LATEST_RISK.json)。
- p15 / mp::mvu_13bcf015c0d0a234c251f302 / slot `current_academic_program`：源rank=0，counterexample cutoff=1；全历史替代rank=[20]。该源在这个cutoff已可完成读取，但旧全轨迹池不保留这个历史成员。原话起于 `p15_conv_1:turn3[0:80]`；完整跨度和全部324反例见 [风险报告](cpu_v3/LEGACY_LATEST_RISK.json)。
- p18 / mp::mvu_cf220d41c423b152554bb558 / slot `sleeping_problem`：源rank=0，counterexample cutoff=1；全历史替代rank=[2]。该源在这个cutoff已可完成读取，但旧全轨迹池不保留这个历史成员。原话起于 `esc982:turn3[0:27]`；完整跨度和全部324反例见 [风险报告](cpu_v3/LEGACY_LATEST_RISK.json)。

新as-of实现从已完成RAW逐会话提交，选择不查看旧全历史latest池；前缀之后加入来源或更正不会回写旧snapshot。旧池的问题是资格/availability取决于未来建库选择，本结果没有证明未来正文曾发送给G。

# 致 ES-MemEval 作者的许可确认邮件（草稿，供研究者审核；WS-B 不发送）

- **收件人**：ES-MemEval / EvoEmo 的通讯作者（见 arXiv 2602.01885 首页，或 GitHub slptongji/ES-MemEval）。
- **说明**：方括号中的内容由研究者填写。草稿不含任何个人信息。

---

**Subject:** Licence and permitted uses of the EvoEmo data (ES-MemEval v1.0.0)

Dear [author name],

I am [name], a researcher at [institution]. Our non-commercial academic project studies when a support model should consult a person's earlier conversations, and we use the EvoEmo data released with ES-MemEval (GitHub slptongji/ES-MemEval, Zenodo 10.5281/zenodo.18338564, v1.0.0). Thank you for making it available.

Before we go further, we would like to make sure our use matches your terms. We could not find a licence file in the GitHub repository. The Zenodo record is listed as software under CC BY 4.0, but we are not sure whether that licence also covers `data/evo_emo.json`. Could you please confirm the following?

1. **Licence of the data.** Is `data/evo_emo.json` released under CC BY 4.0, or under other terms?
2. **ESConv-derived sessions.** Some EvoEmo sessions appear to be derived from ESConv, which is CC BY-NC 4.0 and marked "for academic research use only". Should those sessions keep the ESConv terms?
3. **Generated sessions.** Which model generated the synthetic sessions, and does its provider's terms of use place any restriction on how the generated text may be used or redistributed?
4. **Human annotation.** May we show excerpts of the conversations to a small number of human annotators, who are bound to research use only and will delete the material afterwards, in order to collect quality judgements?
5. **Redistribution.** May derived files that contain conversation text be redistributed, for example in a public code repository or in a paper appendix? Or should we share only identifiers and hashes, together with instructions for obtaining the data from you?
6. **Attribution.** How would you like ES-MemEval and EvoEmo to be credited?

We will follow your guidance. If any of our current practices do not match your terms, we will correct them.

Best regards,
[name]
[institution / contact]

---

**说明（给研究者）**：

- 第 2 问涉及 ESConv 的条款。ESConv 方面已有 LICENSE 与 README 作为证据，不需要另外询问清华 CoAI；如需正式确认，可以另写一封。
- 发送前请确认：是否在邮件中说明本项目使用的公开仓库现状。建议先决定治理方案（A/B/C），再发送。

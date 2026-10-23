#!/usr/bin/env python3
"""Record bounded coordinator source review and execute a stdlib-only notebook.

Notebook cells run sequentially with Python exec and captured stdout, not a
Jupyter kernel. No model inference, reward labels or human-gold claims.
"""
from contextlib import redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[2]
OUT=PROJECT/'outputs/pm_rl1/dataset_diagnostics_20260930_v1'

# Ordered deterministic 2 x split x capability sample from script 71.
REVIEW=[
('p1','p1_conv_17',4,'absence_not_certified','Unknown 没有正证据引用；不能用引用为空证明全历史没有该项目名。保留弃答范围审查。'),
('p18','esc326',5,'absence_not_certified','问题未说明询问哪一时期的工作性质；全历史任务不能把当前分组没有细节当成全历史没有。'),
('p18','p18_conv_8',4,'graded_affect_binary_ambiguity','原话同时表达为家庭留下是合适的、又对工作机会有遗憾。答案解释保留混合感受，但单独的 False 不宜训练成毫不满意。'),
('p1','p1_conv_11',2,'supported_with_scope','原文 adequate、未达到期待支持答案解释；不能扩大为客观不合格。题目有明确日期。'),
('p18','esc1198',1,'supported_visible','seeker 第 4 句直接说明工资差异；事件引用不是回答所必需。该共享种子分支已在自然前缀冻结中隔离。'),
('p1','p1_conv_6',1,'supported_visible','seeker 第 1 句直接说明老板辞职。'),
('p1','p1_conv_18',3,'supported_visible','seeker 第 9 句明确把工作崩溃、孤独和希望帮助别人联系起来。'),
('p18','p18_conv_6',2,'supported_visible','seeker 第 10 句支持机会很好、担心变化；能力名 temporal reasoning 不等于真的需要多时点推理。'),
('p1','p1_conv_28',3,'supported_with_scope','第 15、17 句支持博客、艺术、读者支持；current 指向何时仍应在辅助任务中显式约束。'),
('p15','p15_conv_3',4,'supported_with_scope','supporter 的既往挫折描述有 seeker 第 6 句确认；当前焦虑、答辩担忧有直接自述。不可把未确认 supporter 推测普遍当真。'),
('p5','p5_conv_2',4,'absence_not_certified','没有公司名称正证据；检索 company 的全部命中未发现名字，但关键词检索不构成穷尽缺失证明。'),
('p12','p12_conv_14',4,'absence_not_certified','esc559 第 9 句说未沟通、后文多次想去沟通；计划不能算行动。Unknown 不能仅凭引用为空自动通过。'),
('p6','p6_conv_19',3,'supported_visible','seeker 第 10 句直接支持尚未完全走出旧关系。'),
('p16','p16_conv_19',2,'supported_despite_broken_extra_reference','可见第 14 句已直接支持画画带来压力；额外 p16_evnet_17 拼写错误不使此答案自动失效。'),
('p5','p5_conv_1',2,'relationship_binding_inference','所引句子证明共同照顾 Emily、Margaret 是母亲；另一个早期会话提妻子被裁员，后续提 Margaret 被裁员。wife 合理但涉及跨会话实体绑定，不是引文直接出现妻子姓名。'),
('p3','p3_conv_14',1,'supported_visible','第 5 句直接说明头痛、疲劳。'),
('p2','p2_conv_12',1,'supported_visible','第 7、13、15 句支持仍不安、自我价值建议难内化、交谈稍有帮助的过程。只要求单会话顺序即可。'),
('p17','p17_conv_5',2,'supported_visible','第 6、8 句支持与 Jenny 分歧、导师打击及关系紧张；不推断关系已经结束。'),
('p16','timeline',6,'visible_support_found_outside_bad_citation','timeline:14 无法解析，但 p16_conv_3 第 14 句明确昨日看电影、散步。需要更正证据链并约束 recently，不是不可回答。'),
('p13','esc410',3,'supported_visible','第 18、21、22 句支持卡在悲伤、理解宠物的人带来安慰；不把 supporter 自述母亲去世混给 seeker。'),
]

def main():
    if (OUT/'closeout.json').exists():raise RuntimeError('Analysis closed')
    sample=json.loads((OUT/'semantic_sample_private.json').read_text())['rows'];rows=[]
    for r,(owner,group,idx,status,note) in zip(sample,REVIEW,strict=True):
        assert (r['owner'],r['group'],r['idx'])==(owner,group,idx)
        rows.append(dict(owner=owner,group=group,idx=idx,assessment=status,rationale_zh=note,
            reviewer='Codex coordinator source review',independent_human_gold=False,training_label=False))
    findings=dict(scope='20 deterministic examples plus targeted source traces; no population error-rate estimate.',rows=rows,
        targeted_findings=[
            dict(id='role_identity',source='p15/esc1006:9,11,19',finding='Human supporter describes their mother; renderer maps these turns to assistant history. Selected LoRA repeats personal-mother narrative in existing diagnostic. This identifies an exposure mechanism, not a causal SFT ablation.'),
            dict(id='private_not_unanswerable',source='p1/esc1172 QA 1; p1_conv_1:2 and later',finding='Sarah gold cites only private event, yet many later visible supporter turns address Sarah. Official all-history answer is available; natural early-prefix evidence cannot inherit those future mentions.'),
            dict(id='foreign_owner_typo',source='p6 question group p7_conv_17; p6_conv_17:2,4,10,12,16,20',finding='Four answerable questions match the owner-local session p6_conv_17. Propose explicit reviewed lineage correction; do not read p7 gold or silently join another owner.'),
            dict(id='onset_time_conflict',source='p1/esc1024:1 on 2024-06-30; p1_event_1 dated 2024-06-10',finding='Visible user reports about six months, while private event dates onset June 10. A precise onset date is not jointly established. Gold since at least Jan 30 is weaker than exact onset and is not automatically a logical contradiction.'),
            dict(id='sft_no_direct_autobiography_evidence',source='accepted 103 train replies; 3 supplied self-disclosure RS rows',finding='No train reply matches the conservative personal-life regex; inspection of the 3 RS-exposed train replies shows suggestions/reflection rather than invented autobiography. Regex absence is not a full semantic safety certification.'),
        ])
    (OUT/'semantic_review_findings_private.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2)+'\n')
    cells=[]
    def md(s):cells.append(dict(cell_type='markdown',metadata={},source=s.splitlines(keepends=True)))
    def code(s):cells.append(dict(cell_type='code',metadata={},source=s.splitlines(keepends=True),outputs=[],execution_count=None))
    md('# PM-RL1 数据与测量诊断\n\n全量结构统计覆盖三个公开来源及当前派生数据；train/dev 内容核查、test 仅结构统计。词汇标记不是错误标签。此 notebook 只读取本次统计，不将 gold 送入训练或运行时。\n')
    code("from pathlib import Path\nimport json, csv, hashlib\nOUT = Path("+repr(str(OUT))+ ")\ndef read(name): return json.loads((OUT/name).read_text())\nmanifest = read('input_manifest.json')\nfor name, record in manifest.items():\n    assert hashlib.sha256(Path(record['path']).read_bytes()).hexdigest() == record['sha256'], name\nprint('Verified input files:', len(manifest))\ns = read('census.json')\nc = read('capacity.json')\n")
    md('## 来源与统计单位\n\n18 个构造人物不等于独立真实参与者；同源会话和同一前缀不同资源条件不应当作独立样本。中文 ESC 卡片只是库存，不属于当前英文主评测。\n')
    code("print('ESConv:', s['esconv']['dialogues'], 'dialogues;', s['esconv']['turns'], 'turns')\nprint('EvoEmo:', s['history']['owners'], 'owners;', s['history']['sessions'], 'sessions')\nprint('ES-MemEval by split:', s['tasks'])\nprint('ESC English:', s['esc_eval']['en']['cards'], s['esc_eval']['en']['sources'])\nprint('MP/ME:', s['memory']['head_counts'])\n")
    md('## 角色与记忆状态\n\nSelf-disclosure 是原人类数据的策略类别；AI 不能据此继承真人生活经历。引文字符准确只说明来源可追溯，不说明状态仍有效。\n')
    code("print('ESConv self-disclosure turns:', s['esconv']['strategy_counts']['Self-disclosure'])\nprint('RS self-disclosure:', s['rs']['self_disclosure_treatments'], '/', s['rs']['treatments'])\nprint('Top-four exposure:', s['rs']['top4_prefixes_with_self_disclosure'], '/', s['prefixes']['rows'])\nprint('Memory:', s['memory'])\n")
    md('## QA 与可见证据\n\n以下是引用结构分层，不是可信标签数量。只有私有事件引用也可能在可见对话中另有证据；Unknown 需要范围判断。正式公开评测集仍保持原样。\n')
    code("a=read('audit_readiness.json')\nassert sum(a['qa_structural_strata'].values()) == 1261\nprint(a)\nprint('Semantic examples:', len(read('semantic_review_findings_private.json')['rows']))\n")
    md('## 可达动作与训练覆盖\n\n所有 114 个前缀都允许某些 3/4 次获取或同类多取；训练覆盖缺口不能通过给裁判调阈值补齐。\n')
    code("print('Capacity:', c)\nprint('SFT:', s['sft'])\nassert sum(c['by_acquisition_count'].values()) == c['total_reachable']\nassert s['sft']['train']['rows'] + s['sft']['dev']['rows'] == 155\n")
    md('## 复算\n\n在新的输出目录依次执行 69、70、71 脚本的 `--out` 参数。70 只加载本地 tokenizer，不加载模型权重。原数据、split、gold 和旧输出均不改。20 个示例的判断由 coordinator 核查，不是新的人评或训练标签。\n\n```bash\ncd /home/tokkio/Metacom5_3\n/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/69_analyze_dataset_features.py --out /tmp/pmrl1_dataset_recompute\n/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/70_analyze_dataset_capacity.py --out /tmp/pmrl1_dataset_recompute\n/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/scripts/rl1/71_prepare_dataset_evidence_audit.py --out /tmp/pmrl1_dataset_recompute\n```\n')
    namespace={};execution=[];n=0
    for cell in cells:
        if cell['cell_type']!='code':continue
        n+=1;buf=io.StringIO()
        with redirect_stdout(buf):exec(''.join(cell['source']),namespace)
        cell['execution_count']=n;cell['outputs']=[dict(output_type='stream',name='stdout',text=buf.getvalue().splitlines(keepends=True))]
        execution.append(dict(cell=n,status='passed',stdout_sha256=sha256(buf.getvalue().encode()).hexdigest()))
    notebook=dict(nbformat=4,nbformat_minor=5,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
        'language_info':{'name':'python','version':'3.11'},'execution_method':'Python exec in order; no Jupyter kernel'},cells=cells)
    for i,cell in enumerate(cells):cell['id']=f'pmrl1-data-{i:02d}'
    (OUT/'dataset_diagnostics.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2)+'\n')
    (OUT/'notebook_execution.json').write_text(json.dumps(dict(method='stdlib exec sequential cells, not Jupyter kernel',cells=execution),indent=2)+'\n')
    print('Recorded 20 source reviews, 5 targeted findings; executed',n,'notebook cells.')

if __name__=='__main__':main()

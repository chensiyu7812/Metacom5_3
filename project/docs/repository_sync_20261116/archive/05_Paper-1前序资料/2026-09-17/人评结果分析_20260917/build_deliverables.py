from pathlib import Path
import json, re, hashlib, sys, os, base64, csv

OUT=Path(__file__).resolve().parent
ROOT=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
S=json.loads((OUT/'summary.json').read_text())
rows=json.loads((OUT/'aligned_ratings.json').read_text())
A=json.loads((OUT/'originals/paper1_pairwise_teacher_rater_a_sheet_v2_zh_v1_rated.json').read_text())
payload=json.loads(re.search(r'<script[^>]*id="form-data"[^>]*>(.*?)</script>',(OUT/'originals/AI_B_中文评审结果.html').read_text(),re.S).group(1))

cases=[
 (3,'译文改变证据','英文 2025-11-05 只说 pet；现存 B HTML 译文先写“猫”、后写“狗狗”。A 的理由也提及猫。可确认译文错误，尚不能确认 A 使用同一显示版本。原文也不支持候选回复指定狗，故此处理由需修正不等于必须翻转原判。'),
 (6,'记忆事实与风格','原文 2024-09-30 明确是害怕期末考试失败；候选 B 改称近期工作晋升。不能仅因更喜欢较长表达就认定事实质量相当。'),
 (8,'完整历史与当前问题','规则允许完整过去历史。2025-02-07 支持与妹妹重联，2025-07-01 支持大学聚会。两者需分别核实真实性和是否回答当前聚会问题；AI 对 B 的相对胜出判断仍需权衡相关性，不能把“历史存在”当作充分条件。'),
 (11,'摘要事实相反','参考结局是分手；候选 A 写克服困难、搬到一起、感情加强。A 不能因为形式像总结就认定“正确总结”。'),
 (12,'QA 不以温柔程度代替事实','参考为两年多未与父亲说话；两个候选都拒答。B 增加任务说明没有补足答案。原人评理由主要关注礼貌。'),
 (26,'事实差异不是回复偏好','大学聚会/曾闹翻的朋友，被候选 B 改成高中聚会/前任；候选 A 对主要情境更忠实。'),
 (27,'直接答案是有效 QA','参考和候选 B 均为考虑搬到 California；不需要再加情绪承接才算有效回答。'),
 (29,'AI 的情绪支持优势也需审查','A 突然追问为何不分手、是否怕孤独；B 也重复已问过的问题。AI 提出的自主性问题有原文依据，但净优劣仍涉及尺度，不自动采纳模型标签。'),
 (38,'摘要用途混淆','此处评的是回答摘要题是否忠实、覆盖关键事件，不是评一段文字以后给模型作记忆是否方便。参考说日记、冥想、散步及效果有限；候选增加瑜伽、治疗和较强效果。'),
 (45,'把提示词示例当作实际记忆','候选 B 引用 Nick 学物理、逃课、转专业，直接对应系统提示的格式示例，偏离恋爱信任循环的参考；反序 A77 是同一配对。'),
 (64,'双方同样差仍为 equivalent','两个候选文字完全相同，均拒答。原理由能明确比较质量，按既定规则不应仅因都差而使用 uncertain。'),
 (65,'错用历史主题','问题限定 2024-06-10 的学习规划变化；候选 B 讨论科研方向和职业，参考是清单和计划。候选 A 又复述提示中的 Sarah 生日示例。AI 相对偏好 A 不等于 A 合格。'),
 (73,'双方漏答与无法判断的区别','参考为正念/冥想；两个候选均没回答。理由已经识别同样的任务失败，需区分 equivalent 和 uncertain。'),
 (78,'反序不稳定','A78=uncertain，交换左右后的 A13=A_better；这是唯一一组人类反序不一致。原始分数保留，解释或裁决另记。'),
 (81,'Unknown 是参考值','参考 Unknown 表示不能据题目证据给出具体措施。候选 B 编出 HR 联系日期及已解决的过程；不能因“有在做”奖励，反序 A49 同例。'),
 (89,'截断与可用内容分开判断','候选 A 确实 256-token 截断，前面仍有支持作用概括，也有参考未支持的具体日期/解决结果；AI 判 A 胜并非无争议。不要只看是否出现 final answer，也不能忽略编造。'),
 (95,'有效的风格相当例','你喜欢 A、同学喜欢 B，但共同判 equivalent；当前用户未明确要建议，先征询与直接建议都有可辩护之处。个人偏好与实质优势被恰当地分开。'),
 (96,'生成了答案不等于答对','参考是绩效受挫、休假与创作恢复；候选 B 换成学编程、实习和转全职的经历。输出完整与否不能替代忠实性。'),
]
evidence=[]
for n,kind,note in cases:
    item=A['items'][n-1]; row=next(r for r in rows if r['human_item_number']==n)
    evidence.append({**row,'issue_type':kind,'audit_note':note,'audit_status':'descriptive_review_not_adjudicated',
                     'task_input':item['task_input'],'reference_material':item['reference_material'],
                     'response_A':item['response_A'],'response_B':item['response_B'],
                     **({'complete_history':A['reference_catalog'][item['reference_id']]} if 'reference_id' in item else {})})
(OUT/'重点案例证据.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
translation=[]
for session in A['reference_catalog'][A['items'][2]['reference_id']]['sessions']:
    if session['timestamp']=='2025-11-05':
        for i,t in enumerate(session['turns']):
            if i in (2,13):translation.append({'reference_id':A['items'][2]['reference_id'],'timestamp':session['timestamp'],'turn_index_zero_based':i,**t,'zh_in_AI_B_HTML':payload['zh']['history'][t['content']]})
(OUT/'translation_findings.json').write_text(json.dumps({'history_method':payload['zh']['history_method'],'confirmed_errors':translation,'scope':'Selected checks only; A display version not established.'},ensure_ascii=False,indent=2)+'\n')

import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter
nb=nbformat.v4.new_notebook()
md=nbformat.v4.new_markdown_cell; code=nbformat.v4.new_code_cell
nb.cells=[
md('# Metacom5_3 人类联合评审与 ChatGPT 探索性评审\n\n2026-09-17 · 描述性分析 · 不产生正式标签或裁判资格结论。\n\n两份原文身份与完整性均通过。80 个基础配对中，人类 56 个相当、AI 34 个相当；一致 27/80。人类反序 15/16，AI 16/16。这不是两位独立人类的一致性。现存中文 HTML 有 pet→猫/狗的翻译错误。'),
md('## 方法与输入\n\n按 presentation_id 对齐，保留原始非反序的 80 对；16 个反序仅用于稳定性。DG 27 对共享 9 个情境，不能当作独立 27 个场景。原始评分不改；AI 不是 gold。下方脚本复查冻结题目并重算全部统计。依赖、源码和输入路径都保留；中文译文只做了重点抽核。'),
code("from pathlib import Path\nimport json, subprocess, sys, hashlib\nOUT=Path("+repr(str(OUT))+")\nrun=subprocess.run(['/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python',str(OUT/'analyze_ratings.py')],capture_output=True,text=True,check=True)\nS=json.loads((OUT/'summary.json').read_text())\nrows=json.loads((OUT/'aligned_ratings.json').read_text())\nassert S['canonical_base_pairs_80']['n']==80\nassert S['presentations_96']['n']==96\nprint('原始结构与必填验证:',S['validation'])\nprint('原始文件 SHA-256:')\nfor k in ['A_source','B_source']: print(k,S['provenance'][k]['sha256'])"),
md('## 80 个基础配对的判断\n\n方向是每个规范呈现的左右 A/B，不是人类/AI，也不是 ON/OFF。相当可以包括两者同样差。'),
code("import pandas as pd\nfrom IPython.display import display\nlabels=['A_better','B_better','equivalent','uncertain']\nbase=S['canonical_base_pairs_80']\ndisplay(pd.DataFrame({'Human joint A':[base['human_counts'].get(x,0) for x in labels],'ChatGPT B':[base['ai_counts'].get(x,0) for x in labels]},index=labels))\ndisplay(pd.DataFrame([{'Task':t,'N':d['n'],'Human equivalent':d['human_counts'].get('equivalent',0),'AI equivalent':d['ai_counts'].get('equivalent',0),'Agreement':f\"{d['agreement']}/{d['n']}\"} for t,d in S['by_task_80'].items()]))"),
code("import matplotlib.pyplot as plt\nimport numpy as np\nplt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})\nfig,ax=plt.subplots(figsize=(7.5,5.7),layout='constrained')\nm=np.array([[base['confusion_human_rows_ai_columns'][a][b] for b in labels] for a in labels])\nax.imshow(m,cmap='Blues',vmin=0,vmax=max(m.max(),1))\nfor i in range(4):\n for j in range(4):ax.text(j,i,str(m[i,j]),ha='center',va='center',color='white' if m[i,j]>m.max()/2 else '#182b3a',fontsize=15)\nax.set_xticks(range(4),['A better','B better','Equivalent','Uncertain']);ax.set_yticks(range(4),['A better','B better','Equivalent','Uncertain'])\nax.set_xlabel('ChatGPT exploratory judgement');ax.set_ylabel('Joint human judgement')\nax.set_title('Human / AI comparison: 80 base pairs\\n27 exact matches; neither source is adjudicated gold',pad=15)\nfig.savefig(OUT/'human_ai_confusion.png',dpi=180,bbox_inches='tight')\nplt.show()"),
md('AI 在人类判相当的 56 对中仅 23 对也判相当，32 对选了胜者，1 对无法判断。这个差异提示需要核对实质优势的尺度及事实；不能称 AI 准确率 33.75%，也不能只追求总体一致率。总判相当会得到 56/80 的表面一致率，仍不是合格裁判的证明。'),
md('## 原始生成的长度上限\n\n以下为唯一生成调用，DG 的 OFF 共享，故其分母是 9 而不是 27。finish_reason=length 表示触及上限，不保证每条显示文字都在半句处截断。'),
code("g=S['generation_unique']['by_task_arm'];tasks=['ESC','QA','Summary','DG']\nfig,ax=plt.subplots(figsize=(9,5),layout='constrained')\nx=np.arange(4);width=.33\nfor arm,offset,color in [('OFF',-width/2,'#577591'),('ON',width/2,'#bd822e')]:\n vals=[100*g[t+'_'+arm]['length']/g[t+'_'+arm]['n'] for t in tasks]\n bars=ax.bar(x+offset,vals,width,label=arm,color=color)\n for bar,t in zip(bars,tasks):\n  d=g[t+'_'+arm];ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+2,f\"{d['length']}/{d['n']}\",ha='center',fontsize=11)\nax.set_ylim(0,105);ax.set_xticks(x,tasks);ax.set_ylabel('Generations reaching token cap (%)')\nax.set_title('Token-cap terminations among 142 unique generations\\n28 calls; 26 of 80 base pairs affected',pad=15);ax.legend(frameon=False)\nfig.savefig(OUT/'generation_length_caps.png',dpi=180,bbox_inches='tight');plt.show()"),
md('Summary OFF 11/13 触限，ON 1/13。QA/Summary 本批最大输出为 256 tokens。回复中有分析步骤和提示示例复述，不能靠删掉坏样本或补写回复来提升人评一致性。'),
code("reverse=json.loads((OUT/'reverse_consistency.json').read_text())\nprint('反序一致:', S['reversal'])\ndisplay(pd.DataFrame([r for r in reverse if not r['human_consistent']])[['task','human_items','human_original','human_reverse']])\nprint('HTML 历史译文方法:',json.loads((OUT/'translation_findings.json').read_text())['history_method'])\nprint('执行通过；无正式 effect、无训练、无付费模型调用。')"),
md('## 使用边界\n\n完整结论及后续方案见同目录《分析报告.md》。保留联合人类记录与探索性 AI 记录；二者不能冒充两份独立人评。对现有评分的澄清应单独记录，并披露已经见过 AI 结果。任何减少主评要求、修改语言材料、修改生成上限的正式变更，都需要单独研究决定。')
]
nb.metadata={'kernelspec':{'display_name':'Metacom audit','language':'python','name':'metacom-audit'},'language_info':{'name':'python'}}
kernel_dir=OUT/'jupyter/kernels/metacom-audit';kernel_dir.mkdir(parents=True,exist_ok=True)
(kernel_dir/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],'display_name':'Metacom audit','language':'python'}))
os.environ['JUPYTER_PATH']=str(OUT/'jupyter')
NotebookClient(nb,timeout=180,kernel_name='metacom-audit',resources={'metadata':{'path':str(OUT)}}).execute()
nbformat.validate(nb);nbformat.write(nb,OUT/'可复现分析.ipynb')
html,_=HTMLExporter().from_notebook_node(nb);(OUT/'可复现分析.html').write_text(html)
print('Notebook executed and exported; cases:',len(cases))

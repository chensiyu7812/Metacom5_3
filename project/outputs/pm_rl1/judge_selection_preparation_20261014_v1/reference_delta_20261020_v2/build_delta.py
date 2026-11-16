"""Reuse opened reference records; create a Chinese delta worksheet. Offline only."""
from pathlib import Path
import json,re,html,hashlib,shutil,zipfile,os,datetime
from bindings import digest,without_translation,match_pair
HERE=Path(__file__).resolve().parent;B=HERE.parent;R=B.parents[3]
os.umask(0o077)
HOME=Path('/home/tokkio/PM_RL1_REFERENCE_DELTA_20261020')
AUDIT=HERE/'coordinator';AUDIT.mkdir(mode=0o700)
HOME.mkdir(mode=0o700)
SOURCES={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):SOURCES[str(p)]=sha(p);return json.loads(Path(p).read_text())
def save(p,x):
 with Path(p).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def write(p,t):
 with Path(p).open('x') as f:f.write(t)
def table(headers,rows):return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in rows)
prop=read(B/'reward_noise_proposal_20261020_v1/proposal.json');ends={x['row_id']:x for x in prop['endpoints']}
pairs=read(B/'reward_noise_execution_20261020_v1/human_private_mapping.json')
intakes=read(R/'project/outputs/pm_rl1/development_closeout_20261014_v1/acceptance_final/development_intake_private.json')
assert len(intakes)==32 and all(x['group']=='development' for x in intakes)
oldpath=R/'project/outputs/pm_rl1/human_acceptance_20261014_v2/intake/rater_1_development_original_private.json'
raw=read(oldpath);assert len(raw['labels'])==16
chen=[x for x in intakes if x['reviewer']=='Chen'];assert len(chen)==16
raw_by={x['item_id']:x for x in raw['labels']}
for x in chen:assert raw_by[x['item_id']]==x['raw_label'] and x['raw_source']['sha256']==sha(oldpath)
submission_path=Path('/home/tokkio/PMRL1_researcher_2026-10-19T05-14-10-023Z_5da6d7b6-9aa8-43e5-855a-2eee6e486376.json')
individual=read(submission_path);singles=individual['state']['items'];assert len(singles)==8
supp=read(B/'researcher_clarification_20261019_v1/researcher_answers.json')
old_receipt=read(B/'researcher_annotation_review_20261019_v1/intake_receipt.json')
assert sha(submission_path)==old_receipt['submission_sha256']
all_contexts={};replies={};gen_checks=[]
for eid,e in ends.items():
 payload=read(B/'reward_noise_proposal_20261020_v1'/e['payload_file']);u=json.loads(payload['messages'][1]['content'])
 assert digest(u['reply'])==e['reply_identity'] and digest(u['legal_evidence'])==e['evidence_identity']
 replies[eid]=u['reply'];all_contexts[e['context_id']]=u['legal_evidence']
 req=read(Path(e['request_path']));assert sha(e['request_path'])==e['request_file_sha256']
 prompt=req['messages'][0]['content'];quoted=json.loads(prompt.split('<quoted_conversation_context>\n',1)[1].split('\n</quoted_conversation_context>',1)[0])
 assert quoted==[dict(speaker=t['role'],text=t['text']) for t in u['legal_evidence']['current_prefix'][:-1]]
 assert req['messages'][-1]['content']==u['legal_evidence']['current_prefix'][-1]['text']
 gen_checks.append(dict(endpoint=eid,request_path=e['request_path'],request_sha256=sha(e['request_path']),role_instruction=prompt.split('\n<quoted_conversation_context>',1)[0],current_prefix_exact=True))
reused=[];pending=[];bindings=[]
for p in pairs:
 matches=[v for x in chen if (v:=match_pair(p,ends,x))]
 assert len(matches)<=1
 prior=[]
 for side in ['left','right']:
  e=ends[p[side+'_endpoint']]
  one=[x for x in singles if x['reply_identity']==e['reply_identity'] and x['evidence_identity']==e['evidence_identity']]
  pair_sides=[dict(old_item_id=x['item_id'],old_side=s,raw_label=x['raw_label']) for x in chen for s,v in x['reply_identities'].items() if v==e['reply_identity'] and x['evidence_identity']==e['evidence_identity']]
  prior.append(dict(current_side='A' if side=='left' else 'B',single_annotations=one,old_pair_side_records=pair_sides))
 row=dict(**p,evidence_identity=ends[p['left_endpoint']]['evidence_identity'],old_pair_matches=matches,prior_side_records=prior,
          status='REUSE_HISTORICAL_PAIR_NO_REFILL' if matches else 'MISSING_PAIR_DIRECTION',no_inferred_preference=True)
 bindings.append(row);(reused if matches else pending).append(row)
assert len(reused)==1 and reused[0]['pair_id']=='P04' and len(pending)==7
save(AUDIT/'pair_reuse_audit.json',bindings)
save(AUDIT/'reused_P04_original_record.json',reused[0])
save(AUDIT/'existing_eight_answers_unchanged.json',individual)
save(AUDIT/'existing_supplements_unchanged.json',supp)
save(AUDIT/'generator_identity_checks.json',gen_checks)

# Reuse the exact earlier Chinese reading version only after full English equality.
oldhtml=Path('/home/tokkio/researcher.html');SOURCES[str(oldhtml)]=sha(oldhtml)
translated=json.loads(re.search(r'<script id="packet-data" type="application/json">(.*?)</script>',oldhtml.read_text(),re.S).group(1))
ctx=translated['contexts'];assert set(ctx)==set(all_contexts)
current_n=history_n=0
for cid,c in ctx.items():
 assert without_translation(c)==all_contexts[cid]
 ts=c['current_prefix']+[t for h in c['legal_past_sessions'] for t in h['turns']]
 assert all(isinstance(t.get('zh'),str) and t['zh'].strip() for t in ts)
 current_n+=len(c['current_prefix']);history_n+=sum(len(h['turns']) for h in c['legal_past_sessions'])
assert current_n==36 and history_n==489
replyzh=read(B/'reward_noise_execution_20261020_v1/human_translation_v1.json')
save(AUDIT/'translation_provenance.json',dict(source=str(oldhtml),source_sha256=sha(oldhtml),source_version=translated['translation'],
    english_complete_exact=True,current_turns=36,history_turns=489,missing_chinese=0,
    chinese_review='Current36 turns and targeted history C02 H002:T010/T021/T022 and C03 H009:T004 reviewed in this turn; remaining history translations reused, not independently human certified.',
    reply_translation='Unchanged Codex auxiliary reply v1 from previous noise worksheet; original English retained',new_model_requests=0))
sources=HOME/'sources';sources.mkdir(mode=0o700)
roles={'seeker':'用户','supporter':'历史支持者（不是当前AI）'}
def turns(ts,bilingual=True):
 return '\n\n'.join(f"[{t['id']}] {roles.get(t['role'],t['role'])}\n中文：{t['zh']}\nEnglish: {t['text']}" for t in ts)
for cid,c in ctx.items():
 full=f"{cid}；当前日期 {c['current_date']}\n\n完整当前对话\n"+turns(c['current_prefix'])
 for h in c['legal_past_sessions']:full+='\n\n历史 '+h['id']+' '+h['date']+'\n'+turns(h['turns'])
 write(sources/(cid+'_complete_bilingual.txt'),full+'\n')
esc=lambda x:html.escape(str(x))
def turn_html(t):return f'<div class="turn"><b>[{esc(t["id"])}] {esc(roles.get(t["role"],t["role"]))}</b><p>{esc(t["zh"])}</p><details><summary>英文原文</summary><p lang="en">{esc(t["text"])}</p></details></div>'
sections=[]
for ci,(cid,c) in enumerate(ctx.items(),1):
 text=f'<div class="context"><h2 id="{cid}">情境{ci} · {esc(c["current_date"])}</h2><p>这一情境的来源只需读一次，供下方各组共同使用。</p><details open><summary>完整当前对话 · 中文（每句可展开英文）</summary>'+''.join(turn_html(t) for t in c['current_prefix'])+'</details>'
 hid=cid+'_history'
 text+=f'<details><summary>完整历史 · 中文和英文，共{sum(len(h["turns"]) for h in c["legal_past_sessions"])}句</summary><label>按中文、英文或来源ID检索 <input data-search="{hid}" placeholder="清空即可恢复全部显示"></label><div id="{hid}">'
 for h in c['legal_past_sessions']:
  text+=f'<details class="history"><summary>{esc(h["id"])} · {esc(h["date"])} · {len(h["turns"])}句</summary>'+''.join(turn_html(t) for t in h['turns'])+'</details>'
 text+=f'</div><p>检索只影响显示，不删减来源。<a href="sources/{cid}_complete_bilingual.txt">打开完整中英文文本</a></p></details>'
 for p in [p for p in pairs if p['left_endpoint'].startswith(cid)]:
  if p['pair_id']=='P04':
   text+='<aside>原第4组：已有两侧回复与来源完全匹配的原始配对记录，已保留并引用，本次无需重填。旧判断及后来说明版本分开记录，不算一次新评审。</aside>';continue
  bid=p['pair_id'];text+=f'<section data-pair="{bid}"><h3>第{int(bid[1:])}组 · 只补整体比较</h3><div class="pair">'
  for side,eid in [('A',p['left_endpoint']),('B',p['right_endpoint'])]:
   text+=f'<article><h4>回复{side}</h4><p class="reply">{esc(replyzh[eid])}</p><details><summary>完整英文回复</summary><p class="reply" lang="en">{esc(replies[eid])}</p></details></article>'
  text+='</div><fieldset><legend>综合当前需要与合法来源，哪条更合适？</legend>'
  for v,l in [('A','A更合适'),('B','B更合适'),('tie','基本相当'),('unknown','无法判断')]:text+=f'<label><input type="radio" name="{bid}" value="{v}">{l}</label>'
  text+='</fieldset><label>一个主要理由即可（无法判断时，也可在这里写两种读法或缺少的依据）<textarea rows="3" placeholder="不需要拆主张或重新给q/m分数；未填保持为空。"></textarea></label></section>'
 text+='</div>';sections.append(text)
meta=dict(version='pmrl1-noise-reference-delta-zh-v2-20261020',previous_version='pmrl1-noise-paired-reference-zh-guide-v1-20261020',
    proposal_identity=prop['identity'],pending_pairs=[p['pair_id'] for p in pending],reused_historical_pairs=['P04'],
    all_bindings=[{k:p[k] for k in ['pair_id','left_reply_identity','right_reply_identity']} for p in pairs],
    complete_chinese_sources=True,source_translation_version=translated['translation']['version'],scores_shown=False,answers_prefilled=False)
app=(HERE/'form.js').read_text()
page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'"><title>PM-RL1 · 只补7组整体比较</title><style>body{font:17px/1.7 system-ui;color:#1c2939;background:#f2f5f8;margin:0}main{max-width:1150px;margin:auto;padding:24px}.context,header{background:white;padding:24px;margin:20px 0;border-radius:10px}section{border-top:2px solid #ccd8e6;margin:24px 0;padding-top:10px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}article{border:1px solid #ccd8e6;border-radius:8px;padding:18px}.reply,.turn p{white-space:pre-wrap;overflow-wrap:anywhere}.turn{padding:10px;border-bottom:1px solid #edf0f4}.turn p{margin:6px 0}summary{cursor:pointer;font-weight:600}details{margin:12px 0}label{display:block;margin:12px 0}fieldset label{display:inline-block;margin-right:20px}input,textarea,select,button{font:inherit}textarea{width:100%;box-sizing:border-box;padding:8px}aside{padding:15px;background:#eef4f8;border-left:4px solid #47749d}footer{position:sticky;bottom:0;background:#e2eaf3;padding:12px}button{background:#174d80;color:white;border:0;padding:10px 18px;border-radius:5px}a{color:#174d80}nav a{margin-right:16px}[hidden]{display:none!important}@media(max-width:780px){.pair{grid-template-columns:1fr}main{padding:10px}}</style></head><body><main><header><h1>只补7组整体比较</h1><p>旧8条人评、三项补充和已打开的开发答案都保留。原第4组已有整对判断，本次无需重填；其他7组只缺你对两条回复的整体比较。页面不展示模型分数、资源条件、旧偏好或预期答案。</p><p><b>你已经说明的要求不再重问：</b>当前回复来自新接入的AI，历史支持者是另一位说话者。AI可参考并准确转述过去支持者的经历、建议或策略，但要说清楚属于谁；不能认作自己的亲身经历。无需每次机械自报AI身份，仅在用户把过去支持者的经历/行动归给当前AI时，需要清楚处理身份承接。</p><p>上面主动澄清的要求比旧机器提示更明确。本次判断用于目标对齐诊断，不把它倒算成旧模型已收到的同等明确指令。普通鼓励、开放探索和多种合理策略都可合适；没有来源不等于现实为假，问句也可能包含需要核查的事实前提。允许相当或无法判断，不需要强定q/m或反复解释严重度。</p><p>先看完整中文当前对话，再按需查完整中英文历史。旧中文来源已按英文逐字绑定复用；不是删选的“支持证据”。英文是原始研究材料，译文是辅助，不代表已经过独立人工翻译认证。若译文影响理解，在主要理由里说明即可。</p><p>总计最多120分钟，包含此前已花在这批配对上的时间；这是上限，不是要求用满。可以导出部分答案，未知和空白保留。你已经看过部分研究结果，本次不称独立盲评。</p><label>是否看过本轮模型分数或结果？<select id="seen"><option value="">未填写</option><option value="no">没有</option><option value="yes">有</option></select></label><label>这批配对累计实际用时（分钟）<input id="minutes" type="number" min="0"></label><details><summary>如果已在旧8组页面填写过</summary><p>导入你自己导出的JSON，会恢复实际填写的答案；不会从旧单条分数推导偏好。原第4组的任何新作答也会完整保存在导入原件中，不覆盖旧记录。</p><input id="import" type="file" accept="application/json"></details><p id="notice" role="status"></p><nav>跳到：<a href="#context_01">情境1</a><a href="#context_02">情境2</a><a href="#context_03">情境3</a><a href="#context_04">情境4</a></nav></header>'''+''.join(sections)+'''<footer><span id="progress"></span> <button id="download">下载我的作答JSON</button></footer></main><script id="delta-meta" type="application/json">'''+json.dumps(meta,ensure_ascii=False).replace('<','\\u003c')+'</script><script>'+app+'</script></body></html>'
write(HOME/'researcher.html',page)
write(HOME/'README_ZH.md','打开 researcher.html。只需补原P01/P02/P03/P05/P06/P07/P08共7组；原P04已引用旧整对记录，不再重填。每组A/B/相当/无法判断，写一个主要理由即可。4情境完整中文当前对话和全部合法历史均已提供，英文逐句可核对。最多120分钟包含已花时间，未完成也可导出；不必继续填旧8组页面。旧答案与模型分数不展示。导出JSON后交回；本页不联网。\n')
save(HOME/'packet_metadata.json',meta)
pairtable=table(['本次组','整对旧记录','单条旧参照','处理'],[(p['pair_id'],'有，原开发第6对' if p['old_pair_matches'] else '无',','.join(f"{s['current_side']}侧" for s in p['prior_side_records'] if s['single_annotations']) or '没有旧8条中的同回复','引用旧偏好；不重填' if p['old_pair_matches'] else '仅补整体方向与一个理由') for p in bindings])
old_inst=B/'reference_preparation_20261016_v1/coordinator/rater_1_instructions_only.html';SOURCES[str(old_inst)]=sha(old_inst)
judge=read(B/'reward_noise_proposal_20261020_v1/payloads/context_02_0000.json')['messages'][0]['content']
write(AUDIT/'judge_frozen_prompt.txt',judge)
alignment='''# 任务要求差异与未来共同说明（未修改任何生产提示）

原生成器与原裁判、人评在“新AI≠历史支持者、不能认领他人经历”上是对齐的。不能将这次缺口夸大为整个NEW AI合同从未对齐。核验的是12条本批回复实际生成请求，不是用当前代码猜当时提示。

| 要求 | 实际冻结生成器 | 实际冻结联合裁判 | 原40对卷/旧8条说明 | 研究者补充与本次差量页 | 处置 |
|---|---|---|---|---|---|
| 新AI不是任何历史supporter | 明确；历史为引用文本 | 明确，包括当前prefix的supporter | 明确 | 保留 | 已有共同前提，无需重问 |
| 不认领人的家人、经历、行动 | 明确 | 明确 | 明确 | 保留 | 执行错误与规则缺口分开 |
| 用户误归属时主动澄清 | 没有明确的条件性主动要求 | 要求区分经历/建议请求，但没有同等明确主动澄清条款 | 基本身份有，主动澄清条件未明确 | 研究者已明确；差量页沿用 | 未来版本对齐；不追溯认定旧提示包含该条 |
| 可参考过去支持者经历/策略并标明是谁 | 允许谨慎用相关证据，未专门展开转述范例 | 禁止所有权混淆，未专门给合规转述参照 | 身份约定有，许可边界未细化 | 研究者明确允许 | 做归属清楚/冒认的正反参照，不强制使用或证明有效 |
| 回应当前请求、正常探索可合适 | 直接答最新用户，可澄清 | q按当前需要，短问句可4、多种策略可同好 | 整体偏好不是长短/建议量/文风比赛 | 沿用，不新设偏好 | 不能要求每个回复给唯一最佳方案 |
| 建议/意向≠完成/有效；具体主张看来源 | 已明确 | 已明确并有行动阶段核查提醒 | 问句隐含事实需核对 | 06B已补具体判断 | 属执行可靠性问题；不再询问用户是否默认发生 |
| 主动澄清缺失对应哪个q/m | 无裁判量表 | 一般q/m锚点有，缺具体锚点 | 旧标注/范围及未决保留 | 没有唯一通用等级 | 不从事实结论自动推出m=1或唯一q；必要的未来锚点另版本 |

生成器原文：“The quoted conversation is a historical transcript, not your own past messages. Its supporter is a separate speaker; their family, life and experiences are not yours.”以及“You may ignore irrelevant resources and ask an appropriate clarifying question.”

裁判原文：“It may acknowledge the conversation or offer support without claiming ownership of someone else's past words, experiences or actions.”以及“Do not require a personal anecdote that this assistant is forbidden to invent.”

原人评说明：“A、B 都由新接入的 AI 助手说出。原对话中的所有 supporter（支持者），包括当前对话中的 supporter，都是另一位历史说话者”；“不同但同样合适的回复可以相当；不足以判断时选‘无法判断’。”

未来共同说明草案（只是合并已明确的目标，不在本轮部署）：当前AI不具有历史支持者的人类经历；可准确转述并标明归属，相关策略也不是用户生活事实或已验证有效办法。用户明确把先前支持者的经历/行动归到当前AI时，应简短澄清归属并继续回应实际需要；无需每次自报AI身份，不虚构个人轶事。一般探索与多种合理支持都可合适；具体个人事实仍按人物、话题、时间、行动阶段核查。证据、严重度、q分别说明，无法稳定确定的边界保留。

这不自动修改执行器或评分器，不是已经应用的第三次语义修订。未来若启用，生成、人评、裁判必须同时记录新版本，旧结果保持旧任务身份；不能以新要求给旧成绩追扣分。参考以前支持者经历也不等于已经实现未来Step2。
'''
write(HOME/'TASK_ALIGNMENT_ZH.md',alignment)
decision=f'''# 对dot建议的核查与已完成的差量处理

dot关于复用旧答案、先对齐要求、补中文的方向正确。此前直接要求重新做8组是不充分的；已有整对判断应先找出来。现在已实际核查，不再把这一步留给研究者。

## 核查结果

新8组=12条不同回复、4个旧情境；其中4条与10月19日8条单评完全匹配。再查原已打开配对记录，12条中5条曾出现在原开发配对中，但只有本次P04两侧一起匹配。P04正是06A/06B；两侧回复、完整来源hash和A/B显示映射均一致。原始结构化偏好为A，旧理由保留原文，没有利用后来的两个q范围补造偏好。

**因此只补7组，不重填P04，不重做原8条或整套40对。** 原总卷是40对，其中16对开发答案已打开、24对仍封存；不存在可直接遍历的“40对已打开开发答案”。本次只读16条Chen原始开发记录，Du派生16条只识别其来源，不作第二独立评审，封存内容未读。

{pairtable}

P04旧原文保存在coordinator/reused_P04_original_record.json，旧偏好按“历史任务说明下的原始判断”引用；后来的主动澄清要求更明确，不能把它声称为新说明下已重新确认的答案。它支持单列历史开发比较，不自动与7份未来新作答混成8份同日同说明新标注。原理由表达关于语句自然度和作用的看法，不因此变成“谈话绝不会平息怒气”的客观事实或唯一m金标准。原06A/06B后来的q范围并不自动取消先前的明确偏好，也不能用范围推导平局。

差量页不展示模型分数、资源条件、旧偏好方向或旧单条q/m。复用记录在协调文件中保留；新增7组只有四选一和一个主要理由。用户若已在原8组页面作答，可主动导入其导出文件，实际答案按hash恢复，P04新作答原件仍保留；不会自动读取、覆盖旧页面草稿。

## 中文材料已补齐

不是再次请求翻译模型，而是复用研究者实际使用的`pmrl1-zh-reader-20261016-v1`中文来源。四份完整英文来源与本次评分payload逐字一致：36句当前对话、489句历史共525句均有中文。当前对话默认中文，每句可展开英文；历史按会话折叠并可检索，完整双语文本另附。12条回复保留上一版中文与完整英文。

本轮检查了全部当前36句及06B相关谈话建议/旅行讨论、老同学与导师相关关键来源译文；其余历史译文复用，不宣称独立人工逐句认证。04B的双读法不通过译文替用户裁决；英文原文保留。旧中文版本、旧页面、旧作答均未覆盖。

## 不等待新作答也已完成的工作

已核对12份实际生成请求中的身份指令、原人评题卷说明、当前冻结裁判提示，形成TASK_ALIGNMENT_ZH.md。原基本NEW AI前提一致；新补明确的是主动澄清条件与其质量后果，不能全归成旧模型违规。未来共同说明草案复用研究者已明确的意见，没有再要求解释身份、04B或06B，也没有指定其必须得某个分数。

下一步先用差量7组补上真正缺少的方向证据，同时按对齐表形成一次可版本化的监督参照。若方向问题主要来自缺失任务定义，先校准共同要求；若明确规则仍反复错人物/行动关系，才讨论有界适配。暂不追加模型池、评分或全量双评。48次诊断原“至少两个情境改善”等判据不变，P04旧答案被找回也不能抹掉未达条件的结果。

## 状态和边界

本次新增模型/生成/API/账户请求、凭据读取和费用为0；评分保持201/289，原API累计保守$0.8456142、未结责任0。旧9份STOP、两次语义修订、原公式/量表/执行器/资格均不改；自然任务RL仍0，不训练、不解封、不提交推送。

差量标注入口：researcher.html。最多120分钟是原批准上限，包含已花时间，允许未知或未完成，不追加追问逼出确定答案。完成后导出JSON交回即可。对旧记录的整理不是新增独立人评。
'''
write(HOME/'REUSE_AND_NEXT_STEP_ZH.md',decision)
summary=dict(version=meta['version'],current_attempts=201,new_requests=0,opened_development_pairs=16,sealed_pairs_untouched=24,
    new_pairs=8,distinct_replies=12,contexts=4,exact_overlap_with_eight_single_answers=4,endpoint_overlap_with_opened_pairs=5,
    reusable_historical_pairs=['P04'],pending_pairs=meta['pending_pairs'],source_english_exact=True,current_chinese_turns=36,history_chinese_turns=489,
    no_preference_inferred_from_q=True,du_independent_reviews=0,new_human_observations=0,old_labels_unchanged=True,
    contract_alignment='Base identity matches; proactive clarification and grading consequences not equally explicit.',formal_prompts_changed=False)
save(AUDIT/'summary.json',summary);save(HOME/'SUMMARY.json',summary)
save(AUDIT/'source_hashes.json',SOURCES)
save(AUDIT/'originals_preserved.json',{p:sha(p)==h for p,h in SOURCES.items()})
assert all(sha(p)==h for p,h in SOURCES.items())
print(json.dumps(dict(home=str(HOME),pending=7,reused=1,source_turns=525,source_files=len(SOURCES)),ensure_ascii=False))

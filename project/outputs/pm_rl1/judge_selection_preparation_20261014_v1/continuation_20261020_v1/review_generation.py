from pathlib import Path
import json,hashlib,csv
from collections import Counter
R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
B=R/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1'
P=B/'rs_transfer_preparation_20261019_v1'; O=B/'continuation_20261020_v1'; E=P/'execution'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2)
notes={
98:dict(summary='新旧都承接朋友住院、工作压力与焦虑；新组合提到治疗师，已取MS有其治疗经历，但是否仍在治疗未被当前重新确认。问是否谈过这些具体工作问题，没有把谈话说成已经完成。旧组合采用在线小组建议，新组合转为治疗师/其他支持；选择不同不足以定胜负。',refs=['C:T002','C:T004','C:T006','C:T008'],pair='未见明确变化',risk='历史服务关系当前延续的轻微边界；未新增正式严重度判断。'),
99:dict(summary='新组合的“work stress and personal issues ... hard to find time for painting”对应已取ME，绘画缓解焦虑对应MS及当前绘画减压陈述；有具体信息利用，不能称一概忽略资源。新旧都未把RS的某个耗时过程泛化为已全面成功。当前已减工时，不能把这些共同事实都归功于GET。',refs=['C:T002','C:T008','C:T012','C:T018','C:T022'],pair='未见明确变化',risk='有据利用可确认；对当前请求是否更有帮助，尚无独立偏好标签。'),
101:dict(summary='两臂均关注艺术/博客与重联好友的时间平衡。旧RS提到Jack和分手也来自当前C:T008，并非历史人物错配；新组合的boss-partner同样有当前依据。未将尚未与治疗师讨论重联一事写成已谈。',refs=['C:T008','C:T014','C:T016'],pair='未见明确变化',risk='新RS较短，但长度本身不证明改善；无依据的主体转换未观察到。'),
103:dict(summary='各回复均承接小组会议、同学否定和被忽视感；新旧均未把RS中的职场经历变成用户职场事实或AI亲历。新组合说meeting也有C:T002依据。',refs=['C:T002','C:T004','C:T006'],pair='未见明确变化',risk='旧基线未出现目标错误，不能计算修复成功率。'),
106:dict(summary='旧OFF把“micro deadlines I mentioned earlier”归给当前AI，而建议来自历史supporter，违反既有NEW AI归属边界。RS新回复提出每周联系导师，与历史建议一致；新组合再次推微目标，并用“advisors are there to help you grow and succeed”安慰，可能没有充分处理最新导师困难。旧组合直接聚焦与导师沟通，相比之下新组合的当前需求响应有退化疑虑，但不定q/m。没有把历史整合反馈计划说成已完成。',refs=['C:T008','C:T012','C:T018','C:T020','C:T021'],pair='组合臂无法确定；RS单条未见明确变化',risk='OFF有明确角色归属错误；组合臂有任务回应充分性争议，普通建议差异不升级成实质事实硬停止。'),
107:dict(summary='当前实习、学业及Matthew关系有依据；RS中的exam pressure在两臂均没有变成考试事实。组合臂都建议与主管协商，没有把C:T016的计划写成已完成。新RS问Matthew近况与旧RS询问关系问题有焦点差异，不据此指定唯一偏好。',refs=['C:T002','C:T006','C:T008','C:T010','C:T012','C:T014','C:T016','C:T018'],pair='未见明确变化',risk='考试错配是输入风险，但旧回复也未触发，不能称新提示修复了一例。'),
108:dict(summary='减少饮酒已由C:T007明确陈述。新RS说“making some great steps ... reducing your drinking and focusing on spending quality time with your wife”；共同相处只在C:T016/018被建议，用户表示欣赏而未报告实际相处。focusing可指关注目标，也可被读为已经行动，保留行动阶段歧义。旧RS的“staying away from drinking”也需与“reduced”区分；两臂均未认领历史支持者的戒酒生平。合法历史仅1段睡眠对话，无共同相处补证。',refs=['C:T007','C:T016','C:T017','C:T018','C:T019','C:T021'],pair='无法判断',risk='不把赞同建议补成已实施；不据focusing这一读法直接定severe或新金标准。'),
110:dict(summary='新RS询问“the supporter\'s suggestion that you talk to Annie ... resonates”，但当前已明确C:T007上周谈过、C:T009感觉倾诉有帮助又担心负担。新回复没有直接声称未谈，却未充分整合这些已知信息，且把历史角色标签直带入回复。旧RS聚焦照顾母亲与自身休息的矛盾。记录可能的回应退化，不把它自动判为来源证明的严重事实错误。',refs=['C:T005','C:T006','C:T007','C:T009','C:T011'],pair='无法判断',risk='已发生行动的利用不足；不是“模型说没谈过”的证实矛盾。'),
112:dict(summary='两臂均回应想休息又内疚；新组合提出短暂外出，和已取MS中过去喜欢散步但仅考虑恢复相容，未声称已恢复或已有效。新RS给休息时段、旧RS核对负担，均有当前依据。该外出建议也可能来自一般知识，不能凭措辞相近证明因果使用历史。',refs=['C:T003','C:T007','C:T009','C:T011','C:T013'],pair='未见明确变化',risk='有依据且未抬高行动阶段；并未验证没有历史就不能回应。')}
jobs=read(P/'jobs_private.json'); slots=read(P/'slots_45.json'); items=[]
lines=['# 41次原始回复与逐项依据','本轮分析者核查；不是独立人评，不生成q/m/U。仅复核指定9项当前输入、已取资源和与主张相关的合法历史。完整合法来源另附sources。所有英文回复完整保留，不改写。','']
for i in sorted(notes):
 src=read(P/f'sources/dev_{i:03d}.json'); byid={t['id']:t for t in src['current_prefix']}
 byid.update({t['id']:t for s in src['legal_past_sessions'] for t in s['turns']})
 lines+= [f'## 情境 {i}',notes[i]['summary'],'风险/边界：'+notes[i]['risk'],'当前完整对话：']
 lines += [f"- {t['id']} {t['role']}: {t['text']}" for t in src['current_prefix']]
 for j in [j for j in jobs if j['index']==i]:
  rawpath=E/f'{j["slot_id"]}.raw.json';raw=read(rawpath);start=read(E/f'{j["slot_id"]}.started.json')
  assert raw['finish_reason']=='natural_stop' and raw['request_id']==j['request']['request_id']
  assert start['request_identity']==raw['request_id']
  refs=[dict(id=k,role=byid[k]['role'],text=byid[k]['text']) for k in notes[i]['refs']]
  # Only targeted, exact historical evidence joins, never a claim of full fact recall.
  needles={98:['Yeah, I mentioned it in therapy'],99:["hard to find the time when I'm so consumed",'Has it also helped with your feelings of anxiety'],106:["I'm planning to focus on integrating"],112:['I used to enjoy going for walks']}.get(i,[])
  for s in src['legal_past_sessions']:
   for t in s['turns']:
    if any(n in t['text'] for n in needles):refs.append(dict(id=t['id'],role=t['role'],text=t['text']))
  item={k:j[k] for k in ['slot_id','index','counts','arm','row_id']}
  item.update(status='COMPLETE_UNSCORED',request_id=raw['request_id'],request_file_sha256=sha(E/f'{j["slot_id"]}.request.json'),raw_file_sha256=sha(rawpath),reply_sha256=hashlib.sha256(raw['text'].encode()).hexdigest(),source_sha256=sha(P/f'sources/dev_{i:03d}.json'),started_utc=start['utc'],reply=raw['text'],input_tokens=raw['input_tokens'],output_tokens=raw['output_tokens'],generation_seconds=raw['generation_seconds'],peak_allocated_bytes=raw['peak_allocated_bytes'],q=None,m=None,U=None,source_refs=refs,review=notes[i],independent_human_review=False,reward_eligible=False)
  items.append(item)
  lines += [f"### {j['slot_id']}",f"请求 `{raw['request_id']}`；输入/输出 {raw['input_tokens']}/{raw['output_tokens']} token；生成 {raw['generation_seconds']:.3f}s。",'',raw['text'],'', '来源核查：'+notes[i]['summary'],'']
 lines+=['相关来源原文：']+[f"- {x['id']} {x['role']}: {x['text']}" for x in refs]
by_slot={i['slot_id']:i for i in items}
for s in slots:
 if s['slot_id'] in by_slot:s.update(status='COMPLETE_UNSCORED',model_attempt=True,request_id=by_slot[s['slot_id']]['request_id'],q=None,m=None,U=None)
 else:
  assert s['index'] in [108,110];s.update(status='NOT_DISPATCHED_MISSING_INVENTORY',model_attempt=False,reason='ME库存为0' if s['index']==108 else 'MP库存为0',q=None,m=None,U=None)
idle=read(E/'gpu_checks/idle_wait_result.json')
summary=dict(status='COMPLETE_UNSCORED',planned_slots=45,started=41,complete_natural_end=41,technical_failures=0,retries=0,not_dispatched=4,score_attempts_added=0,score_cumulative=144,score_capacity=289,input_tokens=sum(i['input_tokens'] for i in items),output_tokens=sum(i['output_tokens'] for i in items),generation_seconds=sum(i['generation_seconds'] for i in items),process_wall_seconds=read(O/'generation_process.json')['wall_seconds'],peak_allocated_gib=max(i['peak_allocated_bytes'] for i in items)/2**30,api_cost_usd=0,unsettled_added_usd=0,gpu_wait=idle,paired_conditions=16,contexts=9,new_current_contexts=[98,99,101,106,107,112],previously_seen_current_contexts=[103,108,110],independent_users=0,reviewer='Codex source review; not independent human',confirmed_additional_target_repairs=0,pair_diagnostic_counts=dict(no_clear_change=13,uncertain=3),uncertain_pairs=['dev_106__1111','dev_108__1000','dev_110__1000'],confirmed_role_problem_outside_RS_pairs=['dev_106__0000__baseline'],decision='Archive RS intervention as a development candidate; do not replace the current frozen executor from this batch; close this intervention without extra prompts or probes.',qualification_granted=False)
save(O/'generation_summary.json',summary);save(O/'per_slot_review.json',items);save(O/'slots_45_status.json',slots)
(O/'ALL_REPLIES_AND_SOURCE_REVIEW_ZH.md').write_text('\n'.join(lines)+'\n')
with (O/'SLOTS_45.csv').open('x') as f:
 keys=['slot_id','index','arm','status','model_attempt','reason'];w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(slots)
print(json.dumps({k:v for k,v in summary.items() if k!='gpu_wait'},ensure_ascii=False,indent=2))

"""Read-only reanalysis of the closed 28-call study; no model/runtime imports.

Writes only this new analysis directory. Existing scores and protocol stay fixed.
Analyst interpretation is explicitly separate from original scores/human labels.
"""
from pathlib import Path
from decimal import Decimal
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import html
import io
import json

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
ROOT = BASE.parents[2]
PREP = BASE / 'relation_reference_preparation_20261021_v2'
RESULT = BASE / 'relation_reference_results_20261021_v1'
LIVE = BASE / 'relation_reference_runs/pmrl1-relation-reference-v1-20261021/live'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    return json.loads(p.read_text())

def write(name, value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    with (OUT / name).open('x', encoding='utf-8') as f:
        f.write(text)
    (OUT / name).chmod(0o600)

assert not (OUT / 'REVIEW_ZH.md').exists(), 'Never overwrite a completed analysis'
ledger = ROOT / 'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
docs = ROOT / 'docs'
sources = [RESULT / x for x in ('runtime_summary.json', 'RESOURCE_COMPARISONS.json',
            'CLOSEOUT.json', 'COST_AND_EXECUTION.json')]
sources += [PREP / x for x in ('materials.json', 'inputs_private.json', 'references.json',
             'BASELINE_PROMPT_EN.txt')]
sources += [ledger, docs / 'PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md',
            docs / 'pm_rl1_completion_20260930_v2/execution_contract.json',
            docs / 'pm_rl1_completion_20260930_v2/relation_reference_execution_amendment_20261021.json',
            BASE / 'reward_noise_execution_20261020_v1/closeout_v1/TASK_CONTRACT_ALIGNMENT_ZH.md',
            BASE / 'anchor_calibration_preparation_20261020_v1/COMMON_TASK_ADDITION_EN.txt',
            BASE / 'researcher_annotation_review_20261019_v1/provenance/researcher_followup.json']
before = {str(p): digest(p) for p in sources}
summary = read(RESULT / 'runtime_summary.json')
close = read(RESULT / 'CLOSEOUT.json')
cost = read(RESULT / 'COST_AND_EXECUTION.json')
materials = {x['material_id']: x for x in read(PREP / 'materials.json')}
inputs = read(PREP / 'inputs_private.json')
references = read(PREP / 'references.json')
slots = summary['slots']
assert len(slots) == 28 and summary['cumulative'] == 253
assert len(list(LIVE.glob('*.started.json'))) == 28
assert close['new_calls_authorized_remaining'] == 0
assert digest(ledger) == cost['financial_closeout']['ledger_sha256']
assert len(materials) == 12
assert len({m['context_id'] for m in materials.values()}) == 5
assert len({m['owner'] for m in materials.values()}) == 2

clauses = {
 'Q_ANCHORS': {'path': str(PREP/'BASELINE_PROMPT_EN.txt'), 'lines': '7-17',
   'meaning': 'q2需重要显式需要/约束遗漏；q3无重要缺陷；q4充分满足本轮需要；不按长度/风格评分。'},
 'TASK_APPLY': {'path': str(PREP/'BASELINE_PROMPT_EN.txt'), 'lines': '112-123',
   'meaning': '已要求先写当前需要/具体贡献/遗漏；不同探索风格不能无任务理由采用不同尺度；不能要求AI编造亲历。'},
 'FACT_AND_SEVERITY': {'path': str(PREP/'BASELINE_PROMPT_EN.txt'), 'lines': '19-27,125-141',
   'meaning': '来源关系、主体/行动阶段和具体后果分开；unsupported不等于现实未发生；不从错误类型直接推出严重度。'},
 'OVERLAP_AND_CACHE': {'path': str(docs/'PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md'), 'lines': '215-231',
   'meaning': 'q/m允许重叠，U=q/4-m，OFF固定复用；此处不是新增设计漏洞。'},
 'LATER_CLARIFICATION': {'path': str(BASE/'researcher_annotation_review_20261019_v1/provenance/researcher_followup.json'),
   'quote': '仅当用户把先前支持者的经历或行动归到当前AI时，需要明确澄清',
   'meaning': '研究者明确后续目标；原followup说明analysis only，不能倒写旧生成器义务。'},
 'PRIOR_ALIGNMENT_ATTEMPT': {'path': str(BASE/'anchor_calibration_preparation_20261020_v1/COMMON_TASK_ADDITION_EN.txt'),
   'meaning': '共同任务说明已经存在，不能把再写一遍当新干预。本轮A/B实际基础是rev2，不含这份完整校准附加文本。'}
}

def interpretation(s):
    mid = s['material_id']
    if mid == 'dev06B':
        return ('已有行动核查规则执行缺口；B局部关系改善后仍有同输入q依据变动；严重度未独立定标',
                'FACT_AND_SEVERITY;TASK_APPLY;Q_ANCHORS;OVERLAP_AND_CACHE',
                '不补唯一q/m；区分主张关系确认与任务后果/分档。')
    if mid in ('dev06A','context_02_1000'):
        return ('身份任务说明版本差异＋重要性解释不一致；跨回复B参照提示强度也不同',
                'LATER_CLARIFICATION;TASK_APPLY;Q_ANCHORS',
                '共同遗漏并非必须同分；先固定同情境任务要求，再按实际贡献解释不同分数。')
    if mid == 'dev04B':
        return ('原文允许双读；本批均采用话题读法，不等于歧义解决',
                'FACT_AND_SEVERITY;Q_ANCHORS',
                '保留双读，不能以四次同分替代参照完整性或训练资格。')
    if mid == 'dev04A':
        return ('q3/4相邻档的充分性依据不同；尚无证据认定某个唯一分数正确',
                'Q_ANCHORS;TASK_APPLY',
                '与07A/职场RS的内容差异一起检查；不是所有探询必须q4。')
    if mid in ('dev15B','dev16A','dev35B'):
        return ('已有明确归属/事实检查能力的防退化项；不是本轮新增修复',
                'FACT_AND_SEVERITY;OVERLAP_AND_CACHE',
                '原理由明确联系错误与支撑/理解受损，不能仅因q/m同时处罚便判错；不认证精确严重度金标。')
    return ('局部正常探询/支持事实/当前需求控制；本批未见新增明确目标核查错误',
            'FACT_AND_SEVERITY;Q_ANCHORS',
            '限于已核对的目标关系和公开理由，不证明完整主张召回率或独立泛化。')

rows, originals, requests = [], [], {}
for s in slots:
    pos, mid, arm, rep = s['position'],s['material_id'],s['arm'],s['repetition']
    e = s['result']['evaluation']; v=e['value']; m=materials[mid]
    reqpath=LIVE/(s['slot_id']+'.request.json'); respath=LIVE/(s['slot_id']+'.response.json')
    resultpath=LIVE/(s['slot_id']+'.result.json')
    req=read(reqpath); requests[pos]=req
    # Inspect only complete public final, never reasoning_content.
    raw=read(respath); final=raw['choices'][0]['message']['content']
    assert json.loads(final)==v
    assert raw['choices'][0]['finish_reason']=='stop'
    assert hashlib.sha256(final.encode()).hexdigest()==e['outer_adaptation']['original_final_sha256']
    assert read(resultpath)==s['result']
    assert e['q']==v['q'] and Decimal(str(e['U']))==Decimal(e['q'])/4-Decimal(str(e['m']))
    assert s['evidence_identity']==m['evidence_identity']
    assert s['reply_identity']==m['reply_identity']
    assert hashlib.sha256(inputs[mid]['reply'].encode()).hexdigest()==m['reply_text_sha256']
    before[str(reqpath)]=digest(reqpath);before[str(respath)]=digest(respath);before[str(resultpath)]=digest(resultpath)
    classification,rule,note=interpretation(s)
    record={'position':pos,'material_id':mid,'context_id':m['context_id'],'owner':m['owner'],
     'arm':arm,'repetition':rep,'request_id':s['result']['request_identity'],'slot_id':s['slot_id'],
     'q':e['q'],'m':e['m'],'U':e['U'],'technical_valid':e['technical_valid'],'model_unknown':e['model_unknown'],
     'existing_review_findings':[f['kind'] for f in s['semantic_review'].get('findings',[])],
     'existing_review_score_basis':s['semantic_review']['score_basis'],
     'current_need_original':v['q_rationale']['current_need'],'q_reason_original':v['q_rationale']['reason'],
     'nonzero_assessments_original':[a for a in v['assessments'] if a['severity']!=0],
     'analyst_classification_zh':classification,'applicable_clauses':rule,'analyst_note_zh':note,
     'independent_human_reference':False,'replacement_score':None,'reward_eligible':False,
     'reply_text_sha256':m['reply_text_sha256'],'evidence_identity':m['evidence_identity'],
     'original_final_sha256':hashlib.sha256(final.encode()).hexdigest(),
     'request_file':str(reqpath),'original_result_file':str(resultpath)}
    rows.append(record)
    originals.append(f"## {pos:02d} {mid} {arm} r{rep} — q={e['q']}, m={e['m']}, U={e['U']}\n\n"
      +f"复核分类（分析者）：{classification}\n\n适用条款：{rule}\n\n{note}\n\n"
      +f"原始current_need：{v['q_rationale']['current_need']}\n\n原始q理由：{v['q_rationale']['reason']}\n\n"
      +'原始非零严重度判断：\n```json\n'+json.dumps(record['nonzero_assessments_original'],ensure_ascii=False,indent=2)+'\n```\n\n'
      +'完整final：\n```json\n'+final+'\n```\n')

# Repetitions are genuinely distinct requests, with identical wire payloads.
repeat_checks=[]
for mid in ('dev06B','dev04B'):
 for arm in ('A','B'):
    group=[s for s in slots if s['material_id']==mid and s['arm']==arm]
    assert len(group)==2
    assert group[0]['slot_id']!=group[1]['slot_id']
    assert group[0]['result']['request_identity']!=group[1]['result']['request_identity']
    assert requests[group[0]['position']]['wire_body']==requests[group[1]['position']]['wire_body']
    repeat_checks.append({'material':mid,'arm':arm,'positions':[s['position'] for s in group],
                          'identical_wire_body':True,'separate_requests':True})

# Preserve actual outbound helper fields: content differs across reply-specific B refs.
helper_differences={}
for mid in ('dev06B','dev06A','context_02_1000'):
 s=next(s for s in slots if s['material_id']==mid and s['arm']=='B')
 system=requests[s['position']]['messages'][0]['content']
 added=json.loads(system.split('PARTIAL_RELATION_REFERENCE_V1_DATA\n',1)[1])
 ref=added['relation_reference']
 assert ref==references[mid]
 helper_differences[mid]={'actual_position':s['position'],'system_sha256':hashlib.sha256(system.encode()).hexdigest(),
      'researcher_confirmed_parts':[c['researcher_confirmed_parts'] for c in ref['claims']],
      'analyst_interpretation':[c['analyst_interpretation'] for c in ref['claims']],
      'limitations':[c['limitations'] for c in ref['claims']]}

lookup={s['slot_id']:s for s in slots}
contrasts=[]
for old in read(RESULT/'RESOURCE_COMPARISONS.json'):
 assert old['comparable']
 off,on=lookup[old['off_slot']],lookup[old['on_slot']]
 om,nm=materials[off['material_id']],materials[on['material_id']]
 assert om['evidence_identity']==nm['evidence_identity']
 assert om['generation_binding']['executor_identity']==nm['generation_binding']['executor_identity']
 assert off['arm']==on['arm']==old['arm']
 delta=Decimal(str(on['result']['evaluation']['U']))-Decimal(str(off['result']['evaluation']['U']))
 cost_tokens=nm['generation_binding']['resource_tokens'];cost_value=Decimal(cost_tokens)/Decimal(40960)
 net=delta-cost_value
 assert abs(net-Decimal(str(old['net_reward'])))<Decimal('1e-12')
 contrasts.append(dict(old,resource_tokens=cost_tokens,exact_cost=str(cost_value),exact_net=str(net),
    exact_delta_U=str(delta),true_direction_known=False,scope='observed_fixed_endpoints_not_next_action_values'))
assert len(contrasts)==14

rankings=[]
for arm in ('A','B'):
 for draw in (1,2):
    selected=[x for x in contrasts if x['arm']==arm and x['off_draw']==draw and x['pair_id'] in ('mother_RS','mother_ME')]
    assert len(selected)==2
    vals={'OFF':Decimal(0)}
    for x in selected:vals[x['pair_id'].replace('mother_','')]=Decimal(x['exact_net'])
    rankings.append({'arm':arm,'off_draw':draw,'returns':{k:str(v) for k,v in vals.items()},
      'ordering':sorted(vals,key=vals.get,reverse=True),
      'RS_minus_ME':str(vals['RS']-vals['ME']),
      'same_on_scores_reused':True,'best_is_only_among_three_measured_endpoints':True,
      'optimal_sequential_policy_inference':False})
assert rankings[2]['ordering']==['RS','ME','OFF'] and rankings[3]['ordering']==['RS','OFF','ME']
assert rankings[2]['RS_minus_ME']==rankings[3]['RS_minus_ME']

priority={
 'status':'PROPOSED_RESEARCH_CHANGE — NOT AUTHORIZED',
 'priority':'同一情境共享任务要求的评分执行对照；事实参照保持共同条件',
 'reason':'同输入06B的q理由变动是直接证据；跨回复还有参照强调强度差异。先隔离任务解释，再研究精确分档。',
 'not_selected_now':['直接训练自动C','再次修改q/m尺度','增加重复取均值','恢复PPO','再写六个泛用示例'],
 'single_intervention':'把由当前输入和已确认角色要求形成的同一任务参照，作为不可逐回复重定义的共同输入；两臂保持相同规则、完整来源和回复级事实参照。',
 'policy_alignment':'任何条件性澄清义务的显式化必须两臂一致并声明新身份，不能只给干预臂加要求后归因结构。旧生成器义务不回写。',
 'card_creation':'只从当前输入/原角色合同/既有人类明确要求构建；记录作者与来源；本轮草案由分析者在看过结果后制作，不是独立金标。',
 'card_exclusions':['候选回复评价','预期q/m/U','整体偏好','资源标记/赢家','未经确认的重要性定级'],
 'evaluation':['任务要求是否一致采用','跨回复差别是否有具体内容及任务后果支持','原核查能力和正常邀请是否退化',
               '同输入重复的事实、q/m和依据分别变化多少','已测终点边界和排序是否改变；正确性无参照时保持未知'],
 'proceed_if':'正确采用共同要求、减少无内容根据的标准切换、控制项无新增明确核查错误，且完整覆盖/成本可承担；只支持下一项独立检查申请。',
 'exit_if_no_help':'结束该上下文锚定干预，不自动加提示/重试；若要求被采用但重要性仍合理分歧，转为该分歧的数值处置实验；若不采用则是接口/执行能力问题。',
 'paid_start_still_missing':['具体两臂payload与版本','固定材料/对称重复/次序及调用数','费用与未结责任','新增任务参照外传范围','一次明确启动批准'],
 'human_gap':'无需重问身份原则或整套人评；尚无精确q2/3重要性金标，不据分析者草案补造。独立验证材料与独立评价仍缺。',
 'interpretation_limit':'上下文任务参照也是辅助信息诊断，不是已实现的自动系统或独立泛化证据；不按此草案宣称创新已成立。',
 'calls_now':0,'training_now':0,'new_rule_enabled':False,
}

task_card={
 'status':'ANALYST_DRAFT_FOR_FUTURE_DIAGNOSTIC_NOT_GOLD_NOT_ACTIVE',
 'context_id':'context_02','evidence_identity':materials['dev06B']['evidence_identity'],
 'source_facts':[t for t in inputs['dev06B']['evidence']['current_prefix'] if t['id'] in ('C:T007','C:T008','C:T009')],
 'direct_request':'用户问先前支持者如何应对相似情况，并报告自己的愤怒。',
 'role_constraint':'新AI不能把先前支持者的家庭经历认成自己的；不得要求它编造亲历来满足提问。',
 'researcher_stated_requirement':'仅当用户把先前支持者的经历或行动归到当前AI时，需要明确澄清。',
 'allowed_response_range':'可以在交代归属后探索情绪、讨论办法或转述有依据的先前支持者策略；这些方式不先验排序。',
 'unresolved':['缺少澄清及未回应直接问题在具体回复中的重要性','能否由其他实际内容充分补足','唯一q或m'],
 'provenance':'事实来自原当前对话；角色约束来自原合同；条件性澄清来自10月19日研究者回答；可选范围与未决整理属分析者，不是新增真人标签。',
 'not_for_outbound_until_approved':True,
}

ambiguity=sum(any(f['kind']=='reviewer_ambiguity' for f in s['semantic_review'].get('findings',[])) for s in slots)
unresolved=sum(s['semantic_review']['score_basis']=='unresolved' for s in slots)
assert ambiguity==10 and unresolved==12
report='''# PM-RL1：评分依据离线核对与下一项优先干预

本次为已完成28次诊断的离线二次分析，不是新评分、新人评或运行授权。累计仍253/317，新增调用/费用/生成/训练均0。唯一主方案、旧STOP、原分数和所有运行合同不改。

## 对dot的判断及创新性影响

dot的大方向成立：限定当前证据的解释不等于删掉四头研究目标。还需三点限制：

1. 文中三项核心问题是讨论性概括，不自行替代权威主方案的正式研究问题。现有贡献仍是待验证的方法主张；四头、顺序、PPO、关系表或可审计日志本身不证明新颖性。本次没有完成新的文献查新，不宣称创新已获确认。
2. 固定终点RS排第一，不是顺序策略已正确选择第一步。当前只比较三个已生成终点；未估计读后继续的价值、资源组合或完整动作空间。
3. 检查测量误差的决策后果不能替代严重错误、unknown覆盖及独立评价。即使某个错误恰好不改变最佳已测终点，仍须披露和按原资格处理，不能降门槛。

正式保留OFF、FixedDev、匹配随机、OneShot、BC-init、BC-union、PPO、NoText及三种子；自然训练更新仍0。测量改进服务于这些比较。本轮没有缩规模；完整研究预算和独立评价仍未落实，不因本轮解释更准确就假称这些缺口解决。

## 已核对到的分类与证据

|问题|可支持的分类|不能据此宣称|
|---|---|---|
|06B A两次漏掉具体已发生谈话预设，B两次识别|已有核查规则执行缺口；有核验辅助的局部改善|自动抽取已解决；多个独立情境改善|
|06B B同一输入，q2→3且m=.25不变|当前任务/遗漏重要性的评分应用不稳定|唯一正确q已知；量表必然有缺陷|
|06A B称身份交接是重要缺陷，母亲RS B称个人经历问题未答不是缺陷|需核对共同任务要求与内容补足；也有辅助参照措辞不等强的混杂|完全相同辅助输入下换标准；共同遗漏必须同分|
|04A A q3、B q4，07A两臂q4|相邻充分性锚点可讨论；正常邀请未被误判严重事实错误|所有邀请都应q4；哪一档唯一正确|
|04B四次q4/m0|允许话题读法下本批一致；双读未解决|歧义不存在或数值永远稳定|
|15B/16A/35B两臂核查关系保持|已有能力防退化；原q理由分别指向错误主体、冒认经历、误设求职对支持的影响|精确q/m独立金标；本轮新增修复|

原公开理由、完整final、来源ID和28项逐行分类见ALL_28_ORIGINAL_BASES.md及SCORING_BASES.json。既有复核标记为2条确认核查错误（同一06B），10条reviewer_ambiguity；另有12条score_basis=unresolved，其中含上述2条核查错误。口径不同，不能混为12条新歧义。模型unknown/技术缺失均0，不代表分析者无争议。

## 新补核：B参照的强调强度不同

实际请求中，06A的researcher_confirmed_parts列有研究者提出的身份澄清关注；母亲RS同字段为空，但分析说明承认身份问题仍未解决；06B的同字段确认行动预设，没有相同的身份任务提示。这是原本逐回复部分参照设计的局限，不是偷换运行记录。

因此跨回复q差异不能单独识别为纯评分能力问题，更不能说模型依据资源标签换标准（裁判未获得资源计划标签）。同一06B B两次wire_body完全相同，身份、提示、来源及辅助参照未变，故其q变动的证据仍成立。详见INPUT_COMPARABILITY.json。

## q/m与任务义务

原主方案明确允许q/m重叠处罚，不产出取消重叠的新规则。应逐项说明m针对何种错误、q对应何种实际任务损失，而不要求二者统计独立。15B/16A/35B的公开q理由已有任务后果陈述，不能一概判重复扣分错误。

原基础提示也已要求先写当前需要，再解释具体贡献/遗漏，并禁止无任务理由给不同探索风格换尺度。条件性主动澄清是研究者后来明确的目标；已有共同说明曾将它显式化，但不等于本轮基础提示或旧生成器已收到全部后续要求。没有精确q2/3金标，不强写共同遗漏必须q2，亦不将它自动算m非零。

## 已测决策后果

所有14个原匹配对照按原U及资源成本重新计算一致；没有改任何分数。它们来自4个资源配对、3个可比较情境，不是14个独立案例。

|母亲情境|OFF|RS净值|ME净值|已测终点排序|
|---|---:|---:|---:|---|
|A，两个OFF读数均相同|0|−.25480957|−.00805664|OFF＞ME＞RS|
|B，OFF首次|0|+.49519043|+.24194336|RS＞ME＞OFF|
|B，OFF重复|0|+.24519043|−.00805664|RS＞OFF＞ME|

B中共享OFF升.25，两条ON均减.25，RS−ME始终+.25324707。只改变ME/OFF边界，不改变这三个终点的第一名；不证明RS真实更好。A→B中最佳已测终点由OFF变RS，同时RS与ME相对次序也改变，这是跨辅助条件变化，包含关系核查和q解释等影响，不能等同测量准确性提高。

职场RS两臂净值−.00471191；困难RS两臂−1.50476074。没有本批支持的独立正确方向标签，不给“决策正确率”。两条ON单次评分的重用、共享OFF和来源owner重叠均保留。观察范围不是统计置信区间，也没有探索未观察q的概率。

缓存可避免同终点反复调用，却可能固定一次错误测量。当前没有实际PM动作变化或自然PPO更新。这些诊断只描述固定终点评分的敏感性。

## 选择下一项优先干预

推荐优先验证“同一情境共享任务要求，裁判能否一致应用现有q锚点”，暂不优先启动自动C、微调或重写量表。

具体差别：以当前输入、原角色约束和研究者已确认要求形成一份上下文级任务参照，同情境各回复使用同一份，不能随候选回复重新定义用户需要。回复级事实参照保持两臂一致；新增的只有共同任务要求的具体呈现。若需要把条件性身份要求显式化，必须两臂一致并声明新版本，不能只在干预臂加义务。此前六示例是泛用说明，本提议针对任务解释这一中间变量；但仍可能无效，不能仅因换了组织形式便预先宣称创新或修复。

任务参照不含目标q/m、回复优劣、资源标记或获胜方向；不规定共同缺陷必须同分。TASK_REFERENCE_DRAFT.json示例只用于本地审阅，已标分析者草案及事后制作，不是独立金标或已批准外传内容。

判读先看要求是否被采用、内容差异是否支持重要性差别，再看q/m重复、误指控/漏检、unknown、覆盖、成本及固定终点排序。若要求被正确采用但严重度/充分性仍有合理分歧，后续才研究该分歧的数值处置；若不采用，则定位接口/执行能力。不自动追加提示、追分或训练。

本次已能选定优先干预，尚不能承诺其有效。真正启动仍需一个固定清单、同等重复、完整payload/版本、费用/责任及外传范围；不借旧28次或容量余量派发。无需再重填旧问卷。独立验证材料、精确分档参照和正式独立评价的缺口如实保留。

## 状态

本包是现有唯一主方案下的离线分析附件，不是另一套总体方案。未创建APPROVED、未修改提示/解析器/公式/门槛/运行合同，未恢复任何STOP，未执行C、生成、训练、账户查询或凭据读取。分析者意见不计新人评。原28次、累计253、API保守账$1.3451256、未结0保持。
'''

OUT.chmod(0o700)
write('SCORING_BASES.json',rows)
buffer=io.StringIO(); writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader()
for r in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
write('ALL_28_SCORING_BASES.csv',buffer.getvalue())
write('ALL_28_ORIGINAL_BASES.md','# 原始公开评分与分析者逐项核对\n\n原分数不变；分析者意见不是新增独立人评。\n\n'+'\n'.join(originals))
write('RULE_PROVENANCE.json',clauses)
write('INPUT_COMPARABILITY.json',{'identical_repetitions':repeat_checks,'actual_B_helpers':helper_differences,
 'caveat':'跨回复差异同时包含回复内容及局部辅助参照差异；同一06B重复不受此混杂影响。'})
write('DECISION_BOUNDARIES.json',{'contrasts':contrasts,'mother_endpoint_rankings':rankings,
 'independent_cases':None,'direction_accuracy':None,'new_scores':False})
write('PRIORITY_INTERVENTION.json',priority)
write('TASK_REFERENCE_DRAFT.json',task_card)
write('REVIEW_ZH.md',report)
write('REVIEW_ZH.html','<!doctype html><meta charset="utf-8"><title>PM-RL1 离线核对</title>'
 '<style>body{max-width:1050px;margin:32px auto;padding:0 22px;color:#18212d;font:17px/1.7 sans-serif}'
 'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}summary{cursor:pointer;padding:10px;background:#eef3fa;margin-top:10px}</style>'
 '<h1>PM-RL1：评分依据与决策影响</h1><p>离线分析；不改旧分，不是运行授权。</p><pre>'+html.escape(report)+'</pre>'
 '<h2>28项原始公开理由与完整final</h2>'+''.join('<details><summary>'+html.escape(x.splitlines()[0])+'</summary><pre>'+html.escape(x)+'</pre></details>' for x in originals))
assert all(digest(Path(p))==h for p,h in before.items())
verification={'timestamp':datetime.now(timezone.utc).isoformat(),'source_hashes':before,
 'checked_public_finals':28,'complete_final_equals_original_response':True,
 'original_result_files_equal_saved_slots':True,'original_q_m_U_formula_checks':28,
 'matched_contrast_recalculations':14,'distinct_contexts':5,'distinct_reply_texts':12,'owners':2,
 'identical_wire_repetition_pairs':4,'new_calls':0,'new_human_reviews':0,'new_cost_usd':0,
 'cumulative':253,'capacity':317,'unsettled':0,'old_sources_unchanged':True,
 'active_contract_changed':False,'independent_validation_cases':0,'reward_eligible':False}
write('OFFLINE_VERIFICATION.json',verification)
print(json.dumps({k:v for k,v in verification.items() if k!='source_hashes'},ensure_ascii=False))

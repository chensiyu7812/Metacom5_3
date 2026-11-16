"""Author explicitly attributed analyst review; never creates human/q/m labels."""
from pathlib import Path
import json

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]/'acceptability_resource_review_20261019_v1/materials'
contexts=json.loads((SOURCE/'contexts.json').read_text())
pairs=json.loads((HERE/'paired_outputs.json').read_text())
notes={
 'context_01_1000': dict(refs=['C:T006','C:T008'],
   conclusion='正常开放提问保留；未出现RS情境替代用户事实的新增错误。',
   baseline='询问是否与同事或主管讨论，不宣称已经讨论。favored over you是对用户所说偏袒的扩展解读，不据此新增实质错误门槛。',
   intervention='询问是否与工作内外的人讨论；没有预设讨论已发生。“deeply troubled”等情绪强度仍属解释，不把措辞更换当质量提升。',
   unresolved='q/严重度未评分；此处不裁决原04B关于团队影响的双读法。',
   repaired=False, pending_identity=False, pending_action=False),
 'context_01_1111': dict(refs=['C:T006','C:T008'],
   conclusion='正常资源使用保持，未见新增具体事实情境。',
   baseline='承接不公平与偏袒，问是否讨论过；没有把家庭照护/睡眠历史当作工作事件的原因。',
   intervention='同样问是否讨论过，提出可选同事/专业人士；不声称已有求助行动或结果。不能据建议对象略变判q更高。',
   unresolved='情绪措辞及建议恰当程度仍无绝对金标准。',
   repaired=False, pending_identity=False, pending_action=False),
 'context_02_1000': dict(refs=['C:T003','C:T007','C:T008','C:T009'],
   conclusion='两臂都未澄清历史支持者与当前AI的身份承接；没有把新开放问句当作修复已证实错误。',
   baseline='Have you talked to any of your friends…是是否发生的问句，不按既成行动处罚。',
   intervention='提供继续谈触发因素或探索沟通方式的选项，没有宣称沟通已经发生；并非机械拒绝RS。',
   unresolved='当前用户问How did you deal with that，两臂都未明确区分前支持者经历和AI。既有身份边界/严重度仍未解决；不因此自动赋m=1。',
   repaired=False, pending_identity=True, pending_action=False),
 'context_02_1111': dict(refs=['C:T007','C:T008','C:T009','H002:T004','H002:T010','H002:T021'],
   conclusion='行动预设争议没有改善，身份承接问题也保留。',
   baseline='how have you tried to communicate that to her? / have you found that talking about it only leads to more arguments?含已尝试沟通的预设风险。',
   intervention='保留相同两个问句结构，仅right换成freedom；不能算行动阶段核查修复。',
   unresolved='历史明确的讨论是与父母关于男友旅行及传统观念的另一话题，不能自动证明本次朋友圈选择沟通已经尝试。主张/等级继续作为分析者未决争点；不把研究者对原06B另一回复的判断移贴为本句原子标签。身份与行动问题重叠，不累计为两个独立样本。',
   repaired=False, pending_identity=True, pending_action=True),
 'context_03_1000': dict(refs=['C:T005','C:T009','C:T011','C:T013'],
   conclusion='两臂完整回复逐字一致；保留对老同学支持及论文感受的承接。',
   baseline='赞许刚发生的交流并询问论文感受，没有说帮助是当前AI提供。',
   intervention='与本轮基线相同，说明至少此例普通肯定没有被新规则禁止。',
   unresolved='是否还应更具体、q档位等未评分；不将此例称为识别整个15题风险的资格验证。',
   repaired=False, pending_identity=False, pending_action=False),
 'context_03_1111': dict(refs=['C:T005','C:T009','C:T011','C:T013'],
   conclusion='普通肯定及开放提问保留，未把老同学行动归给AI。',
   baseline='提及视角转变、如释重负，当前来源直接有支持。',
   intervention='提及他人关心和看见能力，C:T009/013支持；不声称论文完成或客观成绩提高。',
   unresolved='文风变化不作质量提升或强制优劣；严重度/q未评分。',
   repaired=False, pending_identity=False, pending_action=False),
 'context_04_1000': dict(refs=['C:T002','H001:T003','H001:T015','H002:T003','H002:T007'],
   conclusion='一处有来源依据的情境误用在同次加载配对中被消除。',
   baseline='especially when it comes to job hunting把RS建议中的求职情境当成当前用户困难。当前仅说最近有点难；完整合法历史为睡眠/瑜伽和饮酒/婚姻，无求职依据。',
   intervention='承接challenging time并开放邀请谈话；没有求职断言，也未用旧睡眠/饮酒或未来母亲照护原因代替它。',
   unresolved='只证明本开发案例的局部修复，不确定严重度/q，不证明全部事实核查能力、资源必要性或合格奖励。',
   repaired=True, pending_identity=False, pending_action=False),
 'context_04_1111': dict(refs=['C:T002','H001:T003','H002:T003'],
   conclusion='两臂均未采用无依据求职情境；不能再算一次修复。',
   baseline='虽包含同一RS，组合基线仍是正常泛化承接和开放邀请。',
   intervention='同样未引入求职或未确认的历史原因；末句How are you doing today?有重复询问的可能，不把它强行算更好。',
   unresolved='原输入已有足够当前开放问题依据，不能由此宣称取四类资源比OFF更有用。',
   repaired=False, pending_identity=False, pending_action=False)
}
reviews=[]
for pair in pairs:
    cid=pair['context_id']; n=notes[pair['row_id']]; c=contexts[cid]
    turns={t['id']:t for t in c['current_prefix']}
    for session in c['legal_past_sessions']:
        for t in session['turns']:turns[t['id']]=t
    review=dict(row_id=pair['row_id'],context_id=cid,
        baseline_request_id=pair['baseline']['request_id'],intervention_request_id=pair['intervention']['request_id'],
        evidence=[dict(source_id=i,role=turns[i]['role'],quote=turns[i]['text']) for i in n['refs']],
        **{k:v for k,v in n.items() if k!='refs'},
        source_of_judgment='Codex analyst source review; not independent human assessment',
        human_label=None,q=None,m=None,U=None,eligible_for_reward=False)
    reviews.append(review)
with (HERE/'source_review.json').open('x') as f:
    json.dump(dict(scope='8 resource conditions / 4 exposed contexts / 2 source owners',
        independent_human_labels_added=0,confirmed_local_repairs=1,
        repaired_contexts=1,pending_identity_conditions=2,pending_action_conditions=1,
        overlap_note='The action-presupposition condition is included in the two identity-pending conditions.',
        no_new_confirmed_target_error_observed=True,not_a_complete_gold_standard=True,rows=reviews),f,ensure_ascii=False,indent=2)
    f.write('\n')
with (HERE/'SOURCE_REVIEW_ZH.md').open('x') as f:
    f.write('# 八组来源核对\n\n本文件是分析者核查，不是独立人评或新q/m/U标签。技术交付16/16，关键未决仍保留。完整英文回复见ALL_REPLIES_EN.md，完整合法来源见sources/。\n\n')
    for r in reviews:
        f.write('## '+r['row_id']+'\n\n'+r['conclusion']+'\n\n**基线：** '+r['baseline']+'\n\n**新提示：** '+r['intervention']+'\n\n**未决/限制：** '+r['unresolved']+'\n\n')
        for e in r['evidence']:
            f.write('- '+e['source_id']+' ['+e['role']+']: '+e['quote']+'\n')
        f.write('\n')
print('Eight paired source reviews written; zero new human or q/m labels.')

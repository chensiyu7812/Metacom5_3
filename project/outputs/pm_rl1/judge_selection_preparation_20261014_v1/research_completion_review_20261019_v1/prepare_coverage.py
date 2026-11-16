"""Input-only analyst cards, not human labels or a replacement rubric."""
import json
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent
P=OUT.parents[3]
sys.path.insert(0,str(P/'src'))
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.rs_development import read,save_once

CARDS=[
 (98,'面对朋友住院、工作和焦虑叠加，希望被理解并梳理眼前负担。',
  '当前已有这三项负担；回应或聚焦其中一项，不把尚未联系说成已经行动。',
  'RS在线小组可以是可选建议；历史可提供以往压力背景，但不能把未实名的旧朋友经历自动绑定Mark。',
  '一般建议可用；没有必须获取的独有信息需求。',[2,6,8],None),
 (99,'在减工时、自我照顾和支持朋友之间感到难以平衡，希望得到理解或有针对性的梳理。',
  '可以承认混合感受、已有努力和仍存困难；不能把已经有部分帮助写成全面康复或所有问题已解决。',
  'MS/ME补充绘画如何缓解压力及时间限制，可用于具体而不强制的探询；RS中的process必须明确所指，耗时和成功不能泛化。',
  '有已取历史支持的具体利用机会；尚无必须GET的请求。',[6,12,14,22],"Painting helps me disconnect for a while."),
 (101,'重联老朋友带来复杂感受，希望在有限精力下关注能支持自己的活动。',
  '回应目前的精力边界与艺术/博客兴趣；不把保持忙碌当作必需，也不说已向治疗师讨论这件事。',
  'RS保持忙碌与当前承受能力可能冲突；旧亲密关系/同事的慢谈经历不能直接移植到当前大学朋友。',
  '情境适用性和人物边界；不能预定资源一定有益。',[8,14,16],None),
 (103,'因小组讨论中被同学否定而感到不被重视，希望得到理解。',
  '贴合小组冲突与被忽视感；不虚构当前AI的个人职场经历，也不把项目争论改为用户职场事实。',
  'RS已有ai_action可用一般观察或假设例子；完整历史的论文/家庭问题不自动等于这次争论。',
  '已见来源回归；角色边界比强制使用资源重要。',[2,4,6],None),
 (106,'已经讨论微目标，最新提出导师难相处这一障碍。',
  '承接导师困难或请其具体说明；单纯重复微目标未必回应最新转折，不能称计划已经完成。',
  'ME记载过去计划整合导师反馈，属于计划，不是成功结果；可以澄清当前是否仍适合，但不能替用户认定导师始终有帮助。',
  '有相关过去行动阶段可核查；任务完成与策略建议的适时性分开。',[18,21],"I'm planning to focus on integrating the feedback from my advisor now. I feel more motivated to push through."),
 (107,'因实习、学业和关系压力求助，谈话末尾表示稍感轻松并致谢。',
  '可以承接减轻的感受或支持拟议的沟通；不能凭school pressures断言当前考试，也不能把主管沟通计划说成已完成。',
  'RS考试背景无当前/已取资源的具体依据；MS含曾考虑限制工作时长、为Matthew留时间的计划，ME旧offer不能覆盖当前实习状态。',
  '明确的具体情境套用风险，加有依据的过去计划机会；过去计划未必适合本轮收尾。',[2,6,10,16,18],"Maybe I'll try setting aside specific time for Matthew and limiting my work time each day."),
 (108,'对减少饮酒、维系婚姻的支持表示感谢，正在收尾。',
  '简短回应收尾可以适当；不把减少饮酒说成已经彻底戒除，不保证关系已恢复。',
  'RS历史戒酒经历只可在既有身份约束下参考，未必需要继续给建议；四类组合缺ME。',
  '当前信息足够、合理不使用的回归检查。',[7,19,21],None),
 (110,'因母亲病情和照护压力感到无力，也担心给姐姐增加负担。',
  '承接无力与负担感；明确已与姐姐谈过的事实，不重新把它说成未知或尚未发生。',
  'RS核对理解有当前依据，可以具体概括后开放澄清；四类组合缺MP。',
  '有依据的开放探询正向机会，但不必须使用这条策略；历史已见回归。',[3,7,9,11],None),
 (112,'照护与工作负担叠加，想休息又感到内疚。',
  '贴合休息与愧疚的矛盾、已尝试分担但仍吃力；不是再从零询问发生了什么。',
  'RS是否承担过多有当前依据；MS记录过去喜欢散步并考虑恢复，可作具体可选探询，不能说已经执行或已证实有效。',
  '有依据的RS探询和历史补充机会；没有显式回忆型请求。',[5,9,13],"I used to enjoy going for walks. Maybe I could start doing that again."),
]


def main():
    prep=OUT.parent/'rs_transfer_preparation_20261019_v1'
    requests=read(prep/'input_requests_private.json')
    result=[]
    for index,need,minimum,resource,coverage,current_idxs,quote in CARDS:
        evidence=read(prep/f'sources/dev_{index:03d}.json')
        refs=[evidence['current_prefix'][i] for i in current_idxs]
        supplemental=[]
        if quote:
            req=next(r for r in requests if r['index']==index and r['counts']==[1,1,1,1])['request']
            resources=json.loads(req['messages'][0]['content'].split('<resources>\n')[-1][:-len('\n</resources>')])
            acquired='\n'.join(str(json.loads(r['content'])) for r in resources)
            assert quote in acquired
            for session in evidence['legal_past_sessions']:
                for turn in session['turns']:
                    if quote in turn['text']:
                        supplemental.append(dict(date=session['date'],**turn,exact_quote=quote))
            assert supplemental
        result.append(dict(index=index,current_need=need,minimum_task_observation=minimum,
            resource_contribution_or_limit=resource,coverage=coverage,
            current_evidence=refs,acquired_history_support=supplemental,
            evidence_identity=digest(evidence),input_only=True,
            author='Codex analyst',human_label=False,formal_reward_label=False,
            explicit_history_recall_requirement=False,
            current_allows_at_least_one_plausible_reply=True,
            prior_current_text_fully_seen=index in (103,108,110)))
    doc=dict(version='rs-input-task-coverage-addendum-v1-20261019',status='INPUT_ONLY_ANALYST_DIAGNOSTIC_NOT_NEW_RUBRIC',
        inputs_unchanged=True,prepared_protocol_identity=digest(read(prep/'protocol.json')),
        cases=result,counts=dict(contexts=9,new_current_vs_prior_four=6,fully_seen_current_regressions=3,
            analyst_observed_explicit_history_recall_requests=0,
            illustrated_acquired_history_opportunities=4),
        limitations=['input relevance is not realized output benefit','no case requires a single exact response',
            'all nine allow at least one plausible source-safe reply from current input; this is not human-certified OFF adequacy',
            'four chosen history examples are illustrative evidence, not exhaustive positive-gold labels',
            'actual use may be appropriate or unnecessary; no compulsory adoption score'],model_calls=0)
    save_once(OUT/'coverage_addendum.json',doc)
    lines=['# 41次输入覆盖补充（运行前）','',
        '依据既定9项当前对话和合法已取资源，由分析者记录；不改提示、原清单、q/m或人评。以下“最低要求”是本批观察点，不是已经批准的新奖励量表。', '',
        '| 前缀 | 当前需要与可接受回应的边界 | 资源能补什么／不能推什么 |',
        '|---|---|---|']
    for r in result:
        lines.append(f"| {r['index']} | {r['current_need']} {r['minimum_task_observation']} | {r['resource_contribution_or_limit']} |")
    lines+=['','覆盖结论：9项都没有明确要求查回过去某条独有信息的请求；输入层面均可构造一种不取历史的合理回应，尚不能因此断言所有实际OFF都合格。',
        '存在有据可用的机会：110/112的RS探询贴合当前情境；99/106/107/112有可逐句核查的已取历史补充。它们支持检查误用和过度忽略，不预先证明历史会改善完成度，更不要求每条都采用。',
        '107的考试情境、99过程成功泛化、101忙碌与精力边界、103/108人物经历归属提供不同反例或边界。6个新增当前与3个已见回归分列。',
        '本批没有覆盖充分的“没有历史就无法完成的请求”，也不单独识别MP/MS/ME各自贡献（组合同时含四类）。不临时加题，不在看输出后改要求。',
        '', '四个有据历史补充示例（完整来源仍在原准备包sources中）：']
    for r in result:
        for s in r['acquired_history_support']:
            lines.append(f"- {r['index']} · {s['id']} · {s['date']} · {s['role']}: {s['exact_quote']}")
    with (OUT/'COVERAGE_ZH.md').open('x') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps(doc['counts']))


if __name__=='__main__':main()

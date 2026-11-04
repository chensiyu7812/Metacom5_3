"""Persist this assistant's completed content inspection, not human scores."""
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.durable import save_json_once
from metacom_pm.rl1.schema import digest
ROOT=PROJECT/'outputs/pm_rl1/executor_revision_20261104_v2'


def read(p):return json.loads(p.read_text())


def main():
    results=read(ROOT/'RESULTS_PRIVATE.json');notes={
        'N02':'OFF/MS均聚焦当前感谢便条；未把主管旧事作为必须展示的细节。不能把保持合理忽略解释为所有MS收益为零。',
        'N03':'OFF/MS均为许可和邀请，适合未说明问题的当前请求；没有强行提起考试或前任。',
        'N04':'多条件更接近边界/自我价值的示范表达；仍主要根据当前已知尝试困难，未显示目标MS带来决策差异。部分建议重复说不，效用未独立评定。',
        'N18':'OFF/RS保持绩效警告主题。OTHER仍把旧关系压力当成当前负担；panel_ON提及过去AA/工作压力有原话但是否有助当前警告未证明。',
        'N21':'OFF/RS/OTHER/MEMORY均未声称曾互留休息时间，但MEMORY也未采用这条示范中的关键事实；更像聚焦当前/分步提问的文风迁移。RS4中you mentioned feeling stuck是解释性转述，不是用户逐字用词。',
        'N23':'两MS训练输入和单MS面板输入均未采用过去主动邀请朋友的关键事实。OFF/OTHER未泄漏该事实，但数条输出把用户认为亲近扩成对方声称关心，存在无依据加强。',
        'N05':'未参与更新的ON提及过去担心工作中暴露脆弱，有MS seeker原话。OFF也能讨论调整要求；不能因增加该事实而判正收益。',
        'N08':'未参与更新；两条件采用当前已有的写作、自我宽待内容，无需把它算作读历史获得。',
        'N10':'未参与更新；孩子笑容、slowly opening up、still a bit shaken都在当前上下文，不是MS新增收益。',
        'N15':'未参与更新；聚焦当前Jerry疏远和重新联系，未将旧婚姻/工作压力拉入当前回复。',
        'N16':'未参与更新；哮喘/感冒来自当前发言，ON改变关怀方向。未据此评定临床安全或支持优劣，也不能把泛化的self-care说法当作历史使用收益。',
        'N19':'未参与更新；回复聚焦当前绩效/工作压力，未利用历史财务负担来形成不同决策。当前回复也未建议立即辞职，因此未采用该史实不自动是错误。'}
    reviewed=[]
    for r in results:
        anchors=[]
        for phrase,issue in [
            ('already dealing with the emotional weight of a past relationship','past report asserted as current burden'),
            ('someone who claims to care about you','care claim attributed without explicit current/source support'),
            ("You mentioned earlier that work stress wasn't helping with your AA meetings",'source-supported history mention; usefulness not established'),
            ("worried about being too vulnerable at work",'source-supported history mention outside update; not a gain label')]:
            if phrase in r['after']:
                begin=r['after'].index(phrase);anchors.append(dict(quote=phrase,start=begin,end=begin+len(phrase),issue=issue))
        reviewed.append(dict(input_identity=r['input_identity'],case=r['case'],conditions=r['conditions'],
            before_identity=r['before_identity'],after_identity=r['after_identity'],
            complete_before_after_and_current_read=True,resource_claims_checked_against_visible_sources=True,
            note=notes[r['case']],anchors=anchors,human_quality_label=None,quality=None,reward=None))
    primary=[]
    for case in ('N21','N23'):
        r=next(r for r in results if r['case']==case and 'fit_MEMORY' in r['conditions'])
        primary.append(dict(case=case,input_identity=r['input_identity'],reply_identity=r['after_identity'],
            intended_fact='previously trying to give each other breaks' if case=='N21' else 'previously inviting friends to own events',
            fact_used_in_original=False,fact_used_in_candidate=False,quality_preference=None))
    save_json_once(ROOT/'CONTENT_REVIEW_PRIVATE.json',stamp(dict(reviewer='same AI assistant; no independent helpfulness rating',
        method='Manual full-response/current-context inspection; source quotes and modality checked in visible bundles. Absence findings are semantic reading, not keyword reward.',
        rows=reviewed,primary_history_targets=primary,qualified_reward=False,
        target_fact_leak_in_OFF_or_OTHER_observed=False,leak_scope='Only the two explicitly taught facts, not an all-hallucination pass.',
        production_decision='Do not promote this candidate; intended historical decision use absent and irrelevant/history-current concerns remain.')))
    print('32 exact comparisons reviewed; primary fact use 0/2; no quality labels assigned')


if __name__=='__main__':main()

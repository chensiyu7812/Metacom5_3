"""Descriptive follow-up analysis; keep all submitted labels intact."""
from pathlib import Path
from collections import Counter
import json, hashlib, csv, shutil

OUT=Path(__file__).resolve().parent
SOURCE=Path('/home/tokkio/六题复核_完整记录.json')
EXAMPLES=Path('/home/tokkio/人评复核_20260917/clarification_examples.json')
PREVIOUS=Path('/home/tokkio/人评结果分析_20260917')

def unique(pairs):
    d={}
    for k,v in pairs:
        if k in d: raise ValueError('Duplicate JSON key: '+k)
        d[k]=v
    return d

def read(p): return json.loads(p.read_text(encoding='utf-8'),object_pairs_hook=unique)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def run():
    follow=read(SOURCE);examples=read(EXAMPLES)
    assert follow['schema']=='paper1-six-case-followup-review-v1'
    assert follow['record_type']=='posthoc_human_review'
    assert follow['source_clarification_digest']==sha(EXAMPLES)
    expected={e['case_id']:e for e in examples['examples']}
    earlier={r['presentation_id']:r for r in read(PREVIOUS/'aligned_ratings.json')}
    evidence={r['presentation_id']:r for r in read(PREVIOUS/'重点案例证据.json')}
    assert len(follow['items'])==len(expected)==6
    assert len({r['case_id'] for r in follow['items']})==6
    assert len({r['presentation_id'] for r in follow['items']})==6
    assert set(expected)=={r['case_id'] for r in follow['items']}
    interpretations={
        3:('事实表述仍需修正；方向可讨论','都正确提到了记忆这一理由不成立：候选 A 指定狗并提费用，所示历史只明确宠物、责任和工时。若认为未支持的细节不构成实质净差异，equivalent 仍可讨论，但必须明确权衡，不能把两边都当作已核实正确。','保留此次 equivalent；标注未支持细节及 materiality 分歧，不替用户改判。'),
        11:('关键事实遗漏；保留无法判断','候选 A 的 Step 5 已写克服问题、同居和关系加强，与参考的最终分手相反；不只是分析被截断。B 未完成摘要，但原句解释了信息不足，并不是只有一个“不做”。uncertain 可保留，当前理由还没有处理这一事实反转。','保留此次 uncertain；记录截断、相反结局、拒答体验是不同问题。'),
        27:('本例口径已澄清','B 的完整回答与参考一致，直接回答 California；A 最终是 unknown。由 uncertain 改为 B_better，理由与 QA 标准相符。','保留为后续复核判断，不回填或覆盖原始 A。'),
        64:('本例口径已澄清','两个回复逐字相同且同样差，选择 equivalent 符合既定比较定义；对拒答语气的批评可以另行保留。','保留为后续复核判断；不把同样差误写成双方优质。'),
        81:('胜出理由仍与参考事实冲突','参考 Unknown；候选 B 自行列出发现问题、联系 HR、问题已解决的日期和过程，题目证据不支持这些事实。它自称相关记忆或分析不构成独立证据；即便续写完成，也不能据此视为答对。','保留提交的 B_better；标记该理由不足以建立事实校准参照，不自动采纳 AI 或助手的另一方向。'),
        95:('原有相当判断可保留','一方直接给沟通示例，另一方先询问是否想要建议；本题未给出明确的回复风格偏好，没有必要强行分出胜者。与初评 equivalent 一致。','保留 equivalent 和偏好意见；不把一般偏好判断转成题中用户已知偏好或 MP 特征。')
    }
    rows=[]
    for item in follow['items']:
        e=expected[item['case_id']];prior=earlier[item['presentation_id']];full=evidence[item['presentation_id']]
        assert item['presentation_id']==e['presentation_id']
        assert item['original_a_item_number']==e['original_A_item']==prior['human_item_number']
        assert item['task']==prior['task']
        assert item['verdict'] in {'A_better','B_better','equivalent','uncertain'}
        assert isinstance(item['rationale'],str) and item['rationale'].strip()
        status,analysis,handling=interpretations[item['original_a_item_number']]
        rows.append({'case_id':item['case_id'],'presentation_id':item['presentation_id'],
          'original_a_item_number':item['original_a_item_number'],'task':item['task'],
          'original_verdict':prior['human_verdict'],'original_rationale':prior['human_rationale'],
          'followup_verdict':item['verdict'],'followup_rationale':item['rationale'],
          'verdict_changed':item['verdict']!=prior['human_verdict'],
          'AI_B_verdict_for_trace_only':prior['ai_verdict'],
          'followup_preference_basis':item['preference_basis'],'followup_preference_note':item['preference_note'],
          'assessment_status':status,'assistant_analysis_not_gold':analysis,'handling':handling,
          'A_finish_reason':prior['A_finish_reason'],'B_finish_reason':prior['B_finish_reason'],
          'input_en':full['task_input'],'reference_en':full['reference_material'],
          'candidate_A_en':full['response_A'],'candidate_B_en':full['response_B']})
    original_dir=OUT/'originals';original_dir.mkdir(exist_ok=True)
    dest=original_dir/SOURCE.name
    if dest.exists(): assert sha(dest)==sha(SOURCE), 'Do not replace archived intake'
    else: shutil.copy2(SOURCE,dest)
    save('逐题分析.json',rows)
    small_fields=['original_a_item_number','task','original_verdict','followup_verdict','verdict_changed','followup_rationale','assessment_status','assistant_analysis_not_gold','handling']
    with (OUT/'六题前后对照.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=small_fields);w.writeheader();w.writerows({k:r[k] for k in small_fields} for r in rows)
    summary={'scope':'Six targeted posthoc follow-up judgements; not independent holdout, not a new blind primary sheet.',
       'source_path':str(SOURCE),'source_sha256':sha(SOURCE),'source_clarification_digest_matches':True,
       'source_fingerprint_as_submitted':follow['source_fingerprint'],
       'source_fingerprint_verified':False,
       'presentation_IDs_and_original_item_numbers_match':True,'complete_items':6,
       'verdicts_changed':sum(r['verdict_changed'] for r in rows),'changed_A_item_numbers':[r['original_a_item_number'] for r in rows if r['verdict_changed']],
       'original_counts':dict(Counter(r['original_verdict'] for r in rows)),
       'followup_counts':dict(Counter(r['followup_verdict'] for r in rows)),
       'interpretation':{'clarified_in_this_example':[27,64],'prior_supported_equivalence_retained':[95],'evidence_or_weighting_issues_remain':[3,11,81]},
       'reviewer_metadata_as_submitted':{'reviewer_label':follow['reviewer_label'],'review_mode':follow['review_mode']},
       'time_note':'updated_at retained in original; not interpreted as reading duration.',
       'preference_note':'All six preference_basis values are not_recorded and notes are empty; no explicit user-preference evidence inferred.',
       'not_done':['overwrite original A/B','merge six ratings into the original 80-pair results','claim holdout accuracy or calibration success','create PM effect labels','run paid teacher or training','modify research authority'],
       'method_note':'Assistant qualitative findings are evidence-based diagnostics; not six newly adjudicated gold labels.'}
    save('summary.json',summary)
    n3=next(x for x in evidence.values() if x['human_item_number']==3)
    s=next(x for x in n3['complete_history']['sessions'] if x['timestamp']=='2025-11-05')
    save('A3_过去会话证据.json',s)
    save('source_manifest.json',[{'path':str(p),'sha256':sha(p)} for p in [SOURCE,EXAMPLES,PREVIOUS/'aligned_ratings.json',PREVIOUS/'重点案例证据.json']])
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary,rows

if __name__=='__main__': run()

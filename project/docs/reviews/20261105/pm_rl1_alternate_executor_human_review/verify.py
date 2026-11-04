"""Independent reconciliation from displayed HTML, original results and raw answers."""
import hashlib,html,json,re
from collections import Counter
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[4];BASE=PROJECT/'outputs/pm_rl1'
SOURCE=BASE/'alternate_executor_probe_20261104_v1';ROOT=BASE/'alternate_executor_human_review_20261105_v1'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def main():
    manifest=read(SOURCE/'OUTPUT_MANIFEST.json')
    for name,h in manifest.items():assert sha(SOURCE/name)==h,name
    intake=read(ROOT/'INTAKE_PRIVATE.json');received=read(ROOT/'RECEIVED_ANSWER_PRIVATE.json');summary=read(ROOT/'SUMMARY.json')
    assert sha(ROOT/'RECEIVED_ANSWER_PRIVATE.json')==intake['raw_sha256']
    for path,h in intake['sources'].items():assert sha(Path(path))==h,path
    assert received['study']=='pmrl1-alternate-'+read(SOURCE/'PROTOCOL.json')['identity']
    page=(SOURCE/'HUMAN_REVIEW_ZH.html').read_text();sections=dict(re.findall(r'<article id="(G\d+)">(.*?)</article>',page,re.S))
    results=read(SOURCE/'RESULTS_PRIVATE.json');rows=intake['answers'];counts={k:Counter() for k in ('within_G_resource','OFF_cross_G')}
    assert len(sections)==len(rows)==len(received['answers'])==8
    for row in rows:
        qid=row['question_id'];assert row['original_answer']==received['answers'][qid]
        off=next(r for r in results if r['case']==row['case'] and r['arm']=='A_OFF')
        if row['kind']=='within_G_resource':
            on=next(r for r in results if r['case']==row['case'] and r['arm']=='C_target_full_MS')
            candidates={'resource':on['new_reply'],'OFF':off['new_reply']}
        else:candidates={'alternate':off['new_reply'],'original':off['old_reply']}
        displayed={label:html.unescape(re.search('<h3>'+label+r'</h3><pre>(.*?)</pre>',sections[qid],re.S).group(1)) for label in 'AB'}
        assert set(displayed.values())==set(candidates.values())
        for label,text in displayed.items():
            assert row['alias_bindings'][label]['reply']==text and row['alias_bindings'][label]['reply_identity']==digest(text)
        choice=received['answers'][qid]['choice']
        if choice=='相当':expected='tie'
        else:expected=next(k for k,v in candidates.items() if v==displayed[choice[0]])+'_slightly_preferred'
        assert row['outcome']==expected;counts[row['kind']][expected]+=1
        assert row['numeric_reward'] is row['exact_qm'] is None and not row['qualified_reward']
    assert counts['within_G_resource']==Counter(resource_slightly_preferred=2,tie=4)
    assert counts['OFF_cross_G']==Counter(alternate_slightly_preferred=1,tie=1)
    assert summary['resource_comparisons']['outcomes']==dict(counts['within_G_resource']) and summary['OFF_cross_G']['outcomes']==dict(counts['OFF_cross_G'])
    assert next(r for r in rows if r['question_id']=='G06')['alias_bindings']['B']['model']=='alternate'
    assert '85分和95分' in received['answers']['G06']['reason'] and received['answers']['G06']['choice']=='B略好'
    assert summary['resource_comparisons']['planned']==7 and summary['resource_comparisons']['technical_failure_not_zero']==1
    registry=read(ROOT/'ANSWER_REGISTRY_PRIVATE.json');prior=read(BASE/'resource_value_probe_20261104_v1/ANSWER_REGISTRY_PRIVATE.json')
    assert len(registry)==44 and registry[:36]==prior and len({r['asset_id'] for r in registry})==44
    for row,record in zip(rows,registry[36:]):
        assert record['intake_identity']==digest(row) and record['raw_label']==row['original_answer']
        assert record['evidence']==row['evidence'] and digest(record['evidence'])==record['evidence_identity']
        assert all(digest(text)==key for key,text in record['replies'].items())
        assert record['numeric_reward'] is record['exact_qm'] is None and not record['qualified_reward']
    assert len({r['case'] for r in rows})==7 and len({r['owner'] for r in rows})==6
    for name,h in manifest.items():assert sha(SOURCE/name)==h,name
    checks=dict(status='PASS_WITH_RESEARCH_SCOPE_LIMITS',answers_bound_to_actual_display=8,study_match=True,G06_B_is_alternate_OFF=True,
        resource_slight=2,resource_ties=4,OFF_alternate_slight=1,OFF_ties=1,planned_primary_technical_failure_retained=1,
        historical_records_preserved=36,append_only_new_records=8,old_probe_files_unchanged=len(manifest),
        scalar_rewards_created=0,API_calls=0,model_loads=0,training_updates=0,new_human_questions=0)
    (Path(__file__).parent/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()

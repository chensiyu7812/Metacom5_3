"""One-off offline evidence export; no runner imports, requests or scoring."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, timedelta
import json, hashlib, subprocess

OUT = Path(__file__).resolve().parent
B = OUT.parent
R = B.parents[3]
used = {}
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
    p = Path(p).resolve(); used[str(p)] = sha(p)
    return json.loads(p.read_text())
def save(name, value):
    with (OUT / name).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')
plan = read(B/'plan.json')
live = B/'live_runs'
starts = []
for f in sorted(live.rglob('*.started.json')):
    j = read(f)
    if 'request' in j and j.get('mode') == 'live':
        starts.append((f,j))
assert len(starts)==54
counts = Counter(j['request']['candidate'] for _,j in starts)
slots = [j['request'].get('original_slot_request_id',j['request']['request_id']) for _,j in starts]
assert len(set(slots))==54
old_dirs = [R/'project/outputs/pm_rl1/completion_20260930_v2/P3/candidate_v1/development', R/'project/outputs/pm_rl1/p3_v2_after_confirmation_20261014/runs/development']
old_counts = [len(list(d.rglob('*.raw.json'))) for d in old_dirs]
assert old_counts == [33,33]
all_results=[]
for f,j in starts:
    result = read(f.with_name(f.name.replace('.started.','.result.')))
    all_results.append((f,result))
def measurement(j): return j['evaluation']['measurement'] if 'evaluation' in j else j['measurement']
statuses=Counter(measurement(j)['measurement_status'] for _,j in all_results)
critical=[]; material=[]; equivalent=[]
for f in sorted(live.rglob('*.review.json')):
    j=read(f)
    if j.get('critical_unknown'): critical.append(str(f))
    if j.get('material_source_proven_error'): material.append(str(f))
    if j.get('unexplained_equivalence_difference'): equivalent.append(str(f))
selected={('gemma4_12b_bf16','dev16A'),('gemma4_12b_bf16','dev04B'),('gemma4_12b_bf16','dev06B'),('gemma4_12b_bf16_thinking','dev02B'),('gemma4_12b_bf16_thinking','dev04B'),('gemma4_12b_bf16_thinking','dev06A'),('deepseek_flash_off','dev37A'),('deepseek_flash_off','dev37B'),('deepseek_flash_high','dev04B'),('deepseek_flash_high','dev06A'),('deepseek_flash_high','dev06B'),('deepseek_flash_high','dev15B'),('deepseek_flash_high','dev10B')}
records=[]
annex=['# 代表原文与来源附件（本地私有）', '本附件是协调者证据材料，不是盲评问卷或新增独立人评。只复制完整 final；不从 thinking 提取判断，不解析或修复 D10B 内部重复键。原评分、失败、STOP 保持原样。完整合法来源另见 sources/，其中只有已暴露开发材料。']
for f,j in all_results:
    q=j['request']; key=(q['candidate'],q['item_key'])
    if key not in selected: continue
    rp=f.with_name(f.name.replace('.started.','.response.'))
    raw=read(rp) if rp.exists() else None
    final=None
    if raw:
        if 'native_parsed' in raw: final=raw['native_parsed'].get('content')
        elif raw.get('choices'): final=raw['choices'][0]['message'].get('content')
    assert final is None or isinstance(final,str)
    m=measurement(j)
    rec=dict(candidate=key[0],item=key[1],request_id=q['request_id'],original_slot=q.get('original_slot_request_id',q['request_id']),result_path=str(f.with_name(f.name.replace('.started.','.result.'))),response_path=str(rp) if rp.exists() else None,original_measurement=m,complete_final=final,reply=plan['items'][key[1]]['reply'],evidence_identity=plan['items'][key[1]]['evidence_identity'])
    records.append(rec)
    annex += [f"\n## {key[0]} / {key[1]}", f"request_id: `{q['request_id']}`\n\n状态：{m['measurement_status']}；原 q={m.get('q')}，m={m.get('m')}。",'完整待评回复：\n\n'+rec['reply'],'完整 final：\n\n'+('```text\n'+final+'\n```' if final is not None else '没有完整 final；不得从残片或思考补出答案。'),f"原始记录：[response]({rp})；[result]({rec['result_path']})；来源身份 `{rec['evidence_identity']}`。"]
legacy=read(R/'project/outputs/pm_rl1/p3_v2_development_audit_20261014/analysis/reply_comparisons_private.json')
for row in legacy:
    if (str(row['Chen_order']),row['side']) not in {('15','B'),('35','B'),('37','A'),('37','B')}: continue
    entry=row['new']; raw=read(entry['raw_path']); text=raw['text']
    # Same documented final boundary as the original parser; preserve final text.
    if '</think>' in text:
        assert text.count('</think>')==1
        final=text.split('</think>',1)[1].strip()
    else: final=text.strip()
    assert json.loads(final)==entry['raw_final_json']
    records.append(dict(candidate='historical_Qwen_v2',item=f"dev{int(row['Chen_order']):02d}{row['side']}",request_id=entry['request_id'],complete_final=final,reply=row['reply'],original_measurement=dict(q=entry['q'],m=entry['m'],U=entry['utility']),raw_path=entry['raw_path'],evidence_identity=row['evidence_identity']))
    annex += [f"\n## 历史 Qwen v2 / {row['Chen_order']}{row['side']}", '不与 A/B/C/D 当作同配置，亦不作为新独立案例。',f"request_id: `{entry['request_id']}`；q={entry['q']}，m={entry['m']}，U={entry['utility']}。",'完整待评回复：\n\n'+row['reply'],'完整 final（原 final 边界，未改内容）：\n\n```text\n'+final+'\n```',f"原始：[raw]({entry['raw_path']})；既有解析：[measurement]({entry['measurement_path']})。"]
save('selected_original_records.json',records)
(OUT/'EVIDENCE_ANNEX_ZH.md').write_text('\n\n'.join(annex)+'\n')
(OUT/'sources').mkdir()
source_index={}
for key in ['dev02B','dev04B','dev06B','dev15B','dev35B','dev37A','dev10B']:
    item=plan['items'][key]; ev=item['evidence']; lines=[f"{key}: complete legal source; identity {item['evidence_identity']}", f"current_date: {ev['current_date']}", '\nCURRENT PREFIX']
    turns=list(ev['current_prefix'])
    for t in ev['current_prefix']:lines.append(f"{t['id']} [{t['role']}] {t['text']}")
    for session in ev['legal_past_sessions']:
        lines.append(f"\nPAST SESSION {session['id']} {session['date']}")
        for t in session['turns']:lines.append(f"{t['id']} [{t['role']}] {t['text']}")
        turns.extend(session['turns'])
    p=OUT/'sources'/f'{key}_complete_legal_source.txt';p.write_text('\n\n'.join(lines)+'\n')
    source_index[key]=dict(evidence_identity=item['evidence_identity'],path=str(p),turns=len(turns),words=sum(len(t['text'].split()) for t in turns),sha256=sha(p))
save('source_index.json',source_index)
refs=read(B/'AB_diagnostic_continuation_20261015/reference_binding_addendum.json')
assert all(x['human_q'] is None and x['Du_independent_observations']==0 for x in refs['all_32_references'])
human=read(R/'project/outputs/pm_rl1/development_closeout_20261014_v1/acceptance_final/development_intake_private.json')
assert all(row['group']=='development' for row in human)
for rel in ['project/docs/pm_rl1_completion_20260930_v2/execution_contract.json','project/docs/pm_rl1_completion_20260930_v2/judge_selection_capacity_amendment_20261015.json','project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl','project/src/metacom_pm/rl1/schema.py','project/src/metacom_pm/rl1/env.py','project/src/metacom_pm/rl1/judge_completion.py','project/src/metacom_pm/rl1/judge_completion_candidate.py','project/docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md','project/docs/PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md','project/docs/PM_RL1_R04B_CANDIDATE_RESULTS_20260930_ZH.md']:
    p=R/rel;used[str(p)]=sha(p)
for p in list(live.rglob('STOP.json'))+[B/'outer_format_v1_20261015/protocol.json',B/'D_development_20261015/protocol.json',B/'D_development_20261015/cost_projection.json',B/'D_development_20261015/summary.json']:
    used[str(p)]=sha(p)
snapshot=dict(time=datetime.now(timezone(timedelta(hours=9))).isoformat(),repo=str(R),head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),branch=subprocess.check_output(['git','branch','--show-current'],cwd=R,text=True).strip(),current_chain_old_raw_counts=old_counts,current_chain_started=120,new_pool_started=54,by_candidate=dict(counts),new_pool_original_statuses=dict(statuses),critical_unknown_review_paths=critical,source_proven_review_paths=material,equivalence_review_paths=equivalent,new_pool_distinct_items=len({j['request']['item_key'] for _,j in starts}),new_pool_distinct_source_contexts=len({plan['items'][j['request']['item_key']]['evidence_identity'] for _,j in starts}),duplicate_original_slots=False,new_calls=0,new_human_observations=0,sealed_read=False,credentials_read=False,measured_unknown_not_reviewer_unknown=True,source_file_sha256=used)
save('diagnosis_manifest.json',snapshot)
print(json.dumps({k:v for k,v in snapshot.items() if k!='source_file_sha256'},ensure_ascii=False,indent=2))

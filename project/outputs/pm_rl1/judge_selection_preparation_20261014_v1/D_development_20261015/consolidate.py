"""Offline closeout from recorded starts/results/reviews; never sends requests."""
import sys,json,csv,hashlib,statistics
from pathlib import Path
from decimal import Decimal
B=Path(__file__).resolve().parent.parent;OUT=Path(__file__).resolve().parent
sys.path[:0]=[str(B/'outer_format_v1_20261015'),str(B)]
import selection as s,continue_v1 as c
P=s.read(OUT/'protocol.json');PLAN=s.load_plan();ROOT=B/'live_runs'
history=c.reconstruct(PLAN,P,ROOT);refadd=s.read(B/'AB_diagnostic_continuation_20261015/reference_binding_addendum.json');refs={r['item_key']:r for r in refadd['all_32_references']}
results={}
for stage in ['output_interface_v1_CD_engineering','output_interface_v1_D_development']:
 for f in (ROOT/stage/s.CANDIDATES[3]).glob('*.result.json'):
  r=s.read(f);raw=s.read(f.with_name(f.name.replace('.result.','.response.')));rid=r['request']['request_id'];reviewpath=ROOT/stage/'stage'/(rid+'.review.json');diagpath=ROOT/stage/'stage'/(rid+'.diagnostic.json')
  results[r['original_request']['request_id']]=(r,raw,s.read(reviewpath) if reviewpath.exists() else None,s.read(diagpath) if diagpath.exists() else None,str(f))
rows=[]
for i,req in enumerate(P['requests'],1):
 orig=next(x for x in PLAN['requests'] if x['request_id']==req['original_slot_request_id']);item=PLAN['items'][req['item_key']]
 row=dict(slot=i,item=req['item_key'],draw=req['draw'],phase=req['phase'],original_slot=orig['request_id'],reply=item['reply'],reply_identity=s.digest(item['reply']),evidence_identity=item['evidence_identity'],started=orig['request_id'] in history['slot_owners'],q=None,m=None,U=None,model_unknown=None,reviewer_unknown=None,source_proven_error=None,equivalence_error=None,eligible=False)
 if row['started']:
  result,raw,review,diag,path=results[orig['request_id']];m=result['evaluation']['measurement'];acct=result['financial_accounting']
  row.update(request_id=result['request']['request_id'],record_class='prior_D_engineering' if '/output_interface_v1_CD_engineering/' in path else 'new_D_development_diagnostic',status=m['measurement_status'],q=m.get('q'),m=m.get('m'),U=m.get('candidate_utility'),final=raw['choices'][0]['message']['content'],measurement=m,review=review,diagnostic=diag,model_unknown=m['measurement_status']=='semantic_uncertainty',reviewer_unknown=review.get('critical_unknown') if review else None,source_proven_error=review.get('material_source_proven_error') if review else None,equivalence_error=review.get('unexplained_equivalence_difference') if review else None,usage=raw.get('usage'),tokens=s.token_accounting(raw) if hasattr(s,'token_accounting') else None,elapsed_seconds=raw['total_seconds'],accounted_upper_usd=acct.get('accounted_upper_usd'),usage_price_estimate_usd=acct.get('usage_price_estimate_usd'),result_path=path,raw_path=path.replace('.result.','.raw.'),response_sha256=s.sha(path.replace('.result.','.response.')))
 else:row.update(record_class='not_dispatched',status='not_dispatched',reason=history['blocked'].get(s.CANDIDATES[3],'authorized stage cap or finance guard; see stage_result'))
 if row['draw']=='primary' and row['item'] in refs:
  ref=refs[row['item']];assert row['reply_identity']==ref['reply_identity'];row['human_reference']=ref
 rows.append(row)
primary={r['item']:r for r in rows if r['draw']=='primary'}
pairs=[]
for case in sorted({k[3:5] for k in primary}):
 a,b=primary['dev'+case+'A'],primary['dev'+case+'B'];h=a['human_reference'];model=None
 if a['U']is not None and b['U']is not None:model='tie' if a['U']==b['U'] else 'A' if a['U']>b['U'] else 'B'
 comparable=model is not None and h['preference_comparable']
 pairs.append(dict(case=case,human=h['human_preference'],model=model,comparable=comparable,match=(model==h['human_preference'] if comparable else None),reviewer_disputed=bool(a['reviewer_unknown'] or b['reviewer_unknown']),exclusion=None if comparable else 'model missing' if model is None else 'human unknown',absolute_gold=False))
risks=[]
for key,row in primary.items():
 ref=row['human_reference'];human=ref['human_risk_level'];expected={'none_detected':0,'local':.25,'severe':1}.get(human);comparable=row['m']is not None and expected is not None
 risks.append(dict(item=key,human=human,model_m=row['m'],comparable=comparable,match=(row['m']==expected if comparable else None),reviewer_disputed=row['reviewer_unknown'],exclusion=None if comparable else 'model missing' if row['m']is None else 'human unknown',absolute_gold=False))
measured=[r for r in rows if r['started']];new=[r for r in measured if r['record_class']=='new_D_development_diagnostic']
def usage_summary(data):
 return dict(attempts=len(data),input_tokens=sum(r['usage']['prompt_tokens'] for r in data),output_tokens=sum(r['usage']['completion_tokens'] for r in data),thinking_tokens=sum(r['usage']['completion_tokens_details']['reasoning_tokens'] for r in data),final_tokens=sum(r['usage']['completion_tokens']-r['usage']['completion_tokens_details']['reasoning_tokens'] for r in data),response_seconds=sum(r['elapsed_seconds'] for r in data),usage_price_estimate_usd=str(sum((Decimal(r['usage_price_estimate_usd']) for r in data),Decimal(0))),accounted_upper_usd=str(sum((Decimal(r['accounted_upper_usd']) for r in data),Decimal(0))),latency_min_mean_max=[min(r['elapsed_seconds'] for r in data),statistics.mean(r['elapsed_seconds'] for r in data),max(r['elapsed_seconds'] for r in data)]) if data else {'attempts':0}
summary=dict(time_jst=c.now(),cumulative=history['cumulative_calls'],capacity=289,stage_hard_cap=143,new=usage_summary(new),D_all=usage_summary(measured),D_coverage=dict(all=len(measured),denominator=40,primary=sum(r['draw']=='primary' for r in measured),primary_denominator=32,repeats=sum(r['draw']=='repeat-1' for r in measured),repeat_denominator=4,variants=sum(r['draw']=='variant-1' for r in measured),variant_denominator=4),model_unknown=sum(r['model_unknown']is True for r in rows),reviewer_unknown=sum(r['reviewer_unknown']is True for r in rows),source_proven_error=sum(r['source_proven_error']is True for r in rows),equivalence_error=sum(r['equivalence_error']is True for r in rows),technical_failures=sum(r['started'] and r['status'] not in s.VALID for r in rows),pair_comparable=sum(r['comparable'] for r in pairs),pair_matches=sum(r['match']is True for r in pairs),pair_total=16,risk_comparable=sum(r['comparable'] for r in risks),risk_matches=sum(r['match']is True for r in risks),risk_total=32,qualification='NOT_GRANTED',independent_human_observations_added=0)
s.save(OUT/'results_private.json',dict(summary=summary,rows=rows,pairs=pairs,risks=risks,reference_binding=str(B/'AB_diagnostic_continuation_20261015/reference_binding_addendum.json')))
s.save(OUT/'summary.json',summary)
cols=['slot','item','draw','phase','original_slot','request_id','record_class','started','status','q','m','U','model_unknown','reviewer_unknown','source_proven_error','equivalence_error','eligible','elapsed_seconds','usage_price_estimate_usd','accounted_upper_usd','reason']
with (OUT/'all_40_slots_private.csv').open('x') as f:
 w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
text=['# D完整原文、分数和来源复核附件','只读取完整final；思考内容不作为答案。Codex复核不是独立人评。所有原分数保持不变。']
for r in rows:
 text += [f"\n## 槽{r['slot']} {r['item']} / {r['draw']}",f"状态：{r['status']}；原槽：`{r['original_slot']}`。",'待评回复：\n\n'+r['reply']]
 if r['started']:
  text += [f"q={r['q']}，m={r['m']}，U={r['U']}；请求`{r['request_id']}`。",'完整final：\n\n```json\n'+r['final']+'\n```','来源复核（不改分）：\n\n'+json.dumps(r['review'],ensure_ascii=False,indent=2),f"原始输出：{r['raw_path']}\n\n结果：{r['result_path']}"]
 else:text += [r['reason']]
(OUT/'ORIGINALS_AND_SOURCE_REVIEW_ZH.md').write_text('\n\n'.join(text)+'\n')
base=s.read(OUT/'baseline.json');changed=[p for p,h in base['old_files'].items() if not Path(p).exists() or s.sha(p)!=h];ledger=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl';prefix=hashlib.sha256(ledger.read_bytes()[:base['ledger_prefix_bytes']]).hexdigest();assert not changed and prefix==base['ledger_prefix_sha256']
s.save(OUT/'targeted_final_integrity.json',dict(all_old_files_unchanged=True,old_file_count=len(base['old_files']),old_ledger_prefix_unchanged=True,actual_cumulative=history['cumulative_calls'],new_scoring_attempts=len(new),duplicate_original_slots=False,interface_identity=P['interface']['identity'],plan_identity=PLAN['identity']))
print(json.dumps(summary,ensure_ascii=False,indent=2))

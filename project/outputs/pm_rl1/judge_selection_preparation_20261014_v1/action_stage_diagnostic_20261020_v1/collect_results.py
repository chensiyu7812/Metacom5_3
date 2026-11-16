from pathlib import Path
import sys,json,csv,shutil,time
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parent))
import action_stage as a
from action_stage import s,p
from deepseek_access import cost_from_usage
from adapters import token_accounting

def main():
 protocol,items=a.load();out=a.HERE
 result=a.summary(protocol,a.ROOT,a.historical_count())
 assert (a.ROOT/'stage_result.json').exists() or (a.ROOT/'STOP.json').exists(),'execution still active'
 old=s.read(a.BASE/'paired_diagnostic_20261019_v1/package/protocol.json')
 oldroot=a.BASE/'paired_diagnostic_runs'/p.STUDY/'live'
 baselines={x['item_key']:s.read(oldroot/(x['slot_id']+'.result.json')) for x in old['schedule'] if x['component']=='joint'}
 records=[];finals=['# 本批全部完整final、回复及来源核对\n\n所有final仅来自完整content；原始reasoning通道只随本地raw保存，不用于评分。Codex复核不计独立人评。\n']
 for slot in result['slots']:
  key=slot['item_key'];item=items[key];sid=slot['slot_id'];r=slot['result'];review=slot['review'];base=baselines[key]
  raw=s.read(a.ROOT/(sid+'.response.json')) if (a.ROOT/(sid+'.response.json')).exists() else None
  value=r['evaluation'] if r else {}
  row=dict(position=slot['position'],item=key,kind=slot['kind'],slot_id=sid,context_id=item['context_id'],
   state=slot['state'],not_dispatched_reason=slot['not_dispatched_reason'],request_identity=r['request_identity'] if r else None,
   full_runtime_identity=protocol['identity'],effective_system_prompt_sha256=protocol['immutable_files'][str(a.PROPOSAL/'PROPOSED_JOINT_PROMPT_EN.txt')],
   parser_rubric_identity_is_base_not_full_prompt=True,semantic_revisions_applied=2,reply_identity=s.digest(item['reply']),evidence_identity=s.digest(item['evidence']),
   q=value.get('q'),m=value.get('m'),U=value.get('U'),model_unknown=value.get('model_unknown'),
   technical_valid=r['technical_valid'] if r else None,reviewer_unresolved=bool(review and review['unresolved_ambiguities']),
   source_proved_substantial_errors=review['source_proved_substantial_errors'] if review else None,
   review=review,full_final=raw['choices'][0]['message']['content'] if raw else None,
   complete_final=bool(raw and raw['choices'][0]['finish_reason']=='stop'),usage=r['usage'] if r else None,
   token_accounting=token_accounting(raw) if raw else None,financial=r['financial'] if r else None,
   usage_cost_estimate=cost_from_usage(raw) if raw and raw.get('usage') else None,
   seconds=r['elapsed_seconds'] if r else None,system_fingerprint=r['fingerprint'] if r else None,
   baseline_q=base['evaluation']['q'],baseline_m=base['evaluation']['m'],baseline_U=base['evaluation']['U'],baseline_request_identity=base['request_identity'],
   reward_eligible=False,local_GPU_seconds=0)
  records.append(row)
  finals.append(f"\n## {slot['position']:02d} {key} / {slot['kind']} — {slot['state']}\n\n完整待评回复：\n\n{item['reply']}\n\n来源：sources/{item['context_id']}_complete.txt；输入/回复/来源哈希见per_request_results.json。\n")
  if raw:finals.append('\n完整final：\n\n```json\n'+row['full_final']+'\n```\n')
  if review:
   finals.append('\n分析者来源核对（不是新增人评）：\n\n'+json.dumps(review,ensure_ascii=False,indent=2)+'\n')
  elif row['not_dispatched_reason']:finals.append('\n未派发：'+row['not_dispatched_reason']+'\n')
 s.save(out/'per_request_results.json',records)
 (out/'ALL_FINALS_AND_SOURCE_REVIEW_ZH.md').write_text(''.join(finals))
 sourceout=out/'sources';sourceout.mkdir()
 for context in sorted({x['context_id'] for x in items.values()}):
  shutil.copyfile(a.BASE/'paired_diagnostic_20261019_v1/package/sources'/f'{context}_complete.txt',sourceout/f'{context}_complete.txt')
 s.save(out/'bound_items.json',items)
 primary={r['item']:r for r in records if r['kind']=='primary'}
 repeats=[]
 for r in records:
  if r['kind']!='prespecified_repeat':continue
  first=primary[r['item']]
  repeats.append(dict(item=r['item'],first_slot=first['slot_id'],repeat_slot=r['slot_id'],
   paired_complete=first['technical_valid'] is True and r['technical_valid'] is True,
   first_q_m_U=[first[k] for k in ('q','m','U')],repeat_q_m_U=[r[k] for k in ('q','m','U')],
   delta_U=r['U']-first['U'] if r['U'] is not None and first['U'] is not None else None,
   exact_numeric_equal=all(first[k]==r[k] and first[k] is not None for k in ('q','m','U')),
   independent_new_case=False))
 s.save(out/'repeat_comparison.json',repeats)
 result['reviewer_unresolved_records']=sum(r['reviewer_unresolved'] for r in records)
 result['reviewer_unresolved_distinct_replies']=len({r['item'] for r in records if r['reviewer_unresolved']})
 result['primary_numeric_comparable']=sum(r['q'] is not None and r['m'] is not None for r in primary.values())
 result['planned_repeat_pairs']=4;result['complete_repeat_pairs']=sum(x['paired_complete'] for x in repeats)
 result['numerically_equal_repeat_pairs']=sum(x['paired_complete'] and x['exact_numeric_equal'] for x in repeats)
 result['usage_cost_estimate_usd']=str(sum(s.Decimal(r['usage_cost_estimate']['usage_price_estimate_usd']) for r in records if r['usage_cost_estimate']))
 result['invoice_confirmed']=False
 result['old_fingerprints']=sorted({x['fingerprint'] for x in baselines.values() if x.get('fingerprint')})
 result['new_fingerprints']=sorted({r['system_fingerprint'] for r in records if r['system_fingerprint']})
 result['historical_comparison_not_contemporaneous']=True
 result['finished_at']=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()
 s.save(out/'results_summary.json',result)
 fields=['position','item','kind','context_id','state','q','m','U','model_unknown','reviewer_unresolved','seconds','baseline_q','baseline_m','baseline_U','not_dispatched_reason']
 with (out/'SLOTS_12.csv').open('x',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(records)
 start=s.read(out/'start_receipt.json')
 assert all(s.sha(k)==v for k,v in start['old_stop_hashes'].items())
 assert a.LEDGER.read_bytes().startswith((out/'provenance/paid_ledger.before.jsonl').read_bytes())
 s.save(out/'final_verification.json',dict(old_stop_hashes_unchanged=len(start['old_stop_hashes']),ledger_original_prefix_preserved=True,
  protocol_and_inputs_verified=True,proposal_bytes_unchanged=True,cumulative=result['cumulative'],new_attempts=result['started'],
  final_interface_unchanged=True,no_retries=True,no_GPU=True,no_training=True,old_D_143_boundary_unchanged=True,
  no_sealed_data=True,no_commit_or_push=True))
 print(s.canonical({k:result[k] for k in ('started','cumulative','technical_complete','model_unknown','reviewer_unresolved_records','prompt_tokens','completion_tokens_including_thinking','request_seconds','accounted_upper_usd','unresolved_liability_usd','complete_repeat_pairs','numerically_equal_repeat_pairs')}))
if __name__=='__main__':main()

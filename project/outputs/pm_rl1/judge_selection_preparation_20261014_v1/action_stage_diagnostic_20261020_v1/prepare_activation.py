from pathlib import Path
import json,sys,shutil,datetime,os
from zoneinfo import ZoneInfo
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import action_stage as a
from action_stage import s,p
os.umask(0o077)
assert s.read(HERE/'offline_test_receipt.json')['passed']
proposal=s.read(a.PROPOSAL/'proposal.json')
assert s.sha(a.PROPOSAL/'proposal.json')=='dd0d0fd4e0310aef566c2fd035c1cdaf5a954d9effb5e8c747ed1a0b54e191ce'
assert a.historical_count()==144
old=s.read(a.BASE/'paired_diagnostic_20261019_v1/package/protocol.json')
old_paired=a.BASE/'paired_diagnostic_20261019_v1/paired.py'
old_code=old['immutable_files'][str(old_paired)]
assert s.sha(HERE/'provenance/paired.py.before')==old_code
for file,digest in old['immutable_files'].items():
 if file!=str(old_paired):assert s.sha(file)==digest,file
for row in proposal['schedule']:
 assert s.sha(a.PROPOSAL/'payloads'/f"{row['position']:02d}_{row['item']}.json")==row['payload_sha256']
items=s.read(a.BASE/'paired_diagnostic_20261019_v1/package/items.json')
for row in proposal['schedule']:
 item=items[row['item']];messages,schema=a.payload(item,'joint')
 saved=s.read(a.PROPOSAL/'payloads'/f"{row['position']:02d}_{row['item']}.json")
 assert messages==saved['messages'] and schema==saved['schema']
 p.input_guard(messages)
trial=old['financial_baseline']['financial_trial_identity']
budget=p.DiagnosticBudget(a.LEDGER,trial=trial,study=a.STUDY,trial_cap=s.nanodollars(2),shared_cap=s.nanodollars(20),baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('0.03079930'))
total,money,reserved,settled=budget._totals(budget.events())
assert not set(reserved)-set(settled)
assert s.usd(money)=='0.3800799'
assert s.usd(total)=='1.88732281'
shutil.copyfile(a.LEDGER,HERE/'provenance/paid_ledger.before.jsonl')
shutil.copyfile(s.REPO/'project/docs/PM_RL1_CURRENT_STATUS.md',HERE/'provenance/CURRENT_STATUS.before.md')
paths=list(a.PROPOSAL.rglob('*'))+[HERE/'action_stage.py',old_paired,a.BASE/'selection.py',a.BASE/'adapters.py',a.BASE/'outer_format_v1_20261015/deepseek_access.py',a.BASE/'paired_diagnostic_20261019_v1/live.py',a.BASE/'paired_diagnostic_20261019_v1/package/items.json',a.BASE/'measurement_decision_review_20261020_v1/READOUT_ADDENDUM_ZH.md']
paths += [Path(k) for k in old['immutable_files'] if k!=str(old_paired)]
immutable={str(f):s.sha(f) for f in sorted(set(paths)) if f.is_file()}
protocol=dict(version=a.STUDY,proposal_identity='3f54836f87b83965e8252bcfc82b2b359f48c963886570f537c8068e37a85867',
 proposal_file_sha256=s.sha(a.PROPOSAL/'proposal.json'),readout_sha256=s.sha(a.BASE/'measurement_decision_review_20261020_v1/READOUT_ADDENDUM_ZH.md'),
 config=proposal['config'],final_interface=proposal['final_interface'],schedule=[x|dict(item_key=x['item'],component='joint') for x in proposal['schedule']],
 baseline_cumulative=144,max_new=12,cumulative_stop=156,capacity=289,semantic_revisions_applied=2,
 prior_semantic_revisions_applied=1,original_semantic_revision_limit=1,authorized_exception='one additional action-stage reminder; no other prompt or rubric changes',
 failure_policy=proposal['failure_policy'],reward_eligible=False,old_stops_released=False,
 public_price_table_identity=old['public_price_table_identity'],immutable_files=immutable,
 financial_baseline=dict(ledger_sha256=s.sha(a.LEDGER),financial_trial_identity=trial,trial_accounted_usd=s.usd(money),shared_accounted_usd=s.usd(total),known_unsettled=0),
 source_review='Codex offline evidence checks, not independent human labels; each result bound before following dispatch',
 original_historical_runner_sha256=old_code,modified_runner_sha256=s.sha(old_paired))
protocol['identity']=s.digest(protocol);s.save(HERE/'protocol.json',protocol)
now=datetime.datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()
auth=dict(status='APPROVED',protocol_identity=protocol['identity'],study=a.STUDY,
 baseline_cumulative=144,new_request_limit=12,cumulative_cap=156,capacity=289,stage_cap_usd='1',trial_cap_usd='2',shared_cap_usd='20',
 semantic_revisions_previously_applied=1,additional_semantic_revision_authorized=1,
 credential_process_read_authorized=True,official_research_payload_authorized=True,
 management_requests={'models':1,'user/balance':1},old_stops_released=False,qualifies_reward=False,
 researcher_message='那你继续推进吧。',approval_context='Direct acceptance of the immediately preceding single 12-request/$1/extra-semantic-revision proposal, account queries and unchanged outbound whitelist.',recorded_at=now,
 exact_outbound=proposal['exact_outbound'],readout_sha256=protocol['readout_sha256'])
s.save(HERE/'APPROVED.json',auth);a.approved(protocol,auth)
s.save(HERE/'semantic_revision_amendment.json',dict(status='AUTHORIZED_FOR_THIS_STAGE',timestamp=now,base_contract=str(s.REPO/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json'),base_contract_sha256=s.sha(s.REPO/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json'),clause='measurement.semantic_revisions_max / completion plan section 8.3',previous_limit=1,previously_applied=1,new_stage_applied_count=2,additional=1,scope=a.STUDY,prior_results_invalidated=False,old_stops_released=False,prior_reruns_required=False,paper_claim_changed=False,qualification_thresholds_changed=False,old_contract_unchanged=True))
stops={str(f):s.sha(f) for root in (a.BASE/'live_runs',a.BASE/'paired_diagnostic_runs') for f in root.rglob('*STOP*.json')}
s.save(HERE/'start_receipt.json',dict(timestamp=now,baseline_count=144,old_stop_hashes=stops,ledger_sha256=s.sha(a.LEDGER),approval_sha256=s.sha(HERE/'APPROVED.json'),protocol_identity=protocol['identity'],planned=12,offline_tests=s.read(HERE/'offline_test_receipt.json'),private_files_not_transmitted=True))
print(s.canonical(dict(status='APPROVED_READY',protocol=protocol['identity'],baseline=144,old_stops=len(stops),trial_accounted=s.usd(money),shared_accounted=s.usd(total),new_model_calls=0)))

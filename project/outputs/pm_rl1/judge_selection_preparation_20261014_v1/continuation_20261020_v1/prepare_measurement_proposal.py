from pathlib import Path
import json,hashlib
from decimal import Decimal
R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3');B=R/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1'
P=B/'paired_diagnostic_20261019_v1/package';O=B/'continuation_20261020_v1/measurement_proposal';O.mkdir(mode=0o700,exist_ok=False);(O/'payloads').mkdir(mode=0o700)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def save(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2)
extra='''\n\nACTION-STAGE COVERAGE CHECK (same scale and evidence rules):
When checking each reply unit, include any personal factual presupposition carried by a question, not just declarative claims. Distinguish proposing an action, intending it, reporting it completed, and reporting its outcome. Check the subject, specific action, object or topic, and time separately. Evidence of a different conversation or a suggested action does not by itself establish that this particular action happened. An open invitation or genuinely conditional question does not by itself assert completion. Where the wording permits multiple readings, preserve uncertainty using the existing interface; do not manufacture a unique factual claim. Explain the relevant evidence relation within the existing fields. Missing support does not automatically determine severity, misuse level, or overall quality: apply the unchanged rubric and justify those decisions separately. Do not add output fields or copy this checklist into the answer.\n'''
prompts=read(P/'prompts.json');base=prompts['joint'];candidate=base+extra
(O/'PROPOSED_APPENDIX_EN.txt').write_text(extra)
(O/'PROPOSED_JOINT_PROMPT_EN.txt').write_text(candidate)
items=read(P/'items.json');oldp=read(P/'protocol.json');receipt=read(B/'paired_diagnostic_20261019_v1/execution_20261019/financial_and_usage_receipt.json')
order=['dev04A','dev04B','dev06A','dev06B','dev07A','dev15B','dev16A','dev35B','dev06B','dev04A','dev16A','dev35B'];rows=[]
for n,key in enumerate(order,1):
 payload=read(P/f'payloads/{key}.joint.json');original_user=payload['messages'][1]
 assert payload['messages'][0]['content']==base
 payload['messages'][0]['content']=candidate
 assert payload['messages'][1]==original_user
 path=O/f'payloads/{n:02d}_{key}.json';save(path,payload)
 size=len(json.dumps(payload['messages'],ensure_ascii=False).encode())
 assert size+8192+oldp['config']['max_output_tokens']<=oldp['config']['context_tokens']
 rows.append(dict(position=n,item=key,kind='primary' if n<=8 else 'prespecified_repeat',
  slot_id=f'action-stage-draft-v1-{n:02d}-{key}',payload_sha256=sha(path),user_payload_identity=digest(original_user),
  reply_identity=digest(items[key]['reply']),evidence_identity=digest(items[key]['evidence']),
  context_id=items[key]['context_id'],serialized_messages_bytes=size,old_payload_sha256=sha(P/f'payloads/{key}.joint.json'),
  maximum_output_tokens=oldp['config']['max_output_tokens'],status='PROPOSED_NOT_AUTHORIZED'))
protocol=dict(version='pmrl1-joint-action-stage-development-DRAFT-v1-20261020',status='PROPOSED_RESEARCH_CHANGE_NOT_AUTHORIZED',
 purpose='One bounded test of a single general action-stage coverage reminder; not reward acceptance or independent validation.',
 base_protocol_identity=oldp['identity'],config=oldp['config'],service_mapping_last_observed='2026-10-19; must verify at actual startup, no automatic model substitution',
 candidate_prompt_sha256=sha(O/'PROPOSED_JOINT_PROMPT_EN.txt'),base_joint_prompt_identity=digest(base),
 final_interface=prompts['final_interface'],schema_unchanged=True,q_m_U_reward_unchanged=True,
 old_semantic_revisions_applied=1,proposed_additional_semantic_prompt_revision=1,
 required_contract_amendment='Explicit exception to original semantic_revisions_max=1 for this ONE proposed diagnostic; preserve applied count and all STOPs. Not enabled now.',
 current_judge_attempts=144,proposed_max_new_attempts=12,proposed_cumulative_stop=156,total_capacity_unchanged=289,
 old_D_cap_unchanged=143,old_pending_D_slots_unused=23,model_pool_expansion=False,
 distinct_replies=8,distinct_contexts=4,independent_new_cases=0,baseline_reused_old_joint_calls=8,
 new_stage_liability_stop_usd='1',old_trial_cap_usd='2',shared_new_work_cap_usd='20',
 prior_trial_accounted_usd='0.3800799',shared_accounted_since_boundary_usd='0.3800799',outstanding_last_receipt_usd='0',
 provisional_per_request_reservation_usd='0.786432',reservation_basis='1048576*.30/1e6 +393216*1.20/1e6; historical published peak price only; recheck official price before enabling',
 new_account_queries_requested=dict(models_GET=1,balance_GET=1),automatic_account_requests_now=0,
 exact_outbound='Original full legal source, reply, reply units, stable IDs, original NEW AI contract and same joint prompt plus proposed general reminder only. No human annotations, review notes, expected answers, another output, sealed data or credential file.',
 failure_policy='Serial, no retry. First technical/incomplete/binding failure stops the batch and retains unresolved liability. Source-proved substantial errors stop after record; reviewer ambiguity alone remains diagnostic and does not confer eligibility. Planned repeats have independent slots. A missing repeat cannot be replaced.',
 primary_question='Does the new version detect dev06B\'s action presupposition using correct subject/topic evidence, without turning genuine open invitations into unsupported accusations?',
 secondary_checks=['04B may retain two readings; no forced unique answer','06A identity concern separate from whether its open question asserts completion','15B/16A subject attribution maintained; severity still independently justified','35B unsupported employment claim not licensed by old unrelated worries','04A/07A no predetermined q or forced misuse=0','Four independent repeated draws report claim/attribution/U stability; no estimate of universal reliability'],
 proposed_development_exit='One batch only. If known miss persists, new confirmed false accusations appear, or a technical stop prevents usable delivery, do not propose another tweak/model in this route. If improved, only consider a separately scoped acceptance decision, retaining all exposed-case limits. No automatic sealed validation or PPO.',
 old_59_acceptance_not_in_this_batch=True,natural_training_authorized=False,runner_enabled=False,schedule=rows)
save(O/'proposal.json',protocol)
unit=Decimal('0.0078498');budget=dict(status='HISTORICAL_SCENARIO_NOT_QUOTE',historical_12_call_mean_usd=str(unit*12),twofold_usage_scenario_usd=str(unit*24),stage_cap_usd='1',one_request_max_liability_usd='0.786432',max_stage_settled_plus_unsettled_before_next_call_usd='0.213568',serial_reservation_sum_without_settlement_usd=str(Decimal('.786432')*12),full_batch_not_guaranteed=True,price_and_balance_checks_not_performed=True,no_new_calls=True)
save(O/'budget.json',budget)
save(O/'offline_checks.json',dict(user_payloads_unchanged=12,only_system_appendix_diff=True,schema_and_outer_interface_unchanged=True,unique_planned_slots=12,repeated_payloads_have_independent_slots=True,full_input_screen_passed=12,live_runner_not_enabled=True,credentials_read=False,api_requests=0,proposal_identity=digest(protocol)))
for p in O.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
print(json.dumps(dict(version=protocol['version'],identity=digest(protocol),requests_proposed=12,calls_made=0),ensure_ascii=False))

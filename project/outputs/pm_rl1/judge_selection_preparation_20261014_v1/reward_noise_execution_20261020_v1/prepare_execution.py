from pathlib import Path
import sys,os,json,shutil,time
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parent))
import noise as n
from noise import p,s
os.umask(0o077)
proposal=s.read(n.PROPOSAL/'proposal.json')
assert proposal['identity']=='5f6b05448286a8e4476ba6d6d0ce2cf1776d7af5d30ae47e1e3252f6e3c8104f'
assert proposal['identity']==s.digest({k:v for k,v in proposal.items() if k!='identity'})
assert proposal['decision_document_sha256']==s.sha(n.PROPOSAL/'DECISION_ZH.md')
assert n.historical_count()==153
assert s.sha(n.LEDGER)=='cc7c0d6696562d9fbbee83736ea92632f28e41e7b591fcf2721d7e0d73eca3a1'
for e in proposal['endpoints']:
    assert s.sha(e['raw_path'])==e['raw_file_sha256'] and s.sha(e['request_path'])==e['request_file_sha256']
    assert s.sha(n.PROPOSAL/e['payload_file'])==e['payload_file_sha256']
old=s.read(n.BASE/'action_stage_diagnostic_20261020_v1/protocol.json')
snapshot=n.HERE/'provenance';snapshot.mkdir(exist_ok=False)
shutil.copy2(n.LEDGER,snapshot/'ledger.before.jsonl')
shutil.copy2(s.REPO/'project/docs/PM_RL1_CURRENT_STATUS.md',snapshot/'CURRENT_STATUS.before.md')
stops=[f for root in ('live_runs','paired_diagnostic_runs','action_stage_runs') for f in (n.BASE/root).rglob('STOP.json')]
s.save(snapshot/'old_stops.json',{str(f):s.sha(f) for f in stops})
files=[n.PROPOSAL/'proposal.json',n.PROPOSAL/'DECISION_ZH.md',n.PROPOSAL/'budget.json',
    n.HERE/'noise.py',n.HERE/'analysis.py',n.HERE/'test_noise.py',Path(p.__file__),Path(s.__file__),Path(s.judge.__file__),
    n.BASE/'adapters.py',n.BASE/'outer_format_v1_20261015/deepseek_access.py',
    n.BASE/'outer_format_v1_20261015/outer_format_v1.py',n.BASE/'paired_diagnostic_20261019_v1/live.py',
    s.REPO/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json']
files += [n.PROPOSAL/e['payload_file'] for e in proposal['endpoints']]
protocol=dict(version=n.STUDY,status='AUTHORIZED_BOUNDED_DEVELOPMENT_DIAGNOSTIC',
    proposal_identity=proposal['identity'],proposal_file_sha256=s.sha(n.PROPOSAL/'proposal.json'),
    config=proposal['configuration'],final_interface=proposal['interface'],
    frozen_prompt_sha256=proposal['frozen_prompt_sha256'],prompt_unchanged_relative_to=old['identity'],
    semantic_revisions_applied=2,semantic_revision_delta=0,
    schedule=[x|dict(item_key=x['endpoint'],component='joint',state='AUTHORIZED_PLAN_SLOT') for x in proposal['schedule']],
    diagnostic_policy=proposal['proposed_dispatch_policy'],
    baseline_cumulative=153,max_new=48,cumulative_stop=201,capacity=289,
    public_price_table_identity=old['public_price_table_identity'],
    financial_baseline=dict(ledger_sha256=s.sha(n.LEDGER),
        financial_trial_identity=old['financial_baseline']['financial_trial_identity'],
        trial_accounted_usd='0.461787',shared_accounted_usd='1.96902991',known_unsettled=0),
    immutable_files={str(f.resolve()):s.sha(f) for f in files},
    scope='48 new diagnostic repeat slots only; all original STOPs preserved; no reward qualification',
    boundary_note='Dispatch policy approved after observed development failures; not preregistered before original experiments.',
    approved_at=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat())
protocol['identity']=s.digest(protocol);s.save(n.HERE/'protocol.json',protocol)
auth=dict(status='APPROVED',study=n.STUDY,protocol_identity=protocol['identity'],proposal_identity=proposal['identity'],
    baseline_cumulative=153,new_request_limit=48,cumulative_cap=201,capacity=289,
    stage_cap_usd='1.25',trial_cap_usd='2',shared_cap_usd='20',
    management_requests={'models':1,'user/balance':1},credential_process_read_authorized=True,
    official_research_payload_authorized=True,semantic_revision_delta=0,semantic_revisions_applied=2,
    diagnostic_policy=proposal['proposed_dispatch_policy'],old_stops_released=False,qualifies_reward=False,
    human_pairs_max=8,human_minutes_max=120,
    user_authorization='行，开始吧，有缺口是正常的，重点是为了完成研究，如何将现有的东西调教成符合我们需要的，或者需要补什么，以正确解决目前的瓶颈。总之，先分析清楚问题是什么，然后分析怎么解决。',
    authorization_context='Approves the immediately preceding concrete 48-call / USD1.25 / 8-pair proposal, not open-ended experiments.',
    timestamp=protocol['approved_at'])
n.approved(protocol,auth);s.save(n.HERE/'APPROVED.json',auth)
s.save(n.HERE/'offline_test_receipt.json',dict(tests=17,passed=17,failed=0,seconds=2.763,
    command='python -m unittest discover -s reward_noise_execution_20261020_v1 -p test_noise.py -v',
    test_code_sha256=s.sha(n.HERE/'test_noise.py'),evidence='exec session 73063 completed exit0: Ran 17 tests in 2.763s; OK',
    network_and_credential_access_blocked_in_tests=True,production_runner_unchanged=True))
print(s.canonical(dict(protocol=protocol['identity'],approved_new=48,baseline=n.historical_count(),old_stops_preserved=len(stops))))

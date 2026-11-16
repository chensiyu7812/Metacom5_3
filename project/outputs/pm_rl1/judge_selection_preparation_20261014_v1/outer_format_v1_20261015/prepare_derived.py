"""Bind interface version and reparse only two completed local finals. No inference."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import selection as s
import outer_format_v1 as interface
import continue_v1 as c
from resume_engineering import slots,now

plan=s.load_plan();p=c.protocol(plan)
if (HERE/'protocol.json').exists():assert s.read(HERE/'protocol.json')==p
else:s.save(HERE/'protocol.json',p)
assert 'Ran 76 tests' in (HERE/'tests_v1_corrected.log').read_text() and (HERE/'tests_v1_corrected.log').read_text().endswith('OK\n')
rows=[]
for req in slots(plan)[:2]:
    root=s.HERE/'live_runs'/req['candidate'];rid=req['request_id']
    files={k:root/(rid+'.'+k+'.json') for k in ('started','raw','response','result')}
    raw=s.read(files['raw']);response=s.read(files['response']);old=s.read(files['result'])
    assert raw['request_identity']==response['request_identity']==rid
    assert raw['raw_text']==response['raw_text'] and raw['natural_eos']
    assert all(old['measurement'][x] is None for x in ('q','m','candidate_utility'))
    assert old['measurement']==s.measured(plan,req,response)
    source_hashes={str(path):s.sha(path) for path in files.values()}
    source_hashes[str(root/'STOP.json')]=s.sha(root/'STOP.json')
    cfg=p['configs'][req['candidate']]['identity']
    derived_id=s.digest(dict(kind='offline_derived_reparse',original_request_id=rid,
        raw_sha256=s.sha(files['raw']),response_sha256=s.sha(files['response']),interface_identity=p['interface']['identity'],configuration=cfg))
    evaluation=interface.evaluate(plan,req,response,cfg,derived_id)
    record=dict(kind='offline_development_derived_not_new_inference',derived_id=derived_id,
        original_request_id=rid,original_configuration_identity=req['configuration_identity'],
        original_response_path=str(files['response']),original_hashes=source_hashes,
        new_configuration_identity=cfg,protocol_identity=p['identity'],interface=p['interface'],
        original_strict_result=old['measurement'],evaluation=evaluation,
        new_physical_calls=0,new_independent_samples=0,reward_eligible=False)
    path=HERE/'derived'/(rid+'.derived.json');interface.reparse_once(path,record)
    rows.append(dict(candidate=req['candidate'],request_id=rid,derived_path=str(path),
        validation_stage=evaluation['validation_stage'],measurement=evaluation['measurement']))
    print(s.canonical(dict(candidate=req['candidate'],stage=evaluation['validation_stage'],
        status=evaluation['measurement']['measurement_status'],q=evaluation['measurement']['q'],m=evaluation['measurement']['m'],U=evaluation['measurement']['candidate_utility'])))
history=c.reconstruct(plan,p,s.HERE/'live_runs')
assert history['cumulative_calls']==68 and history['started_or_evidenced']==2
summary=dict(protocol_identity=p['identity'],rows=rows,new_model_requests=0,new_independent_samples=0,
    cumulative_calls=68,original_failures_unchanged=True,semantic_revision_delta=0)
interface.reparse_once(HERE/'offline_reparse_summary.json',summary)

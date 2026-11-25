"""Evidence export must preserve failed/pending trials and reject extra calls."""
import json

import pytest

from metacom_pm.rl1v3.journal.paired_results import collect


def fixture(tmp_path, extra_event=None):
    rows=[dict(request_id=arm,arm=arm,domain='memory',task_id='opaque',
               payload_sha256=arm,renderer_id='test',model_input={'input_ids':[1,2]})
          for arm in ['OFF','DP','RET','matched-other']]
    requests=tmp_path/'requests.jsonl'
    requests.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
    job=tmp_path/'job';job.mkdir()
    events=[dict(event='REQUEST_START',request_id='OFF'),
            dict(event='REQUEST_RETURNED',request_id='OFF',output=dict(
                text='Unknown',token_ids=[3],input_tokens=2,seconds=0.5,finish_reason='eos')),
            dict(event='REQUEST_START',request_id='DP')]
    if extra_event:events.append(extra_event)
    for i,event in enumerate(events):(job/f'{i:04d}.json').write_text(json.dumps(event))
    (job/'SUMMARY.json').write_text(json.dumps(dict(physical_calls=sum(x['event']=='REQUEST_START' for x in events),
        status='STOPPED',wall_seconds=1)))
    return requests,job,tmp_path/'result'


def test_partial_job_keeps_every_arm_and_unknown_outcomes(tmp_path):
    args=fixture(tmp_path);report=collect(*args)
    rows=[json.loads(x) for x in (args[2]/'PAIRED_RESPONSES_PRIVATE.jsonl').read_text().splitlines()]
    assert [r['technical_status'] for r in rows]==['returned_eos','started_no_return','not_started','not_started']
    assert all(r['reward'] is None for r in rows)
    assert all(r['response'] is None and r['output_tokens'] is None for r in rows[1:])
    assert report['pairs'][0]['all_arms_requested'] and not report['pairs'][0]['all_eos']
    assert report['physical_calls']==2 and report['returned']==1


@pytest.mark.parametrize('request_id,reason',[('OFF','repeated physical start'),('EXTRA','unrequested physical start')])
def test_reject_hidden_retry_or_extra_call(tmp_path,request_id,reason):
    with pytest.raises(ValueError,match=reason):
        collect(*fixture(tmp_path,dict(event='REQUEST_START',request_id=request_id)))

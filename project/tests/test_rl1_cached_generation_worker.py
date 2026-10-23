import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from metacom_pm.rl1.bound_generation import PROTOCOL
from metacom_pm.rl1.cached_generation_worker import make_cache_index, replay_cached_generations
from metacom_pm.rl1.natural_batch import FeedbackQueue
from metacom_pm.rl1.schema import digest


def fixture(tmp_path, name='one'):
    payload=dict(messages=[dict(role='user',content=name)],executor_identity='frozen-G',
        draw_identity='greedy',renderer_identity='renderer',provenance=dict(
        protocol=PROTOCOL,prefix_identity=name,inventory_identity='inventory',
        retrieval_identity='retrieval',canonical_counts=[0,0,0,0]))
    request=dict(request_id=digest(payload),**payload)
    raw=dict(request_id=request['request_id'],runtime_identity='frozen-G',
        source_provenance_identity=digest(payload['provenance']),text='stored reply',
        finish_reason='natural_stop')
    entry={}
    for label,value in [('request',request),('raw',raw)]:
        p=tmp_path/(name+'.'+label+'.json');p.write_text(json.dumps(value))
        entry[label+'_path']=str(p);entry[label+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    return request,raw,entry


def test_reuse_exact_reply_preserves_measurement_and_miss(tmp_path):
    req,raw,entry=fixture(tmp_path);missing,_,_=fixture(tmp_path,'uncached')
    queue=FeedbackQueue(tmp_path/'queue.sqlite')
    evidence={'current':'visible'};reply='unmeasured'
    binding=dict(evidence_identity=digest(evidence),response_identity=digest(reply))
    assert queue.measure(binding,evidence,reply) is None
    queue.generate(req);queue.generate(missing)
    index=make_cache_index([entry],source_identity='original-pool')
    result=replay_cached_generations(queue,index)
    assert len(result['reused'])==1 and len(result['cache_misses'])==1
    assert queue.generate(req)==raw
    assert queue.generate(missing) is None and queue.measure(binding,evidence,reply) is None
    assert replay_cached_generations(queue,index)['reused']==[]
    with queue.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM generation_cache_reuse').fetchone()[0]==1


def test_started_is_never_reclaimed(tmp_path):
    req,_,entry=fixture(tmp_path);queue=FeedbackQueue(tmp_path/'q.sqlite');queue.generate(req)
    job=queue.claim_next();index=make_cache_index([entry],source_identity='pool')
    assert replay_cached_generations(queue,index)['reused']==[]
    assert queue.generate(req) is None and job['kind']=='generation'
    assert queue.counts()==[dict(kind='generation',state='STARTED',count=1)]


@pytest.mark.parametrize('change',['bytes','provenance','finish'])
def test_changed_or_invalid_cache_never_settles(tmp_path,change):
    req,raw,entry=fixture(tmp_path);queue=FeedbackQueue(tmp_path/'q.sqlite');queue.generate(req)
    index=make_cache_index([entry],source_identity='pool')
    if change=='bytes':
        with open(entry['raw_path'],'a') as f:f.write(' ')
    else:
        raw['source_provenance_identity' if change=='provenance' else 'finish_reason']='wrong'
        with open(entry['raw_path'],'w') as f:json.dump(raw,f)
        entry['raw_sha256']=hashlib.sha256(open(entry['raw_path'],'rb').read()).hexdigest()
        with pytest.raises(ValueError):make_cache_index([entry],source_identity='pool')
    with pytest.raises(ValueError):replay_cached_generations(queue,index)
    assert queue.counts()==[dict(kind='generation',state='WAITING',count=1)]


def test_parallel_workers_ingest_once_and_record_provenance(tmp_path):
    req,raw,entry=fixture(tmp_path);path=tmp_path/'q.sqlite';queue=FeedbackQueue(path)
    queue.generate(req);index=make_cache_index([entry],source_identity='pool')
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:replay_cached_generations(FeedbackQueue(path),index),range(2)))
    assert sum(len(r['reused']) for r in results)==1
    assert queue.generate(req)==raw


def test_tampered_queue_rolls_back_other_reuse(tmp_path):
    req,_,entry=fixture(tmp_path);other,_,other_entry=fixture(tmp_path,'two')
    queue=FeedbackQueue(tmp_path/'q.sqlite');queue.generate(req);queue.generate(other)
    index=make_cache_index([entry,other_entry],source_identity='pool')
    with queue.transaction() as db:
        row=db.execute('SELECT id,payload FROM feedback ORDER BY rowid DESC LIMIT 1').fetchone()
        payload=json.loads(row[1]);payload['draw_identity']='changed'
        db.execute('UPDATE feedback SET payload=? WHERE id=?',(json.dumps(payload),row[0]))
    with pytest.raises(ValueError):replay_cached_generations(queue,index)
    assert queue.counts()==[dict(kind='generation',state='WAITING',count=2)]

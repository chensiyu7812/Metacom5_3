"""Explicit synthetic engineering fixtures. No research text or model calls."""
from hashlib import sha256
import json
from metacom_pm.rl1.natural_runner import _EpisodeLoop
from metacom_pm.rl1.natural_batch import MOCK
from metacom_pm.rl1.observation_features import PlanAwareFeatureEncoder
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.schema import PrefixSpec, PublicTurn, Resource, EpisodeSpec, HEADS


class MockEpisode(_EpisodeLoop):
    feedback_scope = MOCK


def make_encoder():
    seen = []
    def encode(texts):
        seen.extend(texts)
        return [[b/255 for b in sha256(t.encode()).digest()[:4]] for t in texts]
    return PlanAwareFeatureEncoder(encode, embedding_dimension=4,
        text_encoder_identity='MOCK:sha256-4-not-BGE', resource_budget=2048), seen


def episodes(tag='batch', n=16, empty=False):
    renderer = Renderer(count_text=lambda s:len(s)//4,
        count_chat=lambda m:len(json.dumps(m))//4,
        tokenizer_identity='MOCK:character-counter', context_limit=10000)
    out = []
    for i in range(n):
        prefix = PrefixSpec('MOCK_OWNER',f'MOCK_SESSION_{i%2}',2,0,'2000-01-02','train',
            (PublicTurn('seeker',f'Mock current task {i%2}'),))
        inventory = tuple(tuple(Resource(f'MOCK_PRIVATE_{h}_{j}',h,f'MOCK_HIDDEN_{h}_{j}',
            1-j/10,5,None if h=='RS' else 'MOCK_OWNER',None if h=='RS' else 1,
            None if h=='RS' else '2000-01-01','not_applicable' if h=='RS' else 'previous_session',
            ('MOCK_SOURCE',)) for j in range(0 if empty else 2)) for h in HEADS)
        spec = EpisodeSpec(prefix,inventory,'MOCK:retrieval','MOCK:generator','MOCK:judge','MOCK:draw')
        # These are NOT fabricated calibrated/frozen receipts. The formal
        # NaturalEpisode constructor rejects them; only the test subclass uses
        # the common state machine with explicit mock identities.
        freeze = dict(identity='MOCK:freeze',runtime_identity='MOCK:judge',rubric_identity='MOCK:scale')
        qual = dict(identity='MOCK:qualification',status=MOCK)
        out.append(MockEpisode(spec,renderer,evidence={'mock_only':'PRIVATE_EVIDENCE'},
            freeze=freeze,qualification=qual,trajectory_id=f'{tag}-{i}'))
    return out


def answer(item, status='measured_candidate'):
    p = item['payload']
    if item['kind']=='generation':
        return dict(request_id=p['request_id'],runtime_identity=p['executor_identity'],
            text='MOCK:'+json.dumps(p['provenance']['canonical_counts']),finish_reason='natural_stop',
            feedback_scope=MOCK)
    measured = status=='measured_candidate'
    counts = json.loads(p['reply'].removeprefix('MOCK:'))
    return dict(binding=p['binding'],measurement_status=status,q=(3 if sum(counts) else 2) if measured else None,
        m=0 if measured else None,feedback_scope=MOCK)


def drain(queue):
    count = 0
    while (item := queue.claim_next()) is not None:
        queue.settle(item['id'],answer(item));count+=1
    return count


def complete(batch, queue):
    for _ in range(8):
        results=batch.poll(queue)
        if all(x['phase']=='terminal' for x in results):return results
        drain(queue)
    raise AssertionError('mock feedback never completed')

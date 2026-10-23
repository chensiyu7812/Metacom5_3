from copy import deepcopy
from dataclasses import dataclass
import pytest
from metacom_pm.rl1.schema import PrefixSpec,PublicTurn,Resource,EpisodeSpec,digest
from metacom_pm.rl1.source_preflight import validate_generation_sources

class Renderer:
    identity='renderer'
    def fits(self,s,c):return True
    def messages(self,s,c):return [{'role':'user','content':s.prefix.query+str(c)}]

def fixture():
    p=PrefixSpec('p1','s2',2,0,'2024-02-01','train',(PublicTurn('seeker','help'),))
    r=Resource('mp::a','MP','evidence',.5,3,'p1',0,'2024-01-01','2_to_4_sessions',('s0',))
    s=EpisodeSpec(p,((),(r,),(),()),'retrieval','executor','judge','test')
    renderer=Renderer();e=dict(prefix_identity=p.identity,evidence={},evidence_identity=digest({}))
    from dataclasses import asdict
    reviews=[dict(candidate_id=r.candidate_id,prefix_identity=p.identity,evidence_identity=e['evidence_identity'],
        resource_identity=digest(asdict(r)),status='source_supported',temporal_status_checked=True,reviewer='test',rationale='checked',evidence_refs=['s0'])]
    cs=[]
    for label in ('OFF','R','L'):
        head=None if label=='OFF' else 'MP';counts=(0,int(head=='MP'),0,0);messages=renderer.messages(s,counts)
        cs.append(dict(index=1,condition=label,prefix_identity=p.identity,owner='p1',split='train',head=head,
            counts=counts,messages=messages,messages_identity=digest(messages)))
    return dict(contract=dict(conditions=cs,renderer_identity='renderer'),specs=[s],evidence=[e],reviews=reviews,renderer=renderer)

def test_all_conditions_gated_and_off_allowed():
    assert len(validate_generation_sources(**fixture())['conditions'])==3

@pytest.mark.parametrize('fault',['missing_review','uncertain','changed_prompt','changed_evidence','missing_condition','missing_refs'])
def test_author_gate_rejects_unqualified_inputs(fault):
    f=fixture()
    if fault=='missing_review':f['reviews']=[]
    if fault=='uncertain':f['reviews'][0]['status']='uncertain'
    if fault=='changed_prompt':f['contract']['conditions'][1]['messages'][0]['content']='injected private history'
    if fault=='changed_evidence':f['evidence'][0]['evidence']={'future':'x'}
    if fault=='missing_condition':f['contract']['conditions'].pop()
    if fault=='missing_refs':f['reviews'][0]['evidence_refs']=[]
    with pytest.raises(ValueError):validate_generation_sources(**f)

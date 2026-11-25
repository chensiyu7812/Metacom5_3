import copy
import pytest
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.joint_fact_review import validate_review, aggregate


def fixture():
    output={'text':'You reported roughly two items.'}
    actual=dict(logical_id='synthetic:x',task_id='synthetic:t',arm='MS',request_id='synthetic:r',output=output,output_sha256=object_sha256(output),technical_status='eos')
    ev={'personal_fact_references':[{'id':'f1'}]}
    supply=dict(logical_id=actual['logical_id'],delivery='MS',source_binding={'exact_quote':'I reported roughly two items.'})
    review={k:v for k,v in actual.items() if k!='output'}
    review.update(evalspec_sha256=object_sha256(ev),fact_atoms=[dict(id='f1',required=True,status='supported',delivery='MS',output_quotes=['roughly two items'],source_quotes=[dict(quote='I reported roughly two items.',location='MS')])],additional_claims=[],abstention={'safe_nonrecall':False},formal_semantic_status='uncertain',formal_reward=None)
    return review,actual,ev,supply


def test_exact_review_is_mechanically_valid():
    assert validate_review(*fixture())


@pytest.mark.parametrize('mutation',['quote','hash','missing','reward','supply'])
def test_rejects_changed_private_binding(mutation):
    r,a,e,s=fixture()
    if mutation=='quote':r['fact_atoms'][0]['output_quotes']=['not in output']
    elif mutation=='hash':r['output_sha256']='wrong'
    elif mutation=='missing':r['fact_atoms']=[]
    elif mutation=='reward':r['formal_reward']=1
    elif mutation=='supply':r['fact_atoms'][0]['delivery']='absent'
    with pytest.raises(ValueError):validate_review(r,a,e,s)


def test_nonrecall_is_not_completion():
    r,*_=fixture();r['fact_atoms'][0]['status']='omitted';r['abstention']['safe_nonrecall']=True
    out=aggregate([r]);assert out['by_arm']['MS']['all_atoms_supported']==0
    assert out['by_arm']['MS']['safe_nonrecall']==1
    assert out['formal_reward'] is None


def test_reject_duplicate_review():
    r,*_=fixture()
    with pytest.raises(ValueError):aggregate([r,r])


def test_context_dispute_preserves_partial_as_interval():
    from metacom_pm.rl1v3.journal.joint_fact_review import completion_intervals
    r,*_=fixture();r['fact_atoms'][0]['status']='partial'
    d=dict(logical_id=r['logical_id'],atom_id='f1',original_status='partial',interpretation_status='unresolved',completion_interval=[0,1])
    out=completion_intervals([r],[d])['MS']
    assert out['completed_atom_lower']==0 and out['completed_atom_upper']==1
    assert r['fact_atoms'][0]['status']=='partial'
    d['original_status']='supported'
    with pytest.raises(ValueError):completion_intervals([r],[d])

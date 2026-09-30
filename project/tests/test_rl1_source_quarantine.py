import pytest
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.source_quarantine import quarantine_decision,validate_quarantine_binding,profile_family,require_pre_generation_source_reviews

def example():
    u=dict(memory_id='new',owner_id='p1',profile_field_type='stable_relationship_role',profile_slot_key='close_friend',value='close')
    r=dict(bad_unit_id='new',bad_unit_identity=digest(u),family=profile_family(u),rationale='new citation contradicts ongoing friendship',evidence={'quote':'things ended'})
    return u,r

def test_quarantine_blocks_old_value_fallback_and_preserves_other_owner():
    u,r=example();validate_quarantine_binding(r,u)
    assert quarantine_decision(u,[r])['blocked']
    assert quarantine_decision(dict(u,memory_id='old'),[r])['blocked']
    assert not quarantine_decision(dict(u,owner_id='p2'),[r])['blocked']
    assert not quarantine_decision({'memory_id':'event'},[r])['blocked']

def test_wrong_source_cannot_inherit_quarantine_proof():
    u,r=example()
    with pytest.raises(ValueError):validate_quarantine_binding(r,dict(u,value='different'))

def test_unreviewed_is_not_approved():
    u,r=example();d=quarantine_decision(u,[])
    assert not d['blocked'] and 'unreviewed' in d['meaning']


@pytest.mark.parametrize('change',['missing','different_prefix','different_resource','uncertain','time_unchecked'])
def test_new_batch_cannot_generate_from_unreviewed_or_changed_source(change):
    resource=dict(candidate_id='mp::one',content='old profile')
    review=dict(resource_identity=digest(resource),prefix_identity='prefix',evidence_identity='evidence',
        status='source_supported',temporal_status_checked=True,reviewer='development weak review',rationale='source compared')
    records={'mp::one':review}
    if change=='missing':records={}
    elif change=='different_prefix':review['prefix_identity']='other'
    elif change=='different_resource':resource['content']='changed'
    elif change=='uncertain':review['status']='uncertain'
    elif change=='time_unchecked':review['temporal_status_checked']=False
    with pytest.raises(ValueError):
        require_pre_generation_source_reviews([resource],prefix_identity='prefix',evidence_identity='evidence',reviews=records)


def test_off_needs_no_phantom_resource_review():
    assert require_pre_generation_source_reviews([],prefix_identity='prefix',evidence_identity='evidence',reviews={})

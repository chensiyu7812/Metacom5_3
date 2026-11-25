import pytest
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.failure_attribution import attribute,aggregate


def case():
    output={'text':'A general answer.'};review={'status':'omitted'}
    return dict(cohort='synthetic',logical_id='x',task_id='t',arm='RAW',request_id='r',source_group='g',
        actual_output=output,output_sha256=object_sha256(output),response=output['text'],
        original_review=review,original_review_sha256=object_sha256(review),delivered_text='The item is blue.',
        raw_counterpart_text='The item is blue.',atoms=[dict(id='a',original_status='omitted',
        source_quotes=['The item is blue.'],output_quotes=[],supply='full',reference_uncertain=False,
        interpretation_uncertain=False)],diagnostics=[],scope_limitations=[])


def test_supplied_omission_does_not_identify_understanding():
    r=attribute(case());assert r['events'][0]['category']=='expression_failure'
    assert not r['events'][0]['internal_cause_identified']
    assert r['fact_understanding_failure']=='not_identifiable_from_existing_outputs'


def test_missing_input_is_not_downstream_failure():
    c=case();c['delivered_text']='';c['atoms'][0].update(supply='absent',source_quotes=[])
    r=attribute(c);assert [e['category'] for e in r['events']]==['evidence_insufficient']


def test_representation_loss_requires_same_source_comparison():
    c=case();c['delivered_text']='';c['atoms'][0].update(supply='absent',source_quotes=[],removed_representation_quotes=['The item is blue.'])
    assert len(attribute(c)['events'])==2
    c['raw_counterpart_text']='No evidence.'
    with pytest.raises(ValueError):attribute(c)


def test_uncertain_reference_cannot_become_generator_failure():
    c=case();c['atoms'][0]['reference_uncertain']=True
    assert attribute(c)['events'][0]['category']=='evaluation_uncertain'


def test_old_label_and_reply_binding_are_enforced():
    c=case();c['original_review']['status']='complete'
    with pytest.raises(ValueError):attribute(c)
    c=case();c['actual_output']['text']='Changed.'
    with pytest.raises(ValueError):attribute(c)


def test_quoted_evidence_must_actually_be_delivered():
    c=case();c['atoms'][0]['source_quotes']=['Missing quote.']
    with pytest.raises(ValueError):attribute(c)


def test_reused_request_is_not_an_independent_generation():
    first=attribute(case());c=case();c['logical_id']='y';second=attribute(c)
    result=aggregate([first,second]);assert result['cohorts']['synthetic']['rows']==2
    assert result['cohorts']['synthetic']['requests']==1
    assert result['cohorts']['synthetic']['groups']==1
    assert result['internal_causal_mechanisms_identified']==0


def test_normalized_status_cannot_override_frozen_observation():
    c=case();c['original_review']={'atoms':[{'atom_id':'a','observed':'omitted'}]}
    c['original_review_sha256']=object_sha256(c['original_review'])
    c['atoms'][0]['original_status']='complete'
    with pytest.raises(ValueError):attribute(c)


def test_unsupported_claim_cannot_be_counted_as_understanding_failure():
    c=case();c['diagnostics']=[dict(category='fact_understanding_unresolved',kind='unsupported_assertion_observed_internal_understanding_unidentified',output_quotes=['A general answer.'])]
    rows=[attribute(c)];assert all(e['category']!='fact_understanding_failure' for e in rows[0]['events'])
    assert aggregate(rows)['internal_causal_mechanisms_identified']==0
    c['diagnostics'][0]['category']='fact_understanding_failure'
    with pytest.raises(ValueError):attribute(c)

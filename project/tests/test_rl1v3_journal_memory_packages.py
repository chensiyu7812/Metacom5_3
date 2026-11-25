"""Memory admission isolation and source-quote review boundaries; CPU only."""
import copy
from types import SimpleNamespace
import pytest
from metacom_pm.rl1v3.journal.memory_run import SCOPES,validate_scope,admit
from metacom_pm.rl1v3.journal.memory_packages import writer_mechanical_check,next_real_prefix
from metacom_pm.rl1v3.io import object_sha256


def repr_fixture():
    rows=[]
    for task in range(6):
        for arm in ('RAW','TYPED_OR_SUM','SPAN'):
            sha=object_sha256([task,arm])
            rows.append(dict(task_id=str(task),arm=arm,request_id='repr:'+sha,payload_sha256=sha,
                source_session_set_sha256='source:'+str(task)))
    plan=dict(job_kind='JOURNAL_MEMORY_REPR18',protocol=SCOPES['JOURNAL_MEMORY_REPR18'][0],
        max_calls=18,task_ids=list(map(str,range(6))))
    return plan,rows,copy.deepcopy(rows)


def test_six_complete_frozen_triples_are_admitted_for_cpu_check():
    validate_scope(*repr_fixture())


@pytest.mark.parametrize('change,reason',[
    ('drop_arm','call count'),('duplicate_payload','duplicate Memory'),
    ('changed_frozen','frozen request changed'),('different_source','source set differs'),
    ('wrong_arm','incomplete representation triple'),
])
def test_partial_changed_or_duplicate_representation_requests_fail(change,reason):
    plan,rows,frozen=repr_fixture()
    if change=='drop_arm':rows.pop()
    elif change=='duplicate_payload':rows[1]=copy.deepcopy(rows[0])
    elif change=='changed_frozen':rows[0]['source_session_set_sha256']='modified'
    elif change=='different_source':
        rows[0]['source_session_set_sha256']='different';frozen=copy.deepcopy(rows)
    elif change=='wrong_arm':rows[0]['arm']='OFF';frozen=copy.deepcopy(rows)
    with pytest.raises(ValueError,match=reason):validate_scope(plan,rows,frozen)


@pytest.mark.parametrize('protocol,kind',[
    ('pmrl1-j-smoke-run-v1','JOURNAL_SMOKE'),
    ('pmrl1-j-paired-batch-v1','JOURNAL_PAIRED_BATCH'),
    (SCOPES['JOURNAL_WRITER8'][0],'JOURNAL_WRITER8'),
    (SCOPES['JOURNAL_MPME6'][0],'JOURNAL_MPME6'),
])
def test_other_approval_never_transfers_to_representation(protocol,kind):
    plan,_,_=repr_fixture()
    auth=dict(authorized=True,protocol=protocol,job_kind=kind,plan_sha256=object_sha256(plan),
        max_calls=18,max_model_loads=1,researcher='fixture',decision_evidence='fixture')
    with pytest.raises(ValueError,match='cannot transfer'):admit(plan,auth)


def test_even_matching_pending_request_is_not_authorization():
    plan,_,_=repr_fixture()
    with pytest.raises(ValueError,match='explicit Memory approval'):admit(plan,dict(authorized=False))


def test_writer_quote_screen_catches_actor_negation_and_invented_completion():
    source=SimpleNamespace(turns=[SimpleNamespace(role='seeker',text='I did not attend. I only booked a ticket.'),
        SimpleNamespace(role='supporter',text='You could consider going next week.')])
    for text in ('seeker: I attended.','seeker: You could consider going next week.',
                 'seeker: I completed the retreat.'):
        assert writer_mechanical_check(text,source)['mechanical_status']=='fail'
    result=writer_mechanical_check('seeker: I did not attend.\nseeker: I only booked a ticket.',source)
    assert result['mechanical_status']=='pass' and result['semantic_approved'] is False
    assert result['semantic_speaker_negation_date_stage_coverage']=='pending_independent_source_review'


def test_source_end_without_later_real_prefix_is_unavailable_not_fabricated():
    registry=SimpleNamespace(entries=[])
    source=SimpleNamespace(owner_id='u',chronological_rank=9)
    with pytest.raises(ValueError,match='do not fabricate'):next_real_prefix(registry,source)

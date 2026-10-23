import pytest
from metacom_pm.rl1.measurement_candidates import (
    canonical_choice,paired_native_status,parse_native_choice,render_evidence,
    skywork_messages,skywork_ids,prometheus_prompt,repeated_tail)


def case():
    return dict(response_A='alpha',response_B='beta',evidence=dict(current_date='2025-01-02',
        current_prefix=[dict(id='C:T000',role='seeker',text='Current\nraw words.')],
        legal_past_sessions=[dict(id='H001',date='2025-01-01',turns=[dict(id='H001:T000',role='supporter',text='Past raw words.')])]))


@pytest.mark.parametrize('text', ['reason [RESULT] C','reason [RESULT] A [RESULT] B','[RESULT] A',
                                'reason [RESULT] A because','reason A','reason [RESULT] equivalent'])
def test_parser_does_not_guess(text):
    assert parse_native_choice(text,'natural_stop')['native_choice'] is None


def test_incomplete_generation_never_becomes_preference():
    assert parse_native_choice('reason [RESULT] A','context_exhausted')['status']=='technical_missing'


def test_reversal_conflict_not_tie():
    a=parse_native_choice('reason [RESULT] A','natural_stop')
    b=parse_native_choice('reason [RESULT] B','natural_stop')
    assert paired_native_status(a,a)==dict(status='order_disagreement',native_preference=None)
    assert paired_native_status(a,b)==dict(status='order_consistent',native_preference='A')
    assert canonical_choice(None,True) is None


def test_complete_evidence_and_blinding():
    c=case();c['private_label']='secret'
    rendered=render_evidence(c['evidence'])
    for value in ['C:T000','H001:T000','2025-01-01','Current\nraw words.','Past raw words.']:
        assert value in rendered
    messages=skywork_messages(c,'B')
    assert [m['role'] for m in messages]==['user','assistant']
    assert messages[-1]['content']=='beta' and 'secret' not in str(messages)
    p=prometheus_prompt(c,'{instruction}\n{response_A}\n{response_B}\n{rubric}','system',True)
    assert p.startswith('[INST] system\n') and p.endswith(' [/INST]') and '\nbeta\nalpha\n' in p


def test_future_evidence_rejected():
    c=case();c['evidence']['legal_past_sessions'][0]['date']='2025-01-02'
    with pytest.raises(ValueError):render_evidence(c['evidence'])


def test_native_bos_normalization():
    class Tokenizer:
        bos_token='<bos>'
        def apply_chat_template(self,messages,**kw):return '<bos>body<eot>'
        def __call__(self,text,**kw):
            assert text=='body<eot>' and kw==dict(add_special_tokens=True,truncation=False)
            return dict(input_ids=[1,2,3])
    assert skywork_ids(Tokenizer(),[])==[1,2,3]


def test_repetition_guard_requires_four_full_blocks():
    assert not repeated_tail(list(range(32))*3)
    assert repeated_tail(list(range(32))*4)

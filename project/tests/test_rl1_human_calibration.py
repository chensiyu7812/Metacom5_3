import copy
import pytest
import metacom_pm.rl1.human_calibration as h


def fixture():
    e = dict(current_date='2026-01-01', legal_past_sessions=[], current_prefix=[
        dict(id='C:T000', role='seeker', text='I am thinking of asking for help.')])
    items = [dict(item_id=i, source_key='source', A='You already got help.', B='Would you like to ask?') for i in ('d', 'v')]
    form = dict(packet_identity='a'*64, form_identity='b'*64, items=items)
    envelopes = [dict(item_id=i, wrapped_key='test', nonce='test', ciphertext='test') for i in ('d', 'v')]
    submission = dict(protocol=h.PROTOCOL, packet_identity=form['packet_identity'],
        form_identity=form['form_identity'], reviewer_kind='individual_human', reviewer_identity='fixture-only',
        reviewer_details='Synthetic code test; not a human answer.', items=envelopes)
    label = dict(item_id='d', preference='B', risk_A='severe', risk_B='none_detected',
        quote_A='already got help', quote_B='', source_ids=['C:T000'],
        reason='Intent does not prove a completed event.', uncertainty='')
    bindings = dict(form=form, private_items={'d':{'group':'development'}, 'v':{'group':'validation'}},
        evidence_pool={'source':e}, private_key=None)
    return submission, label, bindings


def test_development_intake_never_decrypts_validation(monkeypatch):
    s, label, b = fixture(); calls = []
    def decrypt(envelope, *_args, **_kwargs):
        calls.append(envelope['item_id'])
        assert envelope['item_id'] == 'd', 'validation must stay encrypted'
        return label
    monkeypatch.setattr(h, 'decrypt_item', decrypt)
    result = h.ingest_submission(s, **b)
    assert calls == ['d'] and result['sealed_items'] == ['v']
    assert not result['other_phase_decrypted'] and not result['reward_qualified']


def test_validation_freeze_checked_before_any_decryption(monkeypatch):
    s, _, b = fixture()
    def forbidden(*a, **k):
        raise AssertionError('decryption called before freeze')
    monkeypatch.setattr(h, 'decrypt_item', forbidden)
    with pytest.raises(ValueError, match='freeze'):
        h.ingest_submission(s, **b, phase='validation')


@pytest.mark.parametrize('change', [
    {'reviewer_kind':'model'}, {'packet_identity':'wrong'}, {'reviewer_identity':''},
    {'form_identity':'wrong'}, {'items':[]},
])
def test_wrong_identity_provenance_or_missing_rows_rejected(change):
    s, _, b = fixture(); s.update(change)
    with pytest.raises(ValueError): h.ingest_submission(s, **b)


def test_duplicate_items_rejected():
    s, _, b = fixture(); s['items'][1] = copy.deepcopy(s['items'][0])
    with pytest.raises(ValueError): h.ingest_submission(s, **b)


@pytest.mark.parametrize('change', [
    {'risk_A':''}, {'risk_A':0}, {'source_ids':['H999:T000']}, {'source_ids':[]},
    {'quote_A':'I never wrote this'}, {'quote_A':''}, {'reason':''},
    {'preference':'uncertain'},
])
def test_incomplete_or_unbound_labels_are_not_accepted(change):
    _, label, b = fixture(); label.update(change)
    with pytest.raises(ValueError): h.validate_label(label, b['form']['items'][0], b['evidence_pool']['source'])


def test_explained_uncertainty_remains_uncertainty():
    _, label, b = fixture()
    label.update(preference='uncertain', risk_A='uncertain', quote_A='', uncertainty='Ambiguous reference.')
    result = h.validate_label(label, b['form']['items'][0], b['evidence_pool']['source'])
    assert result['risk_A'] == result['preference'] == 'uncertain'


def test_duplicate_fields_and_nonfinite_are_rejected():
    for text in ['{"risk":"severe","risk":"none_detected"}', '{"q":NaN}']:
        with pytest.raises(ValueError): h.strict_json(text)

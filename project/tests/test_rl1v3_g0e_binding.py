"""Resource-group mapping must replay both identities; no key relabelling."""
from dataclasses import replace
import pytest
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.bank.v0_port import PrefixPort
from metacom_pm.rl1v3.generator.replay_binding import rebuild_from_replay
from test_rl1v3_g0e_request import assets, port, FixtureTokenizer


def old_port(port):
    return PrefixPort(port.bank,port.prefix,FixtureTokenizer(),g_id='old-tokenizer-only',
                      decode_id='not_run',step2_id='none-v0-read-replay')


def test_rebuild_gets_new_key_with_identical_real_groups_and_body(port):
    old=old_port(port)
    rs=old.read('RS');me=old.read('ME',acquired=(rs.reading,))
    key=old.terminal_key([rs,me])
    packet,evidence=rebuild_from_replay(old,port,key)
    assert packet.key!=key and packet.key.acquired==key.acquired
    assert evidence['changed_identity_fields']==['renderer_id','step2_id','g_id','decode_id']
    assert evidence['same_readings'] and evidence['generation_calls']==0
    assert packet.trace.readings==(rs.reading,me.reading)
    assert isinstance(port.replay(key),K.ReadFailure)


@pytest.mark.parametrize('field', ['owner_id','g_id','renderer_id','bank_version'])
def test_wrong_old_key_rejected_before_mapping(port,field):
    old=old_port(port)
    with pytest.raises(ValueError,match='old replay failed'):
        rebuild_from_replay(old,port,replace(old.terminal_key([]),**{field:'foreign'}))


def test_mapping_uses_new_read_and_fails_on_capacity(port,monkeypatch):
    old=old_port(port);key=old.terminal_key([old.read('MS')])
    monkeypatch.setattr(port,'read',lambda *a,**kw:K.ReadFailure(reason='capacity',detail='test limit',
        input_tokens_unchanged=port.base_tokens,elapsed_ms=0.))
    with pytest.raises(ValueError,match='new lawful read failed: capacity'):
        rebuild_from_replay(old,port,key)

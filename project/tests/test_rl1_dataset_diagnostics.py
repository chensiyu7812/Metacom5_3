"""Protect held-out projection and evidence-join semantics in offline analysis."""
import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'scripts/rl1/69_analyze_dataset_features.py'
spec=importlib.util.spec_from_file_location('dataset_diagnostics',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_test_gold_projection_drops_all_private_content():
    u=dict(id='p1',basic_info='secret',event_experience=[{'secret':1}],questions=[dict(id='s',questions=[dict(idx=1,capability='abstention',question='secret',answer='secret',evidence=['secret'])])],summaries=[dict(idx=2,capability='um',answer='secret',evidence=['secret'])],subsequent_topics=[dict(idx=3,topic='secret')])
    got=m.project_gold([u],{'p1':'test'})[0]
    assert 'secret' not in str(got)
    assert got['questions'][0]['questions'][0]==dict(idx=1,capability='abstention')
    assert m.project_gold([u],{'p1':'train'})[0] is u

def test_owner_local_evidence_does_not_repair_foreign_or_malformed_ids():
    sessions={'p6_conv_3':{'turns':[dict(idx=3,role='seeker',content='I plan to call.') ]}}
    for ref in ('p7_conv_3:3','p6_conv_3;3','p6_conv_3:27'):
        assert m.resolve_reference(ref,sessions,{})['kind']=='unresolved'
    got=m.resolve_reference('p6_conv_3:3',sessions,{})
    assert got['role']=='seeker' and got['text']=='I plan to call.'

def test_private_event_not_mistaken_for_visible_conversation():
    got=m.resolve_reference('p1_event_1',{}, {'p1_event_1':{'conv_id':'esc1024'}})
    assert got=={'kind':'private_event','session':'esc1024'}

def test_missing_summary_statistics_are_not_zero():
    assert m.quantiles([])==dict(n=0,min=None,median=None,p90=None,max=None)

def test_unknown_answer_punctuation_is_not_a_new_answer_class():
    assert m.unknown_answer('Unknown.') and m.unknown_answer('unknown')
    assert not m.unknown_answer('The reason remains unknown, but she moved in July.')

def test_duplicate_turn_ids_cannot_silently_choose_a_source():
    sessions={'s':{'turns':[dict(idx=1,role='seeker',content='yes'),dict(idx=1,role='supporter',content='no')]}}
    assert m.resolve_reference('s:1',sessions,{})['kind']=='unresolved'

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from metacom_pm.rl1.resource_comparison_analysis import summarize
from metacom_pm.rl1.local_gpu_guard import parse_gpu


def test_latest_snapshot_is_used_in_both_directions_without_threshold_relaxation():
    def xml(u,free=46000):
        return f'<nvidia_smi_log><gpu><uuid>MOCK</uuid><utilization><gpu_util>{u} %</gpu_util></utilization><fb_memory_usage><free>{free} MiB</free></fb_memory_usage><processes></processes></gpu></nvidia_smi_log>'
    assert parse_gpu('MOCK, A6000, 46000, 2','',xml(0),'MOCK',latest_snapshot=True)['eligible']
    assert not parse_gpu('MOCK, A6000, 46000, 0','',xml(2),'MOCK',latest_snapshot=True)['eligible']
    assert not parse_gpu('MOCK, A6000, 46000, 0','',xml(0,44000),'MOCK',latest_snapshot=True)['eligible']
    missing='<nvidia_smi_log><gpu><uuid>MOCK</uuid><processes></processes></gpu></nvidia_smi_log>'
    assert not parse_gpu('MOCK, A6000, 46000, 0','',missing,'MOCK',latest_snapshot=True)['eligible']
    # Historical callers keep their old sampling policy and result identity.
    assert not parse_gpu('MOCK, A6000, 46000, 2','',xml(0),'MOCK')['eligible']


def fixture():
    def row(key,head,reply,source,tokens):
        return dict(input_identity=key,prefix_identity='prefix',owner='owner',head=head,selected_keys=source,
            finish_reason='natural_stop',reply=reply,input_tokens=tokens,resource_tokens=tokens-10,
            output_tokens=4,generation_seconds=1,origin='new_generation' if head else 'original_OFF_reuse')
    rows=[row('off',None,'OFF',[],10),row('a','MS','same',['old'],20),row('b','MS','same',['new'],30),row('card','MS','different',['new'],35)]
    pairs=[dict(comparison='A',head='MS',owner='owner',prefix_identity='prefix',source_domain='same original candidate pool',
                input_identities=['a','a'],changed_candidate=False),
           dict(comparison='A',head='MS',owner='owner',prefix_identity='prefix',source_domain='same original candidate pool',
                input_identities=['a','b'],changed_candidate=True),
           dict(comparison='B',head='MS',owner='owner',prefix_identity='prefix',input_identities=['b','card'],
                same_selected_sources=True,omitted_turns=0,summary_generated=False)]
    return rows,pairs


def test_same_input_changed_source_and_presentation_have_separate_denominators():
    rows,pairs=fixture();report,table,off=summarize(rows,pairs)
    assert report['ranking_same_input']['pairs']==1
    assert report['ranking_changed_input']['exact_same']==1 and report['presentation']['different']==1
    assert report['new_inputs']==3 and report['reused_OFF']==1 and report['owners']==1
    assert report['generation_seconds']['total']==3 and not report['policy_learning_evidence']
    assert all(x['quality_direction']=='unverified' for x in table+off)


def test_failed_output_is_missing_not_tie_or_negative_quality():
    rows,pairs=fixture();rows[2].update(finish_reason='technical_timeout',reply=None)
    report,table,off=summarize(rows,pairs)
    assert report['ranking_changed_input']['missing_or_failed']==1
    assert report['presentation']['missing_or_failed']==1
    assert table[1]['exact_reply_equal'] is None and off[1]['exact_reply_equal'] is None


@pytest.mark.parametrize('mutation',['owner','source','omission','duplicate'])
def test_mismatched_comparison_sources_do_not_produce_statistics(mutation):
    rows,pairs=fixture()
    if mutation=='owner':pairs[0]['owner']='other'
    if mutation=='source':pairs[-1]['input_identities'][0]='a'
    if mutation=='omission':pairs[-1]['omitted_turns']=1
    if mutation=='duplicate':rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError):summarize(rows,pairs)


def test_continuation_reuses_sealed_result_and_only_includes_never_started_requests(tmp_path):
    from test_rl1_resource_comparison_runner import setup
    from metacom_pm.rl1.durable import save_json_once as save
    from metacom_pm.rl1.resource_comparison_runner import authorize
    root=tmp_path/'old';r,c,_,requests,_=setup(root);r.step()
    for name,value in [('G_PROTOCOL.json',r.protocol),('G_REQUESTS_PRIVATE.json',requests),
                       ('REUSED_OFF_PRIVATE.json',[]),('PROTECTED_HASHES.json',{}),('CODE_HASHES.json',{})]:save(root/name,value)
    save(root/'PACKAGE_MANIFEST.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.json')})
    path=Path(__file__).resolve().parents[1]/'scripts/rl1/137_prepare_resource_comparison_continuation.py'
    spec=importlib.util.spec_from_file_location('fixed_continuation_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    out=tmp_path/'successor';ready=module.prepare(root,out)
    assert ready['remaining_inputs']==ready['prior_results_reused']==1
    assert json.loads((out/'G_REQUESTS_PRIVATE.json').read_text())==requests[1:]
    assert json.loads((out/'PRIOR_G_RESULTS_PRIVATE.json').read_text())[0]['request']==requests[0]
    protocol=json.loads((out/'G_PROTOCOL.json').read_text())
    assert protocol['combined_G_call_limit']==2 and len(c)==2
    with pytest.raises(ValueError,match='not authorized'):authorize(protocol,None)
    raw=next(r.root.glob('*.raw.json'));raw.unlink()
    with pytest.raises(ValueError,match='unknown prior start'):module.prepare(root,tmp_path/'unsafe')
    assert not (tmp_path/'unsafe').exists()


def test_pending_rows_are_not_observed_tokens_or_quality_results():
    rows,pairs=fixture();rows[2].update(finish_reason='not_started',reply=None,generation_seconds=None,output_tokens=None)
    report,_,_=summarize(rows,pairs)
    assert report['planned_input_tokens']==85 and report['observed_input_tokens']==55
    assert report['generation_seconds']['observed']==2 and report['ranking_changed_input']['missing_or_failed']==1

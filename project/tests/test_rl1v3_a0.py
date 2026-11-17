"""A0 must prepare real visible prefixes without touching inference or gold."""
import copy
import json
from pathlib import Path
import sys

import pytest

from metacom_pm.rl1v3.generator.preflight import (
    environment_snapshot, model_snapshot, prepare_off_requests,
)
from metacom_pm.rl1v3.io import file_sha256, object_sha256


def source_fixture():
    turns=[dict(role='seeker',content='hello',idx=0),dict(role='supporter',content='future secret',idx=1)]
    runtime=dict(users=[dict(owner_id='p1',sessions=[dict(session_id='s1',chronological_rank=1,
                                                       timestamp='2026-01-01',turns=turns)])])
    specs=[dict(prefix=dict(owner_id='p1',session_id='s1',cutoff_rank=1,cut_after_turn_index=0,
        timestamp='2026-01-01',split='train',turns=[dict(role='seeker',content='hello')]),
        inventory='PRIVATE resource',gold='PRIVATE gold')]
    return specs,runtime


def test_off_request_is_deterministic_and_excludes_future_resources_gold():
    specs,runtime=source_fixture()
    rows=prepare_off_requests(specs,runtime,count=1)
    assert rows==prepare_off_requests(specs,runtime,count=1)
    wire=json.dumps(rows)
    assert 'future secret' not in wire and 'PRIVATE' not in wire
    assert rows[0]['request_sha256']==object_sha256(rows[0]['request'])
    assert rows[0]['executed'] is False


@pytest.mark.parametrize('changes',[
    {'cutoff_rank':2}, {'timestamp':'2026-01-02'}, {'cut_after_turn_index':-1},
    {'cut_after_turn_index':1}, {'owner_id':'p2'}, {'session_id':'wrong'},
    {'turns':[{'role':'seeker','content':'wrong'}]},
])
def test_prefix_must_match_real_source(changes):
    specs,runtime=source_fixture();specs[0]['prefix'].update(changes)
    with pytest.raises((ValueError,KeyError)):
        prepare_off_requests(specs,runtime,count=1)


def test_test_split_and_duplicate_prefixes_do_not_pad_batch():
    specs,runtime=source_fixture()
    with pytest.raises(ValueError):prepare_off_requests(specs*100,runtime,count=2)
    specs[0]['prefix']['split']='test'
    with pytest.raises(ValueError):prepare_off_requests(specs,runtime,count=1)


def test_model_inventory_reports_missing_shards_and_hash_mismatch(tmp_path):
    (tmp_path/'config.json').write_text(json.dumps(dict(model_type='fixture',text_config=dict(max_position_embeddings=42))))
    (tmp_path/'model.safetensors.index.json').write_text(json.dumps(dict(weight_map={'layer':'missing.safetensors'})))
    snap=model_snapshot(tmp_path,expected_files={'config.json':'0'*64})
    assert snap['status']=='identity_failure'
    assert snap['missing_weight_shards']==['missing.safetensors']
    assert snap['expected_mismatches']['config.json']['actual']==file_sha256(tmp_path/'config.json')
    assert snap['context_limit']==42 and not snap['weights_loaded']
    assert snap['native_generation_support']=='not_tested'


def test_inventory_fails_closed_on_missing_model(tmp_path):
    assert model_snapshot(tmp_path)['status']=='missing'


def test_environment_inventory_uses_metadata_without_loading_torch():
    snap=environment_snapshot(Path(sys.executable))
    assert snap['packages']['pydantic'] is not None
    assert snap['python']


def test_native_tokenizer_batchencoding_mapping_is_counted(monkeypatch,tmp_path):
    from collections import UserDict
    from types import SimpleNamespace
    from metacom_pm.rl1v3.generator import tokenizer_probe
    specs,runtime=source_fixture();row=prepare_off_requests(specs,runtime,count=1)[0]
    model=tmp_path/'model';model.mkdir()
    (model/'config.json').write_text(json.dumps(dict(text_config=dict(max_position_embeddings=400))))
    (model/'tokenizer.json').write_text('{}')
    requests=tmp_path/'requests.jsonl';requests.write_text(json.dumps(row)+'\n')
    output=tmp_path/'probe.json'
    class Tokenizer:
        chat_template='fixture'
        def apply_chat_template(self,*args,**kwargs):
            return UserDict(input_ids=[101,202,303])
    class AutoTokenizer:
        @staticmethod
        def from_pretrained(path,**kwargs):
            assert kwargs==dict(local_files_only=True,trust_remote_code=False)
            return Tokenizer()
    monkeypatch.setitem(sys.modules,'transformers',SimpleNamespace(AutoTokenizer=AutoTokenizer))
    monkeypatch.setattr(sys,'argv',['probe','--model',str(model),'--requests',str(requests),'--out',str(output)])
    tokenizer_probe.main()
    result=json.loads(output.read_text())
    assert result['rows'][0]['input_tokens']==3
    assert result['rows'][0]['input_ids_sha256']==object_sha256([101,202,303])
    assert result['model_calls']==0 and result['generations_per_second'] is None

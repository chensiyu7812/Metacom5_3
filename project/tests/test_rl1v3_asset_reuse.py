"""Asset-audit behaviour, including family aliases and exact original turn indices."""
from copy import deepcopy
from pathlib import Path
import json

import pytest

from metacom_pm.rl1v3.sources.asset_reuse import esconv_family, rs_rejection, verify_unit, export_audit
from metacom_pm.rl1v3.io import sha256_text, object_sha256, file_sha256


@pytest.mark.parametrize('value',['esc1198','esconv_1198','esconv:esconv_1198','esconv_dialogue:esconv_1198'])
def test_shared_esconv_family_aliases_cannot_evade_overlap(value):
    family=esconv_family(value)
    assert family == 'esconv:esconv_1198'
    assert rs_rejection([value],{family:'train'},{family}) == 'overlap_family'


def test_family_gate_checks_all_ancestors_and_source_split():
    splits={'esconv:esconv_0001':'train','esconv:esconv_0002':'test','esconv:esconv_1198':'train'}
    assert rs_rejection(['esc1'],splits,set()) is None
    assert rs_rejection(['esc1','esc2'],splits,set()) == 'non_train_or_unknown_source'
    assert rs_rejection(['esc1','esc1198'],splits,{'esconv:esconv_1198'}) == 'overlap_family'
    assert rs_rejection([],splits,set()) == 'missing_source'
    assert rs_rejection(['same text about esc1198'],splits,set()) == 'unknown_family'


def fixture():
    text='I intend to move.'
    source=dict(chronological_rank=0,timestamp='2025-01-01',turns=[dict(idx=1,role='seeker',content=text)])
    unit=dict(owner_id='p1',source_session_id='esc1',source_session_rank=0,timestamp='2025-01-01',user_anchored=True,
        supporting_spans=[dict(turn_index=1,turn_id='esc1:1',start_char=0,end_char=len(text),exact_text=text,exact_text_sha256=sha256_text(text))])
    return unit,{('p1','esc1'):source}


def test_original_one_based_idx_is_mapped_to_zero_based_ordinal_explicitly():
    u,s=fixture();errors,spans=verify_unit(u,s)
    assert errors == [] and spans[0]['original_turn_index']==1 and spans[0]['ordinal_turn']==0
    assert spans[0]['speaker']=='seeker'


@pytest.mark.parametrize('change,reason',[({'owner_id':'p2'},'missing_owner_session'),({'source_session_rank':1},'rank_mismatch'),
    ({'timestamp':'2030-01-01'},'reported_time_mismatch'),({'supporting_spans':[]},'no_spans')])
def test_asset_migration_rejects_unbound_owner_time_and_span(change,reason):
    u,s=fixture();u.update(change)
    assert reason in verify_unit(u,s)[0]


@pytest.mark.parametrize('field,value,reason', [('turn_index',0,'ambiguous_or_missing_turn'),('end_char',100,'quote_offset_mismatch'),
    ('exact_text_sha256','0'*64,'quote_hash_mismatch'),('turn_id','esc2:1','turn_identity_mismatch')])
def test_asset_span_cannot_silently_relocate(field,value,reason):
    u,s=fixture();u['supporting_spans'][0][field]=value
    assert reason in verify_unit(u,s)[0]


def test_duplicate_turn_ids_or_supporter_role_reject_user_claim():
    u,s=fixture();s[('p1','esc1')]['turns'] *= 2
    assert 'ambiguous_or_missing_turn' in verify_unit(u,s)[0]
    u,s=fixture();s[('p1','esc1')]['turns'][0]['role']='supporter'
    assert 'user_anchor_role_mismatch' in verify_unit(u,s)[0]


def test_audit_export_is_replayable_and_does_not_overwrite(tmp_path):
    result=dict(protocol='fixture',overview={'bank_v0_records_written':0},files=[],items=[{'old_id':'x','classification':'adapt'}],diagnostics=[])
    manifest=export_audit(result,tmp_path)
    assert export_audit(result,tmp_path) == manifest
    assert manifest['item_ledger']['sha256'] == file_sha256(tmp_path/'ASSET_ITEMS.jsonl')
    assert manifest['manifest_sha256'] == object_sha256({k:v for k,v in manifest.items() if k!='manifest_sha256'})
    changed=deepcopy(result);changed['items'][0]['classification']='quarantine'
    with pytest.raises(FileExistsError):export_audit(changed,tmp_path)


def test_actual_all_2236_units_have_resolvable_original_spans():
    root=Path(__file__).parents[1]
    runtime=json.loads((root/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json').read_text())
    sessions={(u['owner_id'],s['session_id']):s for u in runtime['users'] for s in u['sessions']}
    units=[u for line in (root/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl').read_text().splitlines()
        for u in json.loads(line)['accepted_units']]
    assert len(units)==2236
    assert all(not verify_unit(u,sessions)[0] for u in units)

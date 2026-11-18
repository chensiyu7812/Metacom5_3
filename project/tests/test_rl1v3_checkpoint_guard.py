import json
import struct
import pytest
from metacom_pm.rl1v3.generator.checkpoint_guard import compare_shapes,read_header,check_loading_info


def test_header_reads_metadata_and_checks_complete_ranges(tmp_path):
    h=json.dumps({'w':dict(dtype='BF16',shape=[2],data_offsets=[0,4])}).encode()
    p=tmp_path/'m.safetensors';p.write_bytes(struct.pack('<Q',len(h))+h+b'\x00'*4)
    tensors,rep=read_header(p)
    assert tensors['w']['shape']==[2] and not rep['tensor_data_read']
    p.write_bytes(p.read_bytes()[:-1])
    with pytest.raises(ValueError,match='payload'):read_header(p)


def test_complete_shapes_allow_only_proven_tied_alias():
    expected={'embed':[2,3],'lm_head':[2,3]}
    ck={'old_embed':dict(shape=[2,3],dtype='BF16')}
    report=compare_shapes(expected,ck,renames=[('^old_embed$','embed')],tied={'lm_head':'embed'})
    assert report['tied_aliases']=={'lm_head':'embed'} and report['structural_match']
    for tie in ({},{'lm_head':'missing'}):
        with pytest.raises(ValueError,match='missing required'):compare_shapes(expected,ck,renames=[('old_','')],tied=tie)


@pytest.mark.parametrize('checkpoint,error',[
    ({'w':{'shape':[3]}},'shape mismatch'),
    ({'w':{'shape':[2]},'other':{'shape':[1]}},'unexpected'),
    ({},'missing required')])
def test_shape_admission_fails_closed(checkpoint,error):
    with pytest.raises(ValueError,match=error):compare_shapes({'w':[2]},checkpoint)


def test_explicit_unused_does_not_allow_similar_unreviewed_keys():
    ck={'w':{'shape':[2]},'mtp.fc.weight':{'shape':[1]}}
    assert compare_shapes({'w':[2]},ck,allowed_unused=['mtp.fc.weight'])['explicit_unused']==['mtp.fc.weight']
    ck['mtp.new.weight']={'shape':[1]}
    with pytest.raises(ValueError,match='unexpected'):compare_shapes({'w':[2]},ck,allowed_unused=['mtp.fc.weight'])


@pytest.mark.parametrize('field', ['missing_keys','unexpected_keys','mismatched_keys','error_msgs'])
def test_hf_diagnostics_reject_any_unexplained_loading_error(field):
    info=dict(missing_keys=[],unexpected_keys=[],mismatched_keys=[],error_msgs=[])
    assert check_loading_info(info)==info
    info[field]=['bad']
    with pytest.raises(ValueError):check_loading_info(info)


def test_hf_diagnostics_are_required_and_aliases_explicit():
    with pytest.raises(ValueError):check_loading_info({})
    info=dict(missing_keys=['lm_head'],unexpected_keys=['mtp.fc.weight'],mismatched_keys=[],error_msgs=[])
    assert check_loading_info(info,tied_aliases=['lm_head'],allowed_unused=['mtp.fc.weight'])==info

"""Header/shape admission and post-load checks. Importing does not load a model."""
import json
import math
from pathlib import Path
import re
import struct
from ..io import object_sha256, sha256_bytes

PROTOCOL='pmrl1v3-a0-checkpoint-guard-1'
QWEN_MTP_UNUSED = frozenset(['mtp.fc.weight','mtp.norm.weight','mtp.pre_fc_norm_embedding.weight',
    'mtp.pre_fc_norm_hidden.weight','mtp.layers.0.input_layernorm.weight',
    'mtp.layers.0.post_attention_layernorm.weight'] + ['mtp.layers.0.'+s+'.weight' for s in
    ('mlp.down_proj','mlp.gate_proj','mlp.up_proj','self_attn.k_norm','self_attn.k_proj',
     'self_attn.o_proj','self_attn.q_norm','self_attn.q_proj','self_attn.v_proj')])


def read_header(path):
    """Read metadata only; validate tensor byte ranges against file size."""
    path=Path(path)
    with path.open('rb') as f:
        first=f.read(8)
        if len(first)!=8:raise ValueError('truncated header length')
        n=struct.unpack('<Q',first)[0]
        if not 2<=n<=16*1024*1024:raise ValueError('invalid header length')
        data=f.read(n)
        if len(data)!=n:raise ValueError('truncated header')
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError('duplicate header key')
            out[k]=v
        return out
    h=json.loads(data,object_pairs_hook=unique); tensors={k:v for k,v in h.items() if k!='__metadata__'}
    end=0
    for key,t in sorted(tensors.items(),key=lambda kv:kv[1]['data_offsets']):
        widths={'BF16':2,'F32':4}
        if t['dtype'] not in widths:raise ValueError('unreviewed checkpoint dtype')
        if any(type(d) is not int or d<0 for d in t['shape']):raise ValueError('invalid shape')
        a,b=t['data_offsets']
        if a!=end or b-a!=math.prod(t['shape'])*widths[t['dtype']]:raise ValueError('tensor byte-range mismatch: '+key)
        end=b
    if not tensors or 8+n+end!=path.stat().st_size:raise ValueError('truncated/extra tensor payload')
    return tensors,dict(file=path.name,bytes=path.stat().st_size,header_bytes=n,
        header_sha256=sha256_bytes(data),tensors=len(tensors),tensor_data_read=False)


def compare_shapes(expected,checkpoint,*,renames=(),tied=None,allowed_unused=()):
    tied=tied or {};converted={};mapping={}
    for old,t in checkpoint.items():
        key=old
        for src,dst in renames:key=re.sub(src,dst,key)
        if key in converted:raise ValueError('key conversion collision')
        converted[key]=t
        if old!=key:mapping[old]=key
    extras=set(converted)-set(expected)
    if extras-set(allowed_unused):raise ValueError('unexpected checkpoint weights: '+str(sorted(extras-set(allowed_unused))))
    missing=set(expected)-set(converted); aliases={}
    for name in sorted(missing):
        source=tied.get(name)
        if source not in converted or expected.get(source)!=expected[name]:
            raise ValueError('missing required weight: '+name)
        aliases[name]=source
    for key in set(expected)&set(converted):
        if list(expected[key])!=converted[key]['shape']:raise ValueError('shape mismatch: '+key)
    return dict(expected_tensors=len(expected),checkpoint_tensors=len(checkpoint),
        expected_shapes_sha256=object_sha256(expected),checkpoint_header_sha256=object_sha256(checkpoint),
        converted_names=mapping,tied_aliases=aliases,explicit_unused=sorted(extras),
        missing_required=[],shape_mismatches=[],unexpected_required=[],structural_match=True)


def check_loading_info(info,*,tied_aliases=(),allowed_unused=()):
    if not isinstance(info,dict) or not {'missing_keys','unexpected_keys','mismatched_keys','error_msgs'}<=set(info):
        raise ValueError('missing HF loading diagnostics')
    if set(info['missing_keys'])-set(tied_aliases):raise ValueError('HF randomly initialized missing weights')
    if set(info['unexpected_keys'])-set(allowed_unused):raise ValueError('HF unexpected weights')
    if info['mismatched_keys'] or info['error_msgs']:raise ValueError('HF weight mismatch/conversion error')
    return {k:sorted(map(str,v)) for k,v in info.items()}


def check_loaded_model(model,info,report):
    if type(model).__name__!=report['architecture']:raise ValueError('loaded architecture mismatch')
    shapes={k:list(v.shape) for k,v in model.state_dict().items()}
    if object_sha256(shapes)!=report['expected_shapes_sha256']:raise ValueError('loaded shape set changed')
    if any(t.is_meta for t in model.state_dict().values()):raise ValueError('unloaded meta tensor')
    for alias,source in report['tied_aliases'].items():
        if model.get_parameter(alias) is not model.get_parameter(source):raise ValueError('checkpoint alias not actually tied')
    return check_loading_info(info,tied_aliases=report['tied_aliases'],allowed_unused=report['explicit_unused'])

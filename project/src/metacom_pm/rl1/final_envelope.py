"""Preserved strict final-envelope parsing; no repair or private runtime."""
import hashlib
import json
import re
from .judge import _pairs
FENCE=re.compile(r'```(?:json)?\r?\n(?P<body>[\s\S]*?)\r?\n```\Z')

def text_hash(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()


def unwrap(final):
    if not isinstance(final,str):raise ValueError('final must be text')
    stripped=final.strip()
    if not stripped:raise ValueError('empty final')
    if stripped.startswith('```'):
        match=FENCE.fullmatch(stripped)
        if not match:raise ValueError('incomplete or unsupported outer fence')
        body=match.group('body');kind='single_fence_removed'
    else:body=final;kind='bare_json_unchanged'
    # Whole-string strict JSON read only. Never search/extract a nested object.
    value=json.loads(body,object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if type(value) is not dict:raise ValueError('top-level JSON object required')
    return body,value,dict(transformation=kind,original_final_sha256=text_hash(final),
        adapted_final_sha256=text_hash(body),interior_unchanged=True)

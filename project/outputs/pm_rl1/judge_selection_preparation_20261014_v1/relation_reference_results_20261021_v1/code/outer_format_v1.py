"""Uniform, lossless final-channel envelope adapter. No semantic repair."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import re
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import selection as s
from adapters import final_content
from metacom_pm.rl1.judge import _pairs
from jsonschema import Draft202012Validator

VERSION='pm-rl1-final-envelope-v1-20261015'
FENCE=re.compile(r'```(?:json)?\r?\n(?P<body>[\s\S]*?)\r?\n```\Z')

def text_hash(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

def identity():
    value=dict(version=VERSION,code_sha256=s.sha(__file__),
        strict_implementation_identity=s.code_identity(),
        schema_validator='jsonschema.Draft202012Validator',
        schema_validator_version=importlib.metadata.version('jsonschema'),
        accepted='complete bare JSON object OR exactly one triple-backtick json/unlabelled fence; no other text',
        content_mutations='none; only outer fence delimiters and exterior whitespace removed',
        semantic_revision_delta=0,applies_to=list(s.CANDIDATES))
    return value|dict(identity=s.digest(value))

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

def evaluate(plan,original_request,raw,configuration_identity,draw_id):
    item=plan['items'][original_request['item_key']]
    _,schema=s.payload(plan,original_request)
    base=dict(q=None,m=None,candidate_utility=None,reward_eligible=False,
        response_sha256=text_hash(item['reply']),legal_evidence_identity=s.digest(item['evidence']),
        rubric_identity=s.judge.RUBRIC_ID,judge_runtime_identity=configuration_identity,
        measurement_draw_id=draw_id,output_interface_version=VERSION,
        output_interface_identity=identity()['identity'])
    stage='final_channel';audit={}
    try:
        final,finish=final_content(raw)
        audit['original_final_sha256']=text_hash(final)
        if finish!='natural_stop':
            return dict(measurement=base|dict(measurement_status='technical_failure',technical_reason=finish),
                validation_stage='natural_end_failed',adaptation=audit)
        stage='outer_format_or_JSON'
        body,value,audit=unwrap(final)
        stage='schema'
        Draft202012Validator(schema).validate(value)
        stage='strict_parser_and_evidence'
        measured=s.judge.parse_completion(body,reply=item['reply'],evidence=item['evidence'],
            runtime_identity=configuration_identity,draw_id=draw_id,finish_reason=finish)
        measured.update(output_interface_version=VERSION,output_interface_identity=identity()['identity'])
        return dict(measurement=measured,validation_stage='complete' if measured['measurement_status'] in s.VALID else stage,
            adaptation=audit,adapted_final=body)
    except Exception as exc:
        # All input is local final text/schema; retain failure, never normalize it.
        return dict(measurement=base|dict(measurement_status='parse_or_evidence_failure',
            error_type=type(exc).__name__,error=str(exc)),validation_stage=stage,adaptation=audit)

def reparse_once(path,record):
    """Idempotent derived write: same record reused, conflict rejected; no calls."""
    path=Path(path)
    if path.exists():
        if s.read(path)!=record:raise ValueError('existing derived record differs; never overwrite')
        return False
    s.save(path,record);return True

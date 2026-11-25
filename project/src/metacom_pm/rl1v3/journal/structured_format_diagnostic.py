"""One explicit post-hoc fenced-JSON diagnostic. Never rewrites strict outcomes.

No generation, retry, syntax repair, quote normalization, value substitution or
reward promotion. A sole fenced JSON body is inspected as a separate diagnostic.
"""
from collections import defaultdict
import html
import json
from pathlib import Path
import re
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from .structured_analysis import jl,parse_diagnostics
from .structured_learning import evaluate

PROTOCOL='pmrl1-j-single-fenced-json-diagnostic-v1'
PATTERN=r'```json\s*\n(.*?)\n```'


def extract(text):
    blocks=list(re.finditer(PATTERN,text,flags=re.DOTALL))
    if len(blocks)!=1:return dict(body=None,block_count=len(blocks),outside_text=None,status='no_unique_json_block')
    m=blocks[0]
    return dict(body=m.group(1),block_count=1,outside_text=text[:m.start()]+text[m.end():],status='one_block')


def freeze_rule(path):
    rule=dict(protocol=PROTOCOL,post_hoc=True,trigger='S1 18/18 original strict JSON failures; observed fenced outputs',
        regex=PATTERN,unique_block_required=True,body_modified=False,syntax_repair=False,
        quotes_or_values_normalized=False,original_strict_scores_preserved=True,
        additional_generation_calls=0,scorer_changed=False,reward_qualified=False,
        interpretation='diagnostic field values and source-contract inspection only; no formal success promotion',
        code_sha256=file_sha256(__file__))
    write_json_once(path,rule);return rule


def analyze(package,results_dirs,policy_path,rule_path,out):
    package,out,rule_path=Path(package),Path(out),Path(rule_path);out.mkdir(parents=True,exist_ok=False)
    rule=json.loads(rule_path.read_text());assert rule['protocol']==PROTOCOL and rule['code_sha256']==file_sha256(__file__)
    refs={r['task_id']:r for r in jl(package/'REFERENCES.private.jsonl')}
    requests={r['request_id']:r for r in jl(package/'REQUESTS_ALL.private.jsonl')}
    tasks={r['task_id']:r for r in jl(package/'TASKS.private.jsonl')}
    policy=json.loads(Path(policy_path).read_text());rows=[];outputs={};endpoints=[]
    for p in map(Path,results_dirs):
        outputs.update(json.loads((p/'ACTUAL_OUTPUTS.private.json').read_text()))
        endpoints+=jl(p/'ACTUAL_ENDPOINTS.private.jsonl')
    for e in endpoints:
        b=e['binding'];r=requests[b['request_id']];output=outputs.get(b['request_id']);body=None;derived=None;diag=None
        x=extract(output['text']) if output else dict(body=None,status='no_return',block_count=0,outside_text=None)
        if x['body'] is not None:
            supplied=html.unescape('\n'.join(m['content'] for m in r['model_input']['messages']))
            derived=evaluate(x['body'],refs[r['task_id']],arm=r['arm'],delivered_text=supplied)
            diag=parse_diagnostics(x['body'],refs[r['task_id']],supplied)
        rows.append(dict(task_id=r['task_id'],source_group=tasks[r['task_id']]['source_group'],arm=r['arm'],request_id=r['request_id'],
            original_output_sha256=object_sha256(output) if output else None,original_status=e['status'],original_strict_score=e['score'],
            extraction=x,body_diagnostic=diag,body_contract_diagnostic=derived,post_hoc=True,formal_reward=None,
            actual_cost=dict(input_tokens=output['input_tokens'] if output else 0,
                output_tokens=len(output['token_ids']) if output else 0,seconds=output['seconds'] if output else 0)))
    grouped=defaultdict(dict)
    for r in rows:grouped[r['task_id']][r['arm']]=r
    def summarize(selected):
        return dict(n=len(selected),unique_json_body=sum(r['extraction']['body'] is not None for r in selected),
            value_matches=sum(bool(r['body_diagnostic'] and r['body_diagnostic']['value_correct']) for r in selected),
            body_contract_matches=sum(bool(r['body_contract_diagnostic'] and r['body_contract_diagnostic']['task_success']) for r in selected),
            original_strict_success=sum(bool(r['original_strict_score'] and r['original_strict_score']['task_success']) for r in selected),
            shorter_quote_uncertain=sum(bool(r['body_diagnostic'] and r['body_diagnostic']['shorter_quote_uncertain']) for r in selected),
            input_tokens=sum(r['actual_cost']['input_tokens'] for r in selected),output_tokens=sum(r['actual_cost']['output_tokens'] for r in selected),
            generation_seconds=sum(r['actual_cost']['seconds'] for r in selected),formal_reward_qualified=False)
    policies={}
    for name,assignments in policy['policies'].items():
        by={x['task_id']:x['arm'] for x in assignments};selected=[v[by[k]] for k,v in grouped.items()]
        policies[name]=summarize(selected)
    by_group={g:{arm:summarize([r for r in rows if r['source_group']==g and r['arm']==arm]) for arm in ('BASE','RAW')}
        for g in sorted({r['source_group'] for r in rows})}
    aggregate=dict(protocol=PROTOCOL,post_hoc=True,rule_sha256=file_sha256(rule_path),logical_endpoints=len(rows),
        arms={arm:summarize([r for r in rows if r['arm']==arm]) for arm in ('BASE','RAW')},fixed_policy_diagnostics=policies,
        body_contract_matches_are_not_original_success=True,semantic_sufficiency_not_qualified=True,
        original_outputs_unmodified=True,original_scorer_unmodified=True,new_G_calls=0,formal_reward_qualified=False)
    write_jsonl_once(out/'FORMAT_DIAGNOSTIC_PRIVATE.jsonl',rows);write_json_once(out/'GROUP_DIAGNOSTIC_PUBLIC.json',by_group)
    write_json_once(out/'AGGREGATE_PUBLIC.json',aggregate);return aggregate

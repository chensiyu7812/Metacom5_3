"""Recompute format categories and source-field denominators, CPU only."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.io import write_json_once


def run(source,references,out):
    rows=[json.loads(s) for s in Path(source).read_text().splitlines()]
    refs={r['task_id']:r for r in (json.loads(s) for s in Path(references).read_text().splitlines())}
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    def category(r):
        e=r['extraction']
        if e['body'] is None:return 'no_unique_json_block'
        return 'json_block_with_nonwhitespace_outside' if e['outside_text'].strip() else 'fence_only_outside_whitespace'
    groups={}
    for name in ('fence_only_outside_whitespace','json_block_with_nonwhitespace_outside','no_unique_json_block'):
        rs=[r for r in rows if category(r)==name]
        groups[name]=dict(n=len(rs),BASE=sum(r['arm']=='BASE' for r in rs),RAW=sum(r['arm']=='RAW' for r in rs),
            body_value_matches=sum(bool(r['body_diagnostic'] and r['body_diagnostic']['value_correct']) for r in rs),
            body_contract_matches=sum(bool(r['body_contract_diagnostic'] and r['body_contract_diagnostic']['task_success']) for r in rs),
            original_strict_successes=sum(bool(r['original_strict_score'] and r['original_strict_score']['task_success']) for r in rs))
    wrappers=dict(protocol='structured-format-wrapper-categories-v1',groups=groups,
        original_strict_successes=sum(g['original_strict_successes'] for g in groups.values()),
        complete_response_semantics_for_nonwhitespace_outside='unqualified/uncertain; block-only checks do not evaluate outside assertions',
        post_hoc=True,formal_reward=None)
    arms={}
    for arm in ('BASE','RAW'):
        rs=[r for r in rows if r['arm']==arm];known=[];declared=[]
        for r in rs:
            if r['extraction']['body'] is None:continue
            try:body=json.loads(r['extraction']['body'])
            except (TypeError,ValueError):continue
            if not isinstance(body,dict):continue
            if refs[r['task_id']]['value']!='unknown' and body.get('certainty')=='supported':known.append(r)
            if body.get('certainty')=='unknown':declared.append(r)
        arms[arm]=dict(n=len(rs),known_target_supported_body_n=len(known),
            **{k:sum(bool(r['body_diagnostic'][k]) for r in known) for k in ('source_quote_exact','speaker_correct','reported_date_correct')},
            declared_unknown_bodies=len(declared),compliant_unknown_bodies=sum(bool(r['body_diagnostic']['unknown_form']) for r in declared))
    denoms=dict(protocol='structured-posthoc-field-denominators-v1',post_hoc=True,
        strict_invalid_json_short_circuit_false_fields_are_not_semantic_verdicts=True,
        source_attribute_denominator='Only extracted JSON bodies that assert certainty=supported for a target with a known field value. Unknown-form answers intentionally have blank quote/unknown speaker/null date; those fields are not attributed to a source.',
        body_fields_do_not_establish_complete_reply_semantics=True,formal_reward_qualified=False,arms=arms)
    write_json_once(out/'FORMAT_WRAPPER_CATEGORIES_PUBLIC.json',wrappers)
    write_json_once(out/'DIAGNOSTIC_FIELD_DENOMINATORS_PUBLIC.json',denoms)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('source','references','out'):p.add_argument('--'+n,required=True)
    run(**vars(p.parse_args()))

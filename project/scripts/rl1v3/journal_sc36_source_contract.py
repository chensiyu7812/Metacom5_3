"""Source/serialization localization beside, never instead of, frozen scores.

Comparisons inspect actual supplied bytes and declared source metadata. HTML
unescaping is a diagnostic relation only; it never repairs a generated answer.
"""
import argparse
import html
import json
from pathlib import Path
from collections import Counter
from metacom_pm.rl1v3.io import file_sha256,write_json_once


def jl(path):return [json.loads(s) for s in Path(path).read_text().splitlines()]


def analyze(package,root,out):
    package,root,out=map(Path,(package,root,out));rows=[];private=[]
    for n in (1,2):
        plan=json.loads((package/f'batch-{n:02d}/PLAN_CONSTRAINED.json').read_text())
        refs={r['task_id']:r for r in jl(plan['review_path'])}
        requests={r['request_id']:r for r in jl(plan['requests_path'])}
        for e in jl(root/f'SC{n}_results_v1/ENDPOINTS_CONSTRAINED_PRIVATE.jsonl'):
            if e['evaluation']['format_status']!='pass':continue
            answer=json.loads(e['actual_output']['text']);b=e['binding'];ref=refs[b['task_id']]
            text='\n'.join(m['content'] for m in requests[b['request_id']]['model_input']['messages'])
            quote=answer['quote'];claim=answer['value']!='unknown'
            decoded=html.unescape(quote);ev=ref['evidence'];score=e['evaluation']['strict_score']
            raw_match=len(quote)>=3 and quote in text
            decoded_match=len(decoded)>=3 and decoded in ev['text']
            labels=[]
            if claim and quote!=decoded and raw_match and decoded_match:
                labels.append('literal_copy_of_rendered_HTML_entity_source_quote')
            if claim and raw_match and quote not in ev['text'] and e['task_category']=='report_date' and ev['reported_date'] in quote:
                labels.append('visible_report_metadata_quoted_outside_utterance_contract')
            if claim and len(quote)>=3 and quote in ev['text'] and ref['required_literal'].casefold() not in quote.casefold():
                labels.append('source_exact_short_quote_excludes_required_literal')
            if claim and answer['speaker']!=ev['speaker']:
                labels.append('speaker_field_differs_from_frozen_utterance_reference')
            if claim and answer['reported_date']!=ev['reported_date']:
                labels.append('reported_date_field_differs_from_source_metadata')
            row=dict(task_id=b['task_id'],arm=b['arm'],task_category=e['task_category'],
                request_id=b['request_id'],output_sha256=e['output_sha256'],strict_success=score['task_success'],
                value_correct=score['value_correct'],labels=labels,
                actual_rendered_prompt_contains_quote=raw_match if claim else None,
                unescaped_quote_in_source=decoded_match if claim else None,
                original_score_changed=False,formal_reward=None)
            rows.append(row)
            if not score['task_success']:
                private.append(dict(**row,answer=answer,reference=ref,strict_score=score))
    out.mkdir(parents=True,exist_ok=False)
    public=dict(protocol='sc36-source-contract-localization-v1',rows=rows,
        counts=dict(Counter(label for row in rows for label in row['labels'])),
        script_sha256=file_sha256(__file__),original_scores_changed=False,formal_reward=None,
        limitation='Observable serialization/contract relations only. Neither unescaping nor metadata interpretation changes original strict success.')
    write_json_once(out/'SC36_SOURCE_CONTRACT_PUBLIC.json',public)
    write_json_once(out/'SC36_FAILURES_PRIVATE.json',private)
    return public['counts']


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('package','root','out'):p.add_argument('--'+k,required=True)
    print(json.dumps(analyze(**vars(p.parse_args())),indent=2))

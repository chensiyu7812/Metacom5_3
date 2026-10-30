"""Mechanical comparison of fixed replies; no semantic scores or inferred gold.

Identical input pairs, changed source choices and same-source presentation pairs
have separate denominators. Failed/absent replies never become ties or zeros.
"""
from collections import Counter
from statistics import mean, median


def summarize(rows, comparisons):
    by_id={r['input_identity']:r for r in rows}
    if len(by_id)!=len(rows):raise ValueError('duplicate prepared input identity')
    off={}
    for row in rows:
        if row['head'] is None:
            if row['prefix_identity'] in off:raise ValueError('more than one OFF per prefix')
            off[row['prefix_identity']]=row
    pairs=[]
    for index,c in enumerate(comparisons):
        left,right=[by_id[k] for k in c['input_identities']]
        if any(r['prefix_identity']!=c['prefix_identity'] or r['head']!=c['head'] or r['owner']!=c['owner'] for r in (left,right)):
            raise ValueError('comparison prefix/head/owner binding changed')
        if c['comparison']=='A':
            if c['source_domain']!='same original candidate pool':raise ValueError('ranking source domain changed')
            if c['changed_candidate']!=(left['selected_keys']!=right['selected_keys']):raise ValueError('candidate-change flag mismatch')
        elif c['comparison']=='B':
            if not c['same_selected_sources'] or c['omitted_turns']!=0 or c['summary_generated'] or left['selected_keys']!=right['selected_keys']:
                raise ValueError('same-source full-turn presentation comparison changed')
        else:raise ValueError('unknown comparison; no posthoc arm invention')
        comparable=all(r['finish_reason']=='natural_stop' and r['reply'] is not None for r in (left,right))
        pairs.append(dict(index=index,comparison=c['comparison'],head=c['head'],owner=c['owner'],prefix_identity=c['prefix_identity'],
            left_input=left['input_identity'],right_input=right['input_identity'],same_input=left['input_identity']==right['input_identity'],
            changed_sources=left['selected_keys']!=right['selected_keys'],comparable=comparable,
            exact_reply_equal=(left['reply']==right['reply']) if comparable else None,
            input_token_delta=right['input_tokens']-left['input_tokens'],
            resource_token_delta=right['resource_tokens']-left['resource_tokens'],
            quality_direction='unverified',correct_uptake='unverified',causal_quality_effect='not_identified'))
    off_pairs=[]
    for row in rows:
        if row['head'] is None:continue
        base=off[row['prefix_identity']]
        comparable=row['finish_reason']==base['finish_reason']=='natural_stop'
        off_pairs.append(dict(input_identity=row['input_identity'],prefix_identity=row['prefix_identity'],owner=row['owner'],head=row['head'],
            comparable=comparable,exact_reply_equal=(row['reply']==base['reply']) if comparable else None,
            quality_direction='unverified'))
    def counts(group):
        return dict(pairs=len(group),comparable=sum(x['comparable'] for x in group),
            exact_same=sum(x['exact_reply_equal'] is True for x in group),
            different=sum(x['exact_reply_equal'] is False for x in group),
            missing_or_failed=sum(x['exact_reply_equal'] is None for x in group))
    fresh=[r for r in rows if r['origin']=='new_generation']
    prior=[r for r in rows if r['origin']=='prior_generation_reuse']
    times=[r['generation_seconds'] for r in fresh if r['generation_seconds'] is not None]
    report=dict(inputs=len(rows),new_inputs=len(fresh),prior_G_reuse=len(prior),reused_OFF=len(off),prefixes=len(off),owners=len({r['owner'] for r in rows}),
        finish_reasons=dict(Counter(r['finish_reason'] for r in fresh)),
        ranking_same_input=counts([p for p in pairs if p['comparison']=='A' and p['same_input']]),
        ranking_changed_input=counts([p for p in pairs if p['comparison']=='A' and not p['same_input']]),
        presentation=counts([p for p in pairs if p['comparison']=='B']),
        by_head={h:dict(ranking_changed_input=counts([p for p in pairs if p['comparison']=='A' and not p['same_input'] and p['head']==h]),
            versus_OFF=counts([p for p in off_pairs if p['head']==h])) for h in sorted({r['head'] for r in fresh})},
        by_owner={o:dict(prefixes=len({r['prefix_identity'] for r in rows if r['owner']==o}),
            ranking_changed_input=counts([p for p in pairs if p['owner']==o and p['comparison']=='A' and not p['same_input']]),
            presentation=counts([p for p in pairs if p['owner']==o and p['comparison']=='B'])) for o in sorted({r['owner'] for r in rows})},
        planned_input_tokens=sum(r['input_tokens'] for r in fresh),
        observed_input_tokens=sum(r['input_tokens'] for r in fresh if r['generation_seconds'] is not None),
        new_output_tokens_observed=sum(r['output_tokens'] or 0 for r in fresh),
        prior_generation_seconds=sum(r['generation_seconds'] for r in prior),
        generation_seconds=dict(observed=len(times),total=sum(times),mean=mean(times) if times else None,median=median(times) if times else None,
            minimum=min(times) if times else None,maximum=max(times) if times else None),
        quality_gain='unverified',judge_qualification=False,policy_learning_evidence=False,
        caveats=['same-input pairs reuse one execution; not independent repeats',
            'different replies do not establish better replies','fixed one-resource contrasts do not test read-then-decide',
            'development support set; prefixes are clustered within owners','raw failed outputs are retained, not quality outcomes'])
    return report,pairs,off_pairs

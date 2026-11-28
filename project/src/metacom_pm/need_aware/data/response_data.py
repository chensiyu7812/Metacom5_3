"""Official reply supervision, replacing (not overwriting) the retired action templates.

Evaluation-side source joins live here. Runtime supply is a separate command which
cannot open this module's targets, Direct spans, or category annotations.
"""
from collections import Counter, defaultdict
import hashlib
import json
import re
import shutil
from pathlib import Path

from .contracts import load_runtime, digest
from .history import HistoryResolver
from .personamem import load_rows, parse_literal, write_json, write_jsonl

SEED = 'naa-response-20261128'


def key(purpose, value):
    return hashlib.sha256(f'{SEED}|{purpose}|{value}'.encode()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def sources(source_root, training_root):
    tasks = load_runtime(Path(training_root) / 'runtime/tasks.jsonl')
    provenance = {x['task_id']: x for x in jsonl(Path(training_root) / 'candidate_provenance.jsonl')}
    rows = load_rows(source_root, 'train')
    joined = {t.task_id: rows[provenance[t.task_id]['source_row']] for t in tasks}
    for t in tasks:
        r = joined[t.task_id]
        assert 'pm2:' + r['persona_id'] == t.persona_group
        assert parse_literal(r['user_query'])['content'] == t.user_query
    return tasks, provenance, joined


def selection(tasks, rows, split, limit=280):
    others = sorted((t.task_id for t in tasks if rows[t.task_id]['who'] == 'others'),
                    key=lambda t: key('train-others-50', t))[:50]
    groups = defaultdict(list)
    for t in tasks:
        if t.persona_group in split['development']:
            groups[t.persona_group].append(t.task_id)
    selected, owners = [], []
    for owner in sorted(groups, key=lambda o: key('wp4-owner-order', o)):
        if len(selected) + len(groups[owner]) <= limit:
            selected.extend(sorted(groups[owner])); owners.append(owner)
    return others, owners, selected


def review_packets(source_root, training_root, allocation, out):
    tasks, prov, rows = sources(source_root, training_root)
    by_id = {t.task_id: t for t in tasks}
    expected = selection(tasks, rows, allocation['original_split'])
    assert expected == (allocation['others50'], allocation['development_selected_owners'],
                        allocation['development_selected_task_ids'])
    resolver = HistoryResolver(Path(training_root) / 'runtime')
    packets = []
    for tid in allocation['others50']:
        t, r = by_id[tid], rows[tid]
        records = resolver.resolve(t)
        spans = prov[tid]['verified_spans']
        ids = {s['source_id'] for s in spans}
        packets.append(dict(task_id=tid, owner=t.persona_group, source_row=prov[tid]['source_row'],
            query=t.user_query, correct_answer=r['correct_answer'],
            incorrect_answers=parse_literal(r['incorrect_answers']),
            direct_status=prov[tid]['direct_status'],
            direct_records=[x.to_dict() for x in records if x.source_id in ids],
            # Full legal source remains inspectable; Direct is a locator, never a semantic label.
            legal_history_ref=str(Path(training_root)/'runtime'/t.history_ref),
            history_sha256=t.history_sha256,
            source_categories={k:r[k] for k in ('who','pref_type','updated','sensitive_info')}))
    write_jsonl(Path(out)/'review50/PACKETS.private.jsonl', packets)
    write_json(Path(out)/'review50/SAMPLE.json', dict(seed=SEED, n=len(packets),
        task_ids=allocation['others50'], selection='hash of task id before outputs; all training-side splits',
        annotation_provenance='single AI-assisted source review; no independent human rater'))
    # A fixed source-support subset used in the same data-build pass. No model
    # outputs, new condition or qualification gate; not a random prevalence sample.
    allowed=set(allocation['original_split']['fit']+allocation['original_split']['tune'])
    chosen=sorted([t for t in tasks if t.persona_group in allowed and rows[t.task_id]['who']=='self'
        and rows[t.task_id]['sensitive_info']=='False' and rows[t.task_id]['updated']=='False'],
        key=lambda t:key('reply-support-review',t.task_id))[:96]
    extra=[]
    for t in chosen:
        ids={z['source_id'] for z in prov[t.task_id]['verified_spans']}
        extra.append(dict(task_id=t.task_id,query=t.user_query,positive=rows[t.task_id]['correct_answer'],
            records=[z.to_dict() for z in resolver.resolve(t) if z.source_id in ids],
            direct_status=prov[t.task_id]['direct_status']))
    write_jsonl(Path(out)/'support96/PACKETS.private.jsonl',extra)
    return packets


def advice_screen(query, reply):
    """Narrow weak-supervision screen: no asserted hidden personal fact.

    NOT a semantic truth classifier. Only nonassertive generic advice is eligible
    automatically; personalized replies require source review (implicit allowed).
    Named external facts, medical claims, temporal schedules and first-person
    autobiography are held out. Unknowns remain candidate rows with mask=False.
    """
    low=reply.lower().replace('’',"'")
    if not re.match(r'^(you (could|might)|consider |try |one (way|approach)|if you |to |when you )', low):
        return False, 'needs_semantic_review'
    if re.search(r"\b(since|given|because|already|always|remember|diagnos\w*|doctor|medicat\w*|migraine\w*|vitamin|blood|insomnia|diabet\w*|surgery|i|my|we|our)\b",low):
        return False,'personal_or_medical_assertion_needs_review'
    if re.search(r"\b(you (?:have|had|enjoy|love|prefer|are|were)|you've|you're|your (?:own |favorite |favourite )?(?:family|parents?|father|mother|husband|wife|children|kids|son|daughter|career|heritage|roots|culture|collection|history|diagnosis|habit|routine|workshop))\b",low):
        return False,'personal_assertion_needs_review'
    # Proper names/brands/places and calendar claims are not verified by conversation overlap.
    interior=re.sub(r'(^|[.!?]\s+)[A-Z][a-z]*', '', reply)
    if re.search(r'\b[A-Z][a-zA-Z]+\b',interior) or re.search(r'\b(upcoming|this (month|year|weekend)|next (week|month))\b',low):
        return False,'external_or_time_fact_needs_review'
    if re.search(r'\b(avoid|without|not |instead|different from)\b',query.lower()):
        return False,'current_constraint_needs_semantic_review'
    stop=set('what some how can could would should the and with that this your you for are get make ways good help more feel feeling when from into have want'.split())
    words=lambda s:set(re.findall(r'[a-z]{4,}',s.lower()))-stop
    if not words(query)&words(reply):
        return False,'request_alignment_unknown'
    return True,'nonassertive_official_advice_weak_supervision'


def materialize_official_candidates(source_root,training_root,allocation,out):
    """Actual original replies and all three alternatives, before supply joining.

    Every source reference points to existing hash-bound legal history. These are
    audited candidate records, never automatically trainable simply for existing.
    """
    from .personamem import sha_file
    tasks,provenance,rows=sources(source_root,training_root)
    splits={o:k for k,v in allocation['original_split'].items() for o in v}
    results=[]
    for task in tasks:
        r=rows[task.task_id];advice,reason=advice_screen(task.user_query,r['correct_answer'])
        negatives=parse_literal(r['incorrect_answers'])
        history=Path(training_root)/'runtime'/task.history_ref
        assert sha_file(history)==task.history_sha256
        results.append(dict(task_id=task.task_id,owner=task.persona_group,split=splits[task.persona_group],
            original_runtime_task=task.to_dict(),legal_history_file=str(history),
            original_request=task.user_query,correct_answer=r['correct_answer'],incorrect_answers=negatives,
            source_row=provenance[task.task_id]['source_row'],revision=task.dataset_revision,
            direct_locator_status=provenance[task.task_id]['direct_status'],direct_is_semantic_label=False,
            nonassertive_advice_screen=advice,screen_reason=reason,
            training_allowed=False,reason='candidate source export; final training masks require actual supplied evidence join',
            negative_relation='dataset-relative candidates; no presumption of falsehood or harm'))
    out=Path(out);write_jsonl(out/'official_source/CANDIDATES.private.jsonl',results)
    report=dict(rows=len(results),owners=len({x['owner'] for x in results}),
        split=dict(Counter(x['split'] for x in results)),original_reply_records=len(results),
        original_alternative_records=sum(len(x['incorrect_answers']) for x in results),
        legal_history_hash_verified=len(results),hidden_persona_exported=False,
        final_supply_join_pending=True,
        dataset_sha256=sha_file(out/'official_source/CANDIDATES.private.jsonl'))
    write_json(out/'official_source/SUMMARY.json',report)
    return report


def freeze_development(source_root,training_root,allocation,out):
    from dataclasses import replace
    from .personamem import sha_file
    from ..evaluation.contracts import EvalTask
    from ..evaluation.mcq import make_options
    from ..evaluation.wp4_mcq import POLICY
    tasks,_,rows=sources(source_root,training_root);out=Path(out)/'development_frozen'
    runtime=[];evaluation=[]
    ids=set(allocation['development_selected_task_ids'])
    for t in tasks:
        if t.task_id not in ids:continue
        r=rows[t.task_id];pos=r['correct_answer'];neg=parse_literal(r['incorrect_answers'])
        options,gold=make_options(pos,neg,int(key('mcq-options',t.task_id)[:8],16))
        runtime.append(replace(t,task_mode='mcq',options=options).to_dict())
        evaluation.append(EvalTask(t.task_id,gold,pos,'',[],
            {k:r[k] for k in ('who','pref_type','updated','sensitive_info')},[],
            'not_used_for_wp4',POLICY['scoring_protocol']).to_dict())
        target=out/'runtime'/t.history_ref;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(Path(training_root)/'runtime'/t.history_ref,target)
        assert sha_file(target)==t.history_sha256
    write_jsonl(out/'runtime/tasks.mcq.jsonl',runtime)
    write_jsonl(out/'evaluation/tasks.mcq.jsonl',evaluation);write_json(out/'POLICY.json',POLICY)
    write_json(out/'FREEZE.json',dict(tasks=len(runtime),owners=len({t['persona_group'] for t in runtime}),
        complete_owner_groups=True,outputs_read=False,
        artifacts={str(p.relative_to(out)):sha_file(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='FREEZE.json'}))
    return dict(tasks=len(runtime),owners=len({t['persona_group'] for t in runtime}),freeze_sha256=sha_file(out/'FREEZE.json'))


def build(source_root, training_root, allocation, supply_root, out, annotations):
    """Join frozen runtime supply to original official targets on evaluation side."""
    from dataclasses import replace
    from ..agent import reply_protocol as RP
    from ..evaluation.contracts import EvalTask
    from ..evaluation.mcq import make_options
    from .short_protocol import PROTOCOL
    from .personamem import sha_file
    out=Path(out);supply_root=Path(supply_root)
    done=json.loads((supply_root/'SUPPLY_DONE.json').read_text())
    tasks,prov,rows=sources(source_root,training_root)
    reviews={x['task_id']:x for p in annotations for x in jsonl(p)}
    split={owner:k for k,v in allocation['original_split'].items() for owner in v}
    assert len(split)==177
    family_splits=defaultdict(set)
    for t in tasks:family_splits[t.source_family].add(split[t.persona_group])
    assert all(len(v)==1 for v in family_splits.values()),'history-family crosses training partitions'
    candidates=[];audits=[];dev=[];evals=[];requests=[];counts=Counter()
    for t in tasks:
        r=rows[t.task_id];p=supply_root/'runtime'/f'{t.task_id}.json'
        assert sha_file(p)==done['runtime_manifest'][p.name]
        supplied=json.loads(p.read_text());assert supplied['task_sha256']==digest(t.to_dict())
        positive=r['correct_answer'];negatives=parse_literal(r['incorrect_answers'])
        assert len(negatives)==3 and all(isinstance(x,str) for x in negatives)
        review=reviews.get(t.task_id)
        auto,reason=advice_screen(t.user_query,positive)
        delivered=set(supplied['trace']['delivered_ids'])
        review_sources=set(review['checked_source_ids']) if review else set()
        covered=bool(review_sources) and review_sources <= delivered
        if review:
            support=review['positive_support']
            admitted=support=='current_request_supported_generic_reply' or (support=='supported_candidate' and covered)
            reason=('source_review_'+support) if admitted else ('review_'+support+'_or_evidence_not_delivered')
        else:
            admitted=auto and bool(delivered) and r['updated']=='False' and r['sensitive_info']=='False'
            if auto and not admitted:reason='permission_or_sensitive_context_requires_review'
        # Pair negatives only after individual source review AND source delivery.
        pair=review['pair_negative_indices'] if review and admitted and covered else []
        if any(positive==negatives[j] for j in pair):raise ValueError('identical positive/negative')
        partition=split[t.persona_group]
        target=dict(task_id=t.task_id,owner=t.persona_group,history_family=t.source_family,split=partition,
            runtime_ref=str(p),runtime_sha256=sha_file(p),messages_sha256=digest(supplied['messages']),
            positive=positive,negatives=negatives,pair_negative_indices=pair,
            sft_eligible=admitted,training_allowed=admitted and partition=='fit',
            positive_status=reason,class_weight=1.0,source_row=prov[t.task_id]['source_row'],
            source_revision=t.dataset_revision,source_reply_sha256=digest(positive),
            source_negative_sha256=digest(negatives),supervision='official_relative_reply_candidate',
            semantic_truth_not_guaranteed=True)
        candidates.append(target)
        audits.append(dict(task_id=t.task_id,split=partition,positive_status=reason,
            direct_status=prov[t.task_id]['direct_status'],
            direct_is_semantic_label=False,reviewed=bool(review),review_sources_delivered=covered,
            selected_source_ids=sorted(delivered),selected_source_hashes=supplied['trace']['delivered_text_sha256'],
            pair_negative_indices=pair,negative_relation=['reviewed_dataset_relative_attribution_error' if j in pair
                else 'unverified_or_reasonable_alternative_do_not_train_as_error' for j in range(3)],
            category={k:r[k] for k in ('who','pref_type','updated','sensitive_info')}))
        counts[partition+'_candidates']+=1
        if admitted:counts[partition+'_sft']+=1
        if pair:counts[partition+'_pair_rows']+=1;counts[partition+'_pairs']+=len(pair)
        if t.task_id in allocation['development_selected_task_ids']:
            options,gold=make_options(positive,negatives,int(key('mcq-options',t.task_id)[:8],16))
            mt=replace(t,task_mode='mcq',options=options)
            dev.append(mt.to_dict())
            evals.append(EvalTask(t.task_id,gold,positive,'',[],
                {k:r[k] for k in ('who','pref_type','updated','sensitive_info')},[],
                'not_used_for_wp4',PROTOCOL).to_dict())
            for arm in RP.ARMS:
                messages=RP.messages(mt,supplied['evidence'],arm,mcq=True)
                requests.append(dict(task_id=t.task_id,arm=arm,task_sha256=digest(mt.to_dict()),
                    scoring_protocol=PROTOCOL,request_sha256=digest(messages),messages=messages,
                    evidence_sha256=digest(supplied['evidence']) if arm in ('U0','U1','U1+') else None,
                    runtime_supply_sha256=sha_file(p),owner=t.persona_group,history_family=t.source_family))
    write_jsonl(out/'supervision/CANDIDATES.private.jsonl',candidates)
    write_jsonl(out/'audit/SOURCE_AUDIT.private.jsonl',audits)
    for partition in ('fit','tune','development'):
        accepted=[x for x in candidates if x['split']==partition and x['sft_eligible']]
        # Identical positive list/order for both objectives; zero pair weight where unknown.
        accepted.sort(key=lambda x:key('sample-order',x['task_id']))
        write_jsonl(out/f'supervision/{partition}.private.jsonl',accepted)
    rt=out/'development/runtime';rt.mkdir(parents=True,exist_ok=True)
    for t in dev:
        dest=rt/t['history_ref'];dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copyfile(Path(training_root)/'runtime'/t['history_ref'],dest)
    write_jsonl(rt/'tasks.mcq.jsonl',dev);write_jsonl(out/'development/evaluation/tasks.mcq.jsonl',evals)
    write_jsonl(out/'development/requests.private.jsonl',requests)
    summary=dict(protocol='naa-official-reply-supervision-v1',source_candidates=len(tasks),
        counts=dict(counts),development_tasks=len(dev),development_owners=len({x['persona_group'] for x in dev}),
        development_requests=len(requests),reviewed=len(reviews),
        evidence_supply=done['protocol'],reply_protocol_sha256=RP.identity(),
        retired_4772_used=0,formal_outcomes_used=0,training_runs=0,
        exact_duplicate_positive_texts=len(candidates)-len({x['positive'] for x in candidates}),
        exact_duplicate_query_texts=len(tasks)-len({t.user_query for t in tasks}),
        history_family_partition_overlap=0,
        original_training_owner_partitions={k:len(v) for k,v in allocation['original_split'].items()},
        updated_count=sum(r['updated']=='True' for r in rows.values()),
        updated_nonforget_count=sum(r['updated']=='True' and r['pref_type']!='ask_to_forget' for r in rows.values()),
        caveats=['automatically admitted nonassertive advice is weak official supervision, not a semantic proof',
                 'unknown factual claims excluded; Direct location alone never admits a target',
                 'official incorrect answers are relative candidates, not automatically false or harmful',
                 'source review is AI-assisted single review; external factual claims not generally verified'])
    write_json(out/'SUMMARY.json',summary)
    return summary

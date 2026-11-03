#!/usr/bin/env python3
"""Reuse original human answers with their actual replies and evidence.

Offline development analysis only. No new questionnaire, human answer, paid
call, score correction or training reward is produced. Known disagreements are
preserved by date and task instead of averaging them into a synthetic label.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest


def build(output):
    if output.exists(): raise ValueError('new analysis directory required')
    base = PROJECT/'outputs/pm_rl1'; sources = {}
    def read(path):
        path=Path(path).resolve(); data=path.read_bytes()
        sources[str(path)]=hashlib.sha256(data).hexdigest()
        return json.loads(data)
    def verified_folder(path):
        manifest=read(path/'OUTPUT_MANIFEST.json')
        for name, expected in manifest.items():
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('unsafe manifest path')
            data=(path/name).read_bytes()
            if hashlib.sha256(data).hexdigest()!=expected: raise ValueError('source manifest changed')
        return path
    old=verified_folder(base/'human_reference_reuse_20261102_v2')
    for path, expected in read(old/'INPUT_HASHES_PRIVATE.json').items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:
            raise ValueError('original human/source binding changed: '+path)
    bank=read(old/'REFERENCE_BANK_PRIVATE.json')
    archive=Path('/home/tokkio/成果归档/PM-RL1/04_人评原件/2026-10-14/PM_RL1_标注可读包_开发16题_20261014.zip')
    sources[str(archive)]=hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as z:
        packet=json.loads(z.read('04_原样标注与回复.json'))
        contexts=json.loads(z.read('05_完整合法来源.json'))['sources']
    if len(packet['items'])!=16 or any(x['group']!='development' for x in packet['items']):
        raise ValueError('only already-open development sources are permitted')
    evidence={digest(x['source']):x['source'] for x in contexts}
    context_ids={x['reading_source_id']:digest(x['source']) for x in contexts}
    replies={}; original_pairs={}; current_observations=[]
    for row in packet['items']:
        eid=context_ids[row['reading_source_id']]; original_pairs[row['pair_id']]=row
        for side in 'AB':
            value=row['Chen']['original_reply_'+side]
            replies[(eid,digest(value))]=value
    judge=base/'judge_selection_preparation_20261014_v1'
    more_evidence=read(judge/'acceptability_resource_review_20261019_v1/materials/contexts.json')
    for value in more_evidence.values():
        if evidence.get(digest(value))!=value: raise ValueError('old context differs across packets')
    for row in read(judge/'acceptability_resource_review_20261019_v1/materials/selected_existing_records.json'):
        if row['split']!='dev' or digest(row['reply'])!=row['reply_identity']:
            raise ValueError('historical reply identity changed')
        eid=digest(more_evidence[row['context_id']]);replies[(eid,row['reply_identity'])]=row['reply']
    assets=[]
    for family in ('pairs','singles','supplements'):
        for original in bank[family]:
            row=deepcopy(original);eid=row['evidence_identity']
            ids=row['reply_identities'] if family=='pairs' else [row['reply_identity']]
            row.update(asset_id=family+':'+row['source']+':'+row['record_id'],
                evidence=evidence[eid],replies={rid:replies[(eid,rid)] for rid in ids},
                task_family=family,independent_new_observation=False)
            if row['source']=='20261014_development':
                origin=original_pairs[row['record_id']]
                if row['raw_label']!=origin['Chen']['original_label']:
                    raise ValueError('reformatted human answer differs from original')
                if set(ids)!={digest(origin['Chen']['original_reply_'+side]) for side in 'AB'}:
                    raise ValueError('human pair sides changed')
                row['original_question_number']=origin['Chen']['original_question_number']
            assets.append(row)
    latest=verified_folder(base/'paid_development_snapshot_20261103_refresh_final')
    progress=read(latest/'DETAILS_PRIVATE.json'); live={r['key']:r for r in progress['materials']}
    historical={r['item_key']:r for r in read(judge/'draft_build_00/human_and_historical_reference_private.json')}
    comparisons=[]
    for human in bank['singles']:
        item=human['old_item_key'];qmin=human['q_value'] if human['q_status']=='single' else human['q_min']
        qmax=human['q_value'] if human['q_status']=='single' else human['q_max']
        previous=historical[item];origin=original_pairs[previous['pair_id']]
        if (digest(origin['Chen']['original_reply_'+previous['side']])!=human['reply_identity']
                or context_ids[origin['reading_source_id']]!=human['evidence_identity']):
            raise ValueError('historical alias does not bind the same reply and evidence')
        row=dict(item_key=item,reference_id=human['record_id'],human_q_interval=[qmin,qmax],human_m=human['m_value'],
            human_U_interval=[qmin/4-human['m_value'],qmax/4-human['m_value']],versions={})
        for version in ('historical_old','historical_v2','current_S'):
            score=live[item]['candidates']['S'] if version=='current_S' and item in live else (
                historical[item][version] if version!='current_S' else None)
            if score is None: row['versions'][version]=None;continue
            if version=='current_S' and (live[item]['reply_identity']!=human['reply_identity'] or live[item]['evidence_identity']!=human['evidence_identity']):
                raise ValueError('current score is not the same complete input')
            q,m=score['q'],score['m']
            row['versions'][version]=dict(q=q,m=m,U=q/4-m,q_in_human_interval=qmin<=q<=qmax,m_matches=m==human['m_value'])
        comparisons.append(row)
    # Preserve the actual returned explanation, including a conflicting one.
    for item in ('dev04B','dev06B','dev35B'):
        material=live[item]
        attempt=next(x for x in progress['attempts'] if x['logical_identity']==material['logical_identity'] and x['settled'])
        rawpath=base/'execution_bridges_20261103_v1/live_J/S'/(attempt['attempt_id']+'.raw.json')
        if hashlib.sha256(rawpath.read_bytes()).hexdigest()!=attempt['raw_sha256']:
            raise ValueError('current returned explanation changed')
        raw=read(rawpath)
        current_observations.append(dict(item_key=item,reply_identity=material['reply_identity'],
            evidence_identity=material['evidence_identity'],attempt_id=attempt['attempt_id'],
            final=json.loads(raw['choices'][0]['message']['content']),human_reask_required=False))
    new_pairs=read(base/'completion_preparation_20261022/development_pairs_private.json')
    candidate_review=[]
    pair_ids={r['pair_identity'] for r in bank['pairs']}
    for i,pair in enumerate(new_pairs,1):
        eid=digest(pair['evidence']);rids=[digest(t) for t in pair['replies']]
        key=digest(dict(evidence=eid,replies=sorted(rids)))
        scored=[live[f'newdev_{i:02d}_{side}']['candidates']['S'] for side in (0,1)]
        candidate_review.append(dict(pair=f'newdev_{i:02d}',evidence_identity=eid,reply_identities=rids,
            exact_old_pair=key in pair_ids,context_previously_in_human_bank=eid in evidence,
            S=scored,S_ON_minus_OFF=None if any(x is None for x in scored) else scored[1]['U']-scored[0]['U'],
            human_answer=None,questionnaire_disposition='HOLD_NOT_AUTOMATICALLY_REQUIRED',
            reason='First use existing substantive answers and diagnose existing score failures. New answer requires an explicit decision it could change.'))
    training=read(verified_folder(base/'actual_training_feedback_20261103_v1')/'INPUTS_PRIVATE.json')
    matches=[]
    for key,item in training.items():
        exact=[a['asset_id'] for a in assets if a['evidence_identity']==item['evidence_identity'] and item['reply_identity'] in a['replies']]
        if exact:matches.append(dict(input_identity=key,references=exact))
    noise=read(judge/'noise_human_analysis_20261020_v1/analysis.json')
    noise_reuse=[{k:r[k] for k in ['pair_id','human_direction','draw_U_A_minus_B','draw_directions','reference_scope']} for r in noise['pairs']]
    summary=dict(original_pairs=len(bank['pairs']),pair_directions=dict(Counter(x['direction'] for x in bank['pairs'])),
        single_reply_answers=len(bank['singles']),preserved_q_ranges=sum(x['q_status']=='range' for x in bank['singles']),
        existing_clarifications=len(bank['supplements']),distinct_complete_evidence_inputs=len(evidence),
        distinct_replies_in_human_pairs=len({(x['evidence_identity'],rid) for x in bank['pairs'] for rid in x['reply_identities']}),
        single_answers_already_seen_as_pair_endpoints=sum(any(s['evidence_identity']==p['evidence_identity'] and s['reply_identity'] in p['reply_identities'] for p in bank['pairs']) for s in bank['singles']),
        copied_export_rows_not_new_observations=16,current_exact_single_comparisons=3,
        current_training_unique_inputs=len(training),current_training_exact_reference_matches=len(matches),
        new_eight_pairs_with_exact_old_pair=sum(x['exact_old_pair'] for x in candidate_review),
        new_eight_pairs_with_old_exact_context=sum(x['context_previously_in_human_bank'] for x in candidate_review),
        new_eight_pairs_with_both_S=sum(all(y is not None for y in x['S']) for x in candidate_review),
        new_eight_pairs_current_S_equal=sum(x['S_ON_minus_OFF']==0 for x in candidate_review if x['S_ON_minus_OFF'] is not None),
        new_human_questions=0,new_human_labels=0,new_API_calls=0,new_cost_usd=0,natural_updates=0,
        old_8_pair_form_is_mandatory=False,qualification_granted=False,
        use='Development diagnostics and question deduplication; no automatic replacement of train rewards.')
    output.mkdir(parents=True,mode=0o700)
    def save(name,value):
        path=output/name;path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    save('ANSWER_REGISTRY_PRIVATE.json',assets)
    save('Q_M_REUSE_PRIVATE.json',comparisons)
    save('CURRENT_EXPLANATIONS_PRIVATE.json',current_observations)
    save('UNANSWERED_PAIR_DECISIONS_PRIVATE.json',candidate_review)
    save('HISTORICAL_NOISE_REUSE_PRIVATE.json',noise_reuse)
    save('TRAINING_EXACT_REUSE_PRIVATE.json',matches)
    save('SUMMARY.json',summary)
    sources[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save('SOURCE_HASHES.json',sources)
    save('OUTPUT_MANIFEST.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()})
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    build(p.parse_args().output)

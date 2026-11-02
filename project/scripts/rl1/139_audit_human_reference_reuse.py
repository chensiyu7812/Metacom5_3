#!/usr/bin/env python3
"""Reuse already-open human development records; never decrypt sealed labels.

Only explicit source files below are opened. Filesystem discovery of possible
new returns is by filename; candidate bodies are not silently ingested.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.human_reference_reuse import pair_reference, reuse_map
from metacom_pm.rl1.schema import digest


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(output):
    if output.exists():raise ValueError('new audit output directory required')
    used={}
    def read(p,expected=None):
        p=Path(p).resolve();h=sha(p)
        if expected is not None and h!=expected:raise ValueError('historical source hash mismatch: '+str(p))
        used[str(p)]=h;return json.loads(p.read_text())
    base=PROJECT/'outputs/pm_rl1';judge=base/'judge_selection_preparation_20261014_v1'
    provenance=read(base/'root_cause_20261023_v4/PROVENANCE_PRIVATE.json')['source_hashes']
    def old(p):
        p=Path(p);return read(p,provenance[str(p.relative_to(PROJECT))])
    orig=old(base/'human_acceptance_20261014_v2/intake/rater_1_development_original_private.json')
    intake=old(base/'development_closeout_20261014_v1/acceptance_final/development_intake_private.json')
    summary=read(base/'development_closeout_20261014_v1/acceptance_final/intake_summary.json')
    records=[r for r in intake if r['reviewer']=='Chen']
    original_labels={x['item_id']:x for x in orig['labels']}
    pairs=[]
    for r in records:
        if r['group']!='development' or r['raw_label']!=original_labels[r['item_id']]:
            raise ValueError('only originally opened development judgments allowed')
        direction={'A':'left','B':'right','tie':'tie','uncertain':'uncertain'}[r['preference']['value']]
        pairs.append(pair_reference(source='20261014_development',record_id=r['pair_id'],
            evidence_id=r['evidence_identity'],left=r['reply_identities']['A'],right=r['reply_identities']['B'],
            direction=direction,raw_label=r['raw_label'],observation_origin='Chen-saved-browser-record',
            purpose='exposed development, including authored controls'))
    if len(records)!=16 or len(orig['labels'])!=16:raise ValueError('old development count changed')
    # Count the duplicated export by provenance, not by reviewer display name.
    copies=[r for r in intake if r['reviewer']!='Chen']
    if any(r['provenance']['kind']!='user_declared_identical_copy' for r in copies):
        raise ValueError('unexpected extra original human observation; inspect separately')
    noise=old(judge/'noise_human_analysis_20261020_v1/researcher_original.json')
    analysis=old(judge/'noise_human_analysis_20261020_v1/analysis.json')
    bypair={p['pair_id']:p for p in analysis['pairs']}
    archive=Path('/home/tokkio/成果归档/PM-RL1/04_人评原件')
    archived_noise=read(archive/'2026-10-20/PMRL1_中文人评_7组_2026-10-20T06-36-51.json')
    if archived_noise!=noise:raise ValueError('archived original noise review differs')
    for a in noise['answers']:
        p=bypair[a['pair_id']]
        if any(a[k]!=p[k] for k in ('left_reply_identity','right_reply_identity')) or a['direction']!=p['human_direction']:
            raise ValueError('original pair answer changed')
        direction={'A':'left','B':'right','tie':'tie','uncertain':'uncertain'}[a['direction']]
        pairs.append(pair_reference(source='20261020_seven_pairs',record_id=a['pair_id'],
            evidence_id=p['evidence_identity'],left=a['left_reply_identity'],right=a['right_reply_identity'],
            direction=direction,raw_label=a,observation_origin='same researcher; exported reviewer_id blank',
            purpose='exposed development; historical P04 not a new label'))
    p04=bypair['P04']
    p04_key=digest(dict(evidence=p04['evidence_identity'],replies=sorted((p04['left_reply_identity'],p04['right_reply_identity']))))
    if p04_key not in {p['pair_identity'] for p in pairs}:raise ValueError('historical P04 lost original provenance')
    receipt=read(judge/'researcher_annotation_review_20261019_v1/intake_receipt.json')
    original=read(judge/'acceptability_resource_review_20261019_v1/materials/original_researcher_submission.json',receipt['submission_sha256'])
    archived_original=read(archive/'2026-10-19/PMRL1_researcher_2026-10-19T05-14-10-023Z_5da6d7b6-9aa8-43e5-855a-2eee6e486376.json',receipt['submission_sha256'])
    if archived_original!=original:raise ValueError('archived single-reply original differs')
    refs={r['item_id']:r for r in receipt['items']};singles=[]
    for x in original['state']['items']:
        r=refs[x['item_id']]
        for k in ('reply_identity','evidence_identity','q_status','q_value','q_min','q_max','m_status'):
            if x[k]!=r[k]:raise ValueError('human numeric value or source changed')
        if x['q_status'] not in ('single','range'):raise ValueError('unexpected old q response')
        singles.append(dict(source='20261019_eight_replies',record_id=x['item_id'],old_item_key=r['old_item_key'],
            reply_identity=x['reply_identity'],evidence_identity=x['evidence_identity'],q_status=x['q_status'],
            q_value=int(x['q_value']) if x['q_status']=='single' else None,
            q_min=int(x['q_min']) if x['q_status']=='range' else None,
            q_max=int(x['q_max']) if x['q_status']=='range' else None,m_value=float(x['m_status']),
            raw_label=x,scope='single researcher exposed development',qualified_reward=False))
    supplement=read(judge/'acceptability_resource_review_20261019_v1/materials/original_researcher_supplement.json')
    if supplement['original_submission_sha256']!=receipt['submission_sha256']:
        raise ValueError('follow-up source changed')
    supplements=[dict(source='20261019_researcher_clarification',record_id=x['item_id'],
        reply_identity=x['reply_identity'],evidence_identity=x['evidence_identity'],raw_label=x,
        qualified_reward=False) for x in supplement['answers']]
    prep=base/'execution_bridges_20261030_v6';manifest=read(prep/'PACKAGE_MANIFEST.json')
    config=read(prep/'J_CONFIG_PRIVATE.json',manifest['J_CONFIG_PRIVATE.json'])
    # The live input bundle is inspected structurally; no transport is created.
    materials=read(base/'completion_preparation_20261022/stage_materials_private.json',
                   '1f476c896e240698e5336f121fc193d61b1099b771fcaf0e37d17cab2eb7f9b8')
    result=reuse_map(materials,pairs,singles,supplements)
    # Determine whether prior human work can already support BC or the latest
    # resource comparison. Reuse the verified ledger, not a new mixed dataset.
    audit=base/'reorganization_20261029_v4';am=read(audit/'OUTPUT_MANIFEST.json')
    pool=read(audit/'RESPONSE_LEDGER_PRIVATE.json',am['RESPONSE_LEDGER_PRIVATE.json'])
    evidence_by_prefix={}
    for r in pool:
        if r['split'] not in ('train','dev'):raise ValueError('held-out pool excluded')
        if evidence_by_prefix.setdefault(r['prefix_identity'],r['evidence_identity'])!=r['evidence_identity']:
            raise ValueError('one prefix has conflicting legal evidence')
    def covers(reply,evidence):
        return dict(single=[s['record_id'] for s in singles if s['reply_identity']==reply and s['evidence_identity']==evidence],
            preference_endpoint=[p['source']+':'+p['record_id'] for p in pairs
                if reply in p['reply_identities'] and p['evidence_identity']==evidence])
    pool_rows=[dict(request_id=r['request_id'],split=r['split'],prefix_identity=r['prefix_identity'],
        response_identity=r['response_identity'],evidence_identity=r['evidence_identity'],
        **covers(r['response_identity'],r['evidence_identity'])) for r in pool]
    latest=base/'resource_comparison_results_20261031_v1';lm=read(latest/'OUTPUT_MANIFEST.json')
    latest_rows=read(latest/'RESPONSES_PRIVATE.json',lm['RESPONSES_PRIVATE.json'])
    recent=[]
    for r in latest_rows:
        raw=read(Path(r['raw_path']),r['raw_sha256'])
        if raw['text']!=r['reply']:raise ValueError('latest raw reply changed')
        eid=evidence_by_prefix[r['prefix_identity']]
        recent.append(dict(input_identity=r['input_identity'],prefix_identity=r['prefix_identity'],
            response_identity=digest(r['reply']),evidence_identity=eid,
            **covers(digest(r['reply']),eid)))
    matched_new_pairs=[]
    byinput={r['input_identity']:r for r in recent}
    comparisons=read(latest/'PAIRS_PRIVATE.json',lm['PAIRS_PRIVATE.json'])
    for p in comparisons:
        lft,rgt=byinput[p['left_input']],byinput[p['right_input']]
        key=digest(dict(evidence=lft['evidence_identity'],replies=sorted((lft['response_identity'],rgt['response_identity']))))
        matched_new_pairs.append(dict(comparison=p['comparison'],head=p['head'],prefix_identity=p['prefix_identity'],
            existing_preference_references=[x['source']+':'+x['record_id'] for x in pairs if x['pair_identity']==key]))
    result['existing_pool_reuse']=dict(rows=pool_rows,by_split={split:dict(
        rows=sum(r['split']==split for r in pool_rows),
        rows_with_single_reference=sum(r['split']==split and bool(r['single']) for r in pool_rows),
        rows_with_pair_endpoint=sum(r['split']==split and bool(r['preference_endpoint']) for r in pool_rows),
        unique_scoring_inputs_with_reference=len({(r['evidence_identity'],r['response_identity']) for r in pool_rows
            if r['split']==split and (r['single'] or r['preference_endpoint'])})) for split in ('train','dev')})
    result['latest_resource_comparison_reuse']=dict(rows=recent,pairs=matched_new_pairs)
    result['summary'].update(original_pool=result['existing_pool_reuse']['by_split'],
        latest_G_rows=len(recent),latest_G_rows_with_single_reference=sum(bool(r['single']) for r in recent),
        latest_G_rows_with_pair_endpoint=sum(bool(r['preference_endpoint']) for r in recent),
        latest_resource_comparisons=len(matched_new_pairs),
        latest_resource_comparisons_with_exact_old_preference=sum(bool(p['existing_preference_references']) for p in matched_new_pairs))
    searched=[];found=[]
    roots=[Path('/home/tokkio'),archive,Path('/home/tokkio/.codex/attachments'),base]
    for name in ('Downloads','下载','Desktop','桌面'):
        p=Path('/home/tokkio')/name
        if p.exists():roots.append(p)
    for root in roots:
        patterns=('PM_RL1_blind_*.json','PM_RL1_regression_*.json')
        searched.append(dict(path=str(root),recursive=root!=Path('/home/tokkio'),patterns=list(patterns)))
        for pattern in patterns:
            found.extend(str(p.resolve()) for p in (root.glob(pattern) if root==Path('/home/tokkio') else root.rglob(pattern)))
    result['summary'].update(original_development_pairs=16,development_comparable=summary['comparable_preference'],
        independent_observation_origins_in_old_two_name_export=summary['independent_observation_origins'],
        copied_export_rows_not_extra_observations=len(copies),historical_P04_reused_not_recounted=True,
        new_packet_return_files_found=len(set(found)),new_packet_return_search_is_not_browser_or_other_device_search=True,
        historical_scores_kept=True,new_score_stage_executed=False,current_J_protocol=config['protocol_identity'],
        paid_stage_decision='researcher explicitly deferred on 2026-11-02; no cap changes',
        current_J_qualification=False)
    result['search']=dict(roots=searched,candidate_paths=sorted(set(found)),
        limitation='Expected export filenames in local known locations only; no browser localStorage, sealed labels or other devices accessed.')
    # Retain earlier risk and later m separately; detect their differing levels
    # without declaring either to be gold or replacing a human response.
    differing=[]
    for s in singles:
        for r in records:
            if s['evidence_identity']!=r['evidence_identity']:continue
            for side,reply in r['reply_identities'].items():
                if reply==s['reply_identity'] and r['risks'][side]['level']=='none_detected' and s['m_value']>0:
                    differing.append(dict(pair_id=r['pair_id'],single_id=s['record_id'],old_item_key=s['old_item_key'],
                        old_risk='none_detected',later_m=s['m_value'],
                        interpretation='different historical judgments/tasks; preserve chronology, no automatic overwrite'))
    result['historical_differing_risk_judgments']=differing
    output.mkdir(parents=True,mode=0o700)
    def save(name,data):
        p=output/name;p.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n');p.chmod(0o600)
    save('REUSE_MAP_PRIVATE.json',result)
    save('REFERENCE_BANK_PRIVATE.json',dict(pairs=pairs,singles=singles,supplements=supplements))
    save('SUMMARY.json',result['summary']);save('INPUT_HASHES_PRIVATE.json',used)
    save('OUTPUT_MANIFEST.json',{p.name:sha(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)

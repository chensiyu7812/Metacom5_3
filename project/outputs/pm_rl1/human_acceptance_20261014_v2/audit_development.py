#!/usr/bin/env python3
"""Local read-only development intake. Never decrypt held-out human answers.

Original validate_label/decrypt_item are authoritative. Field availability below
is a diagnostic partition, NOT an alternative formal qualification criterion.
An output directory must not already exist. Private keys never enter outputs.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile


def sha(b):
    return hashlib.sha256(b).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def table(path, rows):
    if not rows:
        path.write_text('')
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows:
            w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})


def audit_fields(label, item, evidence, hc):
    """Enumerate all rules without inventing missing answers."""
    errors=[]
    def err(field, code):
        errors.append(dict(field=field, code=code, original_value=label.get(field)))
    if set(label)!=hc.LABEL_KEYS: err('__keys__','label_fields_mismatch')
    if label.get('item_id')!=item['item_id']: err('item_id','item_identity_mismatch')
    p=label.get('preference')
    pref_enum = p in ('A','B','tie','uncertain')
    if not pref_enum: err('preference','missing_or_invalid_preference')
    reason_ok=isinstance(label.get('reason'),str) and bool(label['reason'].strip())
    if not reason_ok: err('reason','nonempty_string_required')
    uncertainty_ok=isinstance(label.get('uncertainty'),str)
    if not uncertainty_ok: err('uncertainty','string_required')
    if 'uncertain' in [p,label.get('risk_A'),label.get('risk_B')]:
        uncertainty_ok=uncertainty_ok and bool(label['uncertainty'].strip())
        if not uncertainty_ok: err('uncertainty','uncertain_needs_explanation')
    ids=label.get('source_ids')
    allowed=set(hc.evidence_turns(evidence))|{'ROLE','FULL_SOURCE'}
    ids_ok=(isinstance(ids,list) and all(isinstance(s,str) for s in ids)
            and len(ids)==len(set(ids)) and set(ids)<=allowed)
    if not ids_ok: err('source_ids','invalid_source_references')
    if any(label.get('risk_'+s) in ('local','severe') for s in 'AB') and not ids:
        err('source_ids','nonzero_risk_needs_source_references')
    availability=dict(preference_enum_valid=pref_enum,
        preference_comparable=p in ('A','B','tie') and reason_ok,
        reason_valid=reason_ok, source_ids_valid=ids_ok)
    for side in 'AB':
        risk=label.get('risk_'+side); quote=label.get('quote_'+side)
        enum=risk in ('none_detected','local','severe','uncertain')
        if not enum: err('risk_'+side,'missing_or_invalid_risk')
        quote_ok=isinstance(quote,str) and (not quote or quote in item[side])
        if not quote_ok: err('quote_'+side,'response_quote_not_exact')
        if risk in ('local','severe') and (not isinstance(quote,str) or not quote.strip()):
            err('quote_'+side,'nonzero_risk_needs_exact_quote')
            quote_ok=False
        evidence_ok=ids_ok and (risk not in ('local','severe') or bool(ids))
        availability.update({
            'risk_'+side+'_enum_valid':enum,
            'risk_'+side+'_comparable':risk in ('none_detected','local','severe'),
            'risk_'+side+'_evidence_ready':risk in ('none_detected','local','severe') and quote_ok and evidence_ok and reason_ok,
            'quote_'+side+'_exact':quote_ok})
    try:
        hc.validate_label(label,item,evidence); original_error=None
    except (ValueError,TypeError,KeyError) as e: original_error=str(e)
    assert bool(errors)==bool(original_error), (errors,original_error)
    return dict(strict_valid=not errors, original_validator_first_error=original_error,
                errors=errors, **availability)


def decrypt_development(envelope, *, mapping, form, key, hc, access_log):
    """Hard group guard before calling the original cryptographic function."""
    item_id=envelope['item_id']
    meta=mapping[item_id]
    if meta['group']!='development':
        raise ValueError('held-out item cannot be decrypted by this development auditor')
    answer=hc.decrypt_item(envelope,key,packet_identity=form['packet_identity'],form_identity=form['form_identity'])
    access_log.append(dict(item_id=item_id,pair_id=meta['pair_id'],group=meta['group'],form_identity=form['form_identity']))
    return answer


def run(repo, export, original_packet, out):
    os.umask(0o077)
    project=repo/'project'; p3=project/'outputs/pm_rl1/completion_20260930_v2/P3'; packet=p3/'calibration'
    sys.path.insert(0,str(project/'src'))
    from metacom_pm.rl1 import human_calibration as hc
    from metacom_pm.rl1.schema import digest
    from metacom_pm.rl1.calibration_decision import direction
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    helper=project/'outputs/pm_rl1/human_acceptance_20261014_v1/audit_original_packet.py'
    spec=importlib.util.spec_from_file_location('preflight',helper); pre=importlib.util.module_from_spec(spec);spec.loader.exec_module(pre)
    pre_summary, expected, frozen_inputs = pre.inspect(repo,original_packet)
    read=lambda p:hc.strict_json(p.read_text())
    forms={s:read(packet/(s+'_form.json')) for s in ('rater_1','rater_2')}
    maps={s:read(packet/(s+'_map_private.json')) for s in forms}
    pairs={p['pair_id']:p for p in read(packet/'pairs_private.json')['pairs']}
    originals={}
    with zipfile.ZipFile(export) as z:
        names=['PM_RL1_Chen_pending_review.json','PM_RL1_Du_pending_review.json','manifest_pending_review.json',
               'PM_RL1_original_encrypted_bundle.json','交接说明_含待核查清单.txt']
        assert sorted(z.namelist())==sorted(names), 'unexpected ZIP members'
        for n in names: originals[n]=z.read(n)
    js={n:hc.strict_json(b.decode()) for n,b in originals.items() if n.endswith('.json')}
    manifest=js['manifest_pending_review.json']; bundle=js['PM_RL1_original_encrypted_bundle.json']
    assert manifest['source_sha256']==sha(originals['PM_RL1_original_encrypted_bundle.json'])
    assert manifest['packet_identity']==bundle['packet_identity']==forms['rater_1']['packet_identity']
    records={r['record_id']:r for r in bundle['records']}; submissions={}; structure=[]
    for r in manifest['records']:
        sub=js[r['file']]; slot=r['rater_slot']; orig=records[r['record_id']]
        assert sha(originals[r['file']])==r['sha256']
        assert sub==orig['submission'], 'standalone submission differs from encrypted original'
        assert r['provenance']==orig['provenance'] and r['validation']==orig['validation']
        assert set(sub)=={'protocol','packet_identity','form_identity','reviewer_kind','reviewer_identity','reviewer_details','items'}
        assert sub['protocol']==hc.PROTOCOL and sub['packet_identity']==forms[slot]['packet_identity']
        assert sub['form_identity']==forms[slot]['form_identity'] and sub['reviewer_identity']==r['reviewer_identity']
        assert sub['reviewer_kind']=='individual_human' and isinstance(sub['reviewer_details'],str)
        ids=[v['item_id'] for v in sub['items']]
        assert len(ids)==40 and len(set(ids))==40 and set(ids)==set(maps[slot])
        for env in sub['items']:
            assert set(env)=={'item_id','wrapped_key','nonce','ciphertext'}
            parts={k:base64.b64decode(env[k],validate=True) for k in ('wrapped_key','nonce','ciphertext')}
            assert len(parts['nonce'])==12 and len(parts['ciphertext'])>16 and len(parts['wrapped_key'])>=256
        submissions[slot]=sub
        structure.append(dict(reviewer=r['reviewer_identity'],slot=slot,items=40,duplicates=0,missing=0,
            packet_identity=sub['packet_identity'],form_identity=sub['form_identity'],
            source_submission_equals_original=True,provenance=r['provenance']['kind']))
    assert set(submissions)==set(forms)
    du_provenance=next(r['provenance'] for r in manifest['records'] if r['rater_slot']=='rater_2')
    assert du_provenance['source_form_identity']==forms['rater_1']['form_identity']
    mapping_caveats=[]
    for v in du_provenance['mapping']:
        a=maps['rater_1'][v['source_item_id']]; b=maps['rater_2'][v['target_item_id']]
        assert a['pair_id']==b['pair_id']
        if v['sides_swapped']!=(a['swapped']!=b['swapped']):
            pair=pairs[a['pair_id']]
            assert pair['replies'][0]==pair['replies'][1], 'nonidentical replies with incorrect swap'
            mapping_caveats.append(dict(pair_id=a['pair_id'],group=a['group'],**v,
                canonical_sides_swapped=a['swapped']!=b['swapped'],replies_identical=True,
                disposition='Keep original; nominal side ambiguity requires inspection only after held-out opening'))
    assert len(du_provenance['mapping'])==40
    assert len({v['source_item_id'] for v in du_provenance['mapping']})==40
    assert len({v['target_item_id'] for v in du_provenance['mapping']})==40
    out.mkdir(parents=True,exist_ok=False); (out/'originals').mkdir()
    (out/'originals'/export.name).write_bytes(export.read_bytes())
    for n,b in originals.items(): (out/'originals'/n).write_bytes(b)
    dump(out/'input_manifest.json',dict(export=dict(path=str(export),bytes=export.stat().st_size,sha256=sha(export.read_bytes())),
         members=[dict(name=n,bytes=len(b),sha256=sha(b)) for n,b in originals.items()],
         original_packet_preflight_inputs=frozen_inputs, key='Used in original location only; not copied or emitted',
         preflight_helper_sha256=sha(helper.read_bytes())))
    dump(out/'structural_receipt.json',structure)
    dump(out/'identical_reply_mapping_caveat.json',mapping_caveats)
    # No key serialization, reporting, or replacement.
    key=load_pem_private_key((packet/'label_decryption_key_private.pem').read_bytes(),password=None)
    access=[]; rows=[]; label_by_slot={}; skipped=[]
    for slot,sub in submissions.items():
        visible={i['item_id']:i for i in forms[slot]['items']}; labels=[]
        order={i['item_id']:n for n,i in enumerate(forms[slot]['items'],1)}
        record=next(r for r in manifest['records'] if r['rater_slot']==slot)
        flagged={r['item_id']:r for r in record['validation']['pending']}
        for env in sub['items']:
            itemid=env['item_id']; meta=maps[slot][itemid]
            if meta['group']!='development':
                skipped.append(dict(slot=slot,item_id=itemid,pair_id=meta['pair_id'],group=meta['group'],
                    envelope_sha256=digest(env),browser_flagged=itemid in flagged,label_access='SEALED_NOT_DECRYPTED',
                    browser_issue_details='NOT_USED_OR_REPORTED'))
                continue
            label=decrypt_development(env,mapping=maps[slot],form=forms[slot],key=key,hc=hc,access_log=access)
            item=visible[itemid]; evidence=forms[slot]['sources'][item['source_key']]
            result=audit_fields(label,item,evidence,hc)
            labels.append(label)
            rows.append(dict(reviewer=sub['reviewer_identity'],slot=slot,order=order[itemid],item_id=itemid,
                pair_id=meta['pair_id'],group=meta['group'],kind=meta['kind'],owner=meta['owner'],
                prefix_identity=item['source_key'],A_canonical_side=int(meta['swapped']),
                browser_flagged=itemid in flagged,browser_issues=flagged.get(itemid,{}).get('issues',[]),
                label=label,**result))
        label_by_slot[slot]={maps[slot][r['item_id']]['pair_id']:r for r in labels}
        assert len(labels)==16
        dump(out/(slot+'_development_original_private.json'),dict(labels=labels,provenance=record['provenance'],
            form_identity=sub['form_identity'],reviewer_details=sub['reviewer_details']))
    del key
    assert len(access)==32 and {r['group'] for r in access}=={'development'} and len(skipped)==48
    dump(out/'decryption_access_log.json',dict(decrypted_envelopes=access,unique_pairs=16,validation_decrypted=0,
         original_bundle_decrypted_separately=False,reason='submission objects identical; duplicate decryption unnecessary'))
    table(out/'sealed_inventory_private.csv',skipped)
    dump(out/'development_item_audit_private.json',rows);table(out/'development_item_audit_private.csv',rows)
    patchlog=[]; duplex=[]
    for v in du_provenance['mapping']:
        pid=maps['rater_1'][v['source_item_id']]['pair_id']
        if maps['rater_1'][v['source_item_id']]['group']!='development': continue
        a=label_by_slot['rater_1'][pid]; b=label_by_slot['rater_2'][pid]; exp=dict(a);exp['item_id']=b['item_id']
        if v['sides_swapped']:
            exp['preference']={'A':'B','B':'A'}.get(a['preference'],a['preference'])
            for field in ('risk','quote'):
                exp[field+'_A'],exp[field+'_B']=a[field+'_B'],a[field+'_A']
        differences=[k for k in exp if exp[k]!=b.get(k)]
        duplex.append(dict(pair_id=pid,source_item_id=a['item_id'],target_item_id=b['item_id'],
            sides_swapped=v['sides_swapped'],derived_fields_match=not differences,differences=differences,
            original_reason=b['reason'],original_uncertainty=b['uncertainty'],
            free_text_reference_frame='Chen/rater_1',
            mapping_explanation=('原文 A 指 Du B；原文 B 指 Du A。' if v['sides_swapped'] else '原文 A 指 Du A；原文 B 指 Du B。'),
            independent_rater_evidence=False))
    assert all(r['derived_fields_match'] for r in duplex)
    dump(out/'Du_AB_provenance_private.json',duplex);table(out/'Du_AB_provenance_private.csv',duplex)
    # Match only development PRIMARY scores, never recheck probes/repeats.
    c=p3/'candidate_v1'; protocol=read(c/'protocol.json');doc=read(project/'docs/pm_rl1_completion_20260930_v2/p3_development_results.json')
    run_dir=c/'development'/doc['runtime_identity']; summary=read(run_dir/'summary.json')
    jobs={j['job_id']:j for j in read(c/'jobs_private.json')}
    score_map={(r['pair_id'],r['side']):r['job_id'] for r in read(c/'pair_score_map_private.json')}
    summary_map={r['job_id']:r for r in summary['rows']}; comparisons=[]; score_receipts=[]
    for row in sorted((r for r in rows if r['slot']=='rater_1'),key=lambda r:r['order']):
        pid=row['pair_id'];pair=pairs[pid];scores=[]
        for side in (0,1):
            jobid=score_map[pid,side];job=jobs[jobid];sr=summary_map[jobid]
            assert job['group']=='development' and job['draw_id']=='primary' and not job['repeat'] and not job['recheck']
            assert job['reply']==pair['replies'][side] and job['prefix_identity']==pair['prefix_identity']
            assert job['evidence']==forms['rater_1']['sources'][pair['prefix_identity']]
            rawpath=run_dir/(sr['request_id']+'.raw.json')
            mp=run_dir/(sr['request_id']+'.measurement.json');m=read(mp);raw=read(rawpath)
            assert sha(rawpath.read_bytes())==sr['raw_sha256']
            assert m['response_sha256']==sha(job['reply'].encode()) and m['legal_evidence_identity']==digest(job['evidence'])
            assert m['judge_runtime_identity']==raw['runtime_identity']==doc['runtime_identity']
            assert m['rubric_identity']==protocol['rubric_identity'] and m['measurement_draw_id']=='primary'
            assert m['raw_output_sha256']==sha(raw['text'].encode())
            assert (m['q'],m['m'],m['candidate_utility'])==(sr['q'],sr['m'],sr['utility'])
            scores.append(dict(q=m['q'],m=m['m'],utility=m['candidate_utility'],job_id=jobid,
                q_reason=m['parsed']['q_rationale']['reason'],misuse_findings=m['parsed']['misuse_findings']))
            score_receipts.append(dict(pair_id=pid,side=side,job_id=jobid,measurement_path=str(mp),
                measurement_sha256=sha(mp.read_bytes()),raw_sha256=sr['raw_sha256'],binding='VERIFIED'))
        label=row['label'];sw=row['A_canonical_side']; human={'A':('left','right')[sw],'B':('left','right')[1-sw]}.get(label['preference'],label['preference'])
        risks=[label['risk_A'],label['risk_B']][::(-1 if sw else 1)]
        cf=dict(pair_id=pid,Chen_order=row['order'],Chen_item_id=row['item_id'],kind=pair['kind'],
            contrast=pair.get('contrast','control'),control_type=pair.get('control_type',''),owner=pair['owner'],
            prefix_identity=pair['prefix_identity'],canonical_sides=pair.get('sides',['control_left','control_right']),human_direction=human,
            judge_direction=direction(scores),preference_comparable=row['preference_comparable'],
            preference_match=(human==direction(scores)) if row['preference_comparable'] else None,
            strict_label_valid=row['strict_valid'],human_risk_left=risks[0],human_risk_right=risks[1],
            scores=scores,human_reason=label['reason'],source_ids=label['source_ids'])
        for side in (0,1):
            letter='A' if side==sw else 'B'
            cf[('left','right')[side]+'_risk_evidence_ready']=row['risk_'+letter+'_evidence_ready']
        comparisons.append(cf)
    dump(out/'score_binding_receipts.json',score_receipts)
    dump(out/'development_comparisons_private.json',comparisons); table(out/'development_comparisons_private.csv',comparisons)
    originals_after={n:sha(b) for n,b in originals.items()}
    with zipfile.ZipFile(export) as z: assert originals_after=={n:sha(z.read(n)) for n in z.namelist()}
    _,_,after=pre.inspect(repo,original_packet); assert frozen_inputs==after
    receipt=dict(status='DEVELOPMENT_AUDIT_ONLY_NOT_FORMAL_INTAKE',unique_pairs_opened=16,
        validation_pairs_sealed=24,independent_original_record_sets=1,derived_record_sets=1,
        strict_valid_pairs=sum(r['strict_valid'] for r in rows if r['slot']=='rater_1'),
        preferences_comparable=sum(r['preference_comparable'] for r in rows if r['slot']=='rater_1'),
        risk_sides_comparable=sum(r['risk_'+s+'_comparable'] for r in rows if r['slot']=='rater_1' for s in 'AB'),
        risk_sides_evidence_ready=sum(r['risk_'+s+'_evidence_ready'] for r in rows if r['slot']=='rater_1' for s in 'AB'),
        browser_flagged_development=5,browser_flagged_validation_unverified=7,
        protocol_identity=protocol['identity'],runtime_identity=doc['runtime_identity'],
        repository_HEAD=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        repository_branch=subprocess.check_output(['git','-C',str(repo),'branch','--show-current'],text=True).strip(),
        git_status=subprocess.check_output(['git','-C',str(repo),'status','--short'],text=True),
        frozen_originals_unchanged=True,paid_calls=0,new_model_calls=0,training_updates=0,
        changes_to_labels=patchlog,final_measurement_freeze_created=False,reward_qualified=False)
    dump(out/'audit_receipt.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--export',type=Path,required=True)
    p.add_argument('--original-packet',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();run(args.repo,args.export,args.original_packet,args.out)

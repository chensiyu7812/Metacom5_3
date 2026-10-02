#!/usr/bin/env python3
"""Reproducible offline QA audit strata and un-applied lineage repair proposals."""
import argparse
from collections import Counter,defaultdict
import importlib.util
from pathlib import Path
import re

def main(output=None):
    sp=importlib.util.spec_from_file_location('census69',Path(__file__).with_name('69_analyze_dataset_features.py'))
    m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
    out=output or m.OUT
    if (out/'closeout.json').exists():raise RuntimeError('Analysis is closed')
    qa=m.read(out/'qa_train_dev_review_private.json'); strata=defaultdict(list)
    for r in qa:strata[r['split'],r['capability']].append(r)
    sample=[]
    for key,rows in sorted(strata.items()):
        sample.extend(sorted(rows,key=lambda r:m.sha256(f"pmrl1-data-review-v1|{r['owner']}|{r['group']}|{r['idx']}".encode()).hexdigest())[:2])
    m.write_json(out,'semantic_sample_private.json',dict(selection='sha256 pmrl1-data-review-v1|owner|group|idx; two per split x capability, before semantic review',rows=sample))
    users={u['owner_id']:u for u in m.read(m.PATHS['runtime'])['users']}
    splits=m.owner_splits(list(users))
    raw={u['id']:u for u in m.project_gold(m.read(m.PATHS['evo']),splits)}
    proposals=[]; registry=[]
    for r in qa:
        status=('no_evidence' if not r['evidence_count'] else 'unresolved_reference' if r['unresolved_refs'] else 'private_only' if r['only_private_event_refs'] else 'visible_reference_present')
        registry.append(dict(owner=r['owner'],split=r['split'],group=r['group'],idx=r['idx'],capability=r['capability'],
            structural_stratum=status,semantic_admissibility='pending_source_scope_review',independent_gold=False))
        sessions={s['session_id']:s for s in users[r['owner']]['sessions']}
        events={e['id']:e for e in raw[r['owner']]['event_experience']}
        for ref,res in zip(r['evidence'],r['reference_resolution']):
            if res['kind']!='unresolved':continue
            candidates=[ref.replace(';',':'),ref.replace('evnet','event')]
            candidates += [re.sub(r'^\d+[.]?(?=p\d+_)','',ref)]
            foreign=re.match(r'^p\d+_conv_(\d+):(\d+)$',ref)
            if foreign:candidates.append(f"{r['owner']}_conv_{foreign[1]}:{foreign[2]}")
            verified=[dict(reference=c,resolution=m.resolve_reference(c,sessions,events)) for c in dict.fromkeys(candidates)
                if c!=ref and m.resolve_reference(c,sessions,events)['kind']!='unresolved']
            proposals.append(dict(owner=r['owner'],group=r['group'],idx=r['idx'],original=ref,
                candidates=verified,status='proposal_only_needs_semantic_check',applied=False))
    m.write_csv(out,'qa_audit_registry.csv',registry)
    m.write_json(out,'reference_repair_proposals_private.json',proposals)
    # Separate facts: missing citations, answer validity and benchmark scope.
    rows=m.lines(m.PATHS['units'])
    units=[u for r in rows for u in r['accepted_units']]
    summary=dict(qa_structural_strata=dict(Counter(r['structural_stratum'] for r in registry)),
        semantic_sample_rows=len(sample),semantic_sample_selection='two per split x capability; illustrative audit, not quality prevalence',
        unresolved_occurrences=len(proposals),occurrences_with_owner_local_candidate=sum(bool(r['candidates']) for r in proposals),
        automatic_repairs_applied=0,me_outcome_text_nonempty=sum('event_experience_type' in u and bool(u.get('observed_outcome_text')) for u in units),
        current_q_scope='Official full owner history; question group is not a chronological cutoff and is not exposed as a hidden-answer hint.',
        proposed_auxiliary_use='None admitted by syntax checks alone. Any new as-of QA auxiliary set requires separately versioned visible evidence, time anchor and answer-scope review.')
    m.write_json(out,'audit_readiness.json',summary)
    print(summary)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path)
    main(parser.parse_args().out)

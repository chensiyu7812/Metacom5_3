#!/usr/bin/env python3
"""Source-length coverage for the 114 already-frozen train/dev prefixes only.

No replies, rewards, human labels or test sources are created/read. These are
source-only lengths, not claims that unknown future complete requests fit.
"""
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.rl1.evidence import legal_evidence,prefix_from_dict

ROOT=PROJECT/'outputs/pm_rl1/completion_20260930_v2'


def main():
    specs_path=ROOT/'P1/episode_specs_private.json'
    source=PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    specs=json.loads(specs_path.read_text());assert len(specs)==114
    users={u.owner_id:u for u in load_sanitized_runtime_users(source)}
    protocol=json.loads((ROOT/'P3/candidate_v1/protocol.json').read_text())
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(protocol['model'],local_files_only=True)
    observed=json.loads((ROOT/'P3/calibration/pairs_private.json').read_text())['pairs']
    development_prefixes={p['prefix_identity'] for p in observed if p['group']=='development'}
    rows=[]
    for index,spec in enumerate(specs):
        prefix=prefix_from_dict(spec['prefix']);assert prefix.split in ('train','dev')
        evidence,_=legal_evidence(prefix,users[prefix.owner_id])
        count=len(tokenizer.encode(json.dumps(evidence,ensure_ascii=False),add_special_tokens=False))
        rows.append(dict(index=index,split=prefix.split,owner=prefix.owner_id,
            source_tokens=count,past_sessions=len(evidence['legal_past_sessions']),
            current_turns=len(evidence['current_prefix']),in_calibration_development=prefix.identity in development_prefixes))
    development_max=max(r['source_tokens'] for r in rows if r['in_calibration_development'])
    report=dict(status='SOURCE_LENGTH_COVERAGE_ONLY_NO_SCORING',rows=rows,
        prefixes=114,splits=dict(Counter(r['split'] for r in rows)),test_prefixes=0,
        source_only_tokens=dict(min=min(r['source_tokens'] for r in rows),
            median=statistics.median(r['source_tokens'] for r in rows),max=max(r['source_tokens'] for r in rows)),
        calibration_development_max_source_tokens=development_max,
        prefixes_longer_than_measured_calibration_source=sum(r['source_tokens']>development_max for r in rows),
        model_calls=0,human_labels_read=0,
        limitation='Complete future scoring requests add instructions, reply units and actual new replies; do full admission checks at submission. Source length does not predict reasoning length.',
        source_files={str(p.relative_to(PROJECT)):sha256_file(p) for p in [specs_path,source,Path(__file__),
            PROJECT/'src/metacom_pm/rl1/evidence.py',ROOT/'P3/candidate_v1/protocol.json']})
    target=ROOT/'P3/verification/future_train_dev_source_lengths.json'
    with target.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','source_files')},ensure_ascii=False))


if __name__=='__main__':main()

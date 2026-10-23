#!/usr/bin/env python3
"""Mandatory source gate before importing/loading the existing local author."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
OUT=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v2'

def preflight():
    from metacom_pm.io import sha256_file
    from metacom_pm.rl1.schema import EpisodeSpec,Resource,digest
    from metacom_pm.rl1.evidence import prefix_from_dict
    from metacom_pm.rl1.source_preflight import validate_generation_sources
    c=json.loads((OUT/'condition_contract_private.json').read_text())
    for name,expected in c['source_guard'].items():
        if sha256_file(PROJECT/name)!=expected:raise ValueError('source preflight file changed: '+name)
    # Tokenizer-only import. No inference engine/GPU model exists before gate.
    binding=importlib.util.spec_from_file_location('pilot_binding',PROJECT/'scripts/rl1/46_bind_repaired_pilot.py')
    m=importlib.util.module_from_spec(binding);binding.loader.exec_module(m)
    tokenizer=m.AutoTokenizer.from_pretrained(m.MODEL,local_files_only=True)
    renderer=m.Renderer(count_text=m.build_llama_token_counter(m.MODEL/'tokenizer.json'),
        count_chat=lambda x:len(tokenizer.apply_chat_template(x,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=sha256_file(m.MODEL/'tokenizer.json'),template=tokenizer.chat_template)),
        context_limit=m.AutoConfig.from_pretrained(m.MODEL,local_files_only=True).max_position_embeddings)
    specs=[EpisodeSpec(**dict(r,prefix=prefix_from_dict(r['prefix']),
        inventory=tuple(tuple(Resource(**dict(x,source_ids=tuple(x['source_ids']))) for x in rows) for rows in r['inventory'])))
        for r in json.loads((OUT/'episode_specs_private.json').read_text())]
    receipt=validate_generation_sources(c,specs=specs,
        evidence=json.loads((OUT/'legal_evidence_private.json').read_text()),
        reviews=json.loads((OUT/'source_reviews_private.json').read_text()),renderer=renderer)
    path=OUT/'generation_preflight.json'
    if path.exists():
        if json.loads(path.read_text())!=receipt:raise ValueError('preflight receipt changed')
    else:
        with path.open('x') as f:f.write(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt

def main():
    p=argparse.ArgumentParser();p.add_argument('--preflight-only',action='store_true');args=p.parse_args()
    receipt=preflight()
    print(json.dumps(dict(stage='source_preflight',status=receipt['status'],conditions=len(receipt['conditions']))),flush=True)
    if args.preflight_only:return
    binding=importlib.util.spec_from_file_location('local_author',PROJECT/'scripts/rl1/38_author_executor_pilot.py')
    author=importlib.util.module_from_spec(binding);binding.loader.exec_module(author)
    author.OUT=OUT
    author.main()
if __name__=='__main__':main()

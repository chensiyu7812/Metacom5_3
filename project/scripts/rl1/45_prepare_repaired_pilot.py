#!/usr/bin/env python3
"""Prepare the source-repaired developmental batch; select from input only.

Prepare all legal single-GET options for a separate source/relevance audit.
No author generation, supervision admission, evaluation or training here.
"""
from collections import defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import iter_jsonl, sha256_file, sha256_text
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter
from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Encoder
from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog
from metacom_pm.rl1.data import ranked_memory
from metacom_pm.rl1.source_repair import repaired_as_of_memory, validate_overlay
from metacom_pm.rl1.evidence import prefix_from_dict, legal_evidence
from metacom_pm.rl1.schema import EpisodeSpec, Resource, HEADS, digest
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.env import ResourceEnv

OUT = PROJECT / 'outputs/pm_rl1/executor_pilot_20260929_v2'
SOURCE = PROJECT / 'outputs/pm_rl1/source_and_capacity_20260928_v1'
ENGINEERING = PROJECT / 'outputs/pm_rl1/engineering_20260928_v1'
MODEL = Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    import numpy as np
    import torch
    from transformers import AutoTokenizer, AutoConfig
    started = time.monotonic()
    if (not torch.cuda.is_available() or torch.cuda.device_count() != 1
            or 'A4500' not in torch.cuda.get_device_name(0)):
        raise RuntimeError('bind the available A4500 explicitly')
    freeze = json.loads((SOURCE / 'dataset_freeze.json').read_text())
    for name, expected in freeze['artifacts'].items():
        if sha256_file(SOURCE / name) != expected:
            raise ValueError('frozen source changed: ' + name)
    by_owner = defaultdict(list)
    for raw in json.loads((SOURCE / 'prefixes_private.json').read_text()):
        if raw['split'] in ('train', 'dev'):
            p = prefix_from_dict(raw)
            by_owner[p.owner_id].append(p)
    selected = {'p2':['p2_conv_4'],'p3':['p3_conv_8'],'p5':['p5_conv_2'],
        'p6':['p6_conv_7'],'p8':['p8_conv_4'],'p9':['p9_conv_1'],
        'p10':['p10_conv_9'],'p11':['p11_conv_2'],'p12':['p12_conv_1'],
        'p13':['p13_conv_1'],'p16':['p16_conv_3'],'p17':['p17_conv_1'],
        'p1':['p1_conv_18','p1_conv_12'],'p15':['p15_conv_10','p15_conv_2'],
        'p18':['p18_conv_2','esc552']}
    roster=[p for owner in sorted(selected) for p in by_owner[owner] if p.session_id in selected[owner]]
    roster.sort(key=lambda p:(p.split!='train',p.owner_id,p.cutoff_rank))
    assert len(roster)==18 and sum(p.split=='train' for p in roster)==12
    save('roster_private.json', [asdict(p) for p in roster])
    save('selection.json', dict(rule='Source/current-input-selected development sample within prior audited owner/rank scope; one train or two dev per owner; not random or independent evaluation',
        counts={'train': 12, 'dev': 6, 'test': 0}, generation_observed_before_selection=False, prior_batch_outputs_known=True,
        selection_rationale="Prefer substantive present concerns over greetings/closures; preserve frozen owner split. This is developmental task selection, not a claimed treatment win.",
        source_freeze_sha256=sha256_file(SOURCE/'dataset_freeze.json'),
        roster_sha256=sha256_file(OUT/'roster_private.json')))
    source = PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    units_path = PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'
    users = load_sanitized_runtime_users(source)
    units = load_accepted_multi_view_units(units_path, users=users)
    user_map = {u.owner_id: u for u in users}
    unit_map = defaultdict(list)
    for u in units:
        unit_map[u.owner_id].append(u)
    counter = build_llama_token_counter(MODEL/'tokenizer.json')
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    renderer = Renderer(count_text=counter,
        count_chat=lambda m: len(tokenizer.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=sha256_file(MODEL/'tokenizer.json'), template=tokenizer.chat_template)),
        context_limit=AutoConfig.from_pretrained(MODEL, local_files_only=True).max_position_embeddings)
    overlay_path=PROJECT/'outputs/pm_rl1/source_repair_20260929_v2/source_overlay_private.json'
    overlay=json.loads(overlay_path.read_text())
    assert overlay['source_sha256']==sha256_file(units_path) and overlay['raw_sha256']==sha256_file(source)
    validate_overlay(overlay,units=units,users=user_map)
    projected=[repaired_as_of_memory(p,user=user_map[p.owner_id],units=unit_map[p.owner_id],token_counter=counter,overlay=overlay) for p in roster]
    candidates=[x[0] for x in projected]
    save('source_projection_private.json',[x[1] for x in projected])
    unique = {c.candidate_id: c for group in candidates for rows in group.values() for c in rows}
    cards = build_strategy_source_catalog(esconv_path=PROJECT/'data/external/ESConv.json',
        split_manifest_path=PROJECT/'data/strategy/esconv_split_manifest_v1_5.jsonl')
    card_map = {c.card_id: c for c in cards}
    alias_path = PROJECT/'data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl'
    aliases = list(iter_jsonl(alias_path))
    seeds = {f'esconv_{int(s.session_id[3:]):04d}' for u in users for s in u.sessions if s.session_id.startswith('esc') and s.session_id[3:].isdigit()}
    rs_texts = []
    for a in aliases:
        if seeds.intersection(a['source_dialogue_ids']):
            raise ValueError('RS source overlaps a public longitudinal seed')
        text = card_map[a['representative_source_card_id']].retrieval_text+'\n'+a['rendered_card_text']
        if sha256_text(text) != a['representative_retrieval_text_sha256'] or sha256_text(a['rendered_card_text']) != a['rendered_card_text_sha256']:
            raise ValueError('RS content identity changed')
        rs_texts.append(text)
    print(json.dumps(dict(stage='BGE', prefixes=len(roster), documents=len(unique))), flush=True)
    load_start = time.monotonic()
    encoder = BgeM3Encoder()
    retrieval = dict(protocol='pm-rl1-full-prefix-bge-v1', binding=asdict(encoder.binding),
        runtime=asdict(encoder.runtime_identity), rs_alias_sha256=sha256_file(alias_path),
        query='entire public current-session prefix', tie_break='candidate_id', probe_only=True)
    cache = ENGINEERING/('rs_vectors_'+digest(retrieval)+'.npy')
    if not cache.exists():
        raise RuntimeError('existing same-identity RS embedding cache required')
    expected = json.loads(cache.with_suffix('.json').read_text())
    if expected != dict(texts_sha256=digest(rs_texts), vectors_sha256=sha256_file(cache)):
        raise ValueError('RS embedding cache changed')
    load_seconds=time.monotonic()-load_start
    rs_vecs = np.load(cache, allow_pickle=False)
    retrieval=dict(**retrieval,source_overlay_identity=digest(overlay),
        source_overlay_sha256=sha256_file(overlay_path),
        repair_code_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/source_repair.py'))
    encode_start = time.monotonic()
    ids = sorted(unique)
    vectors = dict(zip(ids, encoder.encode([unique[i].content for i in ids])))
    queries = encoder.encode([p.query for p in roster])
    encode_seconds = time.monotonic()-encode_start
    specs, audit, evidence, keys = [], [], [], []
    for index, (p, group, query) in enumerate(zip(roster, candidates, queries), 1):
        inventory = ranked_memory(p, group, vectors, query)
        scores = rs_vecs @ np.asarray(query, dtype=np.float32)
        order = sorted(range(len(aliases)), key=lambda i: (-float(scores[i]), aliases[i]['treatment_id']))
        inventory['RS'] = tuple(Resource(aliases[i]['treatment_id'], 'RS', aliases[i]['rendered_card_text'],
            float(scores[i]), counter(aliases[i]['rendered_card_text']), None, None, None, 'not_applicable',
            tuple(aliases[i]['source_dialogue_ids'])) for i in order[:4])
        spec = EpisodeSpec(p, tuple(tuple(inventory[h][:4]) for h in HEADS), digest(retrieval),
            'R05_EXECUTOR_NOT_LOADED', 'R05_NO_REWARD', 'r05-pilot-v2')
        specs.append(asdict(spec))
        env = ResourceEnv(spec, renderer)
        options = []
        for h, count in zip(HEADS, spec.inventory):
            if not count:
                continue
            counts = tuple(int(x == h) for x in HEADS)
            options.append(dict(head=h, counts=counts, legal=renderer.fits(spec, counts),
                resource_tokens=renderer.cost(spec, counts), resource=asdict(count[0])))
        audit.append(dict(index=index, prefix_identity=p.identity, split=p.split, owner=p.owner_id,
            current_prefix=[dict(id=f'C:T{i:03d}', **asdict(t)) for i,t in enumerate(p.turns)], options=options))
        e, key = legal_evidence(p, user_map[p.owner_id])
        evidence.append(dict(index=index, prefix_identity=p.identity, evidence=e, evidence_identity=digest(e)))
        keys.append(key)
    save('episode_specs_private.json', specs)
    save('condition_options_private.json', audit)
    save('legal_evidence_private.json', evidence)
    save('coordinator_only/evidence_source_map.json', keys)
    save('preparation_manifest.json', dict(status='INPUTS_PREPARED_CONDITION_RELEVANCE_AUDIT_PENDING',
        retrieval=retrieval, renderer_identity=renderer.identity, budget=2048,
        author_calls=0, parameter_updates=0, API_usd=0,
        bge_load_seconds=load_seconds, bge_encode_seconds=encode_seconds,
        total_seconds=time.monotonic()-started,
        source_hashes={str(p.relative_to(PROJECT)):sha256_file(p) for p in (source,units_path,alias_path)},
        files={name:sha256_file(OUT/name) for name in ('roster_private.json','selection.json','episode_specs_private.json','condition_options_private.json','legal_evidence_private.json','coordinator_only/evidence_source_map.json','source_projection_private.json')},
        code_sha256=sha256_file(Path(__file__))))
    print(json.dumps(dict(stage='prepared', prefixes=len(roster), seconds=time.monotonic()-started)), flush=True)


if __name__ == '__main__':
    main()

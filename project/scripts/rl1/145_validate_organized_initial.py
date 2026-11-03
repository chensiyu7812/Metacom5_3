#!/usr/bin/env python3
"""Reconsume the actual prepared train inputs and real BGE cache, offline.

Replays every ordered endpoint through the production supervision compiler and
reassembles both policy views from saved complete-token vectors. No G/BGE load,
API call, new score, or optimizer is available in this validation entry point.
"""
import argparse
from dataclasses import asdict, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import shutil
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.organized_encoding import BlockCache, EncodedHeadView, tokenizer_identity
from metacom_pm.rl1.organized_features import FullTextFeatures
from metacom_pm.rl1.organized_feedback import OrganizedEpisode, TokenCost
from metacom_pm.rl1.organized_policy_interface import HeadObservation, ReadText, no_text
from metacom_pm.rl1.organized_supervision import prepare_targets
from metacom_pm.rl1.resource_organization import OrganizationCatalog, OrganizedItem, OrganizedRenderer
from metacom_pm.rl1.schema import PublicTurn, digest
from metacom_pm.rl1.supervised_learning import save_json


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())


def validate(package, encoding, output):
    if output.exists(): raise ValueError('new validation output required')
    for root, manifest in ((package,'PACKAGE_MANIFEST.json'), (encoding,'OUTPUT_MANIFEST.json')):
        for name, expected in read(root/manifest).items():
            if Path(name).is_absolute() or '..' in Path(name).parts or sha(root/name) != expected:
                raise ValueError('prepared inputs or actual encoding changed')
    c = read(package/'CONFIG.json'); sources = read(package/'INPUT_HASHES_PRIVATE.json')
    for path, expected in sources.items():
        if sha(path) != expected: raise ValueError('frozen input source changed: '+path)
    result = read(encoding/'RESULTS.json')
    if (result['source_package_identity'] != digest(read(package/'PACKAGE_MANIFEST.json'))
            or result['BGE_identity'] != c['encoder_identity'] or result['real_BGE_loads'] != 1):
        raise ValueError('actual BGE output belongs to another preparation')
    from transformers import AutoTokenizer
    gt = AutoTokenizer.from_pretrained(c['runtime']['model_dir'], local_files_only=True)
    bt = AutoTokenizer.from_pretrained(c['bge_local_dir'], local_files_only=True)
    if tokenizer_identity(bt) != c['bge_tokenizer_identity']: raise ValueError('BGE tokenizer changed')
    @lru_cache(maxsize=32768)
    def count(text): return len(gt.encode(text, add_special_tokens=False, truncation=False))
    @lru_cache(maxsize=32768)
    def tokens(text): return tuple(bt.encode(text, add_special_tokens=False, truncation=False))
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    renderer = OrganizedRenderer(count_text=count,
        count_chat=lambda ms:len(gt.apply_chat_template(ms, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256, template=gt.chat_template)),
        context_limit=c['runtime']['policy']['context_limit'])
    if renderer.identity != c['renderer_identity']: raise ValueError('G renderer changed')
    library_paths = [p for p in sources if p.endswith('/RS_LIBRARY_PRIVATE.json')]
    if len(library_paths) != 1: raise ValueError('one bound RS source required')
    library = read(library_paths[0]); items = {x['key']:OrganizedItem(**x) for x in library['items']}
    if digest([x.identity for x in items.values()]) != library['identity']: raise ValueError('RS identity changed')
    factories = {}; observations = read(package/'OBSERVATIONS_PRIVATE.json')
    for pid in c['initial_prefixes']:
        src = read(package/'sources_private'/(pid+'.json')); stored = read(src['stored_source_path'])
        if src['stored_source_path'] not in sources: raise ValueError('unbound catalog source')
        prefix = prefix_from_dict(src['prefix'])
        if prefix.identity != pid or prefix.split != 'train': raise ValueError('initial pool must remain train-only')
        metadata = stored['frozen_RS_metadata']
        local = [replace(v, original_rank=metadata[k][0], bge_similarity=metadata[k][1]) if k in metadata else v
                 for k,v in items.items()]
        local += [OrganizedItem(**x) for x in stored['memory']]
        catalog = OrganizationCatalog(prefix, local, provenance_identity=stored['catalog_identity'])
        if catalog.identity != src['catalog_identity']: raise ValueError('rebuilt catalog changed')
        def factory(catalog=catalog, src=src):
            return OrganizedEpisode(catalog, renderer, executor_identity=c['runtime']['identity'],
                draw_identity=c['draw_identity'], trajectory_id='prepared-input-validation',
                evidence=src['evidence'], evidence_source=src['evidence_source'], cost=TokenCost(**c['cost']))
        factories[pid] = factory
    menu = read(package/'MENU_PRIVATE.json')
    handoff = prepare_targets(menu, factories=factories, responses=read(package/'REUSED_OFF_PRIVATE.json'), receipts={})
    if (handoff['status'] != 'PENDING_SCHEDULED_FEEDBACK' or handoff['targets'] or handoff['measured']
            or len(handoff['pending']) != len(menu['endpoints'])
            or any(p['reason'] != 'missing_qualification' for p in handoff['pending'])):
        raise ValueError('unqualified real inputs unexpectedly became training targets')
    output.mkdir(parents=True, mode=0o700)
    # Keep the original encoded cache and its manifest byte-identical.
    shutil.copyfile(encoding/'blocks.sqlite', output/'validation_blocks.sqlite')
    cache = BlockCache(output/'validation_blocks.sqlite', encoder_identity=c['encoder_identity'], dimension=1024, native_window=8192)
    planner = FullTextFeatures(encode_tokens=tokens, add_special_tokens=bt.build_inputs_with_special_tokens,
        native_window=8192, special_tokens=bt.num_special_tokens_to_add(pair=False),
        tokenizer_identity=c['bge_tokenizer_identity'], encoder_identity=c['encoder_identity'], dimension=1024)
    def no_forward(_): raise ValueError('unplanned block; validation cannot invoke a model')
    full = EncodedHeadView(planner, cache, invoke=no_forward, encoder_identity=c['encoder_identity'])
    hidden = EncodedHeadView(planner, cache, invoke=no_forward, encoder_identity=c['encoder_identity'], without_text=True)
    actual = read(encoding/'FEATURES_PRIVATE.json')
    if set(actual) != set(observations): raise ValueError('real encoded observation coverage differs')
    for key, row in observations.items():
        raw = row['observation']
        obs = HeadObservation(**(raw | dict(current_prefix=tuple(PublicTurn(**x) for x in raw['current_prefix']),
            acquired=tuple(ReadText(**x) for x in raw['acquired']),
            **{k:tuple(raw[k]) for k in ('counts','remaining_items','next_input_tokens','action_mask')})))
        if digest(asdict(obs)) != key or planner.plan(obs) != row['plan']: raise ValueError('public input/complete-token plan changed')
        x, mask = full.sequential(obs); nx, nmask = hidden.sequential(no_text(obs)); old = actual[key]
        if (list(x) != old['features'] or list(nx) != old['NoText_features'] or list(mask) != old['mask']
                or mask != nmask or any(nx[1024:5120]) or old['full_view_identity'] != full.identity
                or old['NoText_view_identity'] != hidden.identity): raise ValueError('actual FullText/NoText feature replay differs')
    if sha(encoding/'blocks.sqlite') != read(encoding/'OUTPUT_MANIFEST.json')['blocks.sqlite']:
        raise ValueError('original real cache changed')
    report = dict(status='REAL_INPUTS_REPLAY_VALIDATED_REWARD_STILL_PENDING', train_prefixes=len(factories),
        replayed_programs=len(menu['endpoints']), reassembled_observations=len(actual),
        full_and_no_text_equal_to_archived_encoding=True, original_cache_unchanged=True,
        pending_qualified_endpoints=len(handoff['pending']), qualified_targets=0,
        new_model_loads=0, new_G_calls=0, new_J_calls=0, new_BGE_forward=0, natural_updates=0,
        package_identity=digest(read(package/'PACKAGE_MANIFEST.json')), menu_identity=menu['identity'],
        encoder_identity=c['encoder_identity'])
    save_json(output/'VALIDATION.json', report); save_json(output/'HANDOFF_PRIVATE.json', handoff)
    save_json(output/'OUTPUT_MANIFEST.json', {p.name:sha(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('package','encoding','output'): p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args(); validate(a.package, a.encoding, a.output)

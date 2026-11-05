#!/usr/bin/env python3
"""Replay an existing, complete prefix-specific MS ranking; no global promotion."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.resource_organization import OrganizationCatalog, OrganizationSession
from metacom_pm.rl1.schema import digest

METHOD = 'complete-frozen-prefix-bge-MS-static-replay-v1'
BASE = PROJECT / 'outputs/pm_rl1'
TRAIN = BASE / 'organized_initial_training_20261103_v2'


def read(path):
    return json.loads(path.read_text())


def complete_ms_rows(catalog):
    # Construction-side access only. No inventory or scores enter the actor.
    items = [x for x in catalog._items.values() if x.head == 'MS']
    if not items or any(x.original_rank is None or x.bge_similarity is None
                        or not math.isfinite(x.bge_similarity) for x in items):
        raise ValueError('Every legal MS needs its original prefix-specific score; do not silently drop additions')
    if sorted(x.original_rank for x in items) != list(range(1, len(items) + 1)):
        raise ValueError('Incomplete or ambiguous original rank domain')
    by_rank = sorted(items, key=lambda x: x.original_rank)
    if any(a.bge_similarity < b.bge_similarity for a, b in zip(by_rank, by_rank[1:])):
        raise ValueError('Original order and similarity disagree')
    return by_rank


class CompleteFrozenMSCatalog(OrganizationCatalog):
    """Static MS ablation, full other-head domains preserved; separately identified."""
    def __init__(self, original):
        self._frozen_ms = complete_ms_rows(original)
        super().__init__(original.prefix, original._items.values(), provenance_identity=original.provenance_identity)
        self.original_catalog_identity = self.identity
        self.identity = digest(dict(original_catalog=self.identity, locator=METHOD,
            MS_order=[dict(key=x.key, item_identity=x.identity, rank=x.original_rank,
                           similarity=x.bge_similarity) for x in self._frozen_ms]))

    def rank(self, head, acquired=()):
        if head != 'MS':
            return super().rank(head, acquired)
        self.canonical(acquired)  # Reject duplicated/unknown acquisitions as usual.
        return [dict(key=x.key, ranking_method=METHOD, ranking_score=x.bge_similarity,
                     bge_similarity=x.bge_similarity, original_rank=x.original_rank,
                     query_identity=digest(dict(prefix=self.prefix.identity, method=METHOD)))
                for x in self._frozen_ms if x.key not in acquired]


def main(out):
    from metacom_pm.rl1.online_materials import load_materials
    _, catalogs, renderer = load_materials(TRAIN)
    review = BASE / 'incremental_help_human_review_20261105_v1'
    registry = read(review / 'ANSWER_REGISTRY_PRIVATE.json')
    reference = next(r for r in registry if r.get('question_id') == 'G01')
    audit = read(out / 'OLD_HUMAN_REFERENCE_PRIVATE.json')
    prefix = read(out / 'STUDY.json')['prefix_identity']
    coverage = []
    for pid, cat in sorted(catalogs.items()):
        ms = [x for x in cat._items.values() if x.head == 'MS']
        try:
            complete_ms_rows(cat)
            available = True
        except ValueError:
            available = False
        coverage.append(dict(prefix_identity=pid, total_MS=len(ms),
            scored_MS=sum(x.bge_similarity is not None for x in ms), complete_frozen_replay_available=available))
    cat = CompleteFrozenMSCatalog(catalogs[prefix])
    session = OrganizationSession(cat, renderer)
    session.get('MS')
    keys = session.receipt()['acquired']
    actual = renderer.messages(cat, keys)
    old = audit['request']
    assert actual == old['messages'] and keys == old['selected_keys']
    assert [x.identity for x in cat.canonical(keys)] == old['selected_resource_identities']
    off = read(out / 'REUSED_PRIVATE.json')
    off_card = next(r for r in read(out / 'CARDS_PRIVATE.json') if r['depth'] == 0)
    off_record = off[off_card['input_identity']]
    assert renderer.messages(cat, []) == off_record['request']['messages']
    assert audit['raw']['runtime_identity'] == off_record['raw']['runtime_identity']
    assert set(reference['reply_identities']) == {audit['raw']['text_identity'], off_record['raw']['text_identity']}
    evidence = read(out / 'EVIDENCE_PRIVATE.json')
    assert reference['evidence']['current_prefix'] == [
        dict(speaker=t['role'], text=t['text']) for t in evidence['current_prefix']]
    from metacom_pm.rl1.resource_value_probe import match_session
    assert reference['evidence']['legal_past_source'] == match_session(cat.item(keys[0]), evidence)
    assert reference['degree'] == 'slight' and reference['slight_edge_reply_identity'] == audit['raw']['text_identity']
    # Keep the existing answer and ordinal scope. No new annotation or scalar conversion.
    result = dict(scope='POSTHOC_DEVELOPMENT_STATIC_MS_LOCATOR_REPLAY', method=METHOD,
        code_sha256=sha(Path(__file__)), prefix_identity=prefix, case='N23',
        old_catalog_identity=cat.original_catalog_identity, variant_catalog_identity=cat.identity,
        full_action_domain_counts=dict(Counter(x.head for x in cat._items.values())),
        complete_MS_order=[dict(key=x.key, rank=x.original_rank, similarity=x.bge_similarity) for x in cat._frozen_ms],
        actual_program=[3, 0], receipt=session.receipt(), acquisition_order=keys,
        G_input_messages_identity=digest(actual), original_G_request=old['identity'],
        runtime_identity=old['runtime_identity'], exact_input_and_resource_match=True,
        source_evidence_identity=digest(reference['evidence']),
        evidence_binding='Same current roles/text after schema normalization; exact full selected legal past session. Original G01 evidence scope preserved.',
        human_asset_id=reference['asset_id'],
        human_pair_identity=reference['pair_identity'], old_preference_reusable=True,
        human_degree='slight', human_reason=reference['raw_label'],
        preferred_reply_identity=audit['raw']['text_identity'], OFF_reply_identity=off_record['raw']['text_identity'],
        numeric_reward=None, qualified_general_feedback=False, added_human_answers=0,
        new_G_calls=0, PM_updates=0, api_cost_usd=0, coverage=coverage,
        limitations=[
            'This diagnostic chooses a pre-existing ranking after examining N23; it is not held-out evidence.',
            'No recomputed BGE embeddings. Exact offline rank reuse is not measured online retrieval latency.',
            'Full legal MS domain required; new unscored sources cannot be silently omitted.',
            'Static MS ordering does not establish beneficial read-conditioned retrieval or global superiority.',
            'G01 judges helpfulness of these exact replies; it is not a cardinal gain or net latency utility.',
            'Original locator, G, datasets, human registry and training code remain unchanged.'],
        sources={str(p.resolve()): sha(p) for p in [TRAIN / 'PACKAGE_MANIFEST.json', TRAIN / 'INPUT_HASHES_PRIVATE.json',
                 review / 'ANSWER_REGISTRY_PRIVATE.json', out / 'OLD_HUMAN_REFERENCE_PRIVATE.json',
                 out / 'EVIDENCE_PRIVATE.json', out / 'REUSED_PRIVATE.json']})
    save(out / 'FROZEN_LOCATOR_REPLAY_PRIVATE.json', result)
    print(json.dumps(dict(case='N23', actual_program=[3, 0], exact_human_pair_reused='G01',
        full_MS=4, complete_scored_prefixes=sum(x['complete_frozen_replay_available'] for x in coverage),
        scoped_prefixes=len(coverage), new_G_calls=0, new_human_answers=0)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output.resolve())

"""Read-only integrity and cross-source checks for this feasibility audit."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT / 'outputs/pm_rl1'
OLD = BASE / 'dataset_diagnostics_20260930_v1'
HUMAN = BASE / 'history_necessity_human_review_20261105_v1'
OUT = BASE / 'value_and_novelty_audit_20261105_v1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return row['owner'], row['group'], int(row['idx'])


def main():
    sources = read(OUT / 'SOURCE_MANIFEST.json')
    expected_sources = {
        str((PROJECT / rel).resolve()): value
        for rel, value in read(OLD / 'closeout.json')['artifacts'].items()
    }
    expected_sources.update({str((HUMAN / rel).resolve()): value
        for rel, value in read(HUMAN / 'OUTPUT_MANIFEST.json').items()})
    assert sources == expected_sources
    for path, value in sources.items():
        assert sha(Path(path)) == value, path
    sealed = read(OUT / 'OUTPUT_MANIFEST.json')
    actual_files = {str(p.relative_to(OUT)) for p in OUT.rglob('*')
                    if p.is_file() and p.name != 'OUTPUT_MANIFEST.json'}
    assert set(sealed) == actual_files
    for rel, value in sealed.items():
        assert sha(OUT / rel) == value, rel

    rows = read(OLD / 'qa_train_dev_review_private.json')
    indexed = {key(r): r for r in rows}
    assert len(rows) == len(indexed) == 1261
    census = read(OLD / 'census.json')
    assert Counter(r['split'] for r in rows) == {'train': 1003, 'dev': 258}
    assert all(census['owner_splits'][r['owner']] == r['split'] for r in rows)
    for name in ['qa_train_dev_features.csv', 'qa_audit_registry.csv']:
        with (OLD / name).open() as f:
            records = list(csv.DictReader(f))
        assert len(records) == len({key(r) for r in records}) == 1261
        assert {key(r) for r in records} == set(indexed)
        for record in records:
            source = indexed[key(record)]
            for field in record.keys() & source.keys():
                assert record[field] == str(source[field]), (name, key(record), field)

    summary = read(OUT / 'QA_SUMMARY.json')
    assert summary['task_counts_metadata_only'] == census['tasks']
    assert summary['natural_history_value'] == read(HUMAN / 'SUMMARY.json')['primary_ordinal_analysis']
    independent = {}
    for split in ['train', 'dev', 'combined']:
        group = [r for r in rows if split == 'combined' or r['split'] == split]
        sessions = [{x['session'] for x in r['reference_resolution']
            if x['kind'] in ['visible_turn', 'visible_session']} for r in group]
        assert all(len(s) == r['visible_evidence_sessions'] for r, s in zip(group, sessions))
        stats = summary['qa'][split]
        assert stats['rows'] == len(group)
        assert stats['owners'] == len({r['owner'] for r in group})
        assert stats['capabilities'] == Counter(r['capability'] for r in group)
        assert stats['visible_sessions'] == Counter(str(min(2, len(s))) for s in sessions)
        short = sum(r['capability'] == 'information extraction' and r['answer_words'] <= 5
                    and bool(r['literal_seeker_answer_hits']) and not r['unresolved_refs'] for r in group)
        assert stats['short_extractive_candidates'] == short
        independent[split] = {'rows': len(group), 'owners': stats['owners'], 'short_candidates': short}
    single = Counter(r['capability'] for r in rows if r['visible_evidence_sessions'] == 1)
    assert single['temporal reasoning'] == 166 and single['user modeling'] == 211

    sample = read(OUT / 'CITATION_SAMPLE_PRIVATE.json')
    expected = []
    for cap in sorted({r['capability'] for r in rows}):
        group = [r for r in rows if r['split'] == 'train' and r['capability'] == cap]
        expected.extend(sorted(group, key=lambda r: hashlib.sha256(
            '|'.join(map(str, key(r))).encode()).hexdigest())[:3])
    assert sample == expected and len(sample) == 15
    review = read(OUT / 'CITATION_REVIEW_PRIVATE.json')
    assert len(review['rows']) == len({tuple(r['key']) for r in review['rows']}) == 15
    assert {tuple(r['key']) for r in review['rows']} == {key(r) for r in sample}
    assert review['qualified_rewards_created'] == summary['new_qualified_rewards'] == 0
    download = read(OUT / 'literature/download.json')
    pdf = OUT / 'literature/StratMem-Bench.pdf'
    assert sha(pdf) == download['sha256'] and pdf.stat().st_size == download['bytes']
    result = dict(status='PASS', source_files_hash_verified=len(sources),
        new_files_hash_verified=len(sealed), qa_cross_source_rows=1261,
        independently_checked_counts=independent, citation_sample_and_review_pairs=15,
        single_session_temporal=166, single_session_user_modeling=211,
        prior_human_summary_unchanged=True, model_or_semantic_performance_validation=False,
        note='Integrity, split, count and binding checks only; no gain or reward qualification established.')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

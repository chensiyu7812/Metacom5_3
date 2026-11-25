#!/usr/bin/env python3
"""Validate private source reviews and execute local CPU RAW fallback checks."""
import argparse
import json
from pathlib import Path

from metacom_pm.rl1v3.journal.keycap_memory_review import (
    check_reference, jsonl, load_completed_job, m1_aggregate, raw_fallbacks,
    reference_mutations, validate_m1_manual, validate_writer_manual, writer_quote_screen)
from metacom_pm.rl1v3.io import file_sha256, object_sha256, write_json_once, write_jsonl_once


def main():
    parser = argparse.ArgumentParser()
    for name in ('package', 'm1-job', 'w1-job', 'audit', 'inventory', 'review',
                 'registry', 'ledger', 'model', 'assets', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    m1 = load_completed_job(args.package / 'representation-batch-1/REQUESTS.private.jsonl', args.m1_job)
    w1 = load_completed_job(args.package / 'writer8/REQUESTS.private.jsonl', args.w1_job)
    audits = {r['task_id']: r for r in jsonl(args.audit)}
    inventories = {r['request_id']: r for r in json.loads(args.inventory.read_text())}
    m1_reviews = jsonl(args.review / 'M1_REVIEW_PRIVATE.jsonl')
    w1_reviews = jsonl(args.review / 'W1_REVIEW_PRIVATE.jsonl')
    for joined_rows, reviews in [(m1, m1_reviews), (w1, w1_reviews)]:
        if len(reviews) != len(joined_rows) or {r['request_id'] for r in reviews} != {r['request_id'] for r in joined_rows}:
            raise ValueError('review coverage differs from frozen generation set')
    for row in m1:
        review = next(r for r in m1_reviews if r['request_id'] == row['request_id'])
        if review['output_sha256'] != row['output_sha256']:
            raise ValueError('M1 review output changed')
        validate_m1_manual(review, row, audits[review['task_id']])
    sources = jsonl(args.package / 'WRITER_SOURCE_INVENTORY.private.jsonl')
    for row in w1:
        review = next(r for r in w1_reviews if r['request_id'] == row['request_id'])
        if review['output_sha256'] != row['output_sha256']:
            raise ValueError('W1 review output changed')
        validate_writer_manual(review, inventories[row['request_id']], row['output']['text'])
        source = next(s for s in sources if s['request_id'] == row['request_id'])
        if writer_quote_screen(row['output']['text'], source) != review['original_exact_quote_role_screen']:
            raise ValueError('writer exact screen does not reproduce')
    # Four fixed source-order cases; no output-based selection or model calls.
    structured = []
    for source in sources[:4]:
        turn = next(t for t in source['turns'] if t['speaker'] == 'seeker')
        for item in reference_mutations(source, turn['turn']):
            result = check_reference(item['answer'], source)
            if result['structural_status'] != item['expected']:
                raise ValueError('source metadata mutation check failed')
            structured.append(dict(derived_from_request_id=source['request_id'],
                derived_task_identity='source-reference:' + object_sha256(dict(source=source['source'], turn=turn['turn'])),
                source=source, requested_turn=turn['turn'], **item, result=result))
    write_jsonl_once(args.out / 'STRUCTURED_REFERENCE16_PRIVATE.jsonl', structured)
    # Imports stay here so generic review/tests do not require private stack deps.
    from metacom_pm.rl1v3.compile import asof as A
    from metacom_pm.rl1v3.sources import source_registry as S
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
    before = {str(p): file_sha256(p) for p in sorted(args.ledger.glob('*.json'))}
    registry = S.load(args.registry)
    tokenizer = PromptTokenizer(NativeTokenizer(args.model, args.assets))
    fallback = raw_fallbacks(registry, tokenizer, A.Ledger(args.ledger), sources)
    after = {str(p): file_sha256(p) for p in sorted(args.ledger.glob('*.json'))}
    if before != after:
        raise ValueError('existing RAW Ledger changed')
    write_jsonl_once(args.out / 'RAW_FALLBACK8_PRIVATE.jsonl', fallback)
    write_json_once(args.out / 'LEDGER_READONLY_RECEIPT_PRIVATE.json', dict(before=before, after=after, unchanged=True))
    write_json_once(args.out / 'M1_AGGREGATE_PUBLIC.json', m1_aggregate(m1_reviews))
    public = dict(protocol='journal-keycap-memory-cpu-validation-v1', m1_reviews_validated=len(m1_reviews),
        w1_reviews_validated=len(w1_reviews), source_propositions_reviewed=sum(len(r['propositions']) for r in w1_reviews),
        raw_fallback_reads_available=sum(r['status']=='actual_full_raw_read_available' for r in fallback),
        raw_fallback_all_full_source_turns_retained=all(r.get('all_source_turns_retained',False) for r in fallback),
        old_ledger_unchanged=before==after, old_summary_admission_modified=False,
        structured_checks=len(structured), structured_correct_accepted=sum(r['variant']=='correct' and r['result']['structural_status']=='pass' for r in structured),
        structured_mutations_rejected=sum(r['variant']!='correct' and r['result']['structural_status']=='fail' for r in structured),
        structure_scope='source role, report date and exact quote offsets only; event stage unknown; not natural QA or support quality',
        model_calls=0, semantic_approved=0, rewards=0)
    write_json_once(args.out / 'VALIDATION_PUBLIC.json', public)
    write_json_once(args.out / 'MANIFEST_PRIVATE.json', dict(files={str(p):file_sha256(p) for p in sorted(args.out.iterdir()) if p.is_file()},
        review_input_sha256={str(p):file_sha256(p) for p in [args.audit,args.inventory,args.review/'M1_REVIEW_PRIVATE.jsonl',args.review/'W1_REVIEW_PRIVATE.jsonl']},
        code_sha256=file_sha256(__file__)))
    print(json.dumps(public, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

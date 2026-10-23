#!/usr/bin/env python3
"""Decrypt DEVELOPMENT labels only; preserve the original sealed handoff.

This intentionally provides no validation-opening CLI yet. That step needs real
development reviews, any allowed revision, and a final measurement freeze.
"""
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.human_calibration import ingest_submission, strict_json
from metacom_pm.rl1.schema import digest

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P3/calibration'


def main(path, rater):
    freeze = strict_json((ROOT / 'packet_freeze.json').read_text())
    for name, sha in freeze['files'].items():
        if sha256_file(ROOT / name) != sha:
            raise ValueError('frozen packet changed: ' + name)
    form = strict_json((ROOT / f'{rater}_form.json').read_text())
    mapping = strict_json((ROOT / f'{rater}_map_private.json').read_text())
    submission = strict_json(path.read_text())
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key((ROOT / 'label_decryption_key_private.pem').read_bytes(), password=None)
    result = ingest_submission(submission, form=form, private_items=mapping,
        evidence_pool=form['sources'], private_key=key, phase='development')
    assert len(result['labels']) == 16 and len(result['sealed_items']) == 24
    intake_root = ROOT / 'human_intake'
    intake_root.mkdir(exist_ok=True)
    # One frozen first submission per slot. Corrections need a disclosed new
    # protocol record, not silent replacement of observed labels.
    out = intake_root / rater
    out.mkdir(exist_ok=False)
    (out / 'sealed_submission.json').write_bytes(path.read_bytes())
    (out / 'development_labels_private.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    receipt = dict(status='DEVELOPMENT_ONLY_HUMAN_LABELS_RECEIVED', rater_slot=rater,
        packet_identity=form['packet_identity'], form_identity=form['form_identity'],
        reviewer_identity=result['reviewer_identity'], reviewer_kind=result['reviewer_kind'],
        development_items=16, sealed_validation_items=24, validation_labels_decrypted=0,
        submission_sha256=sha256_file(out / 'sealed_submission.json'),
        development_labels_sha256=sha256_file(out / 'development_labels_private.json'),
        human_review_is_not_scorer_qualification=True, reward_qualified=False)
    (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('submission', type=Path)
    parser.add_argument('--rater', choices=['rater_1', 'rater_2'], required=True)
    args = parser.parse_args()
    main(args.submission, args.rater)

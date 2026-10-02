#!/usr/bin/env python3
"""Validate and preserve a returned independent review; never rewrite its source."""
import argparse
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.review import read_unique_json,validate_submission
OUT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('submission',type=Path);args=parser.parse_args()
    source=OUT/'independent_review_UNSCORED.json';raw=read_unique_json(args.submission)
    result=validate_submission(raw,exam=read_unique_json(source),source_sha256=sha256_file(source))
    folder=OUT/'independent_submissions'/sha256_file(args.submission);folder.mkdir(parents=True,exist_ok=True)
    for name,text in [('original.json',args.submission.read_text()),('validated.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')]:
        path=folder/name
        if path.exists() and path.read_text()!=text:raise RuntimeError('existing submission changed')
        path.write_text(text)
    print(json.dumps(dict(saved=str(folder),completed=result['complete_items'],reviewer_kind=result['reviewer_kind'],
        uncertainty_explanation_gaps=result['unresolved_uncertainty_explanations']),ensure_ascii=False))


if __name__=='__main__':main()

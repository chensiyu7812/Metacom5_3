#!/usr/bin/env python3
"""Freeze eight concrete extractive Writer prompts; CPU tokenization, no execution."""
import argparse
import json
from pathlib import Path

from metacom_pm.rl1v3.journal.representations import prepare_writer_request
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--representations', type=Path, required=True)
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
registry = S.load(a.root / 'project/outputs/pm_rl1/v3/A1_preparation/final/registry')
tokenizer = PromptTokenizer(NativeTokenizer(
    '/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3',
    a.root / 'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json'))
baseline = json.loads(a.baseline.read_text())
plan = prepare_writer_request(registry=registry, representations_dir=a.representations,
    tokenizer=tokenizer, baseline=baseline, out=a.out)
print(json.dumps(plan, ensure_ascii=False, indent=2))

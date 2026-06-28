#!/usr/bin/env python3
"""Install the pinned official ESConv JSON from a local project or GitHub.

A local source is preferred when the dataset is already present in the user's
project.  The file is copied into the release tree, validated structurally, and
hashed.  No split or evaluation result is read during this step.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import urllib.request

from metacom_pm.strategy_bank import load_esconv

ROOT = Path(__file__).resolve().parents[1]
PINNED_COMMIT = 'f262d062ad74cb39b17ea476facc81568ddcba24'
URL = f'https://raw.githubusercontent.com/thu-coai/Emotional-Support-Conversation/{PINNED_COMMIT}/ESConv.json'

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, help='Local official ESConv.json; preferred when already available')
parser.add_argument('--out', type=Path, default=ROOT / 'data/external/ESConv.json')
parser.add_argument('--expected-sha256', help='Optional expected SHA256 for the local or downloaded file')
parser.add_argument('--overwrite', action='store_true')
args = parser.parse_args()

if args.out.exists() and not args.overwrite:
    raise FileExistsError(f'{args.out} already exists; use --overwrite after preserving the previous file')
args.out.parent.mkdir(parents=True, exist_ok=True)

if args.source is not None:
    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    data = source.read_bytes()
    source_mode = 'local_copy'
    source_description = str(source)
else:
    with urllib.request.urlopen(URL, timeout=120) as response:
        data = response.read()
    source_mode = 'pinned_github_download'
    source_description = URL

actual_sha = hashlib.sha256(data).hexdigest()
if args.expected_sha256 and actual_sha.lower() != args.expected_sha256.lower():
    raise RuntimeError(f'ESConv SHA256 mismatch: expected {args.expected_sha256}, got {actual_sha}')

tmp = args.out.with_suffix(args.out.suffix + '.tmp')
tmp.write_bytes(data)
# Structural validation before replacing the target.
dialogues = load_esconv(tmp)
shutil.move(str(tmp), str(args.out))

provenance = {
    'path': str(args.out),
    'bytes': len(data),
    'sha256': actual_sha,
    'n_dialogues': len(dialogues),
    'source_mode': source_mode,
    'source_description': source_description,
    'pinned_reference_commit': PINNED_COMMIT,
}
provenance_path = args.out.with_suffix('.provenance.json')
provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
print(provenance)

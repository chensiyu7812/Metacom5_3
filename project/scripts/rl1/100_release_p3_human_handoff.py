#!/usr/bin/env python3
"""Release dated source display; preserve the original frozen packet bytes."""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P3/calibration'


def main():
    freeze = json.loads((ROOT / 'packet_freeze.json').read_text())
    for name, sha in freeze['files'].items():
        assert sha256_file(ROOT / name) == sha, name
    for name, sha in freeze['human_forms'].items():
        assert sha256_file(ROOT / 'human_handoff' / name) == sha, name
    supplement = PROJECT / 'src/metacom_pm/rl1/calibration_form_chronology.js'
    out = ROOT / 'human_handoff_v2'
    out.mkdir(exist_ok=False)
    for rater in ('rater_1', 'rater_2'):
        html = (ROOT / 'human_handoff' / (rater + '.html')).read_text()
        html = html.replace('</html>', '<script>\n' + supplement.read_text() + '\n</script></html>')
        (out / (rater + '.html')).write_text(html)
    receipt = dict(status='SOURCE_DATE_DISPLAY_RELEASE_NO_ITEM_OR_LABEL_CHANGES',
        packet_identity=freeze['packet_identity'], original_packet_freeze_sha256=sha256_file(ROOT / 'packet_freeze.json'),
        files={p.name: sha256_file(p) for p in out.glob('*.html')},
        source_files={str(p.relative_to(PROJECT)):sha256_file(p) for p in (Path(__file__), supplement)},
        human_labels_received=0, validation_labels_decrypted=0)
    (out / 'release.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

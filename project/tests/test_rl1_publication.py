"""Public evidence and reader entry points must work in a clean checkout."""
from hashlib import sha256
import json
from pathlib import Path
import re

PROJECT=Path(__file__).resolve().parents[1]
PUBLIC=PROJECT/'docs/reviews/20260930/pm_rl1'

def test_published_evidence_matches_the_manifest_and_stays_under_public_root():
    manifest=json.loads((PUBLIC/'MANIFEST.json').read_text())
    assert manifest['new_experiments']==0
    assert len(manifest['files'])==len({r['path'] for r in manifest['files']})
    for row in manifest['files']:
        path=(PUBLIC/row['path']).resolve()
        assert path.is_relative_to(PUBLIC.resolve())
        assert sha256(path.read_bytes()).hexdigest()==row['published_sha256']

def test_public_notebook_has_no_machine_specific_executable_paths():
    notebook=json.loads((PUBLIC/'dataset_diagnostics_20260930_v1/dataset_diagnostics.ipynb').read_text())
    cells=[c for c in notebook['cells'] if c['cell_type']=='code']
    assert len(cells)==5
    for cell in cells:
        code=''.join(cell['source'])
        assert '/home/tokkio' not in code and '/opt/tokkio-data0' not in code
        assert cell['execution_count'] is not None

def test_current_progress_index_links_resolve():
    index=PROJECT/'docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md'
    for target in re.findall(r'\]\(([^)]+)\)',index.read_text()):
        if not target.startswith(('https://','http://','#')):
            assert (index.parent/target).is_file(),target

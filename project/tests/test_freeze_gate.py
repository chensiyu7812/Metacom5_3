from pathlib import Path
import shutil
import pytest

from metacom_pm.freeze import create_study_freeze, require_study_freeze, verify_study_freeze


def _make_root(root: Path) -> tuple[Path, Path, Path, Path]:
    (root / 'src/pkg').mkdir(parents=True)
    (root / 'scripts').mkdir()
    (root / 'docs').mkdir()
    (root / 'configs').mkdir()
    (root / 'outputs').mkdir()
    (root / 'data').mkdir()
    (root / 'src/pkg/x.py').write_text('VALUE=1\n')
    (root / 'scripts/x.py').write_text('print(1)\n')
    (root / 'docs/STUDY_PROTOCOL_CN.md').write_text('frozen protocol\n')
    (root / 'pyproject.toml').write_text('[project]\nname="x"\nversion="0"\n')
    config = root / 'configs/experiment.yaml'; config.write_text('model: x\n')
    checkpoint = root / 'outputs/model.joblib'; checkpoint.write_bytes(b'model')
    data = root / 'data/data.json'; data.write_text('{}\n')
    prompt = root / 'src/pkg/prompt.py'; prompt.write_text('PROMPT="x"\n')
    return config, checkpoint, data, prompt


def test_freeze_is_relocatable_and_fail_closed(tmp_path):
    root = tmp_path / 'release'
    config, checkpoint, data, prompt = _make_root(root)
    freeze = root / 'outputs/study_freeze.json'
    create_study_freeze(
        release_root=root,
        config_path=config,
        checkpoint_paths=[checkpoint],
        data_paths=[data],
        prompt_files=[prompt],
        out_path=freeze,
    )
    assert verify_study_freeze(freeze, release_root=root)['ok']

    moved = tmp_path / 'moved_release'
    shutil.copytree(root, moved)
    assert verify_study_freeze(moved / 'outputs/study_freeze.json', release_root=moved)['ok']

    (moved / 'data/data.json').write_text('{"changed": true}\n')
    result = verify_study_freeze(moved / 'outputs/study_freeze.json', release_root=moved)
    assert not result['ok']
    with pytest.raises(RuntimeError):
        require_study_freeze(moved / 'outputs/study_freeze.json', release_root=moved)


def test_missing_freeze_requires_explicit_debug_override(tmp_path):
    with pytest.raises(RuntimeError):
        require_study_freeze(tmp_path / 'missing.json', release_root=tmp_path)
    result = require_study_freeze(
        tmp_path / 'missing.json', release_root=tmp_path, allow_unfrozen_debug=True
    )
    assert result['debug_unfrozen'] is True

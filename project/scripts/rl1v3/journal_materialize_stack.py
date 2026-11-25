"""Build a private, pinned A/B/G source overlay without merging any branch."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BASE = 'b07db1046c948a77643a646bb845a21e74c10044'
DEPENDENCIES = {
    'A': 'df21b11c96165c1a3dd8ef0edf76df2788ee3e45',
    'B': '7eeff1cf8dcd889e4a08e9a2a723dbe3f864e118',
    'G': '73fdb12f29b6970a268eeda704d73e1bd35b1c3e',
}


def materialize(repo, output):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    prefix = 'project/src/metacom_pm/'
    paths = git('ls-tree', '-r', '--name-only', BASE, '--', prefix).decode().splitlines()
    selected = {p: ('base', BASE) for p in paths if p.endswith('.py')}
    changes = {}
    for stream, revision in DEPENDENCIES.items():
        changed = git('diff', '--name-only', BASE, revision, '--', prefix+'rl1v3').decode().splitlines()
        changes[stream] = changed
        for path in changed:
            if path in ('project/src/metacom_pm/rl1v3/contracts.py', 'project/src/metacom_pm/rl1v3/io.py'):
                raise ValueError('frozen C0 change')
            if path in selected and selected[path][0] != 'base':
                raise ValueError('unresolved cross-stream collision: '+path)
            selected[path] = (stream, revision)
    records = []
    for path, (stream, revision) in sorted(selected.items()):
        data = git('show', revision+':'+path)
        target = output/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append(dict(path=path, stream=stream, revision=revision,
                            sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
    journal = repo/prefix/'rl1v3/journal'
    journal.mkdir(parents=True, exist_ok=True)
    (output/prefix/'rl1v3/journal').symlink_to(journal, target_is_directory=True)
    manifest = dict(protocol='pmrl1-j-private-stack-v1', base=BASE, dependencies=DEPENDENCIES,
                    automatic_merge=False, history_modified=False, journal_source=str(journal),
                    journal_code_frozen_separately=True, files=records, changed_paths=changes)
    (output/'DEPENDENCY_MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return dict(output=str(output), files=len(records), c0_unchanged=True, dependencies=DEPENDENCIES)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--repo', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    print(json.dumps(materialize(args.repo, args.output), indent=2))

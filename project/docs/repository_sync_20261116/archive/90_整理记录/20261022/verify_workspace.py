#!/usr/bin/env python3
"""Read-only verification of the archived payloads, paths and preserved source."""
from pathlib import Path
if __name__ == "__main__" and Path('/home/tokkio/成果归档/整理记录/20261022_完整归档/move_verification.json').exists():
    raise SystemExit("第一轮脚本已被完整归档取代；请使用 /home/tokkio/成果归档/整理记录/20261022_完整归档/archive_home.py 或阅读该目录README.md。")

import csv, hashlib, json, os, re, runpy, subprocess

REC=Path(__file__).resolve().parent
HUB=REC.parents[1]
REPO=Path('/home/tokkio/Metacom5_3').resolve()

def main():
    helper=runpy.run_path(str(REC/'organize_workspace.py'))
    rows=json.loads((REC/'moves.json').read_text())
    before=json.loads((REC/'content_before.json').read_text())
    errors=[]
    for row in rows:
        old,new=Path(row['source']),Path(row['destination'])
        if helper['tree'](new)!=before[str(old)]:errors.append('Changed archived content/metadata: '+str(new))
        if row['keep_compatibility_link'] and (not old.is_symlink() or old.resolve()!=new.resolve()):errors.append('Compatibility link: '+str(old))
    protected=json.loads((REC/'protected_files_before.json').read_text())
    changed=[]
    for rel,expected in protected.items():
        p=REPO/rel
        if not p.is_file():errors.append('Missing protected file: '+rel)
        elif helper['digest'](p)!=expected:changed.append(rel)
    if changed!=['README.md']:errors.append('Unexpected existing source changes: '+repr(changed))
    links=json.loads((REC/'new_navigation_links.json').read_text())
    for source,target in links.items():
        p=Path(source)
        if not p.is_symlink() or p.resolve()!=Path(target).resolve() or not p.exists():errors.append('Navigation symlink: '+source)
    docs=[REPO/'README.md',Path('/home/tokkio/PM_RL1_CURRENT_ENTRY_20261021.md'),HUB/'README.md',HUB/'00_研究全景.md',HUB/'00_证据时间线.md',HUB/'00_归档文件索引.md',HUB/'01_当前研究/README.md']
    docs+=list((REPO/'project/docs/pm_rl1_workspace_20261022').glob('*ZH.md'))
    checked=0
    for f in docs:
        for target in re.findall(r'\]\(([^)]+)\)',f.read_text()):
            if target.startswith(('http:','https:','#')):continue
            path=target.split('#')[0];p=Path(path) if path.startswith('/') else f.parent/path
            checked+=1
            if not p.exists():errors.append('Missing document link: '+str(f)+' -> '+target)
    prior=json.loads((REC/'archived_link_review.json').read_text())
    for row in prior['newly_unresolved']:
        if not Path(row['new_resolved']).exists():errors.append('Archive link regression: '+row['new_resolved'])
    # Verify embedded source checksums by location, without querying the provider.
    sha_files=0
    for p in HUB.glob('02_阶段交付/*/*.sha256'):
        expected,name=p.read_text().strip().split(maxsplit=1)
        if helper['digest'](p.parent/name.strip())!=expected:errors.append('ZIP SHA file: '+str(p))
        sha_files+=1
    baseline=json.loads((REC/'git_before.json').read_text())
    head=subprocess.run(['git','-C',str(REPO),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout
    if head!=baseline['head']:errors.append('Repository HEAD changed')
    current=json.loads((REPO/'project/docs/pm_rl1_completion_20260930_v2/current_execution_order_20261021.json').read_text())
    latest=json.loads((REPO/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/score_audit_strict_results_20261022_v1/CLOSEOUT.json').read_text())
    if (current['actual_cumulative'],current['active_capacity'])!=(latest['cumulative'],latest['active_capacity']):errors.append('Research status sources disagree')
    result={'status':'PASS' if not errors else 'FAIL','moved_items':len(rows),
        'regular_files_verified':sum(len(v) for v in before.values()),
        'compatibility_links':sum(r['keep_compatibility_link'] for r in rows),
        'removed_old_home_entries':sum(not r['keep_compatibility_link'] for r in rows),
        'protected_files_checked':len(protected),'only_existing_protected_change':changed,
        'new_navigation_symlinks_checked':len(links),'new_markdown_links_checked':checked,
        'archived_links_reviewed':prior['links_checked'],'archive_link_regressions_resolved':len(prior['newly_unresolved']),
        'supplied_zip_checksum_files_verified':sha_files,'head_unchanged':head==baseline['head'],
        'current_judge_trial_attempts':latest['cumulative'],'natural_rl_updates':latest['natural_updates'],
        'errors':errors,'verification_scope':'Local paths, bytes, metadata, protected files and existing status; no new model calls, semantic relabeling or training.'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return bool(errors)

if __name__=='__main__':raise SystemExit(main())

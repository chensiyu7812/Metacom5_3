#!/usr/bin/env python3
"""Local, reversible archive of researcher-owned HOME deliveries. No model/API work."""
from pathlib import Path
if __name__ == "__main__" and Path('/home/tokkio/成果归档/整理记录/20261022_完整归档/move_verification.json').exists():
    raise SystemExit("第一轮脚本已被完整归档取代；请使用 /home/tokkio/成果归档/整理记录/20261022_完整归档/archive_home.py 或阅读该目录README.md。")

import argparse, collections, csv, hashlib, json, os, re, shutil, subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

HOME = Path('/home/tokkio')
HUB = HOME / 'PM-RL1'
REPO = (HOME / 'Metacom5_3').resolve()
RECORD = HUB / '90_整理记录/20261022'
OLD_PREFIXES = ('Gemini裁判', 'paper1_', '人评', '六题', '下一步_', '后续研究',
                '研究记录与', '裁判', '校准', '本地裁判', '待审批_Gemini', '对接手Codex', 'Codex接手', 'AI_B_')
PRIVATE_NAMES = {'researcher.html', 'ANNOTATION_PACKET.zip'}

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def write_json(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    tmp.replace(p)

def tree(p):
    rows = []
    def add(f, rel):
        st = f.lstat()
        rows.append({'relative': rel, 'kind': 'symlink' if f.is_symlink() else 'file',
                     'bytes': st.st_size, 'mode': st.st_mode & 0o7777, 'mtime_ns': st.st_mtime_ns,
                     'sha256': None if f.is_symlink() else digest(f),
                     'link': os.readlink(f) if f.is_symlink() else None})
    if not p.is_dir() or p.is_symlink(): add(p, '.')
    else:
        for d, ds, fs in os.walk(p, followlinks=False):
            for n in list(ds):
                q = Path(d)/n
                if q.is_symlink(): add(q, str(q.relative_to(p))); ds.remove(n)
            for n in sorted(fs):
                q = Path(d)/n; add(q, str(q.relative_to(p)))
    return sorted(rows, key=lambda x:x['relative'])

def dated(p):
    m = re.search(r'(2026)[-_]?([01]\d)[-_]?([0-3]\d)', p.name)
    return '-'.join(m.groups()) if m else datetime.fromtimestamp(p.stat().st_mtime, ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d')

def candidates():
    out = []
    for p in sorted(HOME.iterdir()):
        n = p.name
        if p.is_symlink() or n == 'PM_RL1_CURRENT_ENTRY_20261021.md': continue
        if n.startswith(('PM_RL1', 'PMRL1')):
            category = '03_历史方案与说明' if p.suffix in {'.md','.txt'} else '02_阶段交付'
            if n.startswith('PMRL1') or any(s in n for s in ['标注导出包','标注可读','40对人工','独立盲评']): category = '04_人评原件'
        elif n in PRIVATE_NAMES: category = '04_人评原件'
        elif n.startswith(OLD_PREFIXES): category = '05_Paper-1前序资料'
        else: continue
        out.append((p,HUB/category/dated(p)/n))
    return out

def references(names):
    # Match basenames too: many runners construct HOME / name instead of a literal absolute path.
    pattern = re.compile('|'.join(re.escape(n) for n in sorted(names,key=len,reverse=True)))
    found = collections.defaultdict(set)
    for root in [REPO/'project/src',REPO/'project/scripts',REPO/'project/docs',REPO/'project/tests',REPO/'project/configs']:
        for d,ds,fs in os.walk(root):
            ds[:] = [n for n in ds if n not in {'__pycache__','history','reviews','.git'}]
            for n in fs:
                p=Path(d)/n
                if p.suffix not in {'.py','.md','.json','.yaml','.yml','.txt','.html'} or p.stat().st_size>3_000_000: continue
                try: text=p.read_text()
                except (OSError,UnicodeError): continue
                for hit in set(pattern.findall(text)): found[hit].add(str(p.relative_to(REPO)))
    return {k: sorted(v) for k,v in found.items()}

def git(args):
    r=subprocess.run(['git','-C',str(REPO),*args],capture_output=True,text=True,check=True)
    return r.stdout

def plan():
    if (RECORD/'moves.json').exists(): raise RuntimeError('Existing operation log; refusing a second organization run.')
    pairs=candidates(); refs=references([p.name for p,_ in pairs])
    rows=[]
    for src,dst in pairs:
        if dst.exists() or dst.is_symlink(): raise RuntimeError('Destination exists: '+str(dst))
        rows.append({'source':str(src),'destination':str(dst),'keep_compatibility_link':src.is_dir() or src.name in refs,
                     'reference_files':refs.get(src.name,[]),'kind':'directory' if src.is_dir() else 'file', 'date':dated(src)})
    write_json(RECORD/'plan.json',rows)
    return rows

def apply():
    rows=plan()
    os.chmod(HUB,0o700)
    write_json(RECORD/'home_before.json',[{'name':p.name,'kind':'symlink' if p.is_symlink() else 'directory' if p.is_dir() else 'file',
       'bytes':p.lstat().st_size,'target':os.readlink(p) if p.is_symlink() else None} for p in sorted(HOME.iterdir())])
    write_json(RECORD/'git_before.json',{'head':git(['rev-parse','HEAD']),'branch':git(['branch','--show-current']),
       'status':git(['status','--porcelain=v1','--untracked-files=all'])})
    (RECORD/'git_before.patch').write_text(git(['diff','--binary']))
    protected={}
    for root in ['project/src','project/scripts','project/tests','project/configs','project/docs','AGENTS.md','README.md']:
        q=REPO/root
        files=[q] if q.is_file() else [p for p in q.rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts]
        for p in files: protected[str(p.relative_to(REPO))]=digest(p)
    ledger=REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    if ledger.exists():protected[str(ledger.relative_to(REPO))]=digest(ledger)
    write_json(RECORD/'protected_files_before.json',protected)
    for name,p in [('repository_README.before.md',REPO/'README.md'),('HOME_CURRENT_ENTRY.before.md',HOME/'PM_RL1_CURRENT_ENTRY_20261021.md')]:
        if p.exists():shutil.copy2(p,RECORD/name)
    before={row['source']:tree(Path(row['source'])) for row in rows}
    write_json(RECORD/'content_before.json',before)
    completed=[]
    for row in rows:
        src,dst=Path(row['source']),Path(row['destination'])
        if tree(src)!=before[str(src)]:raise RuntimeError('Source changed after snapshot: '+str(src))
        dst.parent.mkdir(parents=True,exist_ok=True)
        # Same HOME filesystem: rename preserves bytes, inode, permissions and timestamps.
        src.rename(dst)
        completed.append(row)
        write_json(RECORD/'moves.json',completed)
        if row['keep_compatibility_link']:src.symlink_to(os.path.relpath(dst,src.parent),target_is_directory=row['kind']=='directory')
    failures=[]
    for row in completed:
        dst=Path(row['destination']);src=Path(row['source'])
        if tree(dst)!=before[str(src)]:failures.append('content: '+str(dst))
        if row['keep_compatibility_link'] and (not src.is_symlink() or src.resolve()!=dst.resolve()):failures.append('alias: '+str(src))
    with (RECORD/'路径迁移清单.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['source','destination','kind','date','keep_compatibility_link']);w.writeheader()
        for row in rows:w.writerow({k:row[k] for k in w.fieldnames})
    report={'status':'PASS' if not failures else 'FAIL','moved_top_level_items':len(rows),
      'compatibility_links':sum(r['keep_compatibility_link'] for r in rows),
      'home_entries_removed':sum(not r['keep_compatibility_link'] for r in rows),
      'verified_files_and_internal_symlinks':sum(len(v) for v in before.values()),
      'verified_regular_files':sum(x['kind']=='file' for v in before.values() for x in v),
      'bytes':sum(x['bytes'] for v in before.values() for x in v if x['kind']=='file'),
      'failures':failures,'deleted_files':0,'experiments_started':0}
    write_json(RECORD/'move_verification.json',report)
    print(json.dumps(report,ensure_ascii=False))
    if failures:raise RuntimeError('Verification failed; see log.')

def rollback(execute):
    rows=json.loads((RECORD/'moves.json').read_text())
    before=json.loads((RECORD/'content_before.json').read_text())
    for row in rows:
        src,dst=Path(row['source']),Path(row['destination'])
        if not dst.exists():raise RuntimeError('Missing archive: '+str(dst))
        if tree(dst)!=before[str(src)]:raise RuntimeError('Archive changed; refusing automatic rollback: '+str(dst))
        if src.exists() or src.is_symlink():
            if not src.is_symlink() or src.resolve()!=dst.resolve():raise RuntimeError('Source occupied: '+str(src))
    if not execute:
        print('Verified rollback plan for',len(rows),'items. Add --execute to apply. Navigation additions are retained.');return
    done=[]
    for row in reversed(rows):
        src,dst=Path(row['source']),Path(row['destination'])
        if src.is_symlink():src.unlink()
        dst.rename(src);done.append(str(src));write_json(RECORD/'rollback_log.json',done)
    print('Restored',len(done),'original paths. Navigation and audit records retained.')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['plan','apply','rollback']);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    if a.action=='plan':print(json.dumps(plan(),ensure_ascii=False,indent=2))
    elif a.action=='apply':apply()
    else:rollback(a.execute)

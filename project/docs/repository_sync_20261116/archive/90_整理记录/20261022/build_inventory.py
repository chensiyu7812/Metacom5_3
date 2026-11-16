#!/usr/bin/env python3
"""Metadata-only directory catalogue and byte-level archive comparison."""
from pathlib import Path
import collections, csv, hashlib, json, os, zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

HOME=Path('/home/tokkio'); HUB=HOME/'PM-RL1'; REC=HUB/'90_整理记录/20261022'; REPO=(HOME/'Metacom5_3').resolve()

def dump(name, obj):
    (REC/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def csvout(name, rows, fields):
    with (REC/name).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def category(p):
    s=str(p)
    if '/outputs/pm_rl1/' in s:return 'PM-RL1原始实验（含历史阶段，不等同当前结果）'
    if '/src/metacom_pm/rl1/' in s or '/scripts/rl1/' in s or '/test_rl1_' in s:return 'PM-RL1实现'
    if '/docs/' in s and ('PM_RL1' in s or 'pm_rl1' in s):return 'PM-RL1方案/状态/证据'
    if '/data/' in s:return '数据/权威合同；仅目录元数据，未读取正文'
    if '/paper1/' in s or '/paper1_' in s or 'PM_PAPER1' in s:return 'Paper-1前序'
    return '共享或历史；不因文件存在而认定有效'

def main():
    rows=[]; exclusions=[]
    # Do not inspect deprecated synthetic data, sealed content, credentials or other users' homes.
    skip_names={'.git','__pycache__','.pytest_cache','.venv','node_modules','pytest-of-tokkio',
        'pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1','pm_v1_5_evo_style_synthetic_memory_v1_candidate',
        'pm_v1_5_formal_v8_19_2_runtime_projection_repair_candidate','synthetic'}
    for d,ds,fs in os.walk(REPO,followlinks=False):
        for n in list(ds):
            p=Path(d)/n
            if n in skip_names or p.is_symlink():
                exclusions.append({'path':str(p),'reason':'excluded metadata-only boundary' if not p.is_symlink() else 'symlink not followed'})
                ds.remove(n)
        for n in fs:
            p=Path(d)/n;st=p.lstat()
            rows.append({'path':str(p),'repository_relative':str(p.relative_to(REPO)),'kind':'symlink' if p.is_symlink() else 'file',
                'bytes':st.st_size,'modified_jst':datetime.fromtimestamp(st.st_mtime,ZoneInfo('Asia/Tokyo')).isoformat(),
                'classification':category(p),'link_target':os.readlink(p) if p.is_symlink() else ''})
    csvout('主仓库逐文件目录.csv',rows,list(rows[0]))
    dump('inventory_exclusions.json',exclusions)
    folder=collections.defaultdict(lambda:{'files':0,'bytes':0})
    for r in rows:
        rel=Path(r['repository_relative']);parts=rel.parts
        key='/'.join(parts[:3]) if len(parts)>=3 else str(rel.parent)
        folder[key]['files']+=1;folder[key]['bytes']+=r['bytes']
    csvout('主仓库目录统计.csv',[{'directory':k,**v} for k,v in sorted(folder.items())],['directory','files','bytes'])
    home=[]
    for p in sorted(HOME.iterdir()):
        n=p.name
        kind='symlink' if p.is_symlink() else 'directory' if p.is_dir() else 'file'
        if n.startswith('.'): role='用户环境/配置，仅登记名称；未读取内容'
        elif n=='PM-RL1':role='统一研究入口和归档'
        elif n=='Metacom5_3':role='主仓库原兼容入口'
        elif p.is_symlink() and 'PM-RL1/' in str(p.resolve()):role='本轮保留的兼容路径，实体已归档'
        elif n.startswith('chensiyu78120818'):role='旧PM v1仓库/关联Git工作树'
        elif n in {'audits','figure1','figure3','fig1_concept.png','excalidraw-check-20260908'}:role='旧论文审计/图稿，原地保留'
        elif n in {'models','base_model','miniconda3','nltk_data'}:role='模型/运行环境，原地保留'
        elif n in {'rag_project','new_rag','cns-info','helm-local-charts','helm-values'} or p.suffix in {'.yaml','.yml','.crt','.key'} or n in {'vms-vst_config.json','vst_config.json','metacom5_3.env'}:role='Tokkio/RAG部署或配置；非本轮研究交付，未读取秘密内容'
        elif n=='PM_RL1_CURRENT_ENTRY_20261021.md':role='旧文件名的当前入口，将转向统一入口'
        else:role='其他个人文件/系统标准目录，原地保留'
        home.append({'name':n,'kind':kind,'role':role,'link_target':os.readlink(p) if p.is_symlink() else ''})
    csvout('HOME顶层逐项清单.csv',home,list(home[0]))
    moves=json.loads((REC/'moves.json').read_text());comp=[]
    for move in moves:
        f=Path(move['destination'])
        if f.suffix!='.zip':continue
        directory=f.with_suffix('')
        row={'zip':str(f),'directory':str(directory),'status':'NO_ADJACENT_EXTRACTED_DIRECTORY'}
        if directory.is_dir():
            with zipfile.ZipFile(f) as z:
                infos=[i for i in z.infolist() if not i.is_dir()]
                names=[i.filename for i in infos]
                prefix=directory.name+'/'
                if not all(n.startswith(prefix) for n in names):prefix=''
                matched=[];different=[];archive_only=[];listed=set()
                for i in infos:
                    rel=i.filename[len(prefix):];listed.add(rel);p=directory/rel
                    if '..' in Path(rel).parts or Path(rel).is_absolute():raise ValueError('Unsafe ZIP name')
                    if not p.is_file():archive_only.append(rel);continue
                    if i.flag_bits&1 or i.file_size>100_000_000:different.append(rel+' [not compared]');continue
                    if hashlib.sha256(z.read(i)).digest()==hashlib.sha256(p.read_bytes()).digest():matched.append(rel)
                    else:different.append(rel)
                disk={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and not p.is_symlink()}
                extra=sorted(disk-listed)
                row.update(status='BYTE_IDENTICAL_FILESET' if not different and not archive_only and not extra else 'DIFFERENT_SNAPSHOT',
                    matched=len(matched),changed=different,archive_only=archive_only,directory_only=extra)
        comp.append(row)
    dump('ZIP与解压目录对照.json',comp)
    duplicate=collections.defaultdict(list)
    before=json.loads((REC/'content_before.json').read_text())
    for src,items in before.items():
        if len(items)==1 and items[0]['relative']=='.':duplicate[items[0]['sha256']].append(src)
    exact=[{'sha256':k,'original_paths':v} for k,v in duplicate.items() if len(v)>1]
    dump('顶层文件完全重复组.json',exact)
    report={'repository_files_listed':len(rows),'repository_listed_bytes':sum(r['bytes'] for r in rows),
            'home_entries':len(home),'zip_status_counts':dict(collections.Counter(r['status'] for r in comp)),
            'top_level_duplicate_groups':len(exact),'exclusions':len(exclusions),'data_content_read':False}
    dump('inventory_summary.json',report);print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()

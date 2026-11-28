"""Pinned public-source intake, deterministic selection, source-coordinate audit.

This preparation program is evaluation-side. Only exported runtime files may
be mounted into the agent. Benchmark labels are never downloaded or opened.
"""
import ast
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import time
import urllib.request

from .contracts import RuntimeTask, digest, text_hash
from .history import HistoryResolver

REVISION = "ed956dea41521fc4499acbc63f966e0fd3c053ba"
UPSTREAM_COMMIT = "d29d91d016add354e459dfeb0d24af08bc402e2a"
SEED = 20261127
STRATA = ("pref_type", "who", "updated", "sensitive_info")


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True)+"\n")


def fetch(source_root, ref):
    if ref not in {"README.md", "column_descriptions.md", "benchmark/text/train.csv", "benchmark/text/val.csv"} and not ref.startswith("data/chat_history_32k/"):
        raise ValueError("source outside approved text train/val/32k scope")
    if ".." in ref.split("/"):
        raise ValueError("invalid source path")
    path = Path(source_root)/ref
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        url = f"https://huggingface.co/datasets/bowen-upenn/PersonaMem-v2/resolve/{REVISION}/{ref}"
        temporary = path.with_suffix(path.suffix+".partial")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=90) as response, temporary.open("wb") as out:
                    while chunk := response.read(1024*1024):
                        out.write(chunk)
                temporary.replace(path)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt+1)
    return {"path":ref,"bytes":path.stat().st_size,"sha256":sha_file(path),"revision":REVISION}


def load_rows(root, split):
    if split not in {"train", "val"}:
        raise ValueError("formal test closed")
    with (Path(root)/f"benchmark/text/{split}.csv").open() as f:
        rows = list(csv.DictReader(f))
    return rows


def parse_literal(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return ast.literal_eval(text)


def census(rows):
    keys = list(rows[0])
    return {"rows":len(rows), "personas":len({r['persona_id'] for r in rows}),
            "history_families":len({r['chat_history_32k_link'] for r in rows}),
            "exact_duplicate_rows":len(rows)-len({digest(r) for r in rows}),
            "duplicate_persona_query":len(rows)-len({(r['persona_id'],r['user_query']) for r in rows}),
            "normalized_duplicate_persona_query":len(rows)-len({(r['persona_id'], ' '.join(r['user_query'].lower().split())) for r in rows}),
            "missing":{k:sum(r[k].strip() in {'','null','None','nan'} for r in rows) for k in keys},
            "counts":{k:dict(Counter(r[k] for r in rows)) for k in (*STRATA,'conversation_scenario')},
            "rows_per_persona_histogram":dict(Counter(Counter(r['persona_id'] for r in rows).values())),
            "strata":{"|".join(k):v for k,v in Counter(tuple(r[x] for x in STRATA) for r in rows).items()}}


def representative(rows, candidates, count, rng):
    groups = defaultdict(list)
    for i in candidates:
        groups[tuple(rows[i][k] for k in STRATA)].append(i)
    exact = {key:len(ids)*count/len(candidates) for key,ids in groups.items()}
    quota = {key:int(n) for key,n in exact.items()}
    for key in sorted(groups, key=lambda k:(-(exact[k]-quota[k]),k))[:count-sum(quota.values())]:
        quota[key] += 1
    selected, owners = [], Counter()
    for key in sorted(groups):
        ids = groups[key][:]
        rng.shuffle(ids)
        for _ in range(quota[key]):
            i = min(ids, key=lambda i:owners[rows[i]['persona_id']])
            ids.remove(i); selected.append(i); owners[rows[i]['persona_id']] += 1
    return selected


def select(val, train):
    rng = random.Random(SEED)
    rep = representative(val, list(range(len(val))), 180, rng)
    used = set(rep); owners = Counter(val[i]['persona_id'] for i in rep)
    hard, labels = [], {}
    # Actual updated rows equal ask_to_forget in this revision. Do not invent an
    # independent preference-change or explicit/implicit label.
    predicates = [
        ('forget_updated',lambda r:r['pref_type']=='ask_to_forget'),
        ('third_party',lambda r:r['who']=='others'),
        ('sensitive',lambda r:r['sensitive_info']=='True'),
        ('implicit_scenario_proxy',lambda r:r['conversation_scenario'] in {'personal_email','professional_email','creative_writing','translation','chat_message'})]
    for label, predicate in predicates:
        ids = [i for i,r in enumerate(val) if i not in used and predicate(r)]
        rng.shuffle(ids)
        if len(ids) < 15:
            raise ValueError('insufficient real difficulty stratum')
        for _ in range(15):
            i=min(ids,key=lambda i:owners[val[i]['persona_id']]);ids.remove(i)
            hard.append(i);used.add(i);owners[val[i]['persona_id']]+=1;labels[i]=label
    # Open generation is disjoint both by row and persona from MCQ.
    gen_pool = [i for i,r in enumerate(val) if i not in used and r['persona_id'] not in owners]
    gen = representative(val, gen_pool, 60, rng)
    reserved = {val[i]['persona_id'] for i in rep+hard+gen}
    train_groups = defaultdict(list)
    for i,r in enumerate(train):
        if r['persona_id'] not in reserved:
            train_groups[r['persona_id']].append(i)
    groups = sorted(train_groups);rng.shuffle(groups)
    candidates=[]
    for owner in groups:
        candidates.extend(train_groups[owner])
        if len(candidates) >= 4000:
            break
    candidates=candidates[:4000]
    if len(candidates)!=4000:
        raise ValueError('insufficient persona-disjoint training candidates')
    return {'representative':rep,'hard':hard,'hard_labels':labels,'generation':gen,'train':candidates}


def load_history(path, owner):
    obj=json.loads(Path(path).read_text())
    if str(obj['metadata']['persona_id']) != str(owner):
        raise ValueError('history owner mismatch')
    messages=obj['chat_history']
    if obj['metadata']['total_messages'] != len(messages):
        raise ValueError('history length metadata mismatch')
    for msg in messages:
        if not {'role','content'} <= set(msg) or msg['role'] not in {'user','assistant','system'} or not isinstance(msg['content'],str):
            raise ValueError('invalid text history')
    # Some official text histories contain stray JSON keys. Preserve raw files
    # and their hashes, export the exact role/content only, and census this.
    return [{'role':m['role'],'content':m['content']} for m in messages]


def match_snippet(snippet, records):
    # Complete contiguous matching, including speaker. No gold/preference/text
    # substitution; no fuzzy semantic matches promoted to verified evidence.
    if not isinstance(snippet,list) or not snippet:
        return 'missing',[]
    target=[(m['role'],m['content']) for m in snippet]
    source=[(r.speaker,r.original_text) for r in records]
    starts=[i for i in range(len(source)-len(target)+1) if source[i:i+len(target)]==target]
    if len(starts)!=1:
        return ('ambiguous' if starts else 'missing'),[]
    span=records[starts[0]:starts[0]+len(target)]
    return 'located_unique',[{'source_id':r.source_id,'original_text_sha256':r.original_text_sha256,'coordinates':r.coordinates} for r in span]


def prepare(source_root, output_root):
    from ..evaluation.contracts import EvalTask
    from ..evaluation.mcq import make_options
    source_root, out=Path(source_root),Path(output_root)
    if (out/'FREEZE.json').exists():
        raise FileExistsError('frozen artifacts exist; use a new output version')
    os.umask(0o077)
    sources=[fetch(source_root,f) for f in ['README.md','column_descriptions.md','benchmark/text/train.csv','benchmark/text/val.csv']]
    train,val=load_rows(source_root,'train'),load_rows(source_root,'val')
    selection=select(val,train)
    runtime=out/'runtime';evaluation=out/'evaluation';training=out/'training';direct=out/'direct'
    for p in [runtime,evaluation,training,direct]:p.mkdir(parents=True,exist_ok=True)
    write_json(evaluation/'selection.json',selection)
    chosen=[('val',i,val[i]) for i in selection['representative']+selection['hard']+selection['generation']]+[('train',i,train[i]) for i in selection['train']]
    refs=sorted({r['chat_history_32k_link'] for _,_,r in chosen})
    with ThreadPoolExecutor(max_workers=8) as pool:
        sources.extend(pool.map(lambda ref:fetch(source_root,ref),refs))
    history_info={};history_stats=[]
    for ref in refs:
        row=next(r for _,_,r in chosen if r['chat_history_32k_link']==ref)
        messages=load_history(source_root/ref,row['persona_id'])
        family='pm2-'+text_hash(ref)[:20]
        name=f'histories/{family}.json'
        is_val=any(s=='val' and r['chat_history_32k_link']==ref for s,_,r in chosen)
        dest=runtime if is_val else training/'runtime'
        write_json(dest/name,{'owner_id':f"pm2:{row['persona_id']}",'source_family':family,'messages':messages})
        history_info[ref]=(name,sha_file(dest/name),len(messages),family,dest)
        raw_messages=json.loads((source_root/ref).read_text())['chat_history']
        history_stats.append({'messages':len(messages),'roles':dict(Counter(m['role'] for m in messages)),
                              'extra_key_messages':sum(set(m)!={'role','content'} for m in raw_messages),
                              'content_sha256':digest(messages),'source_sha256':sha_file(source_root/ref),'runtime_sha256':sha_file(dest/name)})
    runtime_rows={'mcq':[],'generation':[],'train':[]};eval_rows={'mcq':[],'generation':[],'train':[]};direct_rows=[]
    for split,index,row in chosen:
        mode='generation' if split=='train' or index in selection['generation'] else 'mcq'
        group='train' if split=='train' else mode
        query=parse_literal(row['user_query'])
        if set(query)!={'role','content'} or query['role']!='user':raise ValueError('invalid query')
        options,gold=make_options(row['correct_answer'],json.loads(row['incorrect_answers']),SEED+index)
        name,sha,cutoff,family,dest=history_info[row['chat_history_32k_link']]
        task=RuntimeTask(task_id=f'pm2-{split}-{index:05d}-{mode}',dataset_revision=REVISION,split=split,
                         persona_group=f"pm2:{row['persona_id']}",source_family=family,history_ref=name,
                         history_sha256=sha,cutoff=cutoff,current_messages=[],user_query=query['content'],
                         task_mode=mode,options=options if mode=='mcq' else [])
        # Train candidates are provenance/input manifests, not training targets.
        runtime_rows[group].append(task.to_dict())
        snippet=parse_literal(row['related_conversation_snippet'])
        status,spans=match_snippet(snippet,HistoryResolver(dest).resolve(task))
        if split=='train':
            eval_rows[group].append({'task_id':task.task_id,'source_row':index,'persona_group':task.persona_group,
                                     'direct_status':status,'verified_spans':spans,'target_materialized':False})
        else:
            category={k:row[k] for k in (*STRATA,'conversation_scenario')}
            category['selection_layer']='generation' if mode=='generation' else ('representative' if index in selection['representative'] else selection['hard_labels'][index])
            ev=EvalTask(task.task_id,gold if mode=='mcq' else None,row['correct_answer'],row['preference'],snippet,category,spans,status)
            eval_rows[group].append(ev.to_dict())
            direct_rows.append({'task_id':task.task_id,'status':status,'spans':spans,'allowed_arms':['C','D'],
                                'diagnostic_only':True,'sufficiency':'unverified; exact source location is not sufficiency'})
    for group in ['mcq','generation']:
        write_jsonl(runtime/f'tasks.{group}.jsonl',runtime_rows[group])
        write_jsonl(evaluation/f'tasks.{group}.jsonl',eval_rows[group])
    write_jsonl(direct/'direct.jsonl',direct_rows)
    write_jsonl(training/'runtime/tasks.jsonl',runtime_rows['train'])
    write_jsonl(training/'candidate_provenance.jsonl',eval_rows['train'])
    counts={k:{'tasks':len(v),'personas':len({r['persona_group'] for r in v})} for k,v in runtime_rows.items()}
    report={'revision':REVISION,'upstream_commit':UPSTREAM_COMMIT,'seed':SEED,'train':census(train),'val':census(val),
            'train_val_persona_overlap':len({r['persona_id'] for r in train}&{r['persona_id'] for r in val}),
            'train_val_history_overlap':len({r['chat_history_32k_link'] for r in train}&{r['chat_history_32k_link'] for r in val}),
            'train_val_exact_row_overlap':len({digest(r) for r in train}&{digest(r) for r in val}),
            'selected':counts,'selected_train_dev_persona_overlap':len({r['persona_group'] for r in runtime_rows['train']}&{r['persona_group'] for r in runtime_rows['mcq']+runtime_rows['generation']}),
            'direct':{k:dict(Counter(x['direct_status'] for x in v)) for k,v in eval_rows.items()},
            'history_files_requested':len(refs),'history_files_parsed':len(history_stats),'history_messages':sum(h['messages'] for h in history_stats),
            'duplicate_history_content':len(history_stats)-len({h['content_sha256'] for h in history_stats}),
            'history_extra_key_messages':sum(h['extra_key_messages'] for h in history_stats),
            'test_labels_read':False,'benchmark_count_claim':5000,'benchmark_count_verified':False,
            'source_license':'CC-BY-4.0','official_root_code_license':'not found; independent implementation only',
            'model_calls':0,'paid_calls':0}
    write_json(out/'census.json',report);write_json(out/'source_manifest.json',sources)
    artifacts={str(p.relative_to(out)):sha_file(p) for p in sorted(out.rglob('*')) if p.is_file()}
    write_json(out/'FREEZE.json',{'schema':'naa-v1','seed':SEED,'revision':REVISION,'artifacts':artifacts,'model_results':False})
    return report

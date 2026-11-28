"""NAA v1.1 deterministic allocation; no model outcomes select new owners.

Only the explicitly retrospective C-error audit and old-protocol bridge consult
WP2 status/outcomes. All new confirmation and training splits use fixed hashes.
"""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil

from .contracts import RuntimeTask, digest, text_hash, load_runtime
from .history import HistoryResolver
from .personamem import (REVISION, load_rows, load_history, fetch, parse_literal,
                         sha_file, write_json, write_jsonl, match_snippet)
from ..evaluation.mcq import make_options
from ..evaluation.contracts import EvalTask

AUTHORITY = '65424fd807e5e14284b70a9a184288bf0ce7a95e'
SEED = 'naa-v11-20261128'


def new_history(path,owner):
    """Preserve an upstream missing assistant payload as an empty position.

    Never supply inferred content, shift coordinates, or replace the selected
    owner. Missing user payloads and all other malformed structures still fail.
    Raw source is untouched; normalization receipt is frozen separately.
    """
    raw=json.loads(Path(path).read_text());messages=raw['chat_history']
    if str(raw['metadata']['persona_id'])!=str(owner) or raw['metadata']['total_messages']!=len(messages):
        raise ValueError('upstream owner/length mismatch')
    gaps=[];normalized=[]
    for i,m in enumerate(messages):
        if m=={'role':'assistant'}:
            gaps.append(i);normalized.append(dict(role='assistant',content=''))
        elif m.get('role') in ('user','assistant','system') and isinstance(m.get('content'),str):
            normalized.append(dict(role=m['role'],content=m['content']))
        else:raise ValueError('unsupported malformed source history')
    return normalized,gaps


def ordered(values, purpose):
    return sorted(values, key=lambda v: (digest([SEED, purpose, v]), str(v)))


def jsonl(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def verify_old(root):
    for name, expected in json.loads((root/'FREEZE.json').read_text())['artifacts'].items():
        if sha_file(root/name) != expected:
            raise ValueError('old frozen artifact changed: '+name)


def allocate(source, old, scored, out):
    source, old, scored, out = map(Path, (source, old, scored, out))
    if out.exists():
        raise FileExistsError('allocation already exists; never overwrite a frozen selection')
    verify_old(old)
    val = load_rows(source, 'val')
    development = load_runtime(old/'runtime/tasks.mcq.jsonl') + load_runtime(old/'runtime/tasks.generation.jsonl')
    training = load_runtime(old/'training/runtime/tasks.jsonl')
    excluded_owners = {t.persona_group for t in development+training}
    excluded_families = {t.source_family for t in development+training}
    pool = defaultdict(list)
    for i, row in enumerate(val):
        owner = 'pm2:'+row['persona_id']
        family = 'pm2-'+text_hash(row['chat_history_32k_link'])[:20]
        if owner not in excluded_owners and family not in excluded_families:
            pool[owner].append(i)
    owners = ordered(list(pool), 'new-owner-allocation')
    # Keep at least 60 owners for WP4 and 82 for later development/confirmation.
    n = min(140, max(0, len(owners)-142))
    if n < 120:
        raise ValueError('fewer than 120 independent WP3 owners after reserves; report real capacity')
    chosen = [ordered(pool[o], 'one-val-row-per-owner')[0] for o in owners[:n]]
    gemma = ordered(chosen, 'gemma-key-arms')[:60]
    train_owners = ordered(sorted({t.persona_group for t in training}), 'training-owner-split')
    if len(train_owners) != 177:
        raise ValueError('original training-owner inventory changed')
    split_owners = dict(fit=train_owners[:125], tune=train_owners[125:151], development=train_owners[151:])
    cells = {(m, arm): {r['task_id']: r for r in jsonl(scored/f'scored.{m}.{arm}.private.jsonl')}
             for m in ('G0e', 'Qwen35') for arm in 'CD'}
    common = set.intersection(*[{tid for tid, r in cell.items() if r['status']=='completed'} for cell in cells.values()])
    # Bridge uses both models' completed B/C and the four-cell common set, no correctness filter.
    for m in ('G0e', 'Qwen35'):
        common &= {r['task_id'] for r in jsonl(scored/f'scored.{m}.B.private.jsonl') if r['status']=='completed'}
    bridge = ordered(sorted(common), 'old-protocol-bridge')[:60]
    wrong = {tid for (m, arm), cell in cells.items() if arm=='C'
             for tid, r in cell.items() if r['status']=='completed' and r['correct'] is False}
    errors = ordered(sorted(wrong), 'fixed-40-C-errors')[:40]
    others = sorted(r['task_id'] for r in jsonl(old/'evaluation/tasks.mcq.jsonl') if r['category']['who']=='others')
    if len(others)!=37 or len(errors)!=40 or len(bridge)!=60:
        raise ValueError('WP2 required retrospective/bridge denominators unavailable')
    result = dict(protocol='naa-v11-allocation-v1', authority_commit=AUTHORITY, seed=SEED,
                  old_freeze_sha256=sha_file(old/'FREEZE.json'), source_revision=REVISION,
                  source_val_sha256=sha_file(source/'benchmark/text/val.csv'),
                  old_excluded_owners=sorted(excluded_owners), old_excluded_families=sorted(excluded_families),
                  available_val_rows=sum(map(len, pool.values())), available_val_owners=len(owners),
                  wp3_rows=chosen, wp3_owners=owners[:n], gemma_rows=gemma,
                  wp4_reserved_owners=owners[n:n+60], future_reserved_owners=owners[n+60:],
                  reserve_note='Untouched val owner reserve, not a claim of formal benchmark/test independence; test closed.',
                  training_owners=split_owners, bridge_task_ids=bridge,
                  review=dict(who_others=others, c_errors_40=errors,
                              overlap=len(set(others)&set(errors)), union=sorted(set(others)|set(errors)),
                              c_error_population=len(wrong), purpose='Retrospective development only; forbidden training labels'),
                  visible_route_rule=dict(version='naa-visible-third-party-v1',
                      pattern=r'(?is)(?:found|came across|received|got)\b.{0,100}\b(?:blog|email|message|passage)|\b(?:my friend|my colleague|my sister|my brother)\b',
                      input='Only user-role text in delivered C sources; no gold, who label, or model output',
                      action='D on a visible match, otherwise C; ambiguous cue errors retained; retrospective only'),
                  new_model_outputs_read=False, new_selection_uses_direct_status=False,
                  training_dev_test_overlap=0)
    write_json(out, result)
    return result


def materialize(source, old, allocation, out):
    source, old, allocation, out = map(Path, (source, old, allocation, out))
    if out.exists():
        raise FileExistsError('new materialization output required')
    os.umask(0o077)
    a = json.loads(allocation.read_text())
    verify_old(old)
    if sha_file(old/'FREEZE.json') != a['old_freeze_sha256'] or sha_file(source/'benchmark/text/val.csv') != a['source_val_sha256']:
        raise ValueError('allocation input binding changed')
    val = load_rows(source, 'val')
    refs = sorted({val[i]['chat_history_32k_link'] for i in a['wp3_rows']})
    with ThreadPoolExecutor(max_workers=6) as pool:
        sources = list(pool.map(lambda ref: fetch(source, ref), refs))
    runtime, evaluation = out/'runtime', out/'evaluation'
    histories, content_seen, normalizations = {}, set(), []
    old_content = {digest(json.loads(p.read_text())['messages'])
                   for root in (old/'runtime/histories', old/'training/runtime/histories') for p in root.glob('*.json')}
    for i in a['wp3_rows']:
        row=val[i]; ref=row['chat_history_32k_link']; messages,gaps=new_history(source/ref, row['persona_id'])
        if gaps:normalizations.append(dict(source_ref=ref,raw_sha256=sha_file(source/ref),message_indices=gaps,
            operation='missing assistant content -> empty position; no text inferred; original index retained'))
        family='pm2-'+text_hash(ref)[:20]; name=f'histories/{family}.json'
        content_sha=digest(messages)
        if content_sha in old_content or content_sha in content_seen:
            raise ValueError('new confirmation has duplicate historical content; do not silently replace selected owner')
        content_seen.add(content_sha)
        write_json(runtime/name, dict(owner_id='pm2:'+row['persona_id'], source_family=family, messages=messages))
        histories[ref]=(name, sha_file(runtime/name), len(messages), family)
    tasks, evals, direct = [], [], []
    resolver=HistoryResolver(runtime)
    for i in a['wp3_rows']:
        row=val[i]; name, sha, cutoff, family=histories[row['chat_history_32k_link']]
        options, gold=make_options(row['correct_answer'], json.loads(row['incorrect_answers']), 20261128+i)
        query=parse_literal(row['user_query'])
        if set(query)!={'role','content'} or query['role']!='user':
            raise ValueError('unexpected official query')
        task=RuntimeTask(f'naa3-pm2-val-{i:05d}-mcq',REVISION,'val','pm2:'+row['persona_id'],family,
                         name,sha,cutoff,[],query['content'],'mcq',options)
        snippet=parse_literal(row['related_conversation_snippet'])
        status, spans=match_snippet(snippet,resolver.resolve(task))
        category={k:row[k] for k in ('pref_type','who','updated','sensitive_info','conversation_scenario')}
        category.update(selection_layer='wp3_confirmation', evidence_sufficiency='unknown')
        ev=EvalTask(task.task_id,gold,row['correct_answer'],row['preference'],snippet,category,spans,status)
        tasks.append(task.to_dict()); evals.append(ev.to_dict())
        direct.append(dict(task_id=task.task_id,status=status,spans=spans,diagnostic_only=True,
                           sufficiency='unknown; exact location is not a semantic label',allowed_arms=['C','C+noise']))
    write_jsonl(runtime/'tasks.mcq.jsonl',tasks)
    write_jsonl(evaluation/'tasks.mcq.jsonl',evals)
    write_jsonl(out/'direct/direct.jsonl',direct)
    write_json(out/'selection.json',dict(allocation_sha256=sha_file(allocation), gemma_task_ids=[f'naa3-pm2-val-{i:05d}-mcq' for i in a['gemma_rows']]))
    oldtasks={t.task_id:t for t in load_runtime(old/'runtime/tasks.mcq.jsonl')}
    oldeval={r['task_id']:r for r in jsonl(old/'evaluation/tasks.mcq.jsonl')}
    olddirect={r['task_id']:r for r in jsonl(old/'direct/direct.jsonl')}
    for tid in a['bridge_task_ids']:
        t=oldtasks[tid]; target=out/'bridge/runtime'/t.history_ref
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(old/'runtime'/t.history_ref,target)
    write_jsonl(out/'bridge/runtime/tasks.mcq.jsonl',[oldtasks[t].to_dict() for t in a['bridge_task_ids']])
    write_jsonl(out/'bridge/evaluation/tasks.mcq.jsonl',[oldeval[t] for t in a['bridge_task_ids']])
    write_jsonl(out/'bridge/direct/direct.jsonl',[olddirect[t] for t in a['bridge_task_ids']])
    counts=Counter(e['direct_status'] for e in evals)
    gemma=set(a['gemma_rows']); gemma_direct=sum(e['direct_status']=='located_unique' for i,e in zip(a['wp3_rows'],evals) if i in gemma)
    report=dict(protocol='naa-wp3-confirmation-material-v1',authority_commit=AUTHORITY,
                allocation_sha256=sha_file(allocation), source_revision=REVISION, source_license='CC-BY-4.0',
                confirmation_tasks=len(tasks),confirmation_owners=len({t['persona_group'] for t in tasks}),
                direct_status=dict(counts),semantic_sufficiency='unadjudicated; not selection criterion',
                independent_from_old_development_owners=300,independent_from_training_owners=177,
                duplicate_content_with_old_or_within_confirmation=0,bridge_tasks=60,gemma_tasks=len(gemma),
                missing_assistant_payloads=sum(len(r['message_indices']) for r in normalizations),
                reserved_wp4_owners=len(a['wp4_reserved_owners']),reserved_future_owners=len(a['future_reserved_owners']),
                logical_slots=7*len(tasks)+3*len(gemma)+2*2*60,
                expected_executable_before_capacity=5*len(tasks)+2*counts['located_unique']+2*len(gemma)+gemma_direct+240,
                structural_before_capacity=2*(len(tasks)-counts['located_unique'])+len(gemma)-gemma_direct,
                protocols=dict(new='naa-short-mcq-v1, modified',bridge='WP2 official old responses retained + modified short B0/C; two models'),
                new_model_calls=0,formal_test_read=False)
    write_json(out/'sources.json',sources);write_json(out/'normalizations.json',normalizations);write_json(out/'RECEIPT.json',report)
    write_json(out/'FREEZE.json',dict(protocol='naa-wp3-confirmation-freeze-v1',artifacts={str(p.relative_to(out)):sha_file(p) for p in sorted(out.rglob('*')) if p.is_file()}))
    return report

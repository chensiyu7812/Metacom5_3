"""Actual source-backed Memory task preparation, private outputs only, no inference."""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import re
import unicodedata

from .. import contracts as K
from ..io import canonical_json, object_sha256, file_sha256, write_json_once, write_jsonl_once
from ..sources import source_registry as S
from ..bank.v0_port import PrefixPort
from ..retrieve.v0 import search
from ..retrieve.native_tokens import NativeTokenizer
from .memory import EndHistoryQA, QARegistry, exact_raw_bank, runtime_task, load_asof

PROTOCOL = 'pmrl1-j-memory-30qa-candidate-v1'
CAPABILITIES = ('information extraction', 'temporal reasoning', 'conflict detection', 'user modeling', 'abstention')
INPUTS = {
    'raw': ('project/data/external/evo_emo.json', 'debae3bb229f56654f13ead9d5d7470c7ece9b11'),
    'sanitized': ('project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json', 'a726aa5008906db518ee332f63f6db14c3df0a0a'),
    'qa_identity': ('project/data/paper1_authority/es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl', '5acb9121bdcd329275a6f6d01db26d7fe185a565')}
OFFICIAL = {
    'src/lib/qa/qa_experiment.py': 'a58d29787b4500f9ba4ba2556398bee0584e9df0',
    'src/lib/shared/chat_rooms/chat_room_builder.py': '67599e8a00095cace875ce073f802451818bb987'}


def blob(path):
    b = Path(path).read_bytes()
    return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()


def ordering(value):
    return hashlib.sha256(('pmrl1-j-memory-dev-v1|' + value).encode()).hexdigest()


def family(owner):
    return 'p13+p18' if owner in ('p13', 'p18') else owner


def resolve_evidence(user, refs):
    sessions = {s['id']: s for s in user['dialog_history']}
    events = {e['id']: e for e in user['event_experience']}
    result = []
    for ref in refs:
        if ref in sessions:
            result.append(dict(ref=ref, kind='session', session_id=ref))
        elif ref in events and events[ref]['conv_id'] in sessions:
            result.append(dict(ref=ref, kind='event_to_session_coarse', session_id=events[ref]['conv_id']))
        elif ':' in ref:
            sid, idx = ref.rsplit(':', 1)
            turns = [t for t in sessions.get(sid, {}).get('dialogue', []) if str(t['idx']) == idx]
            result.append(dict(ref=ref, kind='exact_turn' if len(turns)==1 else 'unresolved',
                session_id=sid if len(turns)==1 else None, original_turn_index=idx))
        else:
            result.append(dict(ref=ref, kind='unresolved', session_id=None))
    return result


def balanced(pool, count):
    groups = defaultdict(list)
    for row in pool:
        groups[family(row['owner_id'])].append(row)
    for rows in groups.values():
        rows.sort(key=lambda r: ordering(r['row_id']))
    selected = []
    for i in range(max(map(len, groups.values()), default=0)):
        for key in sorted(groups, key=ordering):
            if i < len(groups[key]):
                selected.append(groups[key][i])
    return selected[:count]


def choose(raw, identities, folds, excluded_rows):
    # Historical development owner closure only; no new held-out owner exposure.
    dev = {o for o, split in folds['historical_rl1_split'].items() if split == 'dev'}
    for group in folds['family_groups']:
        if dev.intersection(group):
            dev.update(group)
    pool = []
    for user in raw:
        if user['id'] not in dev:
            continue
        for group in user['questions']:
            for q in group['questions']:
                rid = f"{user['id']}::{group['id']}::{q['idx']}"
                if rid in excluded_rows:
                    continue
                identity = identities[rid]
                if identity['capability'] != q['capability'] or identity['evidence_count'] != len(q['evidence']):
                    raise ValueError('QA identity fields differ')
                refs = resolve_evidence(user, q['evidence'])
                sessions = sorted({r['session_id'] for r in refs if r['session_id']})
                if any(r['kind']=='unresolved' for r in refs):
                    continue
                if q['capability'] != 'abstention' and not sessions:
                    continue
                if q['capability'] == 'abstention' and (sessions or q['answer'].strip().casefold() != 'unknown'):
                    continue
                pool.append(dict(row_id=rid, owner_id=user['id'], group_id=group['id'],
                    original_idx=q['idx'], question=q['question'], gold=q['answer'], capability=q['capability'],
                    evidence=q['evidence'], resolution=refs, evidence_sessions=sessions,
                    question_sha256=identity['question_normalized_sha256']))
    result = []
    used_hashes = set()
    for cap in CAPABILITIES:
        rows = [r for r in pool if r['capability']==cap and r['question_sha256'] not in used_hashes]
        # Exactly 3 multi-source per answerable domain when available; no outcome selection.
        first = balanced([r for r in rows if len(r['evidence_sessions']) >= 2], 3) if cap!='abstention' else []
        chosen = list(first)
        for r in balanced([r for r in rows if r not in first], len(rows)):
            if len(chosen) == 6:
                break
            if r['question_sha256'] not in {x['question_sha256'] for x in chosen}:
                chosen.append(r)
        if len(chosen) != 6:
            raise ValueError('insufficient source coverage: '+cap)
        result.extend(chosen)
        used_hashes.update(r['question_sha256'] for r in chosen)
    return result, dict(eligible_pool=len(pool), dev_owner_closure=sorted(dev),
        selection='historical-dev owner-family closure; per capability 3 multi-source then fill to 6; family round-robin SHA256 order; no outcomes; exclude all old 30 QA candidates',
        counts_by_capability=dict(Counter(r['capability'] for r in pool)))


def normalize_exact(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).strip()).casefold().rstrip(' .!?')


def fact_check(response, evalspec):
    """Conservative strict subset; complex semantic comparisons remain unknown."""
    text = normalize_exact(response)
    if not text:
        return dict(status='technical_failure', success=None, reason='empty_output')
    gold = normalize_exact(evalspec['gold'])
    if text == gold:
        return dict(status='pass', success=1, reason='whole_answer_exact_normalization')
    if text == 'unknown' and gold != 'unknown':
        return dict(status='fail', success=0, reason='explicit_abstention_on_answerable_task')
    return dict(status='uncertain', success=None, interval=[0,1],
        reason='requires_independent_semantic_verification; no substring or lexical-F1 success')


def build(root, out, asof_path, model):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_manifest = {}
    for name, (rel, expected) in INPUTS.items():
        path = root/rel
        if blob(path) != expected:
            raise ValueError('fixed input Git blob mismatch: '+name)
        source_manifest[name] = dict(path=str(path), git_blob=expected, sha256=file_sha256(path))
    official_root = root/'project/outputs/vendor_es_memeval'
    for rel, expected in OFFICIAL.items():
        if blob(official_root/rel) != expected:
            raise ValueError('pinned official QA semantics source differs')
    raw = json.loads((root/INPUTS['raw'][0]).read_text())
    identities = {r['row_id']:r for r in map(json.loads,(root/INPUTS['qa_identity'][0]).read_text().splitlines())}
    registry = S.load(root/'project/outputs/pm_rl1/v3/A1_preparation/final/registry')
    # Validate original registry bytes against the fixed sanitized input.
    san = json.loads((root/INPUTS['sanitized'][0]).read_text())['users']
    for user in san:
        for session in user['sessions']:
            source = registry.entry(user['owner_id'], session['session_id']).source
            if [(t.role,t.text) for t in source.turns] != [(t['role'],t['content']) for t in session['turns']]:
                raise ValueError('registry/sanitized dialogue mismatch')
    old_path = root/'project/outputs/pm_rl1/qa_resource_gain_20261105_v1/CANDIDATES_PRIVATE.json'
    old = json.loads(old_path.read_text())
    excluded = {f"{x['source']['owner']}::{x['source']['group']}::{x['source']['idx']}" for x in old}
    selected, selection = choose(raw, identities, registry.folds, excluded)
    prefixes = []
    for row in selected:
        history = [e.source for e in registry.entries if e.source.owner_id==row['owner_id']]
        task_id = ordering(row['row_id'])[:24]
        prefixes.append(EndHistoryQA(task_id=task_id, owner_id=row['owner_id'], question=row['question'],
            cutoff_rank=len(history), timestamp=max(s.date for s in history if s.date),
            family_id='qa-owner:'+family(row['owner_id']),
            ancestor_family_ids=tuple(sorted({s.family_id for s in history})),
            fold=registry.folds['fold_of_owner'][row['owner_id']]))
    qaregistry = QARegistry(registry, prefixes)
    bank = exact_raw_bank(qaregistry, {r['owner_id'] for r in selected})
    tokenizer = NativeTokenizer(model, root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json')
    asof = load_asof(asof_path)
    ledger = asof.Ledger(out/'ledger')
    writer = 'journal-source-exact:'+object_sha256(dict(protocol=PROTOCOL, code=file_sha256(__file__)))
    entries = sorted([e for e in registry.entries if e.source.owner_id in selection['dev_owner_closure']],
        key=lambda e:(e.source.owner_id,e.source.chronological_rank))
    for entry in entries:
        ledger.append(asof.record_from_source(entry,kind='MS_RAW',writer=writer,subject='session'),registry)
    # 24 actual dialogue cuts: complete As-of snapshots and PrefixPort reads.
    real_prefixes = []
    for e in entries:
        s = e.source
        if s.chronological_rank == 0:
            continue
        for i,t in enumerate(s.turns[:-1]):
            if t.role=='seeker' and s.turns[i+1].role=='supporter':
                real_prefixes.append(registry.prefix(s.owner_id,s.session_id,i)); break
    real_prefixes.sort(key=lambda p: ordering(p.prefix_id))
    reads=[]
    for prefix in real_prefixes[:24]:
        snap = asof.materialize(registry,prefix,ledger,writer=writer)
        asof_view = asof.read(snap,'MS',ordinal=1,token_counter=tokenizer,context_remaining=tokenizer.native_context_tokens-320)
        port = PrefixPort(bank,prefix,tokenizer,g_id='G0e-tokenizer-only',decode_id='not_run',output_reserve_tokens=320)
        result = port.read('MS')
        if not isinstance(result,K.ReadSuccess) or not isinstance(asof_view,K.ReadingView):
            raise ValueError('real source read failed')
        if port.verify_records(result.record_ids):
            raise ValueError('source record audit failed')
        reads.append(dict(prefix=prefix,asof_snapshot_sha256=snap['snapshot_sha'],
            asof_reading=asof_view,prefix_port_result=result,
            source_legality_errors=port.verify_records(result.record_ids)))
    runtime=[]; evaluations=[]; requests=[]; coverage=[]
    for row,prefix in zip(selected,prefixes):
        snap = asof.materialize(qaregistry,prefix,ledger,writer=writer)
        if len(snap['source_frontier'].sources) != prefix.cutoff_rank:
            raise ValueError('end-history frontier incomplete')
        runtime.append(runtime_task(prefix,inventory={'MS':True,'MP':False,'ME':False,'RS':False},
            budget=dict(max_get_per_head=1,max_memory_sessions=4,native_context_tokens=tokenizer.native_context_tokens,
                        output_reserve_tokens=320,no_truncation=True)))
        evaluation = dict(task_id=prefix.task_id, origin='original_official_QA', row_id=row['row_id'],
            source_family_ids=[family(row['owner_id'])], owner_id=row['owner_id'], fold=prefix.fold,
            cutoff=dict(mode='official_end_of_history',rank=prefix.cutoff_rank,official_commit='692624208acc077b8867698c1d6fcd998dee641a'),
            capability=row['capability'],gold=row['gold'],answerability='unanswerable' if row['capability']=='abstention' else 'answerable',
            evidence_sets=[row['evidence_sessions']],evidence_resolution=row['resolution'],
            requirements=[dict(id='answer',criterion='Answer original question accurately using available source evidence, or abstain when unknown.',
                allowed_alternatives='Semantically equivalent answers; no requirement to repeat wording or cite a method.',
                source_locator=row['row_id'],verification_type='strict_exact_or_independent_semantic')],
            prohibitions=['fabricated_personal_fact','contradiction_of_decisive_source_evidence'], optional=['source_citation'],
            rubric_version='pmrl1-j-memory-eval-v1',review_state='source_bound_semantic_verification_pending',
            unknown_policy='pending [0,1]; retain in common denominator; no positive reward',
            source_coarse_warning='event-to-session is a candidate location, not exact event entailment')
        evaluations.append(evaluation)
        candidates=bank.candidates('MS',prefix)
        lookup={r.parent_session_id:r for r in candidates}
        ret=search(bank,'MS',prefix)
        byid=bank.by_id
        ret_records=[byid[r.record_id] for r in ret.ranked[:4]]
        direct=[lookup[sid] for sid in row['evidence_sessions']]
        # Match count and approximate native reading length within owner, non-evidence sessions.
        target_tokens=sum(tokenizer.count(r.reading_text) for r in direct)
        count=len(direct) if direct else min(4,len(candidates))
        other=[r for r in candidates if r.parent_session_id not in row['evidence_sessions']]
        target_each=target_tokens/max(1,count) if direct else sum(tokenizer.count(r.reading_text) for r in ret_records)/max(1,count)
        matched=sorted(other,key=lambda r:(abs(tokenizer.count(r.reading_text)-target_each),r.record_id))[:count]
        arms={'OFF':[],'DP':direct,'RET':ret_records,'matched-other':matched}
        for arm,records in arms.items():
            # Complete sessions only. DP evidence count may exceed normal top4; explicit diagnostic.
            records=sorted(records,key=lambda r:(r.source_rank,r.record_id))
            text='\n\n'.join(f'Completed historical session; reported {r.reported_at.date or "unknown"}:\n'+r.reading_text for r in records)
            views=() if not records else (K.ReadingView(head='MS',view='raw',ordinal=1,reading_text=text,
                reported_at=max((r.reported_at for r in records),key=lambda t:t.session_rank),tokens=tokenizer.count(text)),)
            tokens=tokenizer.prompt_tokens(prefix,views)
            status='ready_for_final_renderer_capacity_check' if tokens+320<=tokenizer.native_context_tokens else 'unreachable_capacity'
            requests.append(dict(task_id=prefix.task_id,arm=arm,visible_prefix=prefix.visible(),readings=views,
                private_source_record_ids=[r.record_id for r in records],private_source_session_ids=[r.parent_session_id for r in records],
                base_renderer_prompt_tokens=tokens,reading_tokens=sum(v.tokens for v in views),
                native_context_tokens=tokenizer.native_context_tokens,output_reserve_tokens=320,status=status,
                request_material_sha256=object_sha256(dict(prefix=prefix.visible(),readings=views)),
                intervention='journal_complete_session_bundle; distinct from old single-MS/PP1 identity',
                annotation='DP evaluation-privileged; only RET is deployable retrieval; matched-other not claimed useless'))
        evidence=set(row['evidence_sessions']);ret_ids={r.parent_session_id for r in ret_records}
        coverage.append(dict(task_id=prefix.task_id,capability=row['capability'],family=family(row['owner_id']),
            evidence_sessions=len(evidence),ret_hit_any=bool(evidence&ret_ids) if evidence else None,
            ret_hit_all=evidence<=ret_ids if evidence else None,legal_archive_sessions=prefix.cutoff_rank,
            matched_other_count=len(matched),matched_other_length_delta_tokens=sum(tokenizer.count(r.reading_text) for r in matched)-target_tokens,
            exact_turn_refs=sum(r['kind']=='exact_turn' for r in row['resolution']),
            coarse_event_refs=sum(r['kind']=='event_to_session_coarse' for r in row['resolution'])))
    # No question/gold/evidence metadata is serializable via runtime_task allowlist.
    leaked_keys={'gold','owner_id','fold','source_family_ids','evidence','evidence_sets','capability','requirements','answerability'}
    def keys(x):
        if isinstance(x,dict):
            return set(x)|set().union(*(keys(v) for v in x.values()))
        if isinstance(x,list):return set().union(*(keys(v) for v in x))
        return set()
    if keys(json.loads(canonical_json(runtime))) & leaked_keys:
        raise ValueError('runtime allowlist leak')
    outputs={'tasks_runtime.jsonl':runtime,'evalspec_private.jsonl':evaluations,
             'request_material_private.jsonl':requests,'coverage_private.jsonl':coverage,
             'readings24_private.jsonl':reads,'resources_private.jsonl':bank.records}
    for name,rows in outputs.items():write_jsonl_once(out/name,rows)
    report=dict(protocol=PROTOCOL,status='frozen_candidate_not_G_run',tasks=len(runtime),
        per_capability=dict(Counter(r['capability'] for r in selected)),owners=len({r['owner_id'] for r in selected}),
        independent_owner_family_groups=len({family(r['owner_id']) for r in selected}),
        multi_source_tasks=sum(len(r['evidence_sessions'])>=2 for r in selected),real_prefix_reads=len(reads),
        raw_resources=len(bank.records),ledger_records=len(ledger.rows),
        requests=len(requests),unique_request_materials=len({r['request_material_sha256'] for r in requests}),
        unreachable_base_renderer=sum(r['status']=='unreachable_capacity' for r in requests),
        ret_answerable_denominator=sum(bool(r['evidence_sessions']) for r in selected),
        ret_hit_any=sum(r['ret_hit_any'] is True for r in coverage),ret_hit_all=sum(r['ret_hit_all'] is True for r in coverage),
        runtime_allowlist='pass',source_legality='24 PrefixPort + As-of reads and all candidate sources verified',
        selection=selection,source_manifest=source_manifest,old_candidates_excluded_sha256=file_sha256(old_path),
        upstream_qa=dict(commit='692624208acc077b8867698c1d6fcd998dee641a',files=OFFICIAL,
            semantics='ChatRoomBuilder.fill_chat_room iterates all dialog_history; QaExperiment._create_room calls it before _generate_answer opens each question session'),
        dependencies=dict(asof_path=str(asof_path),asof_sha256=file_sha256(asof_path),
            contracts_sha256=file_sha256(root/'project/src/metacom_pm/rl1v3/contracts.py'),
            registry=registry.version,bank=bank.version,index=bank.index_version,tokenizer=tokenizer.identity),
        outputs={name:dict(rows=len(rows),sha256=file_sha256(out/name)) for name,rows in outputs.items()},
        limitations=['Only 3 independent owner-family groups in historical dev closure; not confirmatory.',
            'SOURCE_EXACT raw sessions are mechanically grounded, not newly approved MP/ME claims; 0 new SUM.',
            'All 30 tasks retain original questions and gold; event refs are coarse locations and semantic gold entailment remains unqualified.',
            'Final journal renderer capacity check and GPU approval remain; no generated answer, reward or policy training.',
            'Evaluation exact match is a strict subset; other semantic answers remain pending, no substring success.'])
    write_json_once(out/'MEMORY_BUILD_REPORT.json',report)
    return report

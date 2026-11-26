"""GE2 source-only adapters and exact-source supply diagnostics, without inference.

Official end-history QA and actual dialogue prefixes retain distinct identities.
Evaluation groups are consumed only by the separate CPU diagnostic functions.
"""
from pathlib import Path
import json
from .. import contracts as K
from ..compile import asof as A
from ..io import canonical_json, decode_contract, file_sha256, object_sha256
from . import pomdp_memory as P, renderer
from .memory import EndHistoryQA, QARegistry
from .memory_port import SnapshotPrefixPort
from .joint_task_port import TaskTokenizer
from .runtime_binding import binding_for, plain
from .selective_memory_validation_sources import load_development_cache

PROTOCOL = 'pmrl1-j-ge2-source-adapter-v1'
TASK_KEYS = {'task_id','timestamp','turns','query','view_protocol'}


def load_factory_inputs(source_config, envelopes=None):
    """Load only an authenticated, already isolated source cache, never EvalSpec."""
    cfg = json.loads(Path(source_config).read_text()) if isinstance(source_config,(str,Path)) else source_config
    for path, sha in cfg['source_inputs_sha256'].items():
        if file_sha256(path) != sha: raise ValueError('source config input identity mismatch')
    return load_development_cache(resources_path=cfg['resources_path'], metadata_path=cfg['metadata_path'],
        allowed_owners=cfg['allowed_owners'], excluded_owners=cfg['excluded_owners'])


def prepare_source_port(task, envelope, registry, tokenizer, baseline, ledger_root):
    """Return (old-factory-compatible prepared tuple, prefix-specific registry)."""
    if set(task) != TASK_KEYS or task != envelope['visible_task'] or object_sha256(task) != envelope['visible_task_sha256']:
        raise ValueError('visible task/envelope mismatch')
    kind = envelope['prefix_kind']
    if kind == 'official_end_history_qa':
        raw = dict(envelope['qa_prefix']); raw['ancestor_family_ids'] = tuple(raw['ancestor_family_ids'])
        prefix = EndHistoryQA(**raw); bound = QARegistry(registry,[prefix])
        if task['query'] != prefix.question or task['turns'] != [{'role':'seeker','text':prefix.question}]:
            raise ValueError('official question changed')
    elif kind == 'actual_dialogue_prefix':
        prefix = decode_contract(K.PrefixSpec, canonical_json(envelope['actual_prefix'])); bound = registry
        if envelope.get('channel') == 'natural' and task['turns'] != [dict(role=t.role,text=t.text) for t in prefix.turns]:
            raise ValueError('natural task is not the actual complete pre-supporter prefix')
    else: raise ValueError('unknown prefix kind')
    if prefix.runtime_sha256 != envelope['asof_runtime_sha256']: raise ValueError('asof identity mismatch')
    bound.context(prefix)
    entries = sorted((e for e in bound.entries if e.source.owner_id == prefix.owner_id and bound.reason(e.source_id,prefix) is None),
        key=lambda e:e.source.chronological_rank)
    writer=P.PROTOCOL+':legal-raw'
    ledger=A.Ledger(Path(ledger_root)/task['task_id'].replace(':','-'))
    for entry in entries: ledger.append(A.record_from_source(entry,kind='MS_RAW',writer=writer,subject='session'),bound)
    snapshot=A.materialize(bound,prefix,ledger,writer=writer)
    baseline_sha = baseline['binding_sha256'] if isinstance(baseline,dict) else baseline
    tok=TaskTokenizer(tokenizer,task['turns'],baseline_sha,file_sha256(renderer.__file__))
    port=SnapshotPrefixPort(bound,prefix,snapshot,tok,g_id=baseline_sha,decode_id='frozen-G0e',step2_id=P.PROTOCOL,output_reserve_tokens=320)
    binding=binding_for(bound,prefix,snapshot,port)
    records=[plain(r) for r in port.bank.candidates('MS',prefix)]
    return (task,prefix,snapshot,tok,port,binding,records),bound


def located_reference(span, records, current_turns=()):
    """Resolve an exact source quote within its same source/role; never token-match."""
    owner=span.get('owner_id'); session=span.get('session_id'); quote=span.get('exact_quote')
    if not quote: raise ValueError('empty source quote')
    speaker=span.get('speaker')
    hits=[]
    for record in records:
        if owner and record['owner_id'] != owner: continue
        if session and record['parent_session_id'] != session: continue
        for ref in record['source_refs']:
            if quote in ref['exact_quote'] and (not speaker or ref['speaker']==speaker):
                hits.append(dict(record_id=record['record_id'],owner_id=record['owner_id'],session_id=record['parent_session_id'],
                    turn_index=ref['turn_index'],speaker=ref['speaker'],exact_quote=quote,
                    start_char=ref['exact_quote'].index(quote),end_char=ref['exact_quote'].index(quote)+len(quote),reported_at=record['reported_at']))
    current=any(quote in t['text'] for t in current_turns)
    return dict(candidates=hits,current_visible=current,unique_legal_location=len(hits)==1,
        unavailable=not hits and not current)


def group_coverage(groups, delivered, visible_text=''):
    """OR of sufficient groups, AND of same-record exact spans; supply only."""
    if not groups: return None
    def seen(ref):
        if ref.get('current_visible') and ref['exact_quote'] in visible_text: return True
        return any(d.get('record_id')==ref.get('record_id') and ref['exact_quote'] in d.get('text','') for d in delivered)
    return any(all(seen(ref) for ref in group) for group in groups)


def evaluate_supply(atoms, delivered, visible_text=''):
    rows=[dict(atom_id=a['id'],requirement_role=a['requirement_role'],
        covered=group_coverage(a.get('sufficient_groups',[]),delivered,visible_text)) for a in atoms]
    required=[r for r in rows if r['requirement_role']=='explicit_answer']
    evaluable=[r for r in required if r['covered'] is not None]
    return dict(atoms=rows,required_slots=len(required),evaluable_source_slots=len(evaluable),
        covered_slots=sum(r['covered'] for r in evaluable),unknown_slots=len(required)-len(evaluable),
        complete_evaluable=bool(evaluable) and all(r['covered'] for r in evaluable),
        complete_all_required=bool(required) and len(required)==len(evaluable) and all(r['covered'] for r in evaluable),
        task_success=None,interpretation='source presentation only; no semantic task-success inference')


def rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def write_once(path, value, *, jsonl=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text=(''.join(canonical_json(x)+'\n' for x in value) if jsonl else canonical_json(value)+'\n')
    with path.open('x') as handle:handle.write(text)


def qa_envelope(runtime, evaluation, registry, task_id=None):
    original_id=runtime['task_id']; task_id=task_id or original_id
    history=[e.source for e in registry.entries if e.source.owner_id==evaluation['owner_id']]
    owner=evaluation['owner_id']; family='p13+p18' if owner in ('p13','p18') else owner
    question=runtime['visible_prefix']['turns'][0]['text']
    prefix=EndHistoryQA(task_id=original_id,owner_id=owner,question=question,cutoff_rank=len(history),
        timestamp=max(s.date for s in history if s.date),family_id='qa-owner:'+family,
        ancestor_family_ids=tuple(sorted({s.family_id for s in history})),fold=evaluation['fold'])
    if prefix.runtime_sha256 != runtime['prefix_identity']: raise ValueError('original QA identity changed')
    task=dict(task_id=task_id,timestamp=prefix.timestamp,turns=[dict(role='seeker',text=question)],
        query=question,view_protocol='ge2-original-official-end-history-qa-v1')
    envelope=dict(task_id=task_id,channel='fact',prefix_kind='official_end_history_qa',qa_prefix=plain(prefix),
        asof_runtime_sha256=prefix.runtime_sha256,visible_task=task,visible_task_sha256=object_sha256(task),
        original_task_id=original_id,scope='Original official complete-history QA; any strict-date audit is a separate diagnostic identity.')
    return task,envelope


def dialogue_envelope(task, old_envelope, *, task_id=None, channel=None, actual_natural=False):
    task=dict(task);task['task_id']=task_id or task['task_id']
    envelope=dict(old_envelope);envelope.update(task_id=task['task_id'],prefix_kind='actual_dialogue_prefix',channel=channel)
    if actual_natural:
        task['turns']=[dict(role=t['role'],text=t['text']) for t in envelope['actual_prefix']['turns']]
        task['query']='\n'.join(t['text'] for t in task['turns'])
        task['view_protocol']='ge2-original-pre-supporter-complete-prefix-v1'
    envelope.update(visible_task=task,visible_task_sha256=object_sha256(task))
    return task,envelope


def normalize_atoms(origin, evaluation, records, turns, *, natural=False):
    """Exact-location audit only. Original semantic observations remain attached."""
    result=[];checks=[]
    def locate(span):
        found=located_reference(span,records,turns); checks.append(dict(original=span,location=found))
        if found['unique_legal_location']:
            return dict(found['candidates'][0],current_visible=found['current_visible'])
        if found['current_visible']:
            return dict(record_id=None,exact_quote=span['exact_quote'],current_visible=True,
                speaker=span.get('speaker'),session_id=span.get('session_id'))
        return None
    if origin=='official30':
        for atom in evaluation['atoms']:
            refs={f"{s['session_id']}:{s['original_idx']}":s for s in atom['source_evidence']}
            groups=[]
            for group in atom.get('sufficient_source_groups',[]):
                located=[locate(refs[key]) if key in refs else None for key in group]
                if located and all(r is not None for r in located):groups.append(located)
            result.append(dict(id=atom['atom_id'],requirement_role='explicit_answer',reference=atom['claim'],
                sufficient_groups=groups,reference_status=atom['status_end_history'],
                original_atom=atom,original_atom_sha256=object_sha256(atom)))
    elif origin=='existing_SMV_joint':
        for atom in evaluation['fact_references']:
            span=dict(atom['source_span']);span['exact_quote']=atom['quote']
            located=locate(span)
            result.append(dict(id=atom['atom_id'],requirement_role='explicit_answer' if atom['atom_id'] in evaluation['required_fact_ids'] else 'correct_if_used',
                reference=atom['semantic_reference'],sufficient_groups=[[located]] if located else [],original_atom=atom))
    else:
        for atom in evaluation['source_binding']['atoms']:
            groups=[]
            for group in atom['evidence_groups']:
                located=[locate(s) for s in group['spans']]
                if located and all(r is not None for r in located):groups.append(located)
            role='optional_background' if natural else 'explicit_answer' if atom['atom_id'] in evaluation['required_fact_ids'] else 'correct_if_used'
            if atom['kind']=='unresolved_boundary':groups=[]
            result.append(dict(id=atom['atom_id'],requirement_role=role,reference=atom['reference'],
                sufficient_groups=groups,kind=atom['kind'],original_atom=atom))
    return result,checks

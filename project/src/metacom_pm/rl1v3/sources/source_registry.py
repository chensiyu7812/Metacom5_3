"""Immutable, dialogue-only source snapshots. No model calls or evaluator fields.

ready_at rank r+1 is a *logical replay* session-end boundary, not a measured
writer timestamp. External RS sources are preinstalled corpus snapshots with
unknown historical dates; their readiness is bound to the registry version,
never compared using an unrelated personal session rank.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict, Counter
import json

from .. import contracts as K
from ..io import canonical_json, decode_contract, file_sha256, object_sha256, write_json_once, write_jsonl_once
from .asset_reuse import session_family, esconv_family, rs_rejection

PROTOCOL = 'pmrl1v3-source-registry-v0.1'
DATASET = 'es_memeval_evoemo_public_v1'
AUDIT = 'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json'
FOLDS = 'project/outputs/pm_rl1/v3/B0/folds.json'
CONFIG = 'project/configs/rl1v3/asset_reuse_v1.json'


class PinnedInputs:
    """Verify only consumed small inputs against the previous 64GB audit."""
    def __init__(self, root):
        self.root = Path(root)
        self.audit = json.loads((self.root / AUDIT).read_text())
        payload = {k:v for k,v in self.audit.items() if k != 'manifest_sha256'}
        if object_sha256(payload) != self.audit['manifest_sha256']:
            raise ValueError('asset audit manifest integrity')
        self.config = json.loads((self.root / CONFIG).read_text())
        self.used = {AUDIT: file_sha256(self.root / AUDIT), CONFIG: file_sha256(self.root / CONFIG)}
        terms='project/configs/rl1v3/source_terms_v0.json'
        self.used[terms]=file_sha256(self.root/terms)

    def path(self, relative):
        path = self.root / relative
        if path.is_absolute() and not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('input outside repository')
        matches = [r for r in self.audit['files'] if r.get('exists') and
                   r['path'].endswith('/'+relative)]
        if not matches or len({r['sha256'] for r in matches}) != 1:
            raise ValueError('input not uniquely pinned by asset audit: '+relative)
        actual = file_sha256(path)
        if actual != matches[0]['sha256']:
            raise ValueError('changed input: '+relative)
        self.used[relative] = actual
        return path

    def read(self, name, *, lines=False):
        path = self.path(self.config[name])
        return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if lines else json.loads(path.read_text())

    def folds(self):
        manifest = json.loads((self.root/'project/outputs/pm_rl1/v3/B0/manifest.json').read_text())
        path = self.root / FOLDS
        if file_sha256(path) != manifest['outputs']['folds.json']['sha256']:
            raise ValueError('B0 folds changed')
        self.used[FOLDS] = file_sha256(path)
        return json.loads(path.read_text())


def _source_id(source):
    return 'source:'+object_sha256(dict(protocol=PROTOCOL, source=source))


def span(source, ordinal, start=0, end=None):
    turn = source.turns[ordinal]
    end = len(turn.text) if end is None else end
    result = K.SourceSpan(source_key=f'{source.dataset}:{source.owner_id}:{source.session_id}:{ordinal}',
        owner_id=source.owner_id, session_id=source.session_id, source_rank=source.chronological_rank,
        turn_index=ordinal, speaker=turn.role, start_char=start, end_char=end,
        exact_quote=turn.text[start:end], raw_turn_sha256=turn.raw_turn_sha256)
    result.verify(source)
    return result


@dataclass(frozen=True)
class Entry:
    source_id: str
    source: K.SourceSession
    original_turn_indices: tuple[int, ...]
    reported_at: K.TimePoint | None
    ready_at: K.TimePoint | None
    availability_scope: str
    fold: int | None
    quality: str = 'original_utterance_not_verified_world_fact'
    risk: str = 'unknown'
    exposure: str = 'previously_public_research_not_independent'


class Registry:
    """Private executor object. Expose prefix.visible(), never this object to PM/G."""
    def __init__(self, entries, *, inputs, folds, excluded_families, rejected=(), operations=()):
        self.entries = tuple(entries)
        self.inputs, self.folds = dict(inputs), dict(folds)
        self.excluded_families = frozenset(excluded_families)
        self.rejected, self.operations = tuple(rejected), tuple(operations)
        self.by_id = {e.source_id:e for e in self.entries}
        self.by_session = {(e.source.owner_id,e.source.session_id):e for e in self.entries}
        if len(self.by_id) != len(self.entries) or len(self.by_session) != len(self.entries):
            raise ValueError('duplicate source identity')
        for e in self.entries:
            if e.source_id != _source_id(e.source) or len(e.original_turn_indices) != len(e.source.turns):
                raise ValueError('invalid source identity/turn mapping')
            if len(set(e.original_turn_indices)) != len(e.original_turn_indices):
                raise ValueError('ambiguous original turn indices')
            if e.availability_scope == 'personal_history':
                if e.source.dataset != DATASET or e.reported_at != K.TimePoint(date=e.source.date,session_rank=e.source.chronological_rank):
                    raise ValueError('invalid personal report time')
                if e.ready_at != K.TimePoint(session_rank=e.source.chronological_rank+1):
                    raise ValueError('invalid logical session-end readiness')
            elif e.availability_scope != 'preinstalled_external_snapshot' or e.source.dataset != 'ESConv':
                raise ValueError('invalid availability scope')
        self.version = 'sources:'+object_sha256(dict(protocol=PROTOCOL,entries=self.entries,
            inputs=self.inputs,folds=self.folds,excluded=sorted(self.excluded_families),rejected=self.rejected,operations=self.operations))

    def entry(self, owner, session):
        return self.by_session[(owner,session)]

    def context(self, prefix):
        current = self.entry(prefix.owner_id,prefix.session_id).source
        history = tuple(e.source for e in self.entries if e.source.owner_id==prefix.owner_id
                        and e.source.chronological_rank < prefix.cutoff_rank and e.source.dataset==prefix.dataset)
        prefix.verify_source_context(current, history)
        if prefix.fold != self.folds['fold_of_owner'][prefix.owner_id]:
            raise ValueError('prefix fold differs from frozen B0')
        return current, history

    def prefix(self, owner, session, cut_turn):
        current = self.entry(owner,session).source
        history = [e.source for e in self.entries if e.source.owner_id==owner and
                   e.source.chronological_rank<current.chronological_rank and e.source.dataset==DATASET]
        families = sorted({f for s in [current,*history] for f in (s.family_id,*s.ancestor_family_ids)})
        p = K.PrefixSpec.create(owner_id=owner,session_id=session,cut_turn=cut_turn,
            turns=current.turns[:cut_turn+1],cutoff_rank=current.chronological_rank,timestamp=current.date,
            dataset=DATASET,family_id=current.family_id,ancestor_family_ids=tuple(families),
            fold=self.folds['fold_of_owner'][owner],split=self.folds['historical_rl1_split'][owner])
        self.context(p)
        return p

    def reason(self, source_id, prefix, *, rs=False):
        e = self.by_id.get(source_id)
        if e is None: return 'missing_source'
        s = e.source
        families = {s.family_id,*s.ancestor_family_ids}
        if rs:
            if s.dataset!='ESConv' or s.source_split!='train': return 'non_train_source'
            if s.excluded_for_overlap or families & (self.excluded_families|set(prefix.ancestor_family_ids)):
                return 'family'
        else:
            if s.owner_id!=prefix.owner_id or s.dataset!=prefix.dataset:return 'owner'
            if s.chronological_rank>=prefix.cutoff_rank:return 'future_source'
            if e.ready_at.session_rank>prefix.cutoff_rank:return 'not_ready'
            if s.date and prefix.timestamp and s.date>prefix.timestamp:return 'future_source'
        for op in self.operations:
            if op['source_id'] != source_id: continue
            known = op['known_at']
            if s.owner_id != prefix.owner_id or rs: return 'version_scope'
            if known['session_rank'] <= prefix.cutoff_rank and (not known.get('date') or
                    (prefix.timestamp and known['date']<=prefix.timestamp)):
                if op['operation']=='INVALIDATE':return 'invalidated'
        return None

    def visible(self, prefix, *, rs=False):
        self.context(prefix)
        return tuple(e for e in self.entries if self.reason(e.source_id,prefix,rs=rs) is None)

    def invalidate(self, source_id, *, known_at, evidence):
        """Append-only administrative version operation; old snapshot stays replayable."""
        e=self.by_id[source_id]; s=e.source
        if s.dataset!=DATASET or known_at.session_rank is None or known_at.session_rank<s.chronological_rank:
            raise ValueError('invalid invalidation time/scope')
        if not evidence:raise ValueError('invalidation requires exact evidence')
        for ref in evidence:
            ref.verify(self.entry(ref.owner_id,ref.session_id).source)
            if ref.owner_id!=s.owner_id or ref.source_rank>=known_at.session_rank:
                raise ValueError('invalidation evidence owner/time')
        op=dict(operation='INVALIDATE',source_id=source_id,known_at=json.loads(canonical_json(known_at)),
                evidence=json.loads(canonical_json(evidence)))
        if op in self.operations:return self  # NOOP
        return Registry(self.entries,inputs=self.inputs,folds=self.folds,excluded_families=self.excluded_families,
                        rejected=self.rejected,operations=(*self.operations,op))


def build(root: Path) -> Registry:
    pinned = PinnedInputs(root); runtime=pinned.read('runtime'); split=pinned.read('esconv_split',lines=True)
    folds=pinned.folds(); entries=[]
    split_by_family={esconv_family(r['dialogue_id']):r['split'] for r in split}
    excluded={esconv_family(r['dialogue_id']) for r in split if r['excluded_for_evoemo_overlap']}
    observed=set()
    for user in runtime['users']:
        owner=user['owner_id']
        if [s['chronological_rank'] for s in user['sessions']] != list(range(len(user['sessions']))):
            raise ValueError('noncontiguous personal history')
        for s in user['sessions']:
            family=session_family(owner,s['session_id'])
            if family.startswith('esconv:'):observed.add(family)
            turns=tuple(K.SourceTurn(turn_index=i,role=t['role'],text=t['content']) for i,t in enumerate(s['turns']))
            source=K.SourceSession(owner_id=owner,session_id=s['session_id'],chronological_rank=s['chronological_rank'],
                date=s['timestamp'],turns=turns,raw_sha256=pinned.used[pinned.config['runtime']],dataset=DATASET,
                family_id=family,license='inherited_research_scope; upstream_EvoEmo_license_unresolved',
                provenance_version=PROTOCOL,source_uri=pinned.config['runtime'],
                transcript_sha256=object_sha256([(t.role,t.text) for t in turns]),
                source_split=folds['historical_rl1_split'][owner],excluded_for_overlap=family in excluded)
            entries.append(Entry(_source_id(source),source,tuple(t['idx'] for t in s['turns']),
                K.TimePoint(date=source.date,session_rank=source.chronological_rank),
                K.TimePoint(session_rank=source.chronological_rank+1),'personal_history',folds['fold_of_owner'][owner]))
    if observed!=excluded:raise ValueError('B0/ESConv family closure mismatch')
    holders=defaultdict(set)
    for e in entries:holders[e.source.family_id].add(e.source.owner_id)
    if any(len({folds['fold_of_owner'][o] for o in owners})!=1 for owners in holders.values()):
        raise ValueError('shared family crosses B0 folds')
    rejected=[]
    for idx,dialogue in enumerate(pinned.read('raw_esconv')):
        sid=f'esconv_{idx:04d}';family=esconv_family(sid)
        reason=rs_rejection([sid],split_by_family,excluded)
        if reason:
            rejected.append(dict(session_id=sid,family_id=family,reason=reason));continue
        turns=tuple(K.SourceTurn(turn_index=i,role=t['speaker'],text=t['content']) for i,t in enumerate(dialogue['dialog']))
        source=K.SourceSession(owner_id='external:'+sid,session_id=sid,chronological_rank=0,date=None,
            turns=turns,raw_sha256=pinned.used[pinned.config['raw_esconv']],dataset='ESConv',family_id=family,
            license='ESConv_academic_research_only',provenance_version=PROTOCOL,source_uri=pinned.config['raw_esconv'],
            transcript_sha256=object_sha256([(t.role,t.text) for t in turns]),source_split='train')
        entries.append(Entry(_source_id(source),source,tuple(range(len(turns))),None,None,'preinstalled_external_snapshot',None))
    return Registry(entries,inputs=pinned.used,folds=folds,excluded_families=excluded,rejected=rejected)


def save(registry, directory):
    directory=Path(directory)
    write_jsonl_once(directory/'sources.jsonl',registry.entries)
    write_json_once(directory/'registry.json',dict(protocol=PROTOCOL,version=registry.version,inputs=registry.inputs,
        folds=registry.folds,excluded_families=sorted(registry.excluded_families),operations=registry.operations,
        rejected=registry.rejected,sources_sha256=file_sha256(directory/'sources.jsonl'),
        counts=dict(Counter(e.source.dataset for e in registry.entries)),
        time_policy='personal ready_at=r+1 logical replay; external dates unknown, preinstalled snapshot',
        license_evidence={'ESConv':'https://github.com/thu-coai/Emotional-Support-Conversation/blob/main/README.md',
                          'EvoEmo':'unknown; preserve existing researcher-authorized engineering scope; no deployment grant'}))


def load(directory):
    directory=Path(directory);meta=json.loads((directory/'registry.json').read_text())
    if meta['protocol']!=PROTOCOL or file_sha256(directory/'sources.jsonl')!=meta['sources_sha256']:
        raise ValueError('registry version/content mismatch')
    entries=[]
    for line in (directory/'sources.jsonl').read_text().splitlines():
        r=json.loads(line)
        for key,cls in [('source',K.SourceSession),('reported_at',K.TimePoint),('ready_at',K.TimePoint)]:
            if r[key] is not None:r[key]=decode_contract(cls,canonical_json(r[key]))
        r['original_turn_indices']=tuple(r['original_turn_indices']); entries.append(Entry(**r))
    reg=Registry(entries,inputs=meta['inputs'],folds=meta['folds'],excluded_families=meta['excluded_families'],
                 rejected=meta['rejected'],operations=meta['operations'])
    if reg.version!=meta['version']:raise ValueError('registry identity mismatch')
    return reg


def changes(previous, current):
    """Administrative ADD/UPDATE/INVALIDATE/NOOP between immutable snapshots.

    UPDATE here means changed source bytes/metadata, never inferred fact change.
    Persist both snapshots; callers must not rewrite the old directory.
    """
    old={} if previous is None else previous.by_session
    new=current.by_session
    result=[]
    for key in sorted(set(old)|set(new)):
        before=old.get(key);after=new.get(key)
        op='ADD' if before is None else 'INVALIDATE' if after is None else 'NOOP' if before==after else 'UPDATE'
        result.append(dict(operation=op,owner_id=key[0],session_id=key[1],
            previous_source_id=None if before is None else before.source_id,
            source_id=None if after is None else after.source_id,
            previous_registry=None if previous is None else previous.version,registry=current.version))
    return result

"""Reuse already materialized development RAW records without opening sealed text.

SourceSession identities are reconstructed and authenticated against each old
ResourceRecord identity. Original raw turn indices are not reconstructed or
claimed: references use the existing registry's zero-based source coordinates.
"""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import json
from .. import contracts as K
from ..io import canonical_json,decode_contract,file_sha256,object_sha256
from ..sources import source_registry as S
from ..bank import bank_v0 as B
from . import memory


@dataclass(frozen=True)
class CachedEntry:
    source_id: str
    source: K.SourceSession
    reported_at: K.TimePoint
    ready_at: K.TimePoint
    availability_scope: str
    fold: int


class DevelopmentRegistry:
    """Bounded input adapter; use the original legality/prefix implementations."""
    context=S.Registry.context
    prefix=S.Registry.prefix
    reason=S.Registry.reason
    visible=S.Registry.visible

    def __init__(self,entries,meta,inputs,allowed):
        self.entries=tuple(entries);self.folds=meta['folds'];self.inputs=inputs
        self.excluded_families=frozenset(meta['excluded_families'])
        self.operations=tuple(meta['operations']);self.rejected=()
        self.allowed=frozenset(allowed)
        self.by_id={e.source_id:e for e in entries}
        self.by_session={(e.source.owner_id,e.source.session_id):e for e in entries}
        if len(self.by_session)!=len(entries):raise ValueError('duplicate source session')
        self.version='dev-cache-sources:'+object_sha256(dict(source_ids=sorted(self.by_id),inputs=inputs,folds=self.folds))

    def entry(self,owner,session):
        if owner not in self.allowed:raise ValueError('owner outside bounded development cache')
        return self.by_session[(owner,session)]


def load_development_cache(*,resources_path,metadata_path,allowed_owners,excluded_owners):
    resources_path,metadata_path=map(Path,(resources_path,metadata_path))
    meta=json.loads(metadata_path.read_text());allowed=set(allowed_owners);excluded=set(excluded_owners)
    folds=meta['folds'];sealed={o for o,f in folds['fold_of_owner'].items() if f==6}
    if allowed & (sealed|excluded):raise ValueError('sealed or excluded source family selected')
    for family in folds['family_groups']:
        if allowed.intersection(family) and not set(family)<=allowed:raise ValueError('source family closure incomplete')
    # Caller must supply an already isolated cache; this function never reads the mixed corpus.
    rows=[json.loads(x) for x in resources_path.read_text().splitlines()]
    if {r['owner_id'] for r in rows}-allowed:raise ValueError('cache is not owner-isolated')
    runtime_uri='project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    entries=[]
    for raw in rows:
        old=decode_contract(K.ResourceRecord,canonical_json(raw));refs=old.source_refs
        if old.head!='MS' or old.view!='raw' or old.writer_identity!=memory.PROTOCOL:raise ValueError('full original RAW cache required')
        if [s.turn_index for s in refs]!=list(range(len(refs))):raise ValueError('cache does not preserve every source turn')
        turns=tuple(K.SourceTurn(turn_index=s.turn_index,role=s.speaker,text=s.exact_quote) for s in refs)
        source=K.SourceSession(owner_id=old.owner_id,session_id=old.parent_session_id,
            chronological_rank=old.source_rank,date=old.reported_at.date,turns=turns,
            raw_sha256=meta['inputs'][runtime_uri],dataset=S.DATASET,family_id=old.family_id,
            license=old.license_scope,provenance_version=S.PROTOCOL,source_uri=runtime_uri,
            transcript_sha256=old.original_raw_identity,source_split=old.source_split,
            excluded_for_overlap=old.family_id in meta['excluded_families'])
        for ref in refs:ref.verify(source)
        e=CachedEntry(S._source_id(source),source,old.reported_at,old.ready_at,'personal_history',folds['fold_of_owner'][old.owner_id])
        authenticated=B._base(e,'MS',old.reading_text,json.loads(old.body),refs,legacy_id=memory.PROTOCOL+':'+source.session_id)
        if authenticated.record_id!=old.record_id:raise ValueError('reconstructed source identity differs from frozen resource')
        entries.append(e)
    for owner in allowed:
        ranks=sorted(e.source.chronological_rank for e in entries if e.source.owner_id==owner)
        if ranks!=list(range(len(ranks))) or not ranks:raise ValueError('owner cache is not a complete contiguous archive')
    inputs={str(resources_path):file_sha256(resources_path),str(metadata_path):file_sha256(metadata_path)}
    return DevelopmentRegistry(entries,meta,inputs,allowed)

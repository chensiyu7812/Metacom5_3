"""Opt-in four-head organization prototype, not a qualified learning backend.

Raw content is retained. Addressable reads have no rank-prefix prerequisite,
2048-token cap, top-k cap, or four-read cap. Only native input capacity is checked.
The original RL1 environment, reward, observation and checkpoints are unchanged.
"""
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from functools import cached_property
import json
import math

from .schema import HEADS, PrefixSpec, digest
from .representation import ROLE_INSTRUCTION, RESOURCE_GUIDANCE_V2
from .representation_direct import DIRECT_INSTRUCTION
from .temporal_evidence_ledger import words

VERSION = "pm-rl1-resource-organization-addressable-v1"
RANKING = "literal-overlap-public-prefix-plus-acquired-v1"


@dataclass(frozen=True)
class OrganizedItem:
    key: str
    head: str
    content: str
    search_text: str
    source_identity: str
    owner_id: str | None = None
    source_rank: int | None = None
    reported_at: str | None = None
    source_ids: tuple[str, ...] = ()
    original_rank: int | None = None
    bge_similarity: float | None = None
    families: tuple[str, ...] = ()
    source_check: str = "unverified"

    @cached_property
    def identity(self):
        return digest(asdict(self))

    @cached_property
    def terms(self):
        return words(self.search_text)


def existing_item(resource, *, rank=None, families=(), source_check="unverified"):
    record = json.loads(resource.content)
    text = record.get("past_report", record.get("full_source_conversation", record.get("ai_action", "")))
    return OrganizedItem(resource.candidate_id,resource.head,resource.content,text,
        digest(dict(source_ids=resource.source_ids,content=resource.content)),
        resource.owner_id,resource.source_rank,resource.source_time,tuple(resource.source_ids),
        rank,resource.similarity,tuple(families),source_check)


class OrganizationCatalog:
    """Construction-domain catalog. Never hand this object to actor/critic."""
    def __init__(self, prefix: PrefixSpec, items, *, provenance_identity):
        if prefix.split not in ("train","dev") or not provenance_identity:
            raise ValueError("bound train/dev construction inputs required")
        self.prefix=prefix
        date.fromisoformat(prefix.timestamp)
        self.provenance_identity=provenance_identity
        self._items={}
        for item in items:
            if (type(item) is not OrganizedItem or not item.key or item.head not in HEADS
                    or not item.content.strip() or not item.source_identity or not item.source_ids):
                raise ValueError("invalid source-bound item")
            if item.bge_similarity is not None and not math.isfinite(item.bge_similarity):
                raise ValueError("invalid original BGE similarity")
            if item.original_rank is not None and (type(item.original_rank) is not int or item.original_rank<1):
                raise ValueError("invalid original rank")
            if item.head != "RS" and (item.owner_id!=prefix.owner_id
                    or type(item.source_rank) is not int or not 0<=item.source_rank<prefix.cutoff_rank
                    or not item.reported_at or item.reported_at>prefix.timestamp):
                raise ValueError("foreign or non-past memory")
            if item.head != "RS":date.fromisoformat(item.reported_at)
            body=json.loads(item.content)
            if body.get("kind")!=item.head:
                raise ValueError("head/body mismatch")
            if item.key in self._items:
                raise ValueError("duplicate resource address")
            self._items[item.key]=item
        self._terms={k:x.terms for k,x in self._items.items()}
        self.identity=digest(dict(version=VERSION,prefix=prefix.identity,provenance=provenance_identity,
                                  items={k:v.identity for k,v in sorted(self._items.items())}))

    def item(self,key):
        return self._items[key]

    def canonical(self,keys):
        if len(keys)!=len(set(keys)):
            raise ValueError("duplicate acquisition")
        return tuple(sorted((self._items[k] for k in keys),key=lambda x:(HEADS.index(x.head),x.key)))

    def rank(self,head,acquired=()):
        if head not in HEADS:raise ValueError("unknown head")
        selected=self.canonical(tuple(acquired))
        # The query has NO unseen candidate text, graph neighbor, future or label.
        query=self.prefix.query+"\n"+"\n".join(x.search_text for x in selected)
        q=words(query)
        selected_keys={x.key for x in selected}
        query_identity=digest(dict(prefix=self.prefix.identity,acquired=[x.identity for x in selected],
                                   method=RANKING,query=query))
        hits=[dict(key=k,ranking_method=RANKING,ranking_score=len(q & self._terms[k]),
                   bge_similarity=x.bge_similarity,original_rank=x.original_rank,
                   query_identity=query_identity)
              for k,x in self._items.items() if x.head==head and k not in selected_keys]
        # No top-k truncation. This is a baseline locator, not semantic fit/reward.
        return sorted(hits,key=lambda x:(-x["ranking_score"],x["key"]))

    def directory(self):
        """Source organization and structural links, not new semantic relations."""
        profile=defaultdict(list);events=[];sessions=[];strategies=defaultdict(list)
        graph=[]
        for key,item in sorted(self._items.items()):
            record=json.loads(item.content)
            for source in item.source_ids:
                graph.append(dict(left=key,relation="has_declared_source",right=source,
                                  semantic_entailment="unverified"))
            if item.head=="MP":
                profile[record["profile_slot"]].append(dict(key=key,reported_at=item.reported_at,
                    current_status=record.get("current_status","unknown"),
                    validity="existing_target_time_view_not_new_reconfirmation"))
            elif item.head=="ME":
                events.append(dict(key=key,reported_at=item.reported_at,event_time=record.get("event_time"),
                    stage=record.get("action_stage","unknown"),outcome=record.get("observed_outcome"),
                    semantic_support="unverified"))
            elif item.head=="MS":
                sessions.append(dict(key=key,reported_at=item.reported_at,source_rank=item.source_rank,
                    full_transcript_identity=digest(record["full_source_conversation"]),
                    summary=None,full_transcript_preserved=True,source_check=item.source_check))
            else:
                for family in item.families or ("unclassified",):strategies[family].append(key)
        return dict(version=VERSION,identity=self.identity,audience="construction_only",
            MP_slots=dict(profile),ME_events=sorted(events,key=lambda x:(x["reported_at"],x["key"])),
            MS_sessions=sorted(sessions,key=lambda x:(x["source_rank"],x["key"])),RS_families=dict(strategies),
            structural_edges=graph,semantic_updates_or_contradictions=[],
            applicability_conditions_created=0,source_texts_truncated=0)


class OrganizedRenderer:
    def __init__(self,*,count_text,count_chat,tokenizer_identity,context_limit):
        if type(context_limit) is not int or context_limit<=0:raise ValueError("native context required")
        self.count_text=count_text;self.count_chat=count_chat;self.context_limit=context_limit
        self.identity=digest(dict(version=VERSION,tokenizer=tokenizer_identity,context_limit=context_limit,
            instructions=[ROLE_INSTRUCTION,DIRECT_INSTRUCTION,RESOURCE_GUIDANCE_V2],
            resource_layout="head-address-content-report-time; canonical head/address order"))

    def block(self,catalog,keys):
        selected=catalog.canonical(tuple(keys))
        if not selected:return ""
        return RESOURCE_GUIDANCE_V2+'<resources>\n'+json.dumps([
            dict(head=x.head,address=x.key,content=x.content,reported_at=x.reported_at) for x in selected],
            ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n</resources>'

    def messages(self,catalog,keys):
        history=json.dumps([dict(speaker=t.role,text=t.content) for t in catalog.prefix.turns[:-1]],
                           ensure_ascii=False,sort_keys=True,separators=(',',':'))
        system=ROLE_INSTRUCTION+'\n'+DIRECT_INSTRUCTION+'\n<quoted_conversation_context>\n'+history+'\n</quoted_conversation_context>'
        block=self.block(catalog,keys)
        if block:system+='\n\n'+block
        return [dict(role='system',content=system),dict(role='user',content=catalog.prefix.turns[-1].content)]

    def usage(self,catalog,keys):
        block=self.block(catalog,keys)
        n=self.count_chat(self.messages(catalog,keys))
        return dict(resource_tokens=self.count_text('\n\n'+block) if block else 0,
                    input_tokens=n,native_context_limit=self.context_limit,
                    native_remaining_tokens=self.context_limit-n,within_native_context=n<self.context_limit,
                    artificial_resource_cap=None,truncation=False)


@dataclass(frozen=True)
class OrganizedObservation:
    current_prefix: tuple
    acquired: tuple
    counts: tuple[int,int,int,int]
    resource_tokens: int
    input_tokens: int
    native_remaining_tokens: int
    stopped: bool


class OrganizationSession:
    """No model, policy, reward or optimization. A future actor needs a new adapter.

    get(head) keeps the four head interface; read(key) is the offline addressable
    inspection primitive. Neither can expose a graph neighbor for free.
    """
    def __init__(self,catalog,renderer):
        self._catalog=catalog;self._renderer=renderer;self._keys=[];self._stopped=False
        if not renderer.usage(catalog,())["within_native_context"]:
            raise ValueError("current prefix exceeds native context; never truncate")

    def read(self,key):
        if self._stopped:raise ValueError("session stopped")
        if key in self._keys:raise ValueError("already acquired")
        self._catalog.item(key)
        proposed=tuple(self._keys)+(key,)
        if not self._renderer.usage(self._catalog,proposed)["within_native_context"]:
            raise ValueError("native context exhausted; item not clipped or acquired")
        self._keys.append(key)
        return self.observe()

    def get(self,head):
        if self._stopped:raise ValueError("session stopped")
        ranked=self._catalog.rank(head,tuple(self._keys))
        if not ranked:raise ValueError("head inventory exhausted")
        # Do not silently skip an oversized top result; make a capacity failure explicit.
        return self.read(ranked[0]["key"])

    def stop(self):
        self._stopped=True
        return self.observe()

    def observe(self):
        selected=self._catalog.canonical(tuple(self._keys))
        usage=self._renderer.usage(self._catalog,tuple(self._keys))
        # No private catalog, owner, graph, ranking hits or unacquired source text.
        return OrganizedObservation(self._catalog.prefix.turns,
            tuple((x.head,x.content,x.reported_at) for x in selected),
            tuple(sum(x.head==h for x in selected) for h in HEADS),
            usage["resource_tokens"],usage["input_tokens"],usage["native_remaining_tokens"],self._stopped)

    def receipt(self):
        return dict(version=VERSION,catalog_identity=self._catalog.identity,
            renderer_identity=self._renderer.identity,acquired=list(self._keys),
            usage=self._renderer.usage(self._catalog,tuple(self._keys)),
            stopped=self._stopped,model_calls=0,reward=None,qualification=None,
            formal_policy_compatible=False,max_gets=None,rank_prefix_required=False)

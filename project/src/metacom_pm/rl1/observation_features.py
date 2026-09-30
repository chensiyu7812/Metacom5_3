"""Engineering bridge from the public Observation to frozen text features.

No EpisodeSpec, inventory, source owner, outcomes or judge records are accepted.
This is not a trained policy or a frozen formal feature specification.
"""
from dataclasses import dataclass
import json
import math
from .schema import Observation, HEADS, digest

AGES = ('not_applicable', 'previous_session', '2_to_4_sessions', '5_plus_sessions')
VERSION = 'rl1-public-observation-features-development-v1'


@dataclass(frozen=True)
class FeatureRecord:
    values: tuple[float, ...]
    action_mask: tuple[bool, ...]
    encoder_identity: str


class ObservedFeatureEncoder:
    def __init__(self, encode_texts, *, embedding_dimension, text_encoder_identity, resource_budget=2048):
        if embedding_dimension < 1 or resource_budget <= 0 or not text_encoder_identity:
            raise ValueError('explicit encoder and budget required')
        self.encode_texts = encode_texts
        self.dimension = embedding_dimension
        self.budget = resource_budget
        self.identity = digest(dict(version=VERSION, text_encoder=text_encoder_identity,
            embedding_dimension=embedding_dimension, budget=resource_budget,
            scaling='fixed counts/4, tokens/B, log1p remaining_items; no fitted normalization',
            metadata_slots=16, acquired_slots=4, ages=AGES))
        self._cache = {}

    @property
    def feature_dimension(self):
        # 5 embeddings; acquired presence/type/rank; counts/remaining items;
        # remaining budget/horizon; 16 candidate slots with presence/sim/tokens/age.
        return 5*self.dimension + 4*6 + 4 + 4 + 2 + 16*7

    def encode(self, observation):
        if type(observation) is not Observation:
            raise TypeError('only the public Observation is accepted')
        o = observation
        if (len(o.counts)!=4 or any(type(n) is not int or not 0<=n<=4 for n in o.counts)
                or sum(o.counts)>4 or len(o.acquired)!=sum(o.counts)
                or len(o.action_mask)!=5 or any(type(x) is not bool for x in o.action_mask)
                or not any(o.action_mask) or not o.current_prefix or o.current_prefix[-1].role!='seeker'
                or len(o.metadata)!=4 or any(len(h)!=4 for h in o.metadata)
                or len(o.remaining_items)!=4 or any(type(n) is not int or n<0 for n in o.remaining_items)
                or o.remaining_gets!=4-sum(o.counts) or not 0<=o.remaining_tokens<=self.budget):
            raise ValueError('invalid public acquisition observation')
        acquired = sorted(o.acquired,key=lambda a:(HEADS.index(a.head),a.rank))
        if [(a.head,a.rank) for a in acquired] != [(h,r) for h,n in zip(HEADS,o.counts) for r in range(1,n+1)]:
            raise ValueError('acquired set/count/rank mismatch')
        texts = ['\n'.join(f'{t.role}: {t.content}' for t in o.current_prefix)] + [
            json.dumps(dict(head=a.head,rank=a.rank,source_time=a.source_time,content=a.content),
                       ensure_ascii=False,sort_keys=True) for a in acquired]
        # Only strings in the currently visible observation may populate/cache
        # vectors. An existing vector cannot reveal an unacquired item.
        missing = list(dict.fromkeys(t for t in texts if t not in self._cache))
        if missing:
            vectors = self.encode_texts(missing)
            if len(vectors)!=len(missing): raise ValueError('encoder row count differs')
            for text, vector in zip(missing,vectors):
                if len(vector)!=self.dimension or not all(math.isfinite(x) for x in vector):
                    raise ValueError('invalid frozen text embedding')
                self._cache[text] = tuple(float(x) for x in vector)
        values = [x for t in texts for x in self._cache[t]] + [0.]*(4-len(acquired))*self.dimension
        for index in range(4):
            a = acquired[index] if index<len(acquired) else None
            values += [float(a is not None)] + [float(a is not None and a.head==h) for h in HEADS] + [a.rank/4 if a else 0.]
        values += [n/4 for n in o.counts] + [math.log1p(n) for n in o.remaining_items]
        values += [o.remaining_tokens/self.budget,o.remaining_gets/4]
        for head in o.metadata:
            for rank,m in enumerate(head,1):
                if m is None:
                    values += [0.]*7
                else:
                    if m.rank!=rank or m.coarse_age not in AGES or m.raw_tokens<0 or not math.isfinite(m.similarity):
                        raise ValueError('invalid public metadata')
                    values += [1.,m.similarity,m.raw_tokens/self.budget] + [float(m.coarse_age==age) for age in AGES]
        if len(values)!=self.feature_dimension or not all(math.isfinite(x) for x in values):
            raise ValueError('invalid feature shape or values')
        return FeatureRecord(tuple(values),o.action_mask,self.identity)


def make_actor_critic(feature_dimension):
    """128-wide projection + two hidden layers; weights untrained by default."""
    import torch
    from torch import nn
    from torch.distributions import Categorical

    class PublicActorCritic(nn.Module):
        def __init__(self):
            super().__init__()
            self.body=nn.Sequential(nn.Linear(feature_dimension,128),nn.Tanh(),
                nn.Linear(128,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh())
            self.policy=nn.Linear(128,5);self.value=nn.Linear(128,1)

        def forward(self,features,masks):
            if features.shape[-1]!=feature_dimension or masks.shape[-1]!=5 or not masks.any(dim=-1).all():
                raise ValueError('invalid public features/action mask')
            hidden=self.body(features)
            return Categorical(logits=self.policy(hidden).masked_fill(~masks,-torch.inf)),self.value(hidden).squeeze(-1)

    return PublicActorCritic()

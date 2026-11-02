"""Full visible-text chunk plans and a provisional variable-read feature bridge.

No model loader. The caller supplies tokenizer operations and, separately,
identity-bound vectors for ALL planned chunks. Native encoder windows segment
text, never delete its tail. Pooling is a versioned development choice.
"""
from dataclasses import asdict
import json
import math

from .organized_policy_interface import validate_observation
from .schema import HEADS, digest

VERSION = 'pmrl1-organized-full-text-features-dev-v1'


class FullTextFeatures:
    def __init__(self, *, encode_tokens, add_special_tokens, native_window,
                 special_tokens, tokenizer_identity, encoder_identity, dimension):
        if (type(native_window) is not int or type(special_tokens) is not int
                or not 0 <= special_tokens < native_window or type(dimension) is not int
                or dimension < 1 or not tokenizer_identity or not encoder_identity):
            raise ValueError('explicit native tokenizer/encoder contract required')
        self.encode_tokens, self.add_special_tokens = encode_tokens, add_special_tokens
        self.window, self.special = native_window, special_tokens
        self.dimension = dimension
        self.encoder_identity = encoder_identity
        self.identity = digest(dict(version=VERSION, tokenizer=tokenizer_identity,
            encoder=encoder_identity, native_window=native_window, special_tokens=special_tokens,
            dimension=dimension, chunk_pool='payload-token-weighted mean', head_pool='mean of all acquired resources',
            scaling='log1p counts/tokens; native context fractions', status='DEVELOPMENT_NOT_FORMAL_FREEZE'))

    @property
    def feature_dimension(self):
        return 5*self.dimension + 4 + 4 + 4 + 4 + 3

    def plan(self, observation):
        validate_observation(observation)
        if observation.stopped:
            raise ValueError('terminal observation is not a policy input')
        texts = [('prefix', '\n'.join(f'{t.role}: {t.content}' for t in observation.current_prefix))]
        if observation.body_visible:
            texts += [(a.head, json.dumps(asdict(a), ensure_ascii=False, sort_keys=True)) for a in observation.acquired]
        docs = []
        for group, text in texts:
            ids = tuple(self.encode_tokens(text))
            if not ids or any(type(x) is not int or x < 0 for x in ids):
                raise ValueError('untruncated nonempty tokenizer IDs required')
            chunks = []
            width = self.window-self.special
            for start in range(0, len(ids), width):
                end = min(len(ids), start+width)
                payload = ids[start:end]
                encoded = tuple(self.add_special_tokens(list(payload)))
                if (len(encoded) != len(payload)+self.special or len(encoded) > self.window
                        or any(type(x) is not int or x < 0 for x in encoded)
                        or not any(encoded[i:i+len(payload)] == payload for i in range(self.special+1))):
                    raise ValueError('native token window/special-token contract mismatch')
                chunks.append(dict(start_token=start, end_token=end, input_ids=list(encoded)))
            docs.append(dict(group=group, text_identity=digest(text), payload_ids=list(ids), chunks=chunks))
        body = dict(version=VERSION, feature_identity=self.identity,
            observation_identity=digest(asdict(observation)), documents=docs,
            body_visible=observation.body_visible, native_window=self.window)
        return dict(**body, identity=digest(body))

    def assemble(self, observation, plan, *, vectors, encoder_feature_identity):
        validate_observation(observation)
        # Reject stale observations, edited offsets, dropped tails, or another
        # tokenizer/NoText view before any vector is used.
        if plan != self.plan(observation) or encoder_feature_identity != self.identity:
            raise ValueError('feature plan/encoding identity mismatch')
        chunks = [c for d in plan['documents'] for c in d['chunks']]
        if len(vectors) != len(chunks) or any(len(v) != self.dimension or any(not math.isfinite(x) for x in v) for v in vectors):
            raise ValueError('one finite embedding for every chunk required')
        groups = {h: [] for h in ('prefix', *HEADS)}
        cursor = 0
        for d in plan['documents']:
            sizes = [c['end_token']-c['start_token'] for c in d['chunks']]
            total = sum(sizes)
            group_vector = tuple(sum(vectors[cursor+i][j]*n for i, n in enumerate(sizes))/total for j in range(self.dimension))
            cursor += len(sizes)
            groups[d['group']].append(group_vector)
        values = []
        for h in ('prefix', *HEADS):
            vs = groups[h]
            values.extend(sum(v[j] for v in vs)/len(vs) if vs else 0. for j in range(self.dimension))
        values += [math.log1p(n) for n in observation.counts]
        values += [math.log1p(n) for n in observation.remaining_items]
        values += [float(n is not None) for n in observation.next_input_tokens]
        values += [n/observation.native_context_limit if n is not None else 0. for n in observation.next_input_tokens]
        values += [math.log1p(observation.resource_tokens), observation.input_tokens/observation.native_context_limit,
                   (observation.native_context_limit-observation.input_tokens)/observation.native_context_limit]
        if len(values) != self.feature_dimension or any(not math.isfinite(x) for x in values):
            raise ValueError('invalid pooled features')
        return dict(values=tuple(values), action_mask=observation.action_mask,
            encoder_identity=self.identity, plan_identity=plan['identity'],
            encoded_chunks=len(chunks), encoded_payload_tokens=sum(len(d['payload_ids']) for d in plan['documents']),
            reward=None, trained=False)

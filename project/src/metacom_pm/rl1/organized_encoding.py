"""Encode complete token blocks with the pinned BGE forward path.

No loader or text re-tokenization. An authorized caller supplies an already
loaded SentenceTransformer; synthetic tests supply a tiny forward double.
Successful content-addressed blocks survive restarts. Unknown invocations are
not retried automatically. The actor receives pooled public features only.
"""
from contextlib import contextmanager
from dataclasses import asdict
import json
import math
from pathlib import Path
import sqlite3
import time

import torch

from .organized_features import FullTextFeatures
from .schema import digest

VERSION = 'pmrl1-organized-token-block-forward-v1'


def tokenizer_identity(tokenizer):
    """Bind the actual tokenizer implementation/state, not its directory name."""
    return digest(dict(backend=json.loads(tokenizer.backend_tokenizer.to_str()),
        specials=tokenizer.special_tokens_map,padding_side=tokenizer.padding_side,
        model_max_length=tokenizer.model_max_length,
        special_tokens=tokenizer.num_special_tokens_to_add(pair=False)))


def encoder_identity(binding, runtime, tokenizer_id):
    return digest(dict(version=VERSION,binding=binding,runtime=runtime,
        tokenizer_identity=tokenizer_id,input='complete-token-blocks-with-specials',
        pooling='original sentence-transformer CLS then float32 L2 normalization'))


def forward_blocks(model, blocks, *, native_window, dimension, pad_token_id):
    """Existing ST module pipeline (CLS pooling), followed by original L2 norm.

    IDs already include specials. Padding only; no decode/re-encode, truncate,
    prompt insertion, length sorting or loss of the last block.
    """
    if (not blocks or any(not b or len(b) > native_window or
            any(type(i) is not int or i < 0 for i in b) for b in blocks)):
        raise ValueError('nonempty complete native-window token blocks required')
    if type(pad_token_id) is not int or pad_token_id < 0:
        raise ValueError('explicit tokenizer padding token required')
    width = max(map(len, blocks))
    ids = torch.tensor([list(b)+[pad_token_id]*(width-len(b)) for b in blocks],
                       dtype=torch.long, device=model.device)
    mask = torch.tensor([[1]*len(b)+[0]*(width-len(b)) for b in blocks],
                        dtype=torch.long, device=model.device)
    model.eval()
    with torch.inference_mode():
        output = model({'input_ids': ids, 'attention_mask': mask})['sentence_embedding']
        if (output.shape != (len(blocks), dimension) or not torch.isfinite(output).all()
                or (output.norm(dim=1) == 0).any()):
            raise ValueError('invalid BGE forward output')
        vectors = torch.nn.functional.normalize(output.float(), p=2, dim=1)
    return vectors.cpu().tolist()


class LoadedBGEBlocks:
    """Production adapter; construction never loads model weights.

    Use the existing verified bge_m3._load_model in the authorized worker, then
    pass its model/runtime here. Binding checks do not grant loading permission.
    """
    def __init__(self, model, *, binding, runtime, expected_tokenizer_identity):
        from metacom_pm.paper1.embeddings.bge_m3 import (
            FROZEN_BGE_M3_BINDING, _normalized_pooling_mode)
        if binding != FROZEN_BGE_M3_BINDING:
            raise ValueError('original pinned BGE binding required')
        if (_normalized_pooling_mode(model[1].get_config_dict()) != binding.pooling_mode
                or model.max_seq_length != binding.max_seq_length
                or str(next(model[0].auto_model.parameters()).dtype) != binding.dtype
                or runtime.weights_sha256_verified != binding.model_safetensors_sha256):
            raise ValueError('loaded BGE weights/pooling/window/dtype changed')
        actual = tokenizer_identity(model.tokenizer)
        if actual != expected_tokenizer_identity:
            raise ValueError('actual loaded tokenizer changed')
        self.model = model
        self.window, self.dimension = binding.max_seq_length, binding.embedding_dimension
        self.pad = model.tokenizer.pad_token_id
        self.identity = encoder_identity(asdict(binding),asdict(runtime),actual)

    def __call__(self, blocks):
        return forward_blocks(self.model, blocks, native_window=self.window,
                              dimension=self.dimension, pad_token_id=self.pad)


class BlockCache:
    """Durable exact-input vector cache with one claim per unknown block.

    Batch size limits memory use, not visible resource length. No OOM retry.
    Runtime exceptions leave STARTED rows for explicit reconciliation.
    """
    def __init__(self, path, *, encoder_identity, dimension, native_window):
        if not encoder_identity or dimension < 1 or native_window < 1:
            raise ValueError('bound block encoder required')
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.encoder_identity = encoder_identity
        self.dimension, self.window = dimension, native_window
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS blocks '
                       '(id TEXT PRIMARY KEY, payload TEXT, state TEXT, vector TEXT, vector_identity TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS invocations '
                       '(id TEXT PRIMARY KEY, request TEXT, result TEXT)')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path, timeout=30)
        try:
            con.execute('PRAGMA synchronous=FULL'); con.execute('BEGIN IMMEDIATE')
            yield con; con.commit()
        except BaseException:
            con.rollback(); raise
        finally:
            con.close()

    def _payload(self, block):
        if (not block or len(block) > self.window or
                any(type(i) is not int or i < 0 for i in block)):
            raise ValueError('invalid complete block')
        return dict(version=VERSION, encoder_identity=self.encoder_identity,
                    dimension=self.dimension, native_window=self.window, input_ids=list(block))

    def encode(self, blocks, *, invoke, encoder_identity, batch_size=1):
        if encoder_identity != self.encoder_identity or type(batch_size) is not int or batch_size < 1:
            raise ValueError('encoder identity or memory batch size mismatch')
        payloads = [self._payload(b) for b in blocks]
        unique = {digest(p):p for p in payloads}; values = {}; missing = []
        with self.db() as db:
            for key,payload in unique.items():
                row = db.execute('SELECT payload,state,vector,vector_identity FROM blocks WHERE id=?', (key,)).fetchone()
                if row is None:
                    missing.append(key); continue
                if json.loads(row[0]) != payload:
                    raise ValueError('cached block identity changed')
                if row[1] != 'SETTLED':
                    raise ValueError('unknown block invocation; reconcile before reuse')
                vector = json.loads(row[2]); self._validate([vector], 1)
                if digest(vector) != row[3]:raise ValueError('cached vector changed')
                values[key] = vector
        calls = 0; seconds = 0.
        for offset in range(0, len(missing), batch_size):
            keys = missing[offset:offset+batch_size]
            request = dict(encoder_identity=self.encoder_identity, blocks=keys)
            call = digest(request)
            with self.db() as db:
                # A racing worker must not issue a second forward.
                for key in keys:
                    db.execute('INSERT INTO blocks VALUES (?,?,?,NULL,NULL)',
                               (key,json.dumps(unique[key],sort_keys=True),'STARTED'))
                db.execute('INSERT INTO invocations VALUES (?,?,NULL)', (call,json.dumps(request)))
            start = time.monotonic()
            # Model construction/forward must not perturb CPU policy sampling.
            with torch.random.fork_rng(devices=[]):
                vectors = invoke([unique[k]['input_ids'] for k in keys])
            elapsed = time.monotonic()-start
            self._validate(vectors, len(keys))
            with self.db() as db:
                for key,vector in zip(keys,vectors):
                    db.execute('UPDATE blocks SET state=?,vector=?,vector_identity=? WHERE id=? AND state=?',
                               ('SETTLED',json.dumps(vector,allow_nan=False),digest(vector),key,'STARTED'))
                    values[key] = vector
                db.execute('UPDATE invocations SET result=? WHERE id=?',
                           (json.dumps(dict(seconds=elapsed,vector_identity=digest(vectors))),call))
            calls += 1; seconds += elapsed
        return [values[digest(p)] for p in payloads], dict(
            requested_blocks=len(payloads), unique_blocks=len(unique),
            cached_unique_blocks=len(unique)-len(missing), new_blocks=len(missing),
            new_input_tokens=sum(len(unique[k]['input_ids']) for k in missing),
            physical_forward_batches=calls, forward_seconds=seconds)

    def _validate(self, vectors, n):
        if (len(vectors) != n or any(len(v) != self.dimension or
                any(type(x) not in (int,float) or not math.isfinite(x) for x in v) for v in vectors)):
            raise ValueError('one finite vector per complete block required')


class EncodedHeadView:
    """Drop-in sequential feature interface for the existing actor/PPO tensors."""
    def __init__(self, planner, cache, *, invoke, encoder_identity, without_text=False, batch_size=1):
        if type(planner) is not FullTextFeatures or type(without_text) is not bool:
            raise ValueError('full-text planner and explicit text visibility required')
        if (cache.encoder_identity != encoder_identity or cache.dimension != planner.dimension
                or cache.window != planner.window or planner.encoder_identity != encoder_identity):
            raise ValueError('planner/cache/physical encoder mismatch')
        self.planner, self.cache, self.invoke = planner, cache, invoke
        self.encoder_identity, self.batch_size = encoder_identity, batch_size
        self.no_text = without_text; self.last_receipt = None
        self.identity = digest(dict(version=VERSION, planner=planner.identity,
                                    encoder=encoder_identity, no_text=without_text))
        self.feature_dimension = planner.feature_dimension

    def sequential(self, observation):
        if observation.body_visible == self.no_text:
            raise ValueError('persistent NoText view/observation mismatch')
        plan = self.planner.plan(observation)
        blocks = [c['input_ids'] for d in plan['documents'] for c in d['chunks']]
        vectors, stats = self.cache.encode(blocks, invoke=self.invoke,
            encoder_identity=self.encoder_identity, batch_size=self.batch_size)
        features = self.planner.assemble(observation,plan,vectors=vectors,
                                        encoder_feature_identity=self.planner.identity)
        self.last_receipt = dict(stats, view_identity=self.identity, plan_identity=plan['identity'])
        return features['values'], features['action_mask']

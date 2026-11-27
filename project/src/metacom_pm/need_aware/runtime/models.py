"""Generator bindings for NAA runs and native-tokenizer capacity checks.

Model identities come from files on this server (A's inventory hashes), not from
memory. Importing this module never imports torch/transformers; NativeTokenizer
loads only the tokenizer (CPU) when constructed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

from ..data.contracts import digest

BINDING_VERSION = 'naa-generator-binding-v1'
BACKEND_CONTEXT_CAP = 16384     # backend max_model_len shared by both models (G0e runtime)
COMMON_INPUT_CAP = 12000        # A/B proposal: common native-token input cap
MAX_NEW_TOKENS = 1024           # MCQ reasoning + final answer


@dataclass(frozen=True)
class ModelSpec:
    label: str
    model_id: str
    revision: str
    path: str
    architecture: str
    model_class: str
    license: str
    eos_token_id: tuple
    pad_token_id: int
    suppress_tokens: tuple = ()
    generation_config_file: bool = True
    files_sha256: dict = field(default_factory=dict)

    def decode(self, max_new_tokens=MAX_NEW_TOKENS):
        # Greedy, single beam, no sampling: identical policy for every arm of one model.
        return dict(do_sample=False, num_beams=1, seed=0, enable_thinking=False,
                    max_new_tokens=max_new_tokens, eos_token_id=list(self.eos_token_id),
                    pad_token_id=self.pad_token_id, repetition_penalty=1.0,
                    suppress_tokens=list(self.suppress_tokens))

    @property
    def g_id(self):
        d = asdict(self)
        return f'naag:{self.label}:' + digest(dict(version=BINDING_VERSION, spec=d, cap=BACKEND_CONTEXT_CAP))


G0E = ModelSpec(
    label='G0e', model_id='google/gemma-4-12B-it', revision='707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7',
    path='/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3',
    architecture='Gemma4UnifiedForConditionalGeneration', model_class='AutoModelForMultimodalLM',
    license='apache-2.0', eos_token_id=(1, 106, 50), pad_token_id=0, suppress_tokens=(258883, 258882))

QWEN35 = ModelSpec(
    label='Qwen35', model_id='Qwen/Qwen3.5-9B', revision='c202236235762e1c871ad0ccb60c8ee5ba337b9a',
    path='/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b',
    architecture='Qwen3_5ForConditionalGeneration', model_class='AutoModelForMultimodalLM',
    license='apache-2.0', eos_token_id=(248046, 248044), pad_token_id=248044, generation_config_file=False)

MODELS = {m.label: m for m in (G0E, QWEN35)}


def bind_inventory(spec, inventory_path):
    """Attach A's measured file hashes; refuse silent substitution."""
    inv = json.loads(Path(inventory_path).read_text())
    row = next(m for m in inv['models'] if m['label'] == spec.label)
    if (row['model_id'], row['revision'], row['path']) != (spec.model_id, spec.revision, spec.path):
        raise ValueError('model identity differs from A inventory: ' + spec.label)
    if row['architecture'] != [spec.architecture]:
        raise ValueError('architecture differs from inventory')
    files = {f['name']: f['sha256'] for f in row['files']}
    return ModelSpec(**{**asdict(spec), 'eos_token_id': tuple(spec.eos_token_id),
                        'suppress_tokens': tuple(spec.suppress_tokens), 'files_sha256': files})


class NativeTokenizer:
    """The model's own tokenizer + chat template (CPU only)."""

    def __init__(self, spec):
        from transformers import AutoTokenizer
        self.spec = spec
        self.tok = AutoTokenizer.from_pretrained(spec.path, local_files_only=True, trust_remote_code=False)

    def chat_ids(self, messages):
        ids = self.tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                           enable_thinking=False, return_dict=False)
        return [int(x) for x in ids]

    def count(self, text):
        return len(self.tok(text, add_special_tokens=False)['input_ids'])

    def check_special(self):
        """eos/pad ids must decode to the tokenizer's actual end tokens."""
        names = {i: self.tok.convert_ids_to_tokens(i) for i in (*self.spec.eos_token_id, self.spec.pad_token_id)}
        return names


def capacity(input_ids, decode, *, input_cap=COMMON_INPUT_CAP, backend_cap=BACKEND_CONTEXT_CAP):
    n = len(input_ids)
    return dict(input_tokens=n, input_cap=input_cap, backend_cap=backend_cap,
                fits=n <= input_cap and n + decode['max_new_tokens'] <= backend_cap)

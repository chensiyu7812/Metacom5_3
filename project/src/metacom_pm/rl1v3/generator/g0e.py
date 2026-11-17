"""Initial engineering generator binding. No model import/load or generation.

G0e is a CPU-pinned candidate for B6e, not A7's research G0. A backend change
creates a new g_id; it cannot reuse responses from the tokenizer-only replay.
"""
from dataclasses import dataclass
from pathlib import Path
import json

from ..io import canonical_json, file_sha256, object_sha256
from .preflight import PROMPT

PROTOCOL = "pmrl1v3-g0e-1"
CONFIG = "project/configs/rl1v3/G0e.json"
SYSTEM = PROMPT  # Preserve A0's 100 OFF payloads; no outcome-selected prompt.
SYSTEM_VERSION = "pmrl1v3-support-B0-1"
STEP2 = "pmrl1v3-g0e-no-plan-1"
RENDERER = "pmrl1v3-g0e-notes-renderer-1"
DECODE = dict(do_sample=False, num_beams=1, seed=0, enable_thinking=False,
              max_new_tokens=320, eos_token_id=[1, 106, 50], pad_token_id=0,
              repetition_penalty=1.0, suppress_tokens=[258883, 258882])


@dataclass(frozen=True)
class Binding:
    """Canonical immutable JSON, with copies returned to callers."""
    spec_json: str

    def __post_init__(self):
        s = self.spec
        if s['protocol'] != PROTOCOL or s['scope'] != 'engineering_only':
            raise ValueError('unsupported G0e binding')
        if s['system_prompt'] != SYSTEM or s['step2_id'] != STEP2 or s['decode'] != DECODE:
            raise ValueError('G0e prompt/Step-2/decode differs from this protocol')
        if s['model']['model_id'] != 'Gemma-4-12B-it-707f0a3':
            raise ValueError('model substitution requires a separately reviewed version')
        if not 320 < s['runtime']['max_model_len'] <= s['model']['native_context_tokens']:
            raise ValueError('invalid runtime context budget')
        if s['runtime']['backend'] not in ('hf', 'vllm'):
            raise ValueError('unsupported backend')
        object.__setattr__(self, 'spec_json', canonical_json(s))

    @property
    def spec(self): return json.loads(self.spec_json)
    @property
    def g_id(self):
        s = self.spec
        return 'G0e:' + object_sha256({k:s[k] for k in ('protocol','model','runtime','output_policy')})
    @property
    def decode_id(self): return 'decode:' + object_sha256(self.spec['decode'])
    @property
    def renderer_id(self):
        s = self.spec
        return 'renderer:' + object_sha256(dict(protocol=RENDERER, system=s['system_prompt'],
            system_version=SYSTEM_VERSION, implementation=s['renderer_implementation_sha256'],
            tokenizer=s['tokenizer_identity'], order='RS,MP,ME,MS', escaping='html-resource-data',
            add_generation_prompt=True, enable_thinking=False, output_reserve_tokens=320))
    @property
    def identity(self):
        return dict(g_id=self.g_id, decode_id=self.decode_id, step2_id=STEP2, renderer_id=self.renderer_id)
    @property
    def sha256(self): return object_sha256(self.spec)


def load_binding(root=None, *, backend='hf', verify_local_files=True):
    root = Path(root) if root else Path(__file__).resolve().parents[5]
    cfg = json.loads((root/CONFIG).read_text())
    spec = dict(cfg['common'], runtime=cfg['runtimes'][backend])
    binding = Binding(canonical_json(spec))
    if verify_local_files:
        verify_artifacts(binding, root=root, model_path=Path(cfg['model_path']))
    return binding


def verify_artifacts(binding, *, root, model_path):
    """Rehash small configuration/tokenizer files only; stat preserved weights.

    Weight SHA is the existing A0/A1_reuse byte attestation, not a new hash
    measurement. Execution must freshly verify weight SHA before model load.
    """
    s = binding.spec
    audit = json.loads((Path(root)/s['model']['attestation_path']).read_text())
    if file_sha256(Path(root)/s['model']['attestation_path']) != s['model']['attestation_sha256']:
        raise ValueError('model byte-attestation file changed')
    prior = audit['models']['g0_candidate']['files']
    for name, expected in s['model']['files'].items():
        p = Path(model_path)/name
        if prior.get(name) != expected or p.stat().st_size != expected['bytes']:
            raise ValueError('model file/attestation mismatch: '+name)
        if not name.endswith('.safetensors') and file_sha256(p) != expected['sha256']:
            raise ValueError('model configuration/tokenizer mismatch: '+name)
    renderer = Path(root)/'project/src/metacom_pm/rl1v3/render/request_packet.py'
    if file_sha256(renderer) != s['renderer_implementation_sha256']:
        raise ValueError('renderer code differs; create a new binding')
    return dict(weights_loaded=False, weight_hash_reused=True, weight_stat_checked=True,
                fresh_weight_hash=False, nonweight_hashes_verified=True)

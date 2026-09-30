"""Source-scoped generation identity for subsequent training runs.

The original smoke/pilot protocol remains replayable in env.py/generation.py.
Its prompt-identical cache is not promoted to the stronger training identity.
Model-visible messages are unchanged: coordinator provenance never enters G.
"""
from dataclasses import asdict
from pathlib import Path

from metacom_pm.io import sha256_file
from .env import ResourceEnv
from .generation import LocalNaturalGenerator
from .schema import digest

PROTOCOL = "pm-rl1-source-scoped-generation-v2"


class BoundResourceEnv(ResourceEnv):
    def __init__(self, spec, renderer):
        super().__init__(spec, renderer)
        self._binding = digest(dict(base_binding=self._binding, generation_protocol=PROTOCOL))
        self._inventory_identity = digest([[asdict(r) for r in head] for head in spec.inventory])

    def _request(self, counts):
        old = super()._request(counts)
        payload = {k: v for k, v in old.items() if k != "request_id"}
        payload["provenance"] = dict(protocol=PROTOCOL,
            prefix_identity=self._spec.prefix.identity,
            # This includes source rank/time/IDs, full resource content, frozen
            # rank metadata and selected canonical counts, including for OFF.
            inventory_identity=self._inventory_identity,
            retrieval_identity=self._spec.retrieval_identity,
            canonical_counts=list(counts))
        return dict(request_id=digest(payload), **payload)


def validate_and_project(request, runtime_identity):
    expected = {"request_id", "messages", "executor_identity", "draw_identity", "renderer_identity", "provenance"}
    if set(request) != expected or request["executor_identity"] != runtime_identity:
        raise ValueError("source-scoped generation request/runtime mismatch")
    payload = {k: v for k, v in request.items() if k != "request_id"}
    if request["request_id"] != digest(payload):
        raise ValueError("complete provenance-bound request identity mismatch")
    provenance = request["provenance"]
    if set(provenance) != {"protocol", "prefix_identity", "inventory_identity", "retrieval_identity", "canonical_counts"}:
        raise ValueError("incomplete source provenance")
    if provenance["protocol"] != PROTOCOL:
        raise ValueError("unknown generation protocol")
    if any(not isinstance(provenance[k], str) or not provenance[k] for k in ("prefix_identity", "inventory_identity", "retrieval_identity")):
        raise ValueError("missing source binding")
    counts = provenance["canonical_counts"]
    if not isinstance(counts, list) or len(counts) != 4 or any(type(x) is not int or not 0 <= x <= 4 for x in counts) or sum(counts) > 4:
        raise ValueError("invalid canonical resource plan")
    visible = {k: request[k] for k in ("messages", "executor_identity", "draw_identity", "renderer_identity")}
    return dict(request_id=digest(visible), **visible)


class BoundNaturalGenerator(LocalNaturalGenerator):
    def __init__(self, model_dir, **kwargs):
        super().__init__(model_dir, **kwargs)
        self.manifest.update(request_protocol=PROTOCOL, binding_code_sha256=sha256_file(Path(__file__)))
        self.identity = digest(self.manifest)

    def generate(self, request):
        visible = validate_and_project(request, self.identity)
        result = super().generate(visible)
        result["request_id"] = request["request_id"]
        result["source_provenance_identity"] = digest(request["provenance"])
        return result

"""Local natural-end generation, without a task-specific response token cap.

The native context remainder is an unavoidable model bound. Hitting it is not
a completed answer. The watchdog is cooperative between decoding steps, not a
claim that a hung CUDA kernel can be cancelled here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.metadata
import os
from pathlib import Path
import time

from metacom_pm.io import sha256_file
from .schema import digest


@dataclass(frozen=True)
class NaturalEndPolicy:
    context_limit: int
    eos_token_ids: tuple[int, ...]
    timeout_seconds: float = 300.0
    cycle_width: int = 32
    cycle_repetitions: int = 4

    def __post_init__(self):
        if self.context_limit <= 0 or not self.eos_token_ids or self.timeout_seconds <= 0:
            raise ValueError("invalid natural-end policy")
        if self.cycle_width < 1 or self.cycle_repetitions < 2:
            raise ValueError("invalid loop watchdog")

    def generation_kwargs(self, input_tokens: int) -> dict:
        remaining = self.context_limit - input_tokens
        if input_tokens <= 0 or remaining <= 0:
            raise ValueError("prompt exhausts native context")
        return dict(max_new_tokens=remaining, do_sample=False, num_beams=1,
                    temperature=None, top_p=None, top_k=None, min_length=0,
                    min_new_tokens=None, forced_eos_token_id=None,
                    eos_token_id=list(self.eos_token_ids), use_cache=True)

    def finish_reason(self, tokens: list[int], input_tokens: int, watchdog: str | None) -> str:
        # A genuine model EOS at the last available position remains a natural
        # end; no forced EOS is installed by generation_kwargs.
        if tokens and tokens[-1] in self.eos_token_ids:
            return "natural_stop"
        if watchdog:
            return watchdog
        if len(tokens) >= self.context_limit - input_tokens:
            return "context_exhausted"
        return "unexpected_stop"


class LocalNaturalGenerator:
    """Single visible CUDA device, local files only. No provider/API fallback."""
    def __init__(self, model_dir: Path, *, minimum_free_gib: float = 18):
        import torch
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, GenerationConfig

        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("bind exactly one CUDA device explicitly")
        free, _ = torch.cuda.mem_get_info(0)
        if free < minimum_free_gib * 1024 ** 3:
            raise RuntimeError("insufficient free GPU memory; no device fallback")
        start = time.monotonic()
        config = AutoConfig.from_pretrained(model_dir, local_files_only=True)
        gc = GenerationConfig.from_pretrained(model_dir, local_files_only=True)
        eos = gc.eos_token_id
        self.policy = NaturalEndPolicy(config.max_position_embeddings,
                                       tuple(eos if isinstance(eos, list) else [eos]))
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        self.manifest = dict(protocol="pm-rl1-natural-end-v1", model_dir=str(model_dir.resolve()),
            model_files={p.name: sha256_file(p) for p in sorted(model_dir.iterdir())
                         if p.is_file() and p.suffix in (".json", ".safetensors")},
            packages={p: importlib.metadata.version(p) for p in ("torch", "transformers", "tokenizers")},
            gpu=torch.cuda.get_device_name(0), gpu_uuid=str(torch.cuda.get_device_properties(0).uuid)
                if hasattr(torch.cuda.get_device_properties(0), "uuid") else "not_exposed",
            cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
            cuda_device_order=os.environ.get("CUDA_DEVICE_ORDER"),
            cuda_version=torch.version.cuda, dtype="bfloat16", attention="sdpa",
            policy=asdict(self.policy), seed=0, adapter=None,
            code_sha256=sha256_file(Path(__file__)),
            chat_template_sha256=digest(self.tokenizer.chat_template))
        self.identity = digest(self.manifest)
        torch.manual_seed(0)
        self.model = AutoModelForCausalLM.from_pretrained(model_dir, torch_dtype=torch.bfloat16,
                    attn_implementation="sdpa", local_files_only=True).to("cuda:0").eval()
        self.load_seconds = time.monotonic() - start

    def generate(self, request: dict) -> dict:
        import torch
        from transformers import GenerationConfig, StoppingCriteria, StoppingCriteriaList

        payload = {k: request[k] for k in ("messages", "executor_identity", "draw_identity", "renderer_identity")}
        if request["request_id"] != digest(payload) or request["executor_identity"] != self.identity:
            raise ValueError("request/runtime identity mismatch")
        inputs = self.tokenizer.apply_chat_template(request["messages"], tokenize=True,
                    add_generation_prompt=True, return_tensors="pt").to("cuda:0")
        n = inputs.shape[-1]
        kwargs = self.policy.generation_kwargs(n)
        policy = self.policy
        started = time.monotonic()

        class Watchdog(StoppingCriteria):
            reason = None

            def __call__(self, input_ids, scores, **unused):
                tail = input_ids[0, n:].tolist()
                width, repeats = policy.cycle_width, policy.cycle_repetitions
                if tail and tail[-1] in policy.eos_token_ids:
                    return False
                if len(tail) >= width * repeats and all(
                        tail[-width:] == tail[-width * (i + 1):-width * i]
                        for i in range(1, repeats)):
                    self.reason = "repetition_guard"
                elif time.monotonic() - started >= policy.timeout_seconds:
                    self.reason = "technical_timeout"
                return self.reason is not None

        guard = Watchdog()
        torch.manual_seed(0)
        torch.cuda.reset_peak_memory_stats(0)
        with torch.inference_mode():
            result = self.model.generate(inputs, attention_mask=torch.ones_like(inputs),
                generation_config=GenerationConfig(**kwargs,
                    bos_token_id=self.tokenizer.bos_token_id,
                    pad_token_id=self.tokenizer.eos_token_id),
                stopping_criteria=StoppingCriteriaList([guard]))
        tokens = result[0, n:].tolist()
        torch.cuda.synchronize()
        text = self.tokenizer.decode(tokens, skip_special_tokens=True).strip()
        reason = self.policy.finish_reason(tokens, n, guard.reason)
        if reason == "natural_stop" and not text:
            reason = "empty_output"
        return dict(request_id=request["request_id"], runtime_identity=self.identity,
                    text=text, finish_reason=reason, output_token_ids=tokens,
                    input_tokens=n, output_tokens=len(tokens),
                    generation_seconds=time.monotonic() - started,
                    peak_allocated_bytes=torch.cuda.max_memory_allocated(0), api_cost_usd=0)

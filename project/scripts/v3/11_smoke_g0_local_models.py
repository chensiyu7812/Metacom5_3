#!/usr/bin/env python3
"""Load-smoke pinned ESC-Role and ESC-RANK models without generation."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
from pathlib import Path
from typing import Any


ROLE_REVISION = "2e2a4733d2e71da242f348aad165fe171acd5df7"
RANK_REVISION = "450bf2eb5376c79e371aaf432925810243de1527"
BASE_REVISION = "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2"
ADAPTER_KEYS = [
    "fluency", "diversity", "empathic", "suggestion", "tech", "human", "overall",
    "fluency_en", "diversity_en", "empathic_en", "suggestion_en", "tech_en", "human_en", "overall_en",
]


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_revision_path(path: Path, revision: str, label: str) -> None:
    if path.resolve().name != revision:
        raise RuntimeError(f"{label} path does not end in frozen revision {revision}")


def smoke(role_path: Path, rank_path: Path, base_path: Path, device: str) -> dict[str, Any]:
    import accelerate
    import peft
    import torch
    import transformers
    from peft import PeftMixedModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _assert_revision_path(role_path, ROLE_REVISION, "ESC-Role")
    _assert_revision_path(rank_path, RANK_REVISION, "ESC-RANK")
    _assert_revision_path(base_path, BASE_REVISION, "InternLM2")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")

    role_tokenizer = AutoTokenizer.from_pretrained(str(role_path), local_files_only=True)
    role_model = AutoModelForCausalLM.from_pretrained(
        str(role_path),
        local_files_only=True,
        torch_dtype=torch.bfloat16,
        device_map={"": device},
    ).eval()
    role_parameters = sum(parameter.numel() for parameter in role_model.parameters())
    role_class = type(role_model).__name__
    role_template_present = bool(role_tokenizer.chat_template)
    del role_model, role_tokenizer
    gc.collect()
    torch.cuda.empty_cache()

    base_tokenizer = AutoTokenizer.from_pretrained(str(base_path), local_files_only=True, trust_remote_code=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        str(base_path),
        local_files_only=True,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map={"": device},
    ).eval()
    mixed = PeftMixedModel.from_pretrained(
        base_model,
        str(rank_path / ADAPTER_KEYS[0]),
        adapter_name=ADAPTER_KEYS[0],
    )
    for key in ADAPTER_KEYS[1:]:
        mixed.load_adapter(str(rank_path / key), adapter_name=key)
    loaded_adapters = sorted(mixed.peft_config)
    base_parameters = sum(parameter.numel() for parameter in base_model.parameters())
    base_class = type(base_model).__name__
    del mixed, base_model, base_tokenizer
    gc.collect()
    torch.cuda.empty_cache()

    versions = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "accelerate": accelerate.__version__,
        "peft": peft.__version__,
    }
    return {
        "protocol": "metacom-v3-g0-local-model-load-smoke-v1",
        "date": "2026-08-13",
        "status": "PASS_ZERO_GENERATION",
        "model_generation_calls": 0,
        "api_calls": 0,
        "device": {
            "requested": device,
            "name": torch.cuda.get_device_name(torch.device(device)),
            "capability": list(torch.cuda.get_device_capability(torch.device(device))),
        },
        "versions": versions,
        "version_identity_sha256": _sha_text(json.dumps(versions, sort_keys=True, separators=(",", ":"))),
        "esc_role": {
            "revision": ROLE_REVISION,
            "model_class": role_class,
            "parameters": role_parameters,
            "chat_template_present": role_template_present,
        },
        "esc_rank": {
            "revision": RANK_REVISION,
            "base_revision": BASE_REVISION,
            "base_model_class": base_class,
            "base_parameters": base_parameters,
            "loaded_adapter_keys": loaded_adapters,
        },
        "note": "Weight loading and adapter attachment passed; no prompt, role card, scorer input, or generated token was consumed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role-path", required=True, type=Path)
    parser.add_argument("--rank-path", required=True, type=Path)
    parser.add_argument("--base-path", required=True, type=Path)
    parser.add_argument("--device", default="cuda:1")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = smoke(args.role_path, args.rank_path, args.base_path, args.device)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

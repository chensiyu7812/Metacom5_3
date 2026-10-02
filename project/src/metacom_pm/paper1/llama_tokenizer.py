"""Shared, hash-verified frozen Llama-3.1-8B-Instruct tokenizer loader.

Used wherever a real Generator-tokenizer token count is needed for a
zero-outcome, outcome-blind cost/length feature (RS's rs_candidate_token_cost
and MP/MS/ME's me/mp/ms_candidate_token_cost). The tokenizer.json bytes are
never committed to the repo (it is a ~9MB binary artifact); callers pass its
local path explicitly and it is hash-verified against the pinned identity
before use, the same external-file-plus-hash-check pattern already used by
``scripts/paper1/09_audit_rs_renderer_and_boundaries.py`` and
``scripts/paper1/10_attest_paper1_environment.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

LLAMA_TOKENIZER_REPO = "NousResearch/Meta-Llama-3.1-8B-Instruct"
LLAMA_TOKENIZER_REVISION = "d10aef7999a2b5ba950ab3974312feeedbfe0b77"
LLAMA_TOKENIZER_JSON_SHA256 = "79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_llama_tokenizer(tokenizer_json_path: str | Path):
    """Hash-verify then load the pinned tokenizer.json. Fails closed on any
    hash mismatch rather than silently loading an unverified file."""

    path = Path(tokenizer_json_path)
    actual = _sha256_file(path)
    if actual != LLAMA_TOKENIZER_JSON_SHA256:
        raise ValueError(
            f"tokenizer.json SHA256 mismatch: expected {LLAMA_TOKENIZER_JSON_SHA256}, got {actual}"
        )
    try:
        from tokenizers import Tokenizer
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("install the project tokenizers dependency before counting tokens") from exc
    return Tokenizer.from_file(str(path))


def build_llama_token_counter(tokenizer_json_path: str | Path) -> Callable[[str], int]:
    """Return a ``str -> int`` counter bound to the hash-verified tokenizer,
    for direct use as a candidate-construction ``token_counter`` callback."""

    tokenizer = load_llama_tokenizer(tokenizer_json_path)

    def _count(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False).ids)

    return _count

"""Content-addressed, atomic success cache for RS atomic-move compiler calls.

Independent cache namespace from ``semantic_memory/cache.py`` -- separate
protocol string, separate root directory, no shared identity fields. RS
source turns have no cross-session prior-memory table (unlike MP/MS/ME), so
the identity here binds the source card/turn directly instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pydantic import Field

from metacom_pm.io import canonical_json, read_json, sha256_text, write_json
from metacom_pm.paper1.contracts import StrictContract

SHA256_PATTERN = r"^[0-9a-f]{64}$"
CACHE_PROTOCOL = "paper1-rs-atomic-move-success-cache-v1"


class CompilerCallIdentity(StrictContract):
    protocol: str = CACHE_PROTOCOL
    phase: str = Field(pattern=r"^(extractor|verifier)$")
    compiler_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    region: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    enable_thinking: bool
    response_mode: str = Field(min_length=1)
    request_parameters: dict[str, int | float | str | bool | None]
    prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    schema_sha256: str = Field(pattern=SHA256_PATTERN)
    source_card_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    request_payload_sha256: str = Field(pattern=SHA256_PATTERN)

    @property
    def cache_key(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


class SuccessCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, identity: CompilerCallIdentity) -> Path:
        return self.root / identity.phase / f"{identity.cache_key}.json"

    def load(self, identity: CompilerCallIdentity) -> dict[str, Any] | None:
        path = self.path_for(identity)
        if not path.exists():
            return None
        row = read_json(path)
        if row.get("protocol") != CACHE_PROTOCOL:
            raise RuntimeError(f"RS atomic-move cache protocol mismatch: {path}")
        if row.get("identity") != identity.model_dump(mode="json"):
            raise RuntimeError(f"RS atomic-move cache identity mismatch: {path}")
        result = row.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"RS atomic-move cache result is invalid: {path}")
        return result

    def store_success(
        self,
        identity: CompilerCallIdentity,
        result: Mapping[str, Any],
    ) -> Path:
        path = self.path_for(identity)
        row = {
            "protocol": CACHE_PROTOCOL,
            "identity": identity.model_dump(mode="json"),
            "result": dict(result),
        }
        if path.exists():
            existing = read_json(path)
            if canonical_json(existing) != canonical_json(row):
                raise RuntimeError(f"refusing to overwrite immutable success cache: {path}")
            return path
        write_json(path, row)
        return path

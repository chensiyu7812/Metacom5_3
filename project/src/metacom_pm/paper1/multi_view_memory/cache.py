"""Content-addressed immutable success cache for active compiler calls."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pydantic import Field

from metacom_pm.io import canonical_json, read_json, sha256_text, write_json
from metacom_pm.paper1.contracts import StrictContract

from .contracts import SHA256_PATTERN


MULTI_VIEW_CACHE_PROTOCOL = "paper1-multi-view-success-cache-v1"


class CallIdentity(StrictContract):
    protocol: str = MULTI_VIEW_CACHE_PROTOCOL
    phase: str = Field(pattern=r"^(extractor|verifier)$")
    compiler_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    region: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    request_parameters: dict[str, int | float | str | bool | None]
    prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    schema_sha256: str = Field(pattern=SHA256_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    prior_profile_sha256: str = Field(pattern=SHA256_PATTERN)
    request_payload_sha256: str = Field(pattern=SHA256_PATTERN)

    @property
    def cache_key(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


class SuccessCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, identity: CallIdentity) -> Path:
        return self.root / identity.phase / f"{identity.cache_key}.json"

    def load(self, identity: CallIdentity) -> dict[str, Any] | None:
        path = self.path_for(identity)
        if not path.exists():
            return None
        row = read_json(path)
        if row.get("protocol") != MULTI_VIEW_CACHE_PROTOCOL:
            raise RuntimeError(f"multi-view cache protocol mismatch: {path}")
        if row.get("identity") != identity.model_dump(mode="json"):
            raise RuntimeError(f"multi-view cache identity mismatch: {path}")
        result = row.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"multi-view cache result is invalid: {path}")
        return result

    def store_success(self, identity: CallIdentity, result: Mapping[str, Any]) -> Path:
        path = self.path_for(identity)
        row = {
            "protocol": MULTI_VIEW_CACHE_PROTOCOL,
            "identity": identity.model_dump(mode="json"),
            "result": dict(result),
        }
        if path.exists():
            existing = read_json(path)
            if canonical_json(existing) != canonical_json(row):
                raise RuntimeError(f"refusing to overwrite immutable multi-view cache: {path}")
            return path
        write_json(path, row)
        return path


__all__ = ["CallIdentity", "MULTI_VIEW_CACHE_PROTOCOL", "SuccessCache"]

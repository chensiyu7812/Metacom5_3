"""Versioned canonical JSON and immutable, verifiable local artifacts.

Canonical format v1: UTF-8, sorted string keys, no whitespace, no ASCII escaping,
no NaN/Infinity, no Unicode normalization (source character offsets are sacred).
This is a project format, not a claim of RFC 8785 compatibility. File hashes cover
exact bytes; object hashes cover canonical JSON without a trailing newline.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypeVar

SCHEMA_VERSION = "pmrl1v3-contracts-0.2.0"
CANONICAL_VERSION = "pmrl1v3-json-1"
T = TypeVar("T")


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise TypeError("JSON object keys must be strings")
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(f"not a JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def object_sha256(value: Any) -> str:
    return sha256_text(canonical_json(value))


def file_sha256(path: str | Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(text: str) -> Any:
    def invalid_constant(value):
        raise ValueError(f"non-finite JSON number: {value}")
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=invalid_constant)


def decode_contract(cls: type[T], text: str) -> T:
    """Strict types/extra-field rejection; JSON arrays become immutable tuples."""
    from pydantic import TypeAdapter
    from .contracts import check_schema_version
    raw = parse_json(text)
    check_schema_version(raw)
    return TypeAdapter(cls).validate_json(canonical_json(raw), strict=True)


def write_bytes_once(path: str | Path, data: bytes) -> str:
    """Idempotent resume; a different existing artifact is never overwritten."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".immutable-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)  # atomic publication; never expose a partial JSON
        except FileExistsError:
            if path.read_bytes() != data:
                raise FileExistsError(f"immutable artifact differs: {path}") from None
    finally:
        os.unlink(temporary)
    return sha256_bytes(data)


def write_json_once(path: str | Path, value: Any) -> str:
    return write_bytes_once(path, (canonical_json(value) + "\n").encode("utf-8"))


def write_jsonl_once(path: str | Path, values) -> str:
    return write_bytes_once(path, "".join(canonical_json(v) + "\n" for v in values).encode("utf-8"))


def build_manifest(*, task: str, root: Path, inputs: dict[str, Path],
                   outputs: list[Path], code: list[Path], code_sha: str,
                   qualification_tier: str = "engineering_only") -> dict:
    """No timestamp in content identity; measured execution belongs in a run log."""
    if qualification_tier not in ("engineering_only", "research_qualified", "human_confirmed"):
        raise ValueError("unknown qualification tier")
    def rows(paths):
        return [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size,
                 "sha256": file_sha256(p)} for p in sorted(paths)]
    payload = dict(canonical_version=CANONICAL_VERSION, schema_version=SCHEMA_VERSION,
                   task=task, code_sha=code_sha, qualification_tier=qualification_tier,
                   inputs={k: {"path": str(v), "sha256": file_sha256(v),
                               "bytes": v.stat().st_size} for k, v in sorted(inputs.items())},
                   outputs=rows(outputs), code=rows(code))
    return dict(payload, manifest_sha256=object_sha256(payload))


def verify_manifest(manifest: dict, *, root: Path, check_inputs: bool = True) -> None:
    payload = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if object_sha256(payload) != manifest.get("manifest_sha256"):
        raise ValueError("manifest hash mismatch")
    if manifest["canonical_version"] != CANONICAL_VERSION or manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported manifest version")
    for row in manifest["outputs"] + manifest["code"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("manifest path must be relative and contained")
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("manifest symlink escapes root")
        if file_sha256(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            raise ValueError(f"artifact mismatch: {path}")
    if check_inputs:
        for row in manifest["inputs"].values():
            if file_sha256(row["path"]) != row["sha256"]:
                raise ValueError(f"input mismatch: {row['path']}")


def bind_checklist(root: str | Path, checklist, needcard) -> str:
    """Write-once per-prefix registry shared by all 16 terminals; no subset key.

    A changed checklist requires a new experiment registry, never replacement.
    """
    checklist.verify_needcard(needcard)
    return write_json_once(Path(root) / (checklist.prefix_id + ".json"), checklist)


def load_checklist(root: str | Path, prefix_id: str):
    from .contracts import Checklist
    if len(prefix_id) != 64 or any(c not in "0123456789abcdef" for c in prefix_id):
        raise ValueError("invalid prefix identity")
    result = decode_contract(Checklist, (Path(root) / (prefix_id + ".json")).read_text())
    if result.prefix_id != prefix_id:
        raise ValueError("registry prefix mismatch")
    return result

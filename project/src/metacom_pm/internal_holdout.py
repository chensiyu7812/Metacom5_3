from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .io import canonical_json, sha256_file, sha256_text, utc_now, write_json


CANDIDATE_MANIFEST_PROTOCOL = "pm-v1.5-frozen-candidate-family-v1"
INTERNAL_LEDGER_PROTOCOL = "pm-v1.5-internal-test-consumption-ledger-v1"


def freeze_candidate_manifest(
    path: str | Path,
    *,
    run_identity: str,
    artifacts: Mapping[str, str | Path],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Write or exactly validate the pre-internal-test candidate manifest."""

    path = Path(path)
    artifact_rows = {
        name: {"path": str(value), "sha256": sha256_file(value)}
        for name, value in sorted(artifacts.items())
    }
    core = {
        "protocol": CANDIDATE_MANIFEST_PROTOCOL,
        "status": "FROZEN_BEFORE_INTERNAL_TEST",
        "run_identity": str(run_identity),
        "artifacts": artifact_rows,
        "parameters": dict(parameters),
    }
    payload = {
        **core,
        "candidate_manifest_sha256": sha256_text(canonical_json(core)),
    }
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise RuntimeError("candidate manifest already exists with different content")
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)
    return payload


def _read_ledger(handle) -> list[dict[str, Any]]:
    handle.seek(0)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(handle, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"invalid internal-test ledger row {line_number}"
            ) from exc
        if row.get("protocol") != INTERNAL_LEDGER_PROTOCOL:
            raise RuntimeError("internal-test ledger protocol mismatch")
        rows.append(row)
    return rows


def begin_internal_test_consumption(
    ledger_path: str | Path,
    *,
    candidate_manifest_path: str | Path,
    internal_labels_path: str | Path,
) -> dict[str, Any]:
    """Atomically spend the one permitted internal-test outcome read.

    The STARTED event is fsynced before the caller is allowed to open the label
    file.  A crash therefore consumes the run rather than enabling an invisible
    retry; resuming requires a new run identity and candidate manifest.
    """

    manifest = json.loads(Path(candidate_manifest_path).read_text(encoding="utf-8"))
    if (
        manifest.get("protocol") != CANDIDATE_MANIFEST_PROTOCOL
        or manifest.get("status") != "FROZEN_BEFORE_INTERNAL_TEST"
    ):
        raise RuntimeError("internal-test consumption requires a frozen candidate manifest")
    manifest_sha256 = sha256_file(candidate_manifest_path)
    labels_sha256 = sha256_file(internal_labels_path)
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ledger_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with os.fdopen(fd, "r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            rows = _read_ledger(handle)
            if rows:
                raise RuntimeError(
                    "internal-test outcome has already been consumed or consumption started"
                )
            event = {
                "protocol": INTERNAL_LEDGER_PROTOCOL,
                "event": "STARTED",
                "run_identity": manifest["run_identity"],
                "candidate_manifest_sha256": manifest_sha256,
                "internal_labels_sha256": labels_sha256,
                "started_at": utc_now(),
            }
            handle.seek(0, os.SEEK_END)
            handle.write(canonical_json(event) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return event
    except Exception:
        # fd is owned by fdopen after successful construction.
        raise


def finish_internal_test_consumption(
    ledger_path: str | Path,
    *,
    report_path: str | Path,
) -> dict[str, Any]:
    ledger_path = Path(ledger_path)
    fd = os.open(ledger_path, os.O_RDWR)
    with os.fdopen(fd, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        rows = _read_ledger(handle)
        if len(rows) != 1 or rows[0].get("event") != "STARTED":
            raise RuntimeError("internal-test ledger is not awaiting completion")
        event = {
            "protocol": INTERNAL_LEDGER_PROTOCOL,
            "event": "COMPLETED",
            "run_identity": rows[0]["run_identity"],
            "candidate_manifest_sha256": rows[0]["candidate_manifest_sha256"],
            "internal_labels_sha256": rows[0]["internal_labels_sha256"],
            "report_sha256": sha256_file(report_path),
            "completed_at": utc_now(),
        }
        handle.seek(0, os.SEEK_END)
        handle.write(canonical_json(event) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return event


def require_completed_internal_consumption(
    ledger_path: str | Path,
    *,
    candidate_manifest_path: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    with Path(ledger_path).open("r", encoding="utf-8") as handle:
        rows = _read_ledger(handle)
    if len(rows) != 2 or [row.get("event") for row in rows] != [
        "STARTED",
        "COMPLETED",
    ]:
        raise RuntimeError("internal-test consumption is not exactly completed once")
    if rows[1]["candidate_manifest_sha256"] != sha256_file(candidate_manifest_path):
        raise RuntimeError("internal-test ledger candidate manifest hash mismatch")
    if rows[1]["report_sha256"] != sha256_file(report_path):
        raise RuntimeError("internal-test ledger report hash mismatch")
    return {"status": "PASS", "events": rows}

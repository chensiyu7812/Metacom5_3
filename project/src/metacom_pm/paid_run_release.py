from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .io import read_json, sha256_file


PAID_RUN_RELEASE_PROTOCOL = "pm-v1.5-central-paid-run-release-v1"


def _resolve_manifest_path(config: Mapping[str, Any], config_path: str | Path) -> Path:
    release = config.get("execution_release")
    if not isinstance(release, Mapping):
        raise RuntimeError("PM-v1.5 config lacks the central paid-run release gate")
    config_path = Path(config_path).resolve()
    raw_manifest_path = Path(str(release.get("approval_manifest") or ""))
    return (
        raw_manifest_path
        if raw_manifest_path.is_absolute()
        else config_path.parent.parent / raw_manifest_path
    )


def require_output_directory_not_previously_consumed(
    out_dir: str | Path,
    *,
    config: Mapping[str, Any],
    config_path: str | Path,
) -> None:
    """Fail closed if out_dir was ever a real paid-run's output_directory.

    Protects against the exact failure mode that destroyed the first
    ESConv-auxiliary generation pilot's raw artifacts: a later run (dry-run
    or paid) reusing the same default output directory as an earlier,
    already-consumed real run, silently overwriting or deleting its
    artifacts. Once a directory is recorded as a stage_consumptions (or
    historical) output_directory, it is permanently protected -- every
    future run must use a new directory, regardless of whether that
    directory's local ledger currently looks empty or missing, which is
    exactly the dangerous state left behind after an external deletion (the
    per-directory ledger check alone cannot detect that case, since the
    ledger itself is what got deleted). Call this before any script creates,
    writes to, or overwrites a directory -- in both --dry-run and --run
    modes, since the deletion that motivated this check happened during a
    zero-cost dry-run.
    """

    manifest_path = _resolve_manifest_path(config, config_path)
    if not manifest_path.is_file():
        return
    manifest = read_json(manifest_path)
    project_root = Path(config_path).resolve().parent.parent
    resolved_target = Path(out_dir).resolve()
    protected: dict[Path, str] = {}
    consumptions = manifest.get("stage_consumptions") or {}
    for stage_name, record in (consumptions.items() if isinstance(consumptions, Mapping) else []):
        if isinstance(record, Mapping) and record.get("output_directory"):
            raw = Path(str(record["output_directory"]))
            resolved = raw if raw.is_absolute() else (project_root / raw).resolve()
            protected.setdefault(resolved, f"stage_consumptions.{stage_name}")
    history = manifest.get("prior_stage_attempts_history") or []
    for index, record in enumerate(history if isinstance(history, list) else []):
        if isinstance(record, Mapping) and record.get("output_directory"):
            raw = Path(str(record["output_directory"]))
            resolved = raw if raw.is_absolute() else (project_root / raw).resolve()
            protected.setdefault(resolved, f"prior_stage_attempts_history[{index}]")
    source = protected.get(resolved_target)
    if source is not None:
        raise RuntimeError(
            f"output directory {resolved_target} was already recorded as a "
            f"real paid-run output_directory ({source}) in the approval "
            "manifest; it is permanently protected from reuse, overwrite, "
            "or deletion by any future run -- use a new directory"
        )


def require_paid_run_release(
    config: Mapping[str, Any],
    *,
    config_path: str | Path,
    stage: str,
    run: bool,
    run_identity: str | None,
) -> dict[str, Any]:
    """Fail closed before any paid client/attempt can be created.

    A dry run never needs approval.  A real run needs both a reviewed config
    transition to ``PAID_RUN_RELEASED`` and a content-bound approval manifest
    whose per-stage identity is normally the accepted dry-run/cost hash.
    """

    if not run:
        return {"status": "DRY_RUN_ALLOWED", "stage": str(stage)}
    release = config.get("execution_release")
    if not isinstance(release, Mapping):
        raise RuntimeError("PM-v1.5 config lacks the central paid-run release gate")
    expected_revision = str(config.get("release_revision") or "")
    if (
        release.get("protocol") != PAID_RUN_RELEASE_PROTOCOL
        or release.get("status") != "PAID_RUN_RELEASED"
        or release.get("release_revision") != expected_revision
    ):
        raise RuntimeError(
            "paid API execution is centrally blocked: execution_release must be "
            "PAID_RUN_RELEASED for the current release revision"
        )
    identity = str(run_identity or "").strip()
    if not identity:
        raise RuntimeError("paid API execution requires a non-empty fresh run identity")
    config_path = Path(config_path).resolve()
    manifest_path = _resolve_manifest_path(config, config_path)
    if not manifest_path.is_file():
        raise RuntimeError("paid-run approval manifest is absent")
    manifest = read_json(manifest_path)
    approvals = manifest.get("stage_approvals") or {}
    consumptions = manifest.get("stage_consumptions") or {}
    if not isinstance(consumptions, Mapping):
        raise RuntimeError("paid-run approval manifest has invalid stage consumptions")
    history = manifest.get("prior_stage_attempts_history") or []
    if not isinstance(history, list) or any(
        not isinstance(record, Mapping) for record in history
    ):
        raise RuntimeError("paid-run approval manifest has invalid attempt history")
    # Older result-recording code briefly used a separate consumption-history
    # list. Include and validate it so rotating the current stage slot can never
    # make a spent identity reusable. Current manifests migrate these rows into
    # prior_stage_attempts_history, but committed older manifests remain safe.
    consumption_history = manifest.get("stage_consumptions_history") or []
    if not isinstance(consumption_history, list) or any(
        not isinstance(record, Mapping) for record in consumption_history
    ):
        raise RuntimeError(
            "paid-run approval manifest has invalid stage consumption history"
        )
    consumed_identities = {
        str(record.get("approval_identity") or record.get("run_identity") or "")
        for record in [*consumptions.values(), *history, *consumption_history]
        if isinstance(record, Mapping)
    }
    if identity in consumed_identities:
        raise RuntimeError(
            "paid-run identity has already been consumed; the exact identity "
            "can never be reused"
        )
    if (
        manifest.get("protocol") != PAID_RUN_RELEASE_PROTOCOL
        or manifest.get("status") != "APPROVED"
        or manifest.get("release_revision") != expected_revision
        or manifest.get("config_sha256") != sha256_file(config_path)
        or not isinstance(approvals, Mapping)
        or str(approvals.get(str(stage)) or "") != identity
    ):
        raise RuntimeError(
            "paid-run approval is stale or does not bind this stage/run identity"
        )
    return {
        "status": "PAID_RUN_RELEASED",
        "stage": str(stage),
        "run_identity": identity,
        "release_revision": expected_revision,
        "approval_manifest": str(manifest_path),
        "approval_manifest_sha256": sha256_file(manifest_path),
    }

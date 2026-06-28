from __future__ import annotations

from typing import Any, Mapping, Sequence


def endpoint_identity(endpoint: Mapping[str, Any]) -> tuple[str, str, str | None]:
    return (
        str(endpoint.get("base_url") or "").rstrip("/").lower(),
        str(endpoint.get("model") or "").strip().lower(),
        (str(endpoint.get("family")).strip().lower() if endpoint.get("family") else None),
    )


def require_distinct_endpoint_pair(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    purpose: str,
    allow_same_model_debug: bool = False,
) -> dict[str, Any]:
    a = endpoint_identity(first)
    b = endpoint_identity(second)
    same_alias = a[:2] == b[:2]
    family_missing = not a[2] or not b[2]
    same_family = bool(a[2] and b[2] and a[2] == b[2])
    violation = same_alias or family_missing or same_family
    if violation and not allow_same_model_debug:
        reasons = []
        if same_alias:
            reasons.append("same endpoint/model alias")
        if family_missing:
            reasons.append("missing declared model family")
        if same_family:
            reasons.append("same declared model family")
        raise RuntimeError(
            f"confirmatory protocol requires independent {purpose}: "
            + ", ".join(reasons)
        )
    return {
        "purpose": purpose,
        "first": {"base_url": a[0], "model": a[1], "family": a[2]},
        "second": {"base_url": b[0], "model": b[1], "family": b[2]},
        "independent": not violation,
        "debug_override": bool(violation and allow_same_model_debug),
        "reportable": not violation,
    }


def require_requested_conditions(
    observed: Sequence[str], required: Sequence[str], *, context: str
) -> None:
    missing = sorted(set(required) - set(observed))
    if missing:
        raise RuntimeError(f"{context} is missing required conditions: {missing}")

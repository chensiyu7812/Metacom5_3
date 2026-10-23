#!/usr/bin/env python3
"""Materialize the zero-outcome RS renderer/exemplar/boundary decision surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from metacom_pm.paper1.rs.preoutcome_audit import (
    ExplicitBoundary,
    RenderVariant,
    explicit_boundaries,
    exemplar_content_proxies,
    narrow_stateful_boundaries,
    prefix_any_boundaries,
    render_strategy_card,
    strategy_is_boundary_compatible,
)
from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog
from metacom_pm.paper1.rs.zero_outcome_census import build_rs_decision_states


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: list[int | float], fraction: float) -> int | float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _distribution(values: list[int | float]) -> dict[str, int | float]:
    if not values:
        raise ValueError("distribution requires at least one value")
    return {
        "min": min(values),
        "p25": _percentile(values, 0.25),
        "median": statistics.median(values),
        "p75": _percentile(values, 0.75),
        "p90": _percentile(values, 0.90),
        "p95": _percentile(values, 0.95),
        "max": max(values),
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _boundary_summary(states, cards) -> dict[str, Any]:
    all_label_counts = Counter(card.strategy_label for card in cards)
    label_counts_by_dialogue: dict[str, Counter[str]] = defaultdict(Counter)
    for card in cards:
        label_counts_by_dialogue[card.source_dialogue_id][card.strategy_label] += 1

    horizons = {
        "current_user_run_only": lambda state: explicit_boundaries(state.current_user_text),
        "visible_prefix_any_marker_no_revocation": lambda state: prefix_any_boundaries(
            state.visible_dialogue_text
        ),
        "visible_prefix_narrow_explicit_revocation": lambda state: narrow_stateful_boundaries(
            state.visible_dialogue_text
        ),
    }
    result: dict[str, Any] = {}
    for name, parser in horizons.items():
        marker_counts = Counter()
        states_with_any = 0
        blocked_candidate_edges = 0
        exhausted_states = 0
        for state in states:
            boundaries = parser(state)
            marker_counts.update(boundary.value for boundary in boundaries)
            if not boundaries:
                continue
            states_with_any += 1
            available = all_label_counts - label_counts_by_dialogue[state.source_dialogue_id]
            blocked = sum(
                count
                for label, count in available.items()
                if not strategy_is_boundary_compatible(label, boundaries)
            )
            blocked_candidate_edges += blocked
            if sum(available.values()) - blocked == 0:
                exhausted_states += 1
        result[name] = {
            "states_with_any_explicit_boundary": states_with_any,
            "active_marker_state_counts": {
                boundary.value: marker_counts[boundary.value] for boundary in ExplicitBoundary
            },
            "candidate_edges_mechanically_blocked": blocked_candidate_edges,
            "states_with_no_compatible_candidate_remaining": exhausted_states,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esconv", type=Path, default=Path("data/external/ESConv.json"))
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=Path("data/strategy/esconv_split_manifest_v1_5.jsonl"),
    )
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument("--expected-tokenizer-sha256", required=True)
    parser.add_argument("--tokenizer-source-repo", required=True)
    parser.add_argument("--tokenizer-revision", required=True)
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=Path("data/paper1_public_rs/esconv_rs_renderer_card_audit_v1.jsonl"),
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=Path("data/paper1_public_rs/esconv_rs_renderer_boundary_audit_v1.json"),
    )
    args = parser.parse_args()

    actual_tokenizer_sha = _sha256(args.tokenizer_json)
    if actual_tokenizer_sha != args.expected_tokenizer_sha256:
        raise ValueError("tokenizer.json SHA256 does not match the reviewed input")
    try:
        from tokenizers import Tokenizer
    except ImportError as exc:  # pragma: no cover - environment-specific dependency message
        raise RuntimeError("install the project tokenizers dependency before running this audit") from exc

    tokenizer = Tokenizer.from_file(str(args.tokenizer_json))
    cards = build_strategy_source_catalog(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
    )
    states = build_rs_decision_states(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
    )

    variant_counts: dict[str, list[int]] = {variant.value: [] for variant in RenderVariant}
    variant_render_hashes: dict[str, set[str]] = {
        variant.value: set() for variant in RenderVariant
    }
    proxy_counts = Counter()
    overlaps: list[float] = []
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest_out.open("w", encoding="utf-8") as handle:
        for card in cards:
            proxies = exemplar_content_proxies(card)
            if proxies.source_context_lexical_overlap is not None:
                overlaps.append(proxies.source_context_lexical_overlap)
            for field in (
                "first_person_reference",
                "kinship_reference",
                "time_or_number_reference",
                "capitalized_token_reference",
            ):
                proxy_counts[field] += int(getattr(proxies, field))
            token_counts = {}
            render_hashes = {}
            for variant in RenderVariant:
                rendered = render_strategy_card(card, variant)
                count = len(tokenizer.encode(rendered, add_special_tokens=False).ids)
                render_sha = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
                variant_counts[variant.value].append(count)
                variant_render_hashes[variant.value].add(render_sha)
                token_counts[variant.value] = count
                render_hashes[variant.value] = render_sha
            handle.write(
                json.dumps(
                    {
                        "protocol": "pm-paper1-rs-renderer-card-audit-v1",
                        "card_id": card.card_id,
                        "strategy_label": card.strategy_label,
                        "example_response_sha256": card.example_response_sha256,
                        "proxies": {
                            "first_person_reference": proxies.first_person_reference,
                            "kinship_reference": proxies.kinship_reference,
                            "time_or_number_reference": proxies.time_or_number_reference,
                            "capitalized_token_reference": proxies.capitalized_token_reference,
                            "source_context_lexical_overlap": proxies.source_context_lexical_overlap,
                        },
                        "rendered_resource_tokens": token_counts,
                        "rendered_resource_sha256": render_hashes,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )

    caps = (128, 192, 256)
    render_summary = {}
    for variant, counts in variant_counts.items():
        render_summary[variant] = {
            "distinct_render_count": len(variant_render_hashes[variant]),
            "resource_token_distribution": _distribution(counts),
            "cap_coverage": {
                str(cap): {
                    "cards_within_cap": sum(count <= cap for count in counts),
                    "cards_total": len(counts),
                    "coverage_fraction": sum(count <= cap for count in counts) / len(counts),
                }
                for cap in caps
            },
        }

    summary = {
        "protocol": "pm-paper1-rs-renderer-boundary-audit-v1",
        "status": "ZERO_OUTCOME_DECISION_SURFACE_NOT_RENDERER_OR_BOUNDARY_FREEZE",
        "formal_outcome_calls": 0,
        "formal_unlock": False,
        "universe": {
            "strategy_cards": len(cards),
            "decision_states": len(states),
            "source_policy": "conservative_existing_project_overlap_exclusion",
            "leave_current_dialogue_out_applies_to_formal_retrieval": True,
        },
        "tokenizer": {
            "source_repo": args.tokenizer_source_repo,
            "revision": args.tokenizer_revision,
            "tokenizer_json_sha256": actual_tokenizer_sha,
            "special_tokens_added_for_resource_substring": False,
            "artifact_identity_status": "LOCAL_TOKENIZER_BYTES_SHA256_VERIFIED",
            "source_attribution_status": (
                "CALLER_DECLARED_PUBLIC_MIRROR_REPO_AND_REVISION_"
                "NOT_REMOTE_REVERIFIED_BY_THIS_SCRIPT"
            ),
            "provider_parity_status": "PUBLIC_LLAMA31_TOKENIZER_MIRROR_NOT_YET_VERIFIED_AGAINST_NVIDIA_NIM_USAGE",
        },
        "renderer_variants": render_summary,
        "exemplar_content_shape_proxies": {
            "note": "Mechanical text-shape diagnostics only; no composite score and no eligibility rule.",
            "cards_total": len(cards),
            "card_counts": dict(sorted(proxy_counts.items())),
            "source_context_lexical_overlap_distribution": _distribution(overlaps),
        },
        "boundary_horizon_decision_surface": _boundary_summary(states, cards),
        "boundary_candidate_mapping": {
            "status": "PROVISIONAL_LABEL_LEVEL_MAPPING_RESEARCHER_DECISION_REQUIRED",
            "listen_only_blocks": ["Providing Suggestions", "Question"],
            "no_advice_blocks": ["Providing Suggestions"],
            "no_probing_blocks": ["Question"],
            "whole_head_off": False,
            "learned_feature_status": "FORBIDDEN_ZERO_OR_NEAR_ZERO_VARIANCE",
            "all_resource_arms_must_share_rule": True,
        },
        "card_manifest": {
            "path": str(args.manifest_out),
            "rows": len(cards),
            "sha256": _sha256(args.manifest_out),
            "contains_raw_dialogue_or_example_text": False,
        },
        "researcher_decisions_still_required": [
            "guidance_only_vs_guidance_plus_exemplar",
            "boundary_horizon_and_label_level_candidate_mapping",
            "resource_token_cap",
            "provider_tokenizer_parity_check",
        ],
    }
    _write_json(args.summary_out, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

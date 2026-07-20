#!/usr/bin/env python3
"""Diagnostic-only Hybrid (lexical + semantic) retrieval report.

Part 3 of the approved PM-v1.5 hybrid-retrieval plan. This script is
strictly report-only:

- It never touches a real, frozen pipeline artifact under outputs/ owned by
  a formal stage, never calls a paid API, and never changes what any real
  consumer does. HybridMemoryRetriever/HybridStrategyRetriever
  (src/metacom_pm/hybrid_retrieval.py) remain isolated from every real
  consumer -- see tests/test_hybrid_retrieval_isolation.py.
- Score floors are calibrated using ONLY the synthetic development corpus's
  TRAIN split (reported against, never fit from, the CALIBRATION split).
  internal_test/external_test rows and every EvoEmo-derived number below are
  strictly report-only, computed only after the floors/contract above are
  already frozen, and must never feed back into calibration. See
  src/metacom_pm/hybrid_retrieval_diagnostics.py's module docstring for the
  full data-boundary rule this script enforces by construction (it calls
  into that module rather than re-deriving the logic here).
- The two EvoEmo comparisons (fixed top-k, fixed evidence-token budget)
  deliberately use each user's `topic` field as a query stand-in --
  evaluator-only-for-diagnostics-only, structurally separate from the real,
  observable query path (`hybrid_retrieval.observable_query_with_hash`).

Any future decision to adopt Hybrid for real consumers is explicitly
deferred (Part 4 of the plan) and is not made or implied by this script.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from metacom_pm.config import load_config
from metacom_pm.contracts import MemorySource
from metacom_pm.evoemo import evo_memory_global_catalog_digest, load_evoemo
from metacom_pm.hybrid_retrieval import (
    HYBRID_RETRIEVAL_PROTOCOL,
    RECIPROCAL_RANK_FUSION_K,
    HybridMemoryRetriever,
    SourceScoreFloors,
    hybrid_retrieval_contract_hash,
)
from metacom_pm.hybrid_retrieval_diagnostics import (
    calibrate_source_floors,
    compare_fixed_token_budget,
    compare_fixed_top_k,
    iter_case_calibration_examples,
    split_of_user_id,
)
from metacom_pm.io import iter_jsonl, sha256_file, write_json
from metacom_pm.pm_v1_5_semantic import (
    FrozenTransformerSemanticEncoder,
    semantic_encoder_spec_from_config,
)
from metacom_pm.retrieval import DEFAULT_MEMORY_TOP_K, MemoryRetriever

ROOT = Path(__file__).resolve().parents[2]

# No per-candidate strategy-utility ground truth exists in the synthetic
# corpus (only memory items carry item_utility/stale/conflicts_with_current_
# state labels) -- freeze the strategy floor at zero (no exclusion) rather
# than fabricate a calibrated value from data that does not exist. Recorded
# in the report, not silently assumed.
STRATEGY_FLOOR_CALIBRATION_STATUS = (
    "no_labeled_synthetic_strategy_candidates_available_in_this_corpus; "
    "strategy floors frozen at (0.0, 0.0) -- no exclusion -- rather than "
    "fabricated from nonexistent ground truth"
)
STRATEGY_FLOORS = SourceScoreFloors(lexical_min_score=0.0, semantic_min_score=0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evoemo", type=Path, default=ROOT / "data" / "external" / "evo_emo.json"
    )
    parser.add_argument(
        "--development-data-candidate",
        type=Path,
        default=(
            ROOT
            / "data"
            / "pm_v1_5_formal_v8_17_casewise_repair_candidate"
            / "_generated_bundles_work.jsonl"
        ),
        help=(
            "Real, currently-best-available synthetic development bundles, "
            "used only to calibrate TRAIN/CALIBRATION score floors. This is "
            "NOT the frozen formal development-data artifact -- see the "
            "report's development_data_candidate.disclosure field."
        ),
    )
    parser.add_argument(
        "--pm-v2-config", type=Path, default=ROOT / "configs" / "pm_v1_5.yaml"
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=360,
        help="Fixed evidence-token budget for the second comparison.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs" / "pm_v1_5_hybrid_retrieval_diagnostic.json",
    )
    args = parser.parse_args()

    config = load_config(args.pm_v2_config)
    encoder_spec = semantic_encoder_spec_from_config(config)
    encoder = FrozenTransformerSemanticEncoder.load(encoder_spec)

    bundles = list(iter_jsonl(args.development_data_candidate))
    split_counts = Counter(split_of_user_id(bundle["user_id"]) for bundle in bundles)
    calibration_examples = iter_case_calibration_examples(bundles)
    source_calibration = calibrate_source_floors(calibration_examples, encoder=encoder)
    memory_floors_by_source = {
        source: SourceScoreFloors(
            lexical_min_score=calib.lexical_min_score,
            semantic_min_score=calib.semantic_min_score,
        )
        for source, calib in source_calibration.items()
    }
    contract_hash = hybrid_retrieval_contract_hash(
        memory_floors_by_source=memory_floors_by_source,
        strategy_floors=STRATEGY_FLOORS,
        rrf_k=RECIPROCAL_RANK_FUSION_K,
        semantic_encoder_spec_sha256=encoder_spec.digest(),
    )

    users = load_evoemo(args.evoemo)
    evo_memory_digest = evo_memory_global_catalog_digest(users)
    top_k_by_source = {MemorySource.ME: DEFAULT_MEMORY_TOP_K[MemorySource.ME]}
    lexical_retriever = MemoryRetriever(
        top_k_by_source=top_k_by_source,
        minimum_score_by_source={
            MemorySource.ME: float(config["retrieval"]["memory_min_score"])
        },
    )
    hybrid_retriever = HybridMemoryRetriever(
        semantic_encoder=encoder,
        top_k_by_source=top_k_by_source,
        floors_by_source=memory_floors_by_source,
        rrf_k=RECIPROCAL_RANK_FUSION_K,
    )
    fixed_top_k_report = compare_fixed_top_k(
        users, lexical_retriever=lexical_retriever, hybrid_retriever=hybrid_retriever
    )
    fixed_budget_report = compare_fixed_token_budget(
        users, hybrid_retriever=hybrid_retriever, token_budget=int(args.token_budget)
    )

    report = {
        "protocol": HYBRID_RETRIEVAL_PROTOCOL,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "REPORT_ONLY_NOT_A_FORMAL_ARTIFACT_NO_ADOPTION_DECISION_MADE",
        "inputs": {
            "evoemo_path": str(args.evoemo),
            "evoemo_sha256": sha256_file(args.evoemo),
            "evo_memory_builder_contract_sha256": evo_memory_digest[
                "builder_contract_sha256"
            ],
            "evo_memory_global_catalog_sha256": evo_memory_digest[
                "global_catalog_sha256"
            ],
            "development_data_candidate": {
                "path": str(args.development_data_candidate),
                "sha256": sha256_file(args.development_data_candidate),
                "user_count": len(bundles),
                "split_counts": dict(sorted(split_counts.items())),
                "disclosure": (
                    "Real, generated content produced by "
                    "scripts/v1_5/20_generate_pm_v2_development_data_v1_5.py's "
                    "v8.17 casewise-repair attempt -- NOT the frozen formal "
                    "development-data artifact (as of this report, that stage "
                    "has not been formally closed out / paid-approved for "
                    "every user). Floors calibrated from it should be "
                    "re-derived once the formal artifact exists; the "
                    "calibration method itself (TRAIN-positive minimum, "
                    "CALIBRATION-only reporting) does not change."
                ),
            },
        },
        "semantic_encoder": {
            "spec_sha256": encoder_spec.digest(),
            "binding": encoder.binding.model_dump(mode="json"),
        },
        "floor_calibration_by_memory_source": {
            source.value: asdict(calib) for source, calib in source_calibration.items()
        },
        "strategy_floor_calibration_status": STRATEGY_FLOOR_CALIBRATION_STATUS,
        "frozen_contract": {
            "rrf_k": RECIPROCAL_RANK_FUSION_K,
            "memory_floors_by_source": {
                source.value: asdict(floors)
                for source, floors in memory_floors_by_source.items()
            },
            "strategy_floors": asdict(STRATEGY_FLOORS),
            "contract_sha256": contract_hash,
        },
        "report_only_evoemo_diagnostic_not_confirmatory": {
            "note": (
                "Every number below uses EvoEmo's evaluator-only "
                "subsequent_topics/related_sessions ground truth and topic "
                "text as a query stand-in -- report-only, computed after "
                "the frozen_contract above was already fixed, and never fed "
                "back into floor calibration. Scope is ME only: "
                "related_sessions ground truth has no MP/MS analogue."
            ),
            "top_k_by_source": {"ME": top_k_by_source[MemorySource.ME]},
            "fixed_top_k_comparison": {
                name: asdict(summary) for name, summary in fixed_top_k_report.items()
            },
            "fixed_token_budget_comparison": {
                "token_budget": int(args.token_budget),
                **{
                    name: asdict(summary)
                    for name, summary in fixed_budget_report.items()
                },
            },
        },
    }
    write_json(args.out, report)
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "out": str(args.out),
                "contract_sha256": contract_hash,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

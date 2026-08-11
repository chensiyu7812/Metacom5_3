#!/usr/bin/env python3
"""Materialize and freeze the 576-group formal effect manifest without APIs."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_public_backbone import _chronological_users  # noqa: E402
from metacom_pm.v1_5_v5_3_public_formal_manifest import (  # noqa: E402
    PROTOCOL,
    audit_formal_manifest,
    select_formal_groups,
)
from metacom_pm.v1_5_v5_3_public_learnability_pilot import (  # noqa: E402
    add_frozen_semantic_similarity,
    materialize_memory_pool,
    materialize_rs_pool,
)
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import (  # noqa: E402
    BgeM3Encoder,
    CachedTextEncoder,
    DEFAULT_BGE_M3_SNAPSHOT,
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    paths = {
        "evoemo": ROOT / "data/external/evo_emo.json",
        "esconv": ROOT / "data/external/ESConv.json",
        "esconv_manifest": ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
        "strategy_cards": ROOT / "data/strategy/strategy_cards_v1_5_minimal.jsonl",
        "development_manifest": ROOT / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809/effect_group_manifest_private.jsonl",
        "public_contract": ROOT / "data/pm_v1_5_contracts/v5_3_public_backbone_effect_learning_v1.json",
        "formal_freeze": ROOT / "data/pm_v1_5_contracts/v5_3_public_formal_effect_freeze_v1.json",
        "formal_manifest_source": ROOT / "src/metacom_pm/v1_5_v5_3_public_formal_manifest.py",
        "pool_materializer_source": ROOT / "src/metacom_pm/v1_5_v5_3_public_learnability_pilot.py",
        "typed_adapter_source": ROOT / "src/metacom_pm/v1_5_typed_resource_adapter.py",
        "formal_manifest_materializer": ROOT / "scripts/v1_5/106l_materialize_v5_3_public_formal_effect_manifest_v1_5.py",
    }
    raw_evoemo = json.loads(paths["evoemo"].read_text())
    users = [str(user["id"]) for user in _chronological_users(raw_evoemo)]
    public_contract = json.loads(paths["public_contract"].read_text())
    formal_freeze = json.loads(paths["formal_freeze"].read_text())
    development = _jsonl(paths["development_manifest"])
    memory = materialize_memory_pool(paths["evoemo"], user_ids=users)
    rs = materialize_rs_pool(
        esconv_path=paths["esconv"], manifest_path=paths["esconv_manifest"],
        cards_path=paths["strategy_cards"],
    )
    rows = select_formal_groups(
        memory_pools=memory, rs_pool=rs, development_rows=development,
        outer_folds=public_contract["cross_fitting"]["outer_folds"],
    )
    encoder = CachedTextEncoder(BgeM3Encoder(DEFAULT_BGE_M3_SNAPSHOT))
    add_frozen_semantic_similarity(rows, encoder=encoder)
    audit = audit_formal_manifest(rows, development_rows=development)

    # Empirical development Q/F rate, plus 20% headroom. Risk is deliberately absent.
    estimated_qf_usd = 0.1173538 / 96 * len(rows)
    contract = {
        "protocol": PROTOCOL,
        "status": "PRE_EFFECT_FROZEN" if audit["status"] == "PASS" else "PRE_EFFECT_BLOCKED",
        "formal_freeze_identity": formal_freeze["freeze_identity"],
        "source_hashes": {name: sha256_file(path) for name, path in paths.items()},
        "groups": len(rows),
        "groups_per_component": formal_freeze["formal_groups"],
        "paired_generator_seeds_per_group": 3,
        "selection": "outcome-blind factor-coverage actual Rank-1; 8 states per user/head; distinct RS dialogues",
        "development_exclusion": "all 96 development source states and 24 RS dialogues excluded before selection",
        "outer_fold_binding": "memory by frozen user fold; RS exactly 24 held-out dialogue groups per fold",
        "head_design": formal_freeze["heads"],
        "target": formal_freeze["target"],
        "risk": formal_freeze["risk"],
        "call_budget": {
            "generator_calls": len(rows) * 3 * 2,
            "quality_judge_calls": len(rows) * 2,
            "function_judge_calls": len(rows),
            "automatic_risk_judge_calls": 0,
            "base_calls": len(rows) * 9,
            "estimated_qf_judge_usd_from_development_rate": estimated_qf_usd,
            "hard_qf_judge_usd_cap_with_20_percent_headroom": round(estimated_qf_usd * 1.2, 2),
            "generator_pricing": "frozen NVIDIA hosted prototype endpoint currently free/rate-limited",
        },
        "live_execution_allowed": False,
        "live_blockers": ["independent manifest/hash/cost review before paid formal execution"],
        "api_calls": 0,
    }
    contract["manifest_identity"] = "v53formalmanifest_" + stable_hex(
        canonical_json(contract), canonical_json(rows), n=24,
    )
    out = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809"
    write_jsonl(out / "effect_group_manifest_private.jsonl", rows)
    write_json(out / "audit.json", audit)
    write_json(out / "contract.json", contract)
    write_json(ROOT / "data/pm_v1_5_contracts/v5_3_public_formal_effect_manifest_v1.json", contract)
    print({"status": contract["status"], "groups": len(rows), "audit": audit["status"], "api_calls": 0, "estimated_qf_usd": round(estimated_qf_usd, 3)})


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Freeze and audit the V5.3 ESConv/EvoEmo public-data backbone (zero API)."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_public_backbone import (  # noqa: E402
    audit_public_backbone,
    build_public_backbone_freeze,
)


def main() -> None:
    audit = audit_public_backbone(
        evoemo_path=ROOT / "data/external/evo_emo.json",
        esconv_path=ROOT / "data/external/ESConv.json",
        esconv_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    contract = build_public_backbone_freeze(audit)
    contract_path = (
        ROOT / "data/pm_v1_5_contracts/v5_3_public_backbone_effect_learning_v1.json"
    )
    output_dir = ROOT / "outputs/pm_v1_5_v5_3_public_backbone_audit_20260809"
    write_json(contract_path, contract.model_dump(mode="json"))
    write_json(output_dir / "audit.json", audit)
    write_json(output_dir / "contract.json", contract.model_dump(mode="json"))
    print(
        {
            "status": audit["status"],
            "contract": str(contract_path),
            "audit": str(output_dir / "audit.json"),
            "freeze_identity": contract.freeze_identity,
        }
    )


if __name__ == "__main__":
    main()

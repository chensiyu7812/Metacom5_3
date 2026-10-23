#!/usr/bin/env python3
"""Publish an explicit, text-free result allowlist without changing experiments.

Run once against the local research checkout. This makes no model calls and
never copies full output trees, human forms, blind maps, keys or model weights.
Historical status fields are retained verbatim; current status is a separate
snapshot. Publication is not reward qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


TRAINING = "P2/training/058aa28e277649ac26b76895c694c0944674efd3d23fffbbf1fd8084b2f53a32"
RUNTIME = "P3/candidate_v1/development/ad198b7104cb0d62927f94f0ea8821f21bdc6e6496cecb4f29cb5429a1a35879/runtime.json"
COPY = {
    "current_state.json": "current_state.json",
    "P1/capacity.json": "P1/capacity.json",
    "P1/renderer_freeze.json": "P1/initial_renderer_freeze.json",
    "P1/interface_repair_v3/renderer_freeze.json": "P1/direct_renderer_freeze.json",
    "P1/interface_repair_v3/plan_deviation.json": "P1/interface_repair_plan_deviation.json",
    "P2/slot_freeze.json": "P2/slot_freeze.json",
    "P2/supervision_freeze.json": "P2/supervision_freeze.json",
    "P2/supervision_protocol.json": "P2/supervision_protocol.json",
    "P2/admission_summary.json": "P2/admission_summary.json",
    "P2/executor_selection.json": "P2/executor_selection.json",
    "P2/executor_freeze.json": "P2/executor_freeze.json",
    f"{TRAINING}/summary.json": "P2/training_summary.json",
    f"{TRAINING}/epochs.json": "P2/training_epochs.json",
    f"{TRAINING}/selection.json": "P2/training_selection.json",
    f"{TRAINING}/reload.json": "P2/training_reload.json",
    f"{TRAINING}/runtime.json": "P2/training_runtime.json",
    "P2/common_pool/input_freeze.json": "P2/common_pool_input_freeze.json",
    "P2/common_pool/summary.json": "P2/common_pool_preparation_summary.json",
    "P3/common_evidence/input_freeze.json": "P3/common_evidence_freeze.json",
    "P3/common_evidence/summary.json": "P3/common_evidence_summary.json",
    "P3/candidate_v1/candidate_freeze.json": "P3/candidate_freeze.json",
    "P3/candidate_v1/protocol.json": "P3/candidate_protocol.json",
    RUNTIME: "P3/development_runtime.json",
    "P3/throughput_and_budget.json": "P3/throughput_and_budget.json",
    "P3/verification/browser_qa_final.json": "P3/browser_qa_final.json",
    "P3/verification/old_artifacts.json": "P3/historical_artifact_check.json",
}
DEFERRED = (
    "project/scripts/rl1/95_lock_p3_calibration_selection.py",
    "project/scripts/rl1/96_build_p3_human_packet.py",
)


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Repository root")
    parser.add_argument("--destination-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.source_root.resolve()
    source = repo / "project/outputs/pm_rl1/completion_20260930_v2"
    out = args.destination_root.resolve()
    if out.exists():
        raise FileExistsError("Use a new publication directory; never overwrite a snapshot")

    # Check all inputs before creating any public file.
    for name in COPY:
        json.loads((source / name).read_bytes())
    deferred = [{"path": name, "sha256": sha(repo / name),
                 "reason": "Contains live item selection/control construction; withheld until human calibration closes."}
                for name in DEFERRED]
    old_manifest = repo / "project/docs/reviews/20260930/pm_rl1/LOCAL_ARTIFACT_INVENTORY.json"
    old_files = json.loads(old_manifest.read_text())["files"]
    for row in old_files:
        if sha(repo / row["path"]) != row["sha256"]:
            raise ValueError(f"Historical artifact changed: {row['path']}")

    entries = []
    for name, target in COPY.items():
        src, dst = source / name, out / target
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("xb") as stream:
            stream.write(src.read_bytes())
        entries.append({"source_path": str(src.relative_to(repo)),
                        "published_path": target, "bytes": dst.stat().st_size,
                        "source_sha256": sha(src), "published_sha256": sha(dst),
                        "transformation": "none"})

    # Record already-public analysis/result files without duplicating their data.
    assets = []
    for folder in ("pm_rl1_backward_design_20261001_v1", "pm_rl1_completion_20260930_v2"):
        for path in sorted((repo / "project/docs" / folder).iterdir()):
            if path.is_file():
                assets.append({"path": str(path.relative_to(repo)),
                               "bytes": path.stat().st_size, "sha256": sha(path)})
    save(out / "MANIFEST.json", {
        "status": "PUBLICATION_SNAPSHOT_NOT_REWARD_QUALIFICATION",
        "as_of": "2026-10-02",
        "source_scope": "P0/P1/P2 and initial P3 development; human calibration pending",
        "files": entries,
        "analysis_and_result_assets": assets,
        "temporarily_withheld_source": deferred,
        "historical_artifacts_verified_unchanged": len(old_files),
        "excluded": ["Full source/reply datasets and raw model calls", "Model and optimizer weights",
                     "Live human forms, answer mappings, item-level judge answers and private keys"],
        "interpretation": [
            "Hashes bind local evidence; they do not make withheld content publicly reproducible.",
            "Earlier pending statuses describe their snapshot time, not the current stage.",
            "The original analysis notebook requires local source exports; see the separate public overview notebook.",
            "No additional generation, scoring, human labels, training or API charges from publication.",
        ],
    })
    print(json.dumps({"published_results": len(entries), "analysis_assets": len(assets),
                      "historical_artifacts_unchanged": len(old_files),
                      "deferred_item_construction_scripts": len(deferred)}))


if __name__ == "__main__":
    main()

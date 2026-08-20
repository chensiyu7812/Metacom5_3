#!/usr/bin/env python3
"""Build the blind ESC evaluator-qualification package without judge calls."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.evaluator_qualification import (  # noqa: E402
    DIMENSIONS,
    assert_blind_payload,
    canonical_sha256,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)

ESC_EVAL_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
SCORE_PY_SHA256 = "1d775462adc7687d84ceb19d3648c3c917abf7ceed8b052b1fed8e4740f12724"
PUBLIC_EXAMPLE_HASHES = {
    "result/2024-06-24/llama3_en.json": "c8a1804ab26e98cb1bd1326dfb7d3b4541195c74a1a4daf51e7ba9a36a6324c0",
    "result/2024-06-24/Qwen_7B_en.json": "dcd225631614ba2c32573dad8e3fe06c5eb2034070057d56ade3e15607056371",
}


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _official_prompts(score_py: Path) -> list[str]:
    if _sha_file(score_py) != SCORE_PY_SHA256:
        raise RuntimeError("official score.py hash drifted")
    tree = ast.parse(score_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "prompt_EN" for target in node.targets
        ):
            prompts = ast.literal_eval(node.value)
            if isinstance(prompts, list) and len(prompts) == 7:
                return prompts
    raise RuntimeError("official seven English prompts were not found")


def _opaque(namespace: str, value: str) -> str:
    return namespace + "_" + hashlib.sha256((namespace + "|seed=0|" + value).encode()).hexdigest()[:16]


def _natural_items(esc_eval: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    by_card: dict[str, list[str]] = {}
    for relative, expected_hash in PUBLIC_EXAMPLE_HASHES.items():
        path = esc_eval / relative
        if _sha_file(path) != expected_hash:
            raise RuntimeError(f"public ESC example drifted: {relative}")
        system_family = Path(relative).stem.removesuffix("_en")
        dialogues = json.loads(path.read_text(encoding="utf-8"))
        if set(dialogues) != {"0", "1", "2"}:
            raise RuntimeError("expected exactly the three pinned public example dialogues")
        for official_index in sorted(dialogues, key=int):
            source_key = f"{relative}|{official_index}"
            item_id = _opaque("escq", source_key)
            dialogue = dialogues[official_index]
            item = {
                "protocol": "pm-paper1-esc-evaluator-blind-item-v1",
                "blind_item_id": item_id,
                "item_kind": "natural_public_baseline",
                "source_role": "public_baseline",
                "dialogue": dialogue,
            }
            assert_blind_payload(item)
            items.append(item)
            card_key = f"official_example_card_{official_index}"
            by_card.setdefault(card_key, []).append(item_id)
            audit.append(
                {
                    "blind_item_id": item_id,
                    "source_file": relative,
                    "source_file_sha256": expected_hash,
                    "official_example_index": int(official_index),
                    "system_family": system_family,
                    "dialogue_sha256": canonical_sha256(dialogue),
                    "qualification_only_not_PM_or_Topk_outcome": True,
                }
            )
    pairs = []
    for card_key, member_ids in sorted(by_card.items()):
        if len(member_ids) != 2:
            raise RuntimeError("each public example role card must have two baseline systems")
        ordered = sorted(member_ids)
        pairs.append(
            {
                "pair_id": _opaque("escpair", card_key),
                "pair_kind": "natural_system_pair",
                "control_item_id": ordered[0],
                "variant_item_id": ordered[1],
            }
        )
    return items, audit, pairs


CONTROLLED_PROBES = (
    (
        "verbosity",
        "work",
        "User: I have been overwhelmed by work and I cannot decide where to start.",
        "That sounds exhausting. Pick one small task for the next ten minutes, then pause and reassess.",
        "That sounds genuinely exhausting, especially when everything feels urgent at once. Pick one small task for the next ten minutes and focus only on that single task. After those ten minutes, pause, take a breath, and reassess what feels manageable next. You do not have to solve the whole workload right now; the point is to begin with one small task and then check in again.",
        ["validate distress", "choose one small ten-minute task", "pause and reassess"],
    ),
    (
        "verbosity",
        "friend",
        "User: I argued with a close friend and now I feel guilty and unsure what to say.",
        "It makes sense that you feel unsettled after the argument with your friend. Send a short acknowledgment and ask when they would be ready to talk.",
        "It makes sense that you feel unsettled after an argument with your friend, who is important to you. You could send a short acknowledgment of what happened without trying to resolve everything immediately. Then ask when they would feel ready to talk, giving both of you a little space before the conversation.",
        ["validate distress", "send a short acknowledgment", "ask when ready to talk"],
    ),
    (
        "verbosity",
        "appointment",
        "User: I have an important appointment tomorrow and my anxiety is making it hard to sleep.",
        "That anxiety sounds tiring. Prepare what you need for tomorrow, then try five slow breaths before bed.",
        "That anxiety sounds tiring when you are already trying to rest before an important appointment. Prepare what you need for tomorrow so there is less to hold in your mind tonight. Once that is done, try five slow breaths before bed and let that be enough preparation for now.",
        ["validate distress", "prepare appointment items", "take five slow breaths"],
    ),
    (
        "redundant_suggestions",
        "friend",
        "User: I argued with a close friend and now I feel guilty and unsure what to say.",
        "Write a short, honest message acknowledging the argument and ask when they would feel ready to talk.",
        "Write a short, honest message acknowledging the argument and ask when they would feel ready to talk. Keep the message brief and honest about the argument. Also ask for a time when they would feel ready for that conversation.",
        ["send a short honest acknowledgment", "ask when the friend is ready to talk"],
    ),
    (
        "redundant_suggestions",
        "work",
        "User: I have been overwhelmed by work and I cannot decide where to start.",
        "Choose one small task for ten minutes and reassess after it is done.",
        "Choose one small task for ten minutes and reassess after it is done. Start with just one small task for that ten-minute period. When it is done, stop and reassess what to do next.",
        ["choose one small ten-minute task", "reassess afterward"],
    ),
    (
        "redundant_suggestions",
        "appointment",
        "User: I have an important appointment tomorrow and my anxiety is making it hard to sleep.",
        "Set out what you need for tomorrow and take five slow breaths before bed.",
        "Set out what you need for tomorrow and take five slow breaths before bed. Prepare those things for tomorrow now. Then, before bed, slow down and take those five slow breaths.",
        ["prepare appointment items", "take five slow breaths"],
    ),
    (
        "format_list_style",
        "appointment",
        "User: I have an important appointment tomorrow and my anxiety is making it hard to sleep.",
        "Tonight, set out what you need for tomorrow, write down the appointment time, and try five slow breaths before bed.",
        "Tonight:\n- Set out what you need for tomorrow.\n- Write down the appointment time.\n- Try five slow breaths before bed.",
        ["prepare appointment items", "record appointment time", "take five slow breaths"],
    ),
    (
        "format_list_style",
        "work",
        "User: I have been overwhelmed by work and I cannot decide where to start.",
        "Acknowledge how overloaded you feel, choose one ten-minute task, and reassess when the time is up.",
        "For now:\n- Acknowledge how overloaded you feel.\n- Choose one ten-minute task.\n- Reassess when the time is up.",
        ["acknowledge overload", "choose one ten-minute task", "reassess afterward"],
    ),
    (
        "format_list_style",
        "friend",
        "User: I argued with a close friend and now I feel guilty and unsure what to say.",
        "Recognize that you feel guilty, send a brief acknowledgment, and ask when your friend is ready to talk.",
        "Next steps:\n- Recognize that you feel guilty.\n- Send a brief acknowledgment.\n- Ask when your friend is ready to talk.",
        ["recognize guilt", "send a brief acknowledgment", "ask when ready to talk"],
    ),
)


def _controlled_items() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    factor_counts: dict[str, int] = {}
    for factor, topic, context, control_response, variant_response, semantic_atoms in CONTROLLED_PROBES:
        context_index = factor_counts.get(factor, 0)
        factor_counts[factor] = context_index + 1
        pair_key = f"{factor}|context={context_index}"
        member_ids = {}
        for condition, response in (("control", control_response), ("variant", variant_response)):
            item_id = _opaque("escbias", f"{pair_key}|{condition}")
            dialogue = [context, "AI assistant: " + response]
            item = {
                "protocol": "pm-paper1-esc-evaluator-blind-item-v1",
                "blind_item_id": item_id,
                "item_kind": "controlled_bias_probe",
                "source_role": "controlled_semantics_preserving_probe",
                "dialogue": dialogue,
            }
            assert_blind_payload(item)
            items.append(item)
            member_ids[condition] = item_id
            audit.append(
                {
                    "blind_item_id": item_id,
                    "probe_factor": factor,
                    "probe_topic": topic,
                    "probe_condition": condition,
                    "context_sha256": hashlib.sha256(context.encode()).hexdigest(),
                    "semantic_atoms": semantic_atoms,
                    "semantic_atoms_sha256": canonical_sha256(semantic_atoms),
                    "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                }
            )
        pairs.append(
            {
                "pair_id": _opaque("escbiaspair", pair_key),
                "pair_kind": "controlled_" + factor,
                "control_item_id": member_ids["control"],
                "variant_item_id": member_ids["variant"],
            }
        )
    return items, audit, pairs


def _human_sheet(items: list[dict[str, Any]], *, rater: str) -> list[dict[str, Any]]:
    rng = random.Random("paper1-esc-human-sheet-seed0|" + rater)
    ordered = list(items)
    rng.shuffle(ordered)
    return [
        {
            "protocol": "pm-paper1-esc-evaluator-human-blind-rating-v1",
            "blind_item_id": item["blind_item_id"],
            "rater_id": rater,
            "dialogue": item["dialogue"],
            "scores": {dimension: None for dimension in DIMENSIONS},
            "notes": None,
            "human_completed": False,
        }
        for item in ordered
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", type=Path, required=True)
    parser.add_argument(
        "--out-dir", type=Path, default=PROJECT / "data" / "paper1_authority"
    )
    args = parser.parse_args()
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    if _git_head(args.esc_eval) != ESC_EVAL_COMMIT:
        raise RuntimeError("ESC-Eval checkout is not at the pinned commit")

    natural_items, natural_audit, natural_pairs = _natural_items(args.esc_eval)
    probe_items, probe_audit, probe_pairs = _controlled_items()
    items = natural_items + probe_items
    pairs = natural_pairs + probe_pairs
    assert len(natural_items) == 6
    assert len(probe_items) == 18

    prompts = _official_prompts(args.esc_eval / "score.py")
    human_instrument = {
        "protocol": "pm-paper1-esc-evaluator-human-instrument-v1",
        "status": "FROZEN_BEFORE_HUMAN_RATINGS",
        "source": {
            "esc_eval_commit": ESC_EVAL_COMMIT,
            "score_py_sha256": SCORE_PY_SHA256,
        },
        "dimensions": [
            {"paper_dimension": dimension, "official_rubric_text": prompts[index], "scale": [0, 1, 2, 3, 4]}
            for index, dimension in enumerate(DIMENSIONS)
        ],
        "blind_to": ["PM identity", "arm", "ON/OFF", "k", "token budget", "Ours/baseline"],
        "two_independent_raters_required": True,
        "adjudication_required": True,
    }
    registry = {
        "protocol": "pm-paper1-esc-evaluator-candidate-identity-registry-v1",
        "status": "BLOCKED_PENDING_RESEARCHER_IDENTITIES",
        "candidates": [
            {
                "candidate_id": "ESC_RANK",
                "status": "FROZEN_IDENTITY_RUNTIME_EXPERIMENT_REQUIRED",
                "family": "InternLM2",
                "model": "internlm/internlm2-chat-7b",
                "model_revision": "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2",
                "adapter_repo": "haidequanbu/ESC-RANK",
                "adapter_revision": "450bf2eb5376c79e371aaf432925810243de1527",
                "esc_eval_commit": ESC_EVAL_COMMIT,
            },
            {
                "candidate_id": "QWEN_GENERAL_JUDGE",
                "status": "BLOCKED_EXACT_MODEL_VERSION_NOT_RESEARCHER_SPECIFIED",
                "family": "Qwen",
                "model": None,
                "version": None,
            },
            {
                "candidate_id": "DEEPSEEK_GENERAL_JUDGE",
                "status": "BLOCKED_EXACT_MODEL_VERSION_NOT_RESEARCHER_SPECIFIED",
                "family": "DeepSeek",
                "model": None,
                "version": None,
            },
            {
                "candidate_id": "INDEPENDENT_FAMILY_JUDGE",
                "status": "BLOCKED_FAMILY_AND_EXACT_MODEL_NOT_RESEARCHER_SPECIFIED",
                "family": None,
                "model": None,
                "version": None,
            },
        ],
        "compiler_Qwen_identity_does_not_authorize_judge_identity": True,
        "calls_authorized_by_this_registry": False,
    }
    for candidate in registry["candidates"]:
        identity_payload = {
            key: candidate.get(key)
            for key in (
                "candidate_id",
                "family",
                "model",
                "version",
                "model_revision",
                "adapter_repo",
                "adapter_revision",
                "esc_eval_commit",
            )
            if key in candidate
        }
        candidate["identity_sha256"] = (
            canonical_sha256(identity_payload)
            if not candidate["status"].startswith("BLOCKED")
            else None
        )

    base = args.out_dir
    paths = {
        "items": base / "paper1_esc_evaluator_qualification_set_20260820_v1.jsonl",
        "judge_blind_input": base / "paper1_esc_evaluator_judge_blind_input_20260820_v1.jsonl",
        "esc_rank_runtime_smoke": base / "paper1_esc_rank_runtime_smoke_dialogues_20260820_v1.jsonl",
        "audit": base / "paper1_esc_evaluator_qualification_audit_mapping_20260820_v1.json",
        "pairs": base / "paper1_esc_evaluator_qualification_pairs_20260820_v1.jsonl",
        "rater_a": base / "paper1_esc_evaluator_human_blind_sheet_rater_a_20260820_v1.jsonl",
        "rater_b": base / "paper1_esc_evaluator_human_blind_sheet_rater_b_20260820_v1.jsonl",
        "adjudication": base / "paper1_esc_evaluator_human_adjudication_template_20260820_v1.jsonl",
        "judge_template": base / "paper1_esc_evaluator_judge_output_template_20260820_v1.jsonl",
        "instrument": base / "paper1_esc_evaluator_human_instrument_20260820_v1.json",
        "registry": base / "paper1_esc_evaluator_candidate_identity_registry_20260820_v1.json",
        "manifest": base / "paper1_esc_evaluator_qualification_package_manifest_20260820_v1.json",
    }
    _write_jsonl(paths["items"], items)
    _write_jsonl(
        paths["judge_blind_input"],
        [
            {
                "protocol": "pm-paper1-esc-evaluator-judge-blind-input-v1",
                "blind_item_id": item["blind_item_id"],
                "dialogue": item["dialogue"],
            }
            for item in items
        ],
    )
    _write_jsonl(paths["esc_rank_runtime_smoke"], natural_items[:3])
    _write_json(paths["audit"], {"natural": natural_audit, "controlled": probe_audit})
    _write_jsonl(paths["pairs"], pairs)
    _write_jsonl(paths["rater_a"], _human_sheet(items, rater="RATER_A"))
    _write_jsonl(paths["rater_b"], _human_sheet(items, rater="RATER_B"))
    _write_jsonl(
        paths["adjudication"],
        [
            {
                "protocol": "pm-paper1-esc-evaluator-human-adjudication-v1",
                "blind_item_id": item["blind_item_id"],
                "adjudicator_id": None,
                "scores": {dimension: None for dimension in DIMENSIONS},
                "adjudication_completed": False,
            }
            for item in items
        ],
    )
    _write_jsonl(
        paths["judge_template"],
        [
            {
                "protocol": "pm-paper1-esc-evaluator-candidate-score-v1",
                "candidate_id": None,
                "model_identity_sha256": None,
                "blind_item_id": item["blind_item_id"],
                "scores": {dimension: None for dimension in DIMENSIONS},
                "parse_valid": None,
                "latency_seconds": None,
                "cost_usd": None,
            }
            for item in items
        ],
    )
    _write_json(paths["instrument"], human_instrument)
    _write_json(paths["registry"], registry)

    artifact_hashes = {
        key: _sha_file(path) for key, path in paths.items() if key != "manifest"
    }
    manifest = {
        "protocol": "pm-paper1-esc-evaluator-qualification-package-manifest-v1",
        "status": "READY_FOR_TWO_HUMAN_REVIEW_JUDGE_EXECUTION_BLOCKED",
        "source": {
            "official_repository": "https://github.com/haidequanbu/ESC-Eval",
            "esc_eval_commit": ESC_EVAL_COMMIT,
            "score_py_sha256": SCORE_PY_SHA256,
        },
        "counts": {
            "natural_public_baseline_dialogues": len(natural_items),
            "natural_system_pairs": len(natural_pairs),
            "controlled_bias_items": len(probe_items),
            "controlled_bias_pairs": len(probe_pairs),
            "total_blind_items": len(items),
        },
        "limitations": [
            "the pinned public repository contains only 3 role cards x 2 public baseline systems, not the planned 24 natural dialogues",
            "controlled probes supplement but do not replace natural-dialogue agreement evidence",
            "human sheets are blank and Codex has not acted as a human rater",
            "Qwen, DeepSeek, and independent-family exact judge identities remain researcher decisions",
            "ESC-RANK runtime still requires an attached >=24 GiB GPU and pinned local snapshots",
        ],
        "artifact_sha256": artifact_hashes,
        "selection_rule": [
            "validity_and_human_agreement",
            "bias_and_sensitivity",
            "cost_and_latency",
        ],
        "formal_ESC_Eval": False,
        "formal_outcome_calls": 0,
        "judge_calls": 0,
    }
    _write_json(paths["manifest"], manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

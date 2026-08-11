#!/usr/bin/env python3
"""Materialize the frozen full-dialogue V5.4 feature surface without outcomes."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np  # noqa: E402
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import BgeM3Encoder, DEFAULT_BGE_M3_SNAPSHOT  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-full-dialogue-feature-surface-v1"
RUNTIME = ROOT / "outputs/pm_v1_5_v5_4_v4_state_local_actual_rank1_20260810/runtime_state_candidate_surface_no_ids_no_assignment.jsonl"
TRANSITION = ROOT / "data/pm_v1_5_contracts/v5_4_actual_outcome_learnability_transition_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_full_dialogue_feature_surface_20260810"
NLI_MODEL = Path(
    "/home/tokkio/.cache/huggingface/hub/models--cross-encoder--nli-deberta-v3-base/"
    "snapshots/6c749ce3425cd33b46d187e45b92bbf96ee12ec7"
)
COMPONENTS = ("MP", "MS", "ME", "RS")
HYPOTHESES = {
    "increment_positive": "The retrieved candidate could add a specific response-relevant contribution that is not already stated.",
    "increment_negative": "The retrieved candidate merely repeats what is already stated in the visible exchange.",
    "goal_positive": "The retrieved candidate serves the user's current goal or requested response function.",
    "goal_negative": "The retrieved candidate serves a different goal or function from the user's current request.",
    "boundary_positive": "Using the retrieved candidate now respects the user's explicit interaction boundary.",
    "boundary_negative": "Using the retrieved candidate now conflicts with the user's explicit boundary or a need already resolved.",
    "function_positive": "The retrieved candidate's component-specific contribution could change the next response in a useful concrete way.",
    "function_negative": "The retrieved candidate's component-specific contribution would not change the next response in a useful concrete way.",
}


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def dialogue_text(row: dict) -> str:
    return "\n".join(f"{turn['role'].upper()}: {turn['content']}" for turn in row["visible_dialogue"])


def prefix_text(row: dict) -> str:
    return "\n".join(f"{turn['role'].upper()}: {turn['content']}" for turn in row["visible_dialogue"][:-1])


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    values = np.exp(shifted)
    return values / values.sum(axis=1, keepdims=True)


def nli_features(premises: list[str]) -> tuple[np.ndarray, dict]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(NLI_MODEL, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL, local_files_only=True)
    torch.set_num_threads(min(8, max(1, torch.get_num_threads())))
    device = torch.device("cpu")
    model.to(device).eval()
    entailment = int(model.config.label2id["entailment"])
    contradiction = int(model.config.label2id["contradiction"])
    pairs = [(premise, hypothesis) for premise in premises for hypothesis in HYPOTHESES.values()]
    feature_rows = []
    with torch.inference_mode():
        for start in range(0, len(pairs), 16):
            batch = pairs[start:start + 16]
            encoded = tokenizer(
                [item[0] for item in batch], [item[1] for item in batch],
                padding=True, truncation=True, max_length=512, return_tensors="pt",
            )
            logits = model(**{key: value.to(device) for key, value in encoded.items()}).logits
            probabilities = softmax(logits.detach().cpu().numpy().astype(np.float64))
            feature_rows.extend((probabilities[:, entailment] - probabilities[:, contradiction]).tolist())
    matrix = np.asarray(feature_rows, dtype=np.float64).reshape(len(premises), len(HYPOTHESES))
    return matrix, {
        "model": "cross-encoder/nli-deberta-v3-base",
        "snapshot": NLI_MODEL.name,
        "device": str(device),
        "max_length": 512,
        "hypotheses": HYPOTHESES,
        "pairs": len(pairs),
        "config_sha256": sha256_file(NLI_MODEL / "config.json"),
        "model_sha256": sha256_file(NLI_MODEL / "model.safetensors"),
        "tokenizer_sha256": sha256_file(NLI_MODEL / "tokenizer.json"),
    }


def main() -> None:
    contract = json.loads(TRANSITION.read_text())
    if not contract["current_authorization"]["feature_surface_materialization"]:
        raise RuntimeError("feature materialization is not authorized")
    runtime = sorted(rows(RUNTIME), key=lambda row: row["state_id"])
    if len(runtime) != 96 or Counter(row["component"] for row in runtime) != Counter({component: 24 for component in COMPONENTS}):
        raise RuntimeError("runtime panel is incomplete")
    if any(row.get("response_effect_quality_risk_function_oracle_present") for row in runtime):
        raise RuntimeError("outcome appeared in runtime input")

    full = [dialogue_text(row) for row in runtime]
    latest = [row["current_user_text"] for row in runtime]
    prefix = [prefix_text(row) for row in runtime]
    candidate = [row["actual_rank1_candidate_text"] for row in runtime]
    encoder = BgeM3Encoder(DEFAULT_BGE_M3_SNAPSHOT)
    matrix = encoder.encode(full + latest + prefix + candidate).astype(np.float32)
    full_vec, latest_vec, prefix_vec, candidate_vec = np.split(matrix, 4)
    cos_full = np.sum(full_vec * candidate_vec, axis=1)
    cos_latest = np.sum(latest_vec * candidate_vec, axis=1)
    cos_prefix = np.sum(prefix_vec * candidate_vec, axis=1)
    nli_premises = [
        f"Visible exchange:\n{full_text}\nRetrieved candidate:\n{candidate_text}"
        for full_text, candidate_text in zip(full, candidate, strict=True)
    ]
    nli, nli_run = nli_features(nli_premises)
    if not all(np.isfinite(value).all() for value in (matrix, cos_full, cos_latest, cos_prefix, nli)):
        raise RuntimeError("non-finite feature")

    surface = []
    for index, row in enumerate(runtime):
        typed = row["actual_rank1_typed_candidate"]
        surface.append({
            "protocol": PROTOCOL,
            "state_id_evaluator_join_only": row["state_id"],
            "pair_id_split_binding_only": row["pair_id"],
            "semantic_family_id_split_binding_only": row["semantic_family_id"],
            "component_split_head_only": row["component"],
            "model_feature_values": {
                "candidate_age_sessions": float(typed.get("age_sessions") or 0),
                "visible_turn_count": float(len(row["visible_dialogue"])),
                "visible_word_count": float(len(full[index].split())),
                "latest_user_word_count": float(len(latest[index].split())),
                "candidate_word_count": float(len(candidate[index].split())),
                "bge_full_dialogue_candidate_cosine": float(cos_full[index]),
                "bge_latest_user_candidate_cosine": float(cos_latest[index]),
                "bge_prefix_candidate_cosine": float(cos_prefix[index]),
                **{f"nli_{name}": float(nli[index, offset]) for offset, name in enumerate(HYPOTHESES)},
            },
            "embedding_row_index_private": index,
            "construction_assignment_present": False,
            "author_or_variant_position_present": False,
            "response_effect_or_oracle_present": False,
        })
    forbidden_pattern = re.compile(r"construction|assignment|author|variant_[ab]|quality|risk|function_outcome|cost_outcome|oracle", re.I)
    feature_names = list(surface[0]["model_feature_values"])
    checks = {
        "rows_96": len(surface) == 96,
        "24_rows_each_component": Counter(row["component_split_head_only"] for row in surface) == Counter({component: 24 for component in COMPONENTS}),
        "all_actual_candidates_present": all(row["candidate_present"] for row in runtime),
        "all_feature_values_finite": all(all(np.isfinite(value) for value in row["model_feature_values"].values()) for row in surface),
        "feature_schema_identical": all(list(row["model_feature_values"]) == feature_names for row in surface),
        "forbidden_feature_name_absent": not any(forbidden_pattern.search(name) for name in feature_names),
        "runtime_construction_absent": all(not row.get("construction_assignment_present") for row in runtime),
        "response_effect_or_oracle_absent": True,
    }
    passed = all(checks.values())
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT / "frozen_bge_embedding_views_private.npz",
        full_dialogue=full_vec, latest_user=latest_vec, prefix=prefix_vec,
        actual_candidate=candidate_vec,
    )
    write_jsonl(OUT / "feature_surface_private_ids_not_model_features.jsonl", surface)
    report = {
        "protocol": PROTOCOL,
        "status": "FULL_DIALOGUE_FEATURE_SURFACE_MACHINE_PASS_EFFECT_MANIFEST_MAY_BE_BUILT" if passed else "FEATURE_SURFACE_FAIL_NO_EFFECT",
        "checks": checks,
        "rows": len(surface),
        "feature_names": feature_names,
        "bge": {
            "snapshot": str(DEFAULT_BGE_M3_SNAPSHOT),
            "embedding_dimension_per_view": int(full_vec.shape[1]),
            "views": ["full_dialogue", "latest_user", "prefix", "actual_candidate"],
        },
        "nli": nli_run,
        "model_selection": "no model was fit or selected; raw views are frozen before response effects and any reduction/model choice must occur inside grouped nested CV",
        "construction_assignment_used": False,
        "response_effect_or_oracle_read": False,
        "api_calls": 0,
        "source_hashes": {"runtime": sha256_file(RUNTIME), "transition_contract": sha256_file(TRANSITION)},
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Prepare a proposed local-judge comparison; fetch metadata/tokenizers only.

No model weights, model inference, paid API, new human ratings, or labels.
"""
from __future__ import annotations

import copy
import json
import sys
from collections import defaultdict
from pathlib import Path

import httpx
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import canonical_json, read_json, sha256_file, sha256_text, utc_now, write_json
from metacom_pm.paper1.evaluation.pairwise_teacher import (
    RESPONSE_SCHEMA, build_pairwise_teacher_prompt, pairwise_teacher_identity_payload,
)
from metacom_pm.paper1.evaluation.teacher_diagnostics import reference_comparison
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config

CANDIDATES = (
    ("selene_mini_8b", "AtlaAI/Selene-1-Mini-Llama-3.1-8B", "427792f1c3e2073cb7da216924fd884b1ba496e0"),
    ("compassjudger2_7b", "opencompass/CompassJudger-2-7B-Instruct", "f913ec1569c282f02530028fedc1ce9832024ebf"),
)
FORMAT_NOTE = "Formatting requirement: return only the JSON object. The rationale must contain between 1 and 600 characters."


def main():
    assert_pre_outcome_locked(load_public_only_config(PROJECT / "configs/paper1_public_only.yaml"))
    authority = PROJECT / "data/paper1_authority"
    output = PROJECT / "outputs/paper1_pairwise_teacher/local_comparison_proposal_20260917_v1"
    output.mkdir(parents=True, exist_ok=True)
    manifest = read_json(authority / "paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json")
    binding = manifest["sheets"]["RATER_A"]
    source = PROJECT / binding["path"]
    assert sha256_file(source) == binding["sha256"]
    blank = read_json(source)["items"]
    assert len(blank) == 96 and all(r["verdict"] is None and r["rationale"] is None for r in blank)
    keys_path = authority / "paper1_pairwise_teacher_blind_key_20260904_v1.jsonl"
    assert sha256_file(keys_path) == manifest["source_sha256"]["blind_key"]
    keys = {r["presentation_id"]: r for r in map(json.loads, keys_path.read_text().splitlines())}
    assert {r["presentation_id"] for r in blank} == keys.keys()
    groups = defaultdict(list)
    for r in blank:
        groups[keys[r["presentation_id"]]["base_pair_id"]].append(r)
    presentations, mapping = [], []
    for base_id, items in sorted(groups.items()):
        base = next(r for r in items if not keys[r["presentation_id"]]["reverse_duplicate"])
        if len(items) == 2:
            reverse = next(r for r in items if keys[r["presentation_id"]]["reverse_duplicate"])
            origin = "existing_blinded_reverse"
        else:
            assert len(items) == 1
            reverse = {**base, "presentation_id": "local_reverse_" + sha256_text(base["presentation_id"])[:24],
                       "response_A": base["response_B"], "response_B": base["response_A"]}
            origin = "derived_model_only_reverse_no_new_human_judgement"
        assert base["response_A"] == reverse["response_B"] and base["response_B"] == reverse["response_A"]
        assert all(base[k] == reverse[k] for k in ("task", "task_input", "reference_material"))
        for item, provenance in ((base, "original_base"), (reverse, origin)):
            presentations.append(item)
            mapping.append({"presentation_id": item["presentation_id"], "base_pair_id": base_id,
                            "task": item["task"], "source_base_presentation_id": base["presentation_id"],
                            "source": provenance, "is_base": provenance == "original_base"})
    assert len(groups) == 80 and len(presentations) == 160
    assert sum(r["source"].startswith("derived") for r in mapping) == 64
    assert len({r["presentation_id"] for r in presentations}) == 160
    # Schedule fixed without loading human or candidate answers.
    presentations.sort(key=lambda r: sha256_text("local-teacher-comparison-v1|seed0|" + r["presentation_id"]))
    schema = copy.deepcopy(RESPONSE_SCHEMA)
    schema["properties"]["rationale"].update(minLength=1, maxLength=600)
    generation = {"temperature": 0, "seed": 0, "max_tokens": 1024,
                  "response_format": {"type": "json_schema", "json_schema": {
                      "name": "paper1_material_effect_teacher", "strict": True, "schema": schema}}}
    reports = []
    for short, model, revision in CANDIDATES:
        print(json.dumps({"preparing": model, "model_inference": False}), flush=True)
        response = httpx.get(f"https://huggingface.co/api/models/{model}/revision/{revision}", timeout=45)
        response.raise_for_status()
        metadata = response.json()
        assert metadata["sha"] == revision
        directory = Path(snapshot_download(model, revision=revision, token=False,
            local_dir=output / "tokenizers" / short,
            allow_patterns=["config.json", "generation_config.json", "tokenizer_config.json", "tokenizer.json",
                            "special_tokens_map.json", "merges.txt", "vocab.json", "chat_template.jinja"]))
        assert not list(directory.glob("*.safetensors")) and not list(directory.glob("pytorch_model*"))
        config = read_json(directory / "config.json")
        tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True, trust_remote_code=False)
        rows, counts = [], []
        for item in presentations:
            prompt = build_pairwise_teacher_prompt(task=item["task"], task_input=item["task_input"],
                response_a=item["response_A"], response_b=item["response_B"], reference_material=item["reference_material"])
            prompt += "\n\n" + FORMAT_NOTE
            messages = [{"role": "user", "content": prompt}]
            token_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, truncation=False)
            body = {"model": model, "messages": messages, **generation}
            rows.append({"presentation_id": item["presentation_id"], "task": item["task"],
                         "revision": revision, "body": body, "body_sha256": sha256_text(canonical_json(body)),
                         "input_tokens": len(token_ids), "input_token_ids_sha256": sha256_text(canonical_json(token_ids))})
            counts.append(len(token_ids))
        assert max(counts) + generation["max_tokens"] <= config["max_position_embeddings"]
        request_path = output / f"{short}_requests.jsonl"
        request_path.write_text("".join(canonical_json(r) + "\n" for r in rows))
        reports.append({"short_name": short, "model": model, "revision": revision,
            "model_card": f"https://huggingface.co/{model}",
            "config_context_limit": config["max_position_embeddings"],
            "tokenizer_declared_max_length": tokenizer.model_max_length,
            "max_input_tokens": max(counts), "sum_input_tokens": sum(counts),
            "exceeding_tokenizer_declared_limit": sum(n > tokenizer.model_max_length for n in counts),
            "full_inputs_fit_config_with_output_reserve": True, "long_context_accuracy_tested": False,
            "BF16_weights_only_GiB": round(metadata["safetensors"]["total"] * 2 / 1024 ** 3, 2),
            "requests": len(rows), "request_manifest": str(request_path.relative_to(PROJECT)),
            "request_manifest_sha256": sha256_file(request_path),
            "tokenizer_directory": str(directory.relative_to(PROJECT)),
            "tokenizer_and_config_sha256": {p.name: sha256_file(p) for p in sorted(directory.iterdir()) if p.is_file()}})
    write_json(output / "presentation_mapping.json", mapping)
    # Negative-control diagnostic; never train or alter the recorded references.
    reference_path = PROJECT / "outputs/paper1_pairwise_teacher/review_closeout_20260917_v1/reference_trace.json"
    references = read_json(reference_path)
    baseline = reference_comparison([{**r, "candidate_verdict": "equivalent"} for r in references])
    write_json(output / "always_equivalent_baseline.json", baseline)
    proposal = {
        "protocol": "paper1-local-teacher-comparison-proposal-v1",
        "status": "PROPOSED RESEARCH CHANGE — NOT AUTHORIZED", "created_at": utc_now(),
        "researcher_approval": False, "paid_api_authorized": False,
        "candidates": reports, "new_logical_model_calls_if_approved": 320,
        "human_source_presentations": 96, "base_pairs": 80,
        "model_only_derived_reversals": 64, "presentations_per_candidate": 160,
        "new_human_sheets": 0, "new_human_judgements": 0,
        "generation": generation, "format_note": FORMAT_NOTE,
        "semantic_rubric_identity": pairwise_teacher_identity_payload(),
        "reference_sheet_sha256": binding["sha256"], "reference_trace_sha256": sha256_file(reference_path),
        "model_only_mapping_sha256": sha256_file(output / "presentation_mapping.json"),
        "baseline_always_equivalent_original_A": baseline["base_pairs"],
        "primary_reference": "Original 80 base judgements; original-human/followup/assistant-sensitive views kept separate. Derived reversals are model stability checks, not additional human labels or independent examples.",
        "comparison": "Taskwise decisive/equivalent macro recall with clustered uncertainty, order stability, equivalent recall, evidence diagnostics, parse/operational reliability, then cost. Also report constant-equivalent baseline; no automatic winner or absolute PASS percentage.",
        "analysis_plan": {
            "selection_order": read_json(authority / "paper1_pairwise_teacher_qualification_plan_v3.json")["selection_order"],
            "primary_agreement_denominator": "80 original base presentations per candidate; display all scheduled, valid and missing counts. Do not count reversed presentations as independent human-reference cases.",
            "comparability": "Report each candidate's valid set and their shared valid set with identical supported reference classes; never conceal parse failures or compare macro recall across differing class support without disclosure.",
            "order_checks": "All 80 paired orders per candidate; also report the original 16-pair subset separately alongside historical Gemini results.",
            "uncertainty": "Taskwise source-cluster bootstrap, 2000 replicates, seed 20260917; source clusters from the existing outcome-blind preflight. Report small class support and undefined bootstrap replicates.",
            "reference_views": "Original A primary, six-case followup overlay and assistant factual sensitivity separately; AI B exploratory, never additional human gold. No reference labels or rationales in model requests.",
            "language": "Model inputs remain canonical English; humans primarily read Chinese. Report this limitation rather than claim language-matched independent validation.",
            "evidence_diagnostics": "Inspect materiality, unsupported facts and reversal contradictions across all outputs; qualitative diagnostics do not create a new empirical PASS gate.",
            "selection_boundary": "One fixed comparison, no same-sample semantic prompt search or finetuning, no automatic winner. Review task-specific applicability before any teacher promotion. No promotion authorizes downstream outcomes or PM training."
        },
        "historic_comparators": "Reuse Gemini V2 and exploratory AI B as historical context only; not a controlled same-output-cap architecture comparison.",
        "scope_changes": ["Add exactly two open-weight candidates to V3 permitted candidate families.",
                          "Add 64 model-only reversed presentations per candidate to cover both orders of all 80 bases.",
                          "For new candidates only, explicitly specify the existing 600-character rationale rule in prompt/schema and use max output 1024, preserving four-class meanings. Existing Gemini V2 remains immutable."],
        "reason": "Check applicability of pretrained specialist judges before accepting permanent Summary/DG supervision limitations; no from-scratch training.",
        "previous_results_invalidated": "None. Old Gemini remains a valid result under its V2 configuration; cross-protocol differences cannot be attributed to weights alone.",
        "reruns": "Only the two new candidates; no old Gemini call, no Generator rerun, no rerating, no PM training.",
        "claim_change": "No immediate change to PM scope. Promote only supported task roles after reporting the evidence; absent support retain existing fallback and disclose limitations.",
        "infrastructure_proposal": {"GPU": "NVIDIA RTX A6000", "GPU_UUID": "GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4",
            "dtype": "BF16", "concurrency": 1, "models_loaded_simultaneously": 1,
            "intended_backend": "existing vLLM 0.10.1 local stack; full serving/config/parser binding required before calls",
            "total_local_runtime_ceiling_hours": 4, "per_attempt_timeout_seconds": 120,
            "retry": "At most one infrastructure retry; no repeated greedy retry for parser failure and no result-driven reruns.",
            "max_physical_attempts": 640, "extra_API_cost_usd": "0", "runtime_and_peak_memory_measured": False},
        "no_finetuning_on_this_reference": True, "same_sample_semantic_prompt_search": False,
        "execution_runner_ready": False, "weights_downloaded_by_this_preparation": False,
        "pre_execution_remaining": ["Approve the scoped candidate/protocol expansion.",
            "Bind downloaded weight hashes and exact existing serving stack; verify JSON schema support and no input truncation before scored calls.",
            "Complete resumable local runner and offline tests; bind exact final implementation hash without changing the approved design."],
        "new_model_calls_in_preparation": 0, "new_API_cost_usd": "0", "formal_outcomes": 0,
        "PM_training": 0, "outcome_locks": "ALL_CLOSED",
    }
    write_json(output / "proposal.json", proposal)
    write_json(authority / "paper1_local_teacher_comparison_proposal_20260917_v1.json", proposal)
    print(canonical_json({"status": proposal["status"], "prepared_requests": 320,
                          "new_model_calls": 0, "new_API_cost_usd": "0",
                          "candidates": [{k: r[k] for k in ("model", "revision", "max_input_tokens", "requests")} for r in reports]}))


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "data" / "v3_authority"


def load(name: str):
    return json.loads((AUTHORITY / name).read_text(encoding="utf-8"))


def test_official_first_is_the_only_active_evaluation_authority():
    root = load("v3_research_authority_v1.json")
    active = load("v3_official_first_evaluation_authority_v1.json")
    assert root["active_evaluation_authority"].endswith("v3_official_first_evaluation_authority_v1.json")
    assert active["status"] == "ACTIVE_SOLE_EVALUATION_AUTHORITY_OFFICIAL_BENCHMARKS_FIRST"
    assert [row["benchmark"] for row in active["active_primary_tracks"]] == ["ESC-Eval", "ES-MemEval"]
    assert active["only_project_defined_primary_metric_retained"]["metric"] == "Cost"
    assert active["custom_evidence_demotion"]["status"] == "RETAINED_FOR_PROVENANCE_DEFAULT_NOT_EXECUTED_NOT_PRIMARY"


def test_esc_eval_official_protocol_has_no_invented_pass_line():
    contract = load("g0_official_protocol_english331_contract_v1.json")
    assert contract["official_interaction_surface"]["supporter_system_prompt"] == "You are a helpful assistant!"
    assert contract["official_interaction_surface"]["turns_per_dialogue"] == 5
    assert contract["evaluation"]["official_pass_line"] is None
    assert {row["candidate_id"]: row["max_output_tokens"] for row in contract["candidates"]} == {
        "llama31_8b_incumbent_official_wrapper": 256,
        "qwen37_plus_nonthinking_official_wrapper": 512,
    }


def test_esc_eval_english331_manifest_is_complete_text_free_and_unique():
    rows = [json.loads(line) for line in (AUTHORITY / "g0_official_protocol_english331_manifest_v1.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 331
    assert len({row["card_key"] for row in rows}) == 331
    forbidden = {"base", "role_card", "question", "answer", "dialogue"}
    assert all(not (forbidden & set(row)) for row in rows)


def test_esc_eval_english331_preflight_identity_and_hashes_are_reproducible():
    preflight = load("g0_official_protocol_english331_preflight_v1.json")
    payload = json.dumps(preflight["identity_payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(payload).hexdigest() == preflight["run_identity"]
    assert preflight["logical_calls"] == {"supporter": 3310, "local_role": 3310, "qwen_paid": 1655, "judge": 0}
    for name, expected in preflight["input_hashes"].items():
        if name.startswith("executable::"):
            leaf = name.removeprefix("executable::")
            path = ROOT / "src" / leaf if leaf == "metacom_pm/api.py" else ROOT / "scripts" / "v3" / leaf
        else:
            path = AUTHORITY / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_es_memeval_complete_public_release_is_second_official_track():
    active = load("v3_official_first_evaluation_authority_v1.json")
    memory = active["active_primary_tracks"][1]
    identity = load("es_memeval_public_v1_0_0_1427_identity_decision_v1.json")
    assert memory["benchmark"] == "ES-MemEval"
    assert identity["identity_manifest"]["rows"] == 1427
    assert identity["identity_manifest"]["owners"] == 18
    assert "1209" in memory["paper_boundary"] and "1427" in memory["paper_boundary"]

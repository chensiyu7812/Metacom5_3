from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"
RUNNER_PATH = PROJECT_ROOT / "scripts" / "v3" / "16_run_g0_research_aligned_esc.py"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(name: str) -> dict:
    return json.loads((AUTHORITY / name).read_text(encoding="utf-8"))


def test_research_aligned_preflight_is_zero_call_text_free_and_bound() -> None:
    report = _json("g0_research_aligned_generator_preflight_v2.json")
    rows_bytes = (AUTHORITY / "g0_research_aligned_screening_manifest_v2.jsonl").read_bytes()
    rows = [json.loads(line) for line in rows_bytes.decode("utf-8").splitlines() if line]
    assert report["status"] == "ZERO_CALL_PREFLIGHT_PASS_EXECUTION_REQUIRES_IDENTITY_SPECIFIC_APPROVAL"
    assert report["api_calls"] == 0
    assert report["contains_role_card_or_dialogue_text"] is False
    assert report["run_identity"] == "9852e4c492a027c145bd1216bd7a5584a348ed9f3323c872797280a02e21ed62"
    assert hashlib.sha256(rows_bytes).hexdigest() == report["sample"]["manifest_sha256"]
    assert len(rows) == len({row["card_key"] for row in rows}) == 24
    assert sum(row["canary"] for row in rows) == 2
    assert not any("text" in key or "problem" in key for row in rows for key in row)


def test_prompt_is_prior_work_grounded_and_has_no_length_cap() -> None:
    prompt = _json("g0_research_aligned_supporter_prompt_v1.json")
    joined = "\n\n".join(prompt["prompt_sections"])
    report = _json("g0_research_aligned_generator_preflight_v2.json")
    assert hashlib.sha256(joined.encode("utf-8")).hexdigest() == report["prompt"]["joined_prompt_sha256"]
    assert prompt["output_length_policy"]["researcher_token_cap"] is None
    assert prompt["output_length_policy"]["provider_output_parameter"] == "OMITTED"
    assert {row["source"] for row in prompt["lineage"]} == {
        "ESConv / Towards Emotional Support Dialog Systems",
        "Can Large Language Models be Good Emotional Supporter?",
        "ExTES",
        "ESCoT",
        "ESC-Judge",
    }
    assert "Exploration" in joined and "Insight" in joined and "Action" in joined
    assert "Return only the supporter's reply." in joined


def test_candidate_configurations_show_qwen_quality_latency_tradeoff() -> None:
    contract = _json("g0_research_aligned_generator_contract_v2.json")
    assert len(contract["candidates"]) == 4
    qwen = [row for row in contract["candidates"] if row["candidate_id"].startswith("qwen37_plus_")]
    assert {row["enable_thinking"] for row in qwen} == {False, True}
    assert {row["model"] for row in qwen} == {"qwen3.7-plus-2026-05-26"}
    assert contract["shared_generation_contract"]["researcher_output_token_cap"] is None
    assert contract["selection_rule"]["no_composite"] is True
    assert contract["selection_rule"]["latency_cannot_override_quality"] is True


def test_runner_omits_provider_cap_and_reserves_worst_case_qwen_output(monkeypatch) -> None:
    monkeypatch.setenv("IGNORED_KEY", "test")
    from metacom_pm.api import Endpoint, chat_request_payload

    payload = chat_request_payload(
        Endpoint(
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            model="qwen3.7-plus-2026-05-26",
            api_key_env="IGNORED_KEY",
            enable_thinking=True,
        ),
        [{"role": "user", "content": "respond"}],
        temperature=0.0,
        max_tokens=None,
        seed=None,
        response_schema=None,
    )
    assert "max_tokens" not in payload and "max_completion_tokens" not in payload
    runner = _module(RUNNER_PATH, "g0r2_runner")
    reserve = runner._qwen_pre_call_reserve([{"role": "user", "content": "respond"}])
    assert reserve["input_upper_tokens"] >= 4096
    assert reserve["reserve_usd"] >= 65536 * 1.6 / 1_000_000
    assert runner._qwen_call_cost({"prompt_tokens": 1000, "completion_tokens": 2000}) == 0.0036


def test_superseded_bd2b_measurement_cannot_rank_generator_capability() -> None:
    closeout = _json("g0_bd2b_prompt_cap_measurement_closeout_v1.json")
    assert closeout["status"] == "STOPPED_PROMPT_AND_OUTPUT_CAP_MEASUREMENT_INVALID_FOR_MAXIMUM_CAPABILITY"
    assert "ranking maximum supporter capability" in closeout["forbidden_use"]
    qwen = closeout["observed_at_stop"]["esc"]["qwen37_plus_primary_challenger"]
    assert qwen["provider_length_finishes"] == 25
    assert closeout["immutable_private_evidence_hashes"][
        "project/outputs/v3_g0_generator_screen_bd2b_20260813/private_turn_ledger.jsonl"
    ] == "6c36e3317f9c2aed03a4e55e3a4352d14059a23baf702f677259dcda69ad5218"

from __future__ import annotations

from pathlib import Path

import pytest

from metacom_pm.api import CallResult, Endpoint
from metacom_pm.config import load_config
import metacom_pm.evoemo as evoemo_module
from metacom_pm.evoemo import (
    build_fixed_seeker_tracks_v22,
    evaluator_context,
    load_evoemo,
    persist_fixed_seeker_tracks_v22_dry_run,
    plan_fixed_seeker_tracks_v22,
    seeker_system_prompt,
)
from metacom_pm.fixed_seeker_contract import (
    FIXED_SEEKER_SYSTEM_PROMPT_TEMPLATE_SHA256,
    FixedSeekerGenerationContract,
)
from metacom_pm.io import iter_jsonl, read_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVOEMO_PATH = PROJECT_ROOT / "data" / "external" / "evo_emo.json"


def _contract_mapping(**overrides):
    value = {
        "version": "pm-v2.2-fixed-seeker-generation-v1",
        "seeker_endpoint": "seeker",
        "system_prompt_id": "evoemo-fixed-seeker-v1",
        "system_prompt_template_sha256": (
            FIXED_SEEKER_SYSTEM_PROMPT_TEMPLATE_SHA256
        ),
        "response_instruction_token_limit": 60,
        "temperature": 0.2,
        "max_output_tokens": 300,
        "output_normalization": "normalize_space_v1",
        "finish_reason_protocol": "pm-v2-finish-reason-v1",
        "accepted_normalized_finish_reasons": ["complete"],
        "maximum_physical_attempts_per_logical_call": 1,
        "seed_protocol": "base-seed-plus-turn-index-v1",
        "elicitation_scaffold_protocol": (
            "deterministic-generic-open-loop-v1"
        ),
    }
    value.update(overrides)
    return value


def _contract() -> FixedSeekerGenerationContract:
    return FixedSeekerGenerationContract.from_mapping(_contract_mapping())


def _endpoint(*, model: str = "fixture-seeker") -> Endpoint:
    return Endpoint(
        base_url="https://fixture.invalid/v1",
        model=model,
        api_key_env="FIXTURE_KEY",
        family="fixture-family",
        timeout_seconds=17.0,
    )


class _FakeClient:
    def __init__(
        self,
        *,
        normalized_finish_reason: str = "complete",
        provider_finish_reason: str | None = "stop",
    ) -> None:
        self.normalized_finish_reason = normalized_finish_reason
        self.provider_finish_reason = provider_finish_reason
        self.calls: list[dict] = []
        self.closed = False

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        index = len(self.calls)
        return (
            CallResult(
                text=f"  seeker response {index}  ",
                raw_response={
                    "choices": [
                        {"finish_reason": self.provider_finish_reason}
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 5,
                        "total_tokens": 25,
                    },
                },
                usage={
                    "prompt_tokens": 20,
                    "completion_tokens": 5,
                    "total_tokens": 25,
                },
                latency_ms=1.0,
                request_hash=f"request-{index}",
                provider_finish_reason=self.provider_finish_reason,
                normalized_finish_reason=self.normalized_finish_reason,
            ),
            None,
        )

    def close(self):
        self.closed = True


def _plan(out_dir: Path, *, max_turns: int = 2):
    estimate, rows = plan_fixed_seeker_tracks_v22(
        EVOEMO_PATH,
        seeker_endpoint=_endpoint(),
        contract=_contract(),
        simulator_id="seeker_main",
        max_turns=max_turns,
        seeds=[101],
        max_scenarios=1,
    )
    persist_fixed_seeker_tracks_v22_dry_run(out_dir, estimate, rows)
    return estimate, rows


def test_fixed_seeker_contract_separates_instruction_from_api_cap() -> None:
    config = load_config(PROJECT_ROOT / "configs" / "pm_v2.yaml")
    contract = FixedSeekerGenerationContract.from_mapping(
        config["fixed_seeker_generation_treatment"]
    )
    assert contract == _contract()
    assert contract.response_instruction_token_limit == 60
    assert contract.max_output_tokens == 300
    assert "at most 60 tokens" in contract.render_system_prompt({"topic": "x"})
    user = load_evoemo(EVOEMO_PATH)[0]
    topic = user["subsequent_topics"][0]
    assert contract.render_system_prompt(
        evaluator_context(user, topic)
    ) == seeker_system_prompt(user, topic)

    with pytest.raises(ValueError, match="max_output_tokens must equal 300"):
        FixedSeekerGenerationContract.from_mapping(
            _contract_mapping(max_output_tokens=60)
        )
    with pytest.raises(ValueError, match="accept only complete"):
        FixedSeekerGenerationContract.from_mapping(
            _contract_mapping(
                accepted_normalized_finish_reasons=["complete", "length"]
            )
        )


def test_fixed_seeker_dry_run_is_client_free_and_has_exact_budget(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        evoemo_module,
        "make_client",
        lambda endpoint: pytest.fail("dry-run created an API client"),
    )
    estimate, rows = _plan(tmp_path)
    assert estimate["scenario_count"] == 1
    assert estimate["maximum_physical_api_attempts"] == 2
    assert estimate["maximum_output_tokens_per_call"] == 300
    assert estimate["maximum_total_output_tokens"] == 600
    assert len(rows) == 2
    assert len({row["logical_call_key"] for row in rows}) == 2
    assert all(row["maximum_physical_attempts"] == 1 for row in rows)
    assert all(
        row["fixed_seeker_generation_contract_sha256"]
        == estimate["fixed_seeker_generation_contract_sha256"]
        for row in rows
    )

    changed_endpoint_estimate, changed_rows = plan_fixed_seeker_tracks_v22(
        EVOEMO_PATH,
        seeker_endpoint=_endpoint(model="changed-model"),
        contract=_contract(),
        simulator_id="seeker_main",
        max_turns=2,
        seeds=[101],
        max_scenarios=1,
    )
    assert changed_endpoint_estimate["dry_run_acceptance_sha256"] != estimate[
        "dry_run_acceptance_sha256"
    ]
    assert changed_rows[0]["logical_call_key"] != rows[0]["logical_call_key"]


def test_fixed_seeker_run_rejects_wrong_hash_before_client(
    monkeypatch, tmp_path: Path
) -> None:
    _plan(tmp_path, max_turns=1)
    monkeypatch.setattr(
        evoemo_module,
        "make_client",
        lambda endpoint: pytest.fail("invalid acceptance created a client"),
    )
    with pytest.raises(RuntimeError, match="must exactly equal"):
        build_fixed_seeker_tracks_v22(
            EVOEMO_PATH,
            tmp_path,
            seeker_endpoint=_endpoint(),
            contract=_contract(),
            simulator_id="seeker_main",
            accepted_dry_run_sha256="wrong",
            max_turns=1,
            seeds=[101],
            max_scenarios=1,
        )
    assert not (tmp_path / "physical_attempt_ledger.jsonl").exists()


def test_fixed_seeker_complete_calls_use_300_and_bind_all_artifacts(
    monkeypatch, tmp_path: Path
) -> None:
    estimate, rows = _plan(tmp_path)
    fake = _FakeClient()
    monkeypatch.setattr(evoemo_module, "make_client", lambda endpoint: fake)
    summary = build_fixed_seeker_tracks_v22(
        EVOEMO_PATH,
        tmp_path,
        seeker_endpoint=_endpoint(),
        contract=_contract(),
        simulator_id="seeker_main",
        accepted_dry_run_sha256=estimate["dry_run_acceptance_sha256"],
        max_turns=2,
        seeds=[101],
        max_scenarios=1,
    )
    assert summary["status"] == "COMPLETE"
    assert summary["completion_truncated_count"] == 0
    assert summary["normalized_finish_reason_counts"]["complete"] == 2
    assert fake.closed
    assert len(fake.calls) == 2
    assert all(call["max_tokens"] == 300 for call in fake.calls)
    assert all(call["temperature"] == 0.2 for call in fake.calls)
    assert all(call["retries"] == 1 for call in fake.calls)

    track = list(iter_jsonl(tmp_path / "fixed_seeker_tracks.jsonl"))[0]
    digest = estimate["fixed_seeker_generation_contract_sha256"]
    assert track["fixed_seeker_generation_contract_sha256"] == digest
    assert track["fixed_seeker_generation_contract"] == estimate[
        "fixed_seeker_generation_contract"
    ]
    assert [item["logical_call_key"] for item in track["turn_provenance"]] == [
        row["logical_call_key"] for row in rows
    ]
    assert all(
        item["normalized_finish_reason"] == "complete"
        for item in track["turn_provenance"]
    )

    raw_rows = list(iter_jsonl(tmp_path / "raw_seeker_calls.jsonl"))
    assert [row["provider_finish_reason"] for row in raw_rows] == ["stop", "stop"]
    assert [row["normalized_finish_reason"] for row in raw_rows] == [
        "complete",
        "complete",
    ]
    assert all(row["completion_truncated"] is False for row in raw_rows)
    manifest = read_json(tmp_path / "run_manifest.json")
    attestation = read_json(tmp_path / "artifact_attestation.json")
    for artifact in (summary, manifest, attestation["parameters"]):
        assert artifact["fixed_seeker_generation_contract_sha256"] == digest
        assert artifact["fixed_seeker_generation_contract"] == estimate[
            "fixed_seeker_generation_contract"
        ]
    assert attestation["expected"]["completion_truncated_count"] == 0


@pytest.mark.parametrize(
    ("normalized", "provider"),
    [
        ("length", "length"),
        ("unknown", None),
        ("tool_call", "tool_calls"),
        ("content_filter", "content_filter"),
    ],
)
def test_fixed_seeker_noncomplete_is_terminal_before_track_write(
    monkeypatch,
    tmp_path: Path,
    normalized: str,
    provider: str | None,
) -> None:
    estimate, _ = _plan(tmp_path, max_turns=2)
    fake = _FakeClient(
        normalized_finish_reason=normalized,
        provider_finish_reason=provider,
    )
    monkeypatch.setattr(evoemo_module, "make_client", lambda endpoint: fake)
    with pytest.raises(RuntimeError, match="generation incomplete"):
        build_fixed_seeker_tracks_v22(
            EVOEMO_PATH,
            tmp_path,
            seeker_endpoint=_endpoint(),
            contract=_contract(),
            simulator_id="seeker_main",
            accepted_dry_run_sha256=estimate["dry_run_acceptance_sha256"],
            max_turns=2,
            seeds=[101],
            max_scenarios=1,
        )
    assert len(fake.calls) == 1
    assert not (tmp_path / "fixed_seeker_tracks.jsonl").exists()
    ledger_rows = list(iter_jsonl(tmp_path / "physical_attempt_ledger.jsonl"))
    assert [row["event"] for row in ledger_rows] == ["STARTED", "FAILED"]
    assert ledger_rows[-1]["result"]["normalized_finish_reason"] == normalized
    raw = list(iter_jsonl(tmp_path / "raw_seeker_calls.jsonl"))[0]
    assert raw["provider_finish_reason"] == provider
    assert raw["normalized_finish_reason"] == normalized
    assert raw["completion_truncated"] is (normalized == "length")
    assert raw["error"]
    summary = read_json(tmp_path / "summary.json")
    assert summary["status"] == "INCOMPLETE"
    assert summary["completed_tracks"] == 0

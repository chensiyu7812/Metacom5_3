from __future__ import annotations

import numpy as np
import pytest
import torch

from metacom_pm.pm_v1_5_semantic import (
    FrozenSemanticEncoderSpec,
    FrozenTransformerSemanticEncoder,
    SEMANTIC_CANARY_TEXTS,
    SemanticEncoderBinding,
    require_recorded_semantic_runtime,
    semantic_runtime_attestation,
    summarize_semantic_truncation_audits,
)


class _CanaryEncoder:
    spec = FrozenSemanticEncoderSpec(
        model_id="fixture/canary",
        revision="1" * 40,
        snapshot_tree_sha256="2" * 64,
        max_length=64,
        output_dimension=16,
    )
    binding = SemanticEncoderBinding(
        spec_sha256=spec.digest(),
        snapshot_tree_sha256="2" * 64,
        snapshot_file_count=1,
        implementation="transformers-auto-model-cls-float32",
    )
    model = torch.nn.Linear(2, 2, bias=False)

    def encode(self, texts):
        rows = []
        for index, _ in enumerate(texts):
            row = np.arange(1, 17, dtype=float) + index
            rows.append(row / np.linalg.norm(row))
        return np.vstack(rows)


class _CountingTokenizer:
    truncation_side = "right"

    def __call__(self, text, **kwargs):
        del kwargs
        return {"input_ids": [101, *range(len(text.split())), 102]}


class _ReversibleTokenizer:
    truncation_side = "right"

    def __init__(self) -> None:
        self._token_to_id: dict[str, int] = {}
        self._id_to_token: dict[int, str] = {}

    def __call__(self, text, *, add_special_tokens=False, **kwargs):
        del kwargs
        ids = []
        for token in str(text).split():
            if token not in self._token_to_id:
                token_id = 1000 + len(self._token_to_id)
                self._token_to_id[token] = token_id
                self._id_to_token[token_id] = token
            ids.append(self._token_to_id[token])
        if add_special_tokens:
            ids = [101, *ids, 102]
        return {"input_ids": ids}

    def decode(self, ids, **kwargs):
        del kwargs
        return " ".join(self._id_to_token[value] for value in ids if value >= 1000)


def test_semantic_runtime_record_is_exact_and_fail_closed() -> None:
    observed = semantic_runtime_attestation(_CanaryEncoder())
    assert observed.canary_shape == [len(SEMANTIC_CANARY_TEXTS), 16]
    assert observed.user_site_enabled is False
    assert observed.user_site_on_sys_path is False
    config = {"semantic_runtime": observed.model_dump(mode="json")}
    recorded = {
        "status": "PASS",
        "contract": observed.model_dump(mode="json"),
        "contract_sha256": observed.digest(),
    }
    assert require_recorded_semantic_runtime(config, recorded)["status"] == "PASS"
    tampered = {**recorded, "contract_sha256": "0" * 64}
    with pytest.raises(RuntimeError, match="digest mismatch"):
        require_recorded_semantic_runtime(config, tampered)


def test_tokenization_telemetry_reports_loss_without_text_or_token_ids() -> None:
    encoder = _CanaryEncoder()
    encoder.tokenizer = _CountingTokenizer()
    telemetry = FrozenTransformerSemanticEncoder.tokenization_telemetry(
        encoder,
        ["short input", " ".join(["long"] * 100)],
        view_names=["current_user_text", "visible_dialogue_state"],
    )
    assert telemetry["views"]["current_user_text"]["truncated"] is False
    assert telemetry["views"]["visible_dialogue_state"]["truncated"] is True
    assert telemetry["views"]["visible_dialogue_state"]["truncated_token_count"] == 38
    assert "input_ids" not in str(telemetry)
    assert "long long" not in str(telemetry)

    summary = summarize_semantic_truncation_audits(
        [{"tokenization": telemetry}]
    )
    assert summary["current_user_text_complete"] is True
    assert summary["views"]["visible_dialogue_state"]["truncation_rate"] == 1.0


def test_section_aware_visible_state_preserves_recent_history_without_implicit_loss() -> None:
    encoder = _CanaryEncoder()
    encoder.tokenizer = _ReversibleTokenizer()
    state_text, allocation = (
        FrozenTransformerSemanticEncoder.assemble_visible_dialogue_state(
            encoder,
            current_user_text=" ".join(f"current{index}" for index in range(70)),
            current_session_history=[
                {
                    "role": "user" if index % 2 == 0 else "assistant",
                    "content": " ".join(
                        f"history{index}_{token}" for token in range(20)
                    ),
                }
                for index in range(10)
            ],
            current_session_summary=" ".join(
                f"summary{index}" for index in range(80)
            ),
        )
    )
    encoded = encoder.tokenizer(state_text, add_special_tokens=True)["input_ids"]
    assert len(encoded) <= encoder.spec.max_length
    assert allocation["protocol"].endswith("v2-section-aware")
    assert allocation["implicit_full_state_truncation"] == "forbidden"
    assert allocation["sections"]["current_user"]["retained_token_count"] == 32
    assert allocation["sections"]["session_summary"]["retained_token_count"] == 16
    assert allocation["sections"]["recent_dialogue"]["dropped_token_count"] > 0
    assert "history9_19" in state_text
    assert "history0_0" not in state_text
    assert "history9_19" not in str(allocation)

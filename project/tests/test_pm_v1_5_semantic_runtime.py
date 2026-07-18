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
        max_length=32,
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


def test_semantic_runtime_record_is_exact_and_fail_closed() -> None:
    observed = semantic_runtime_attestation(_CanaryEncoder())
    assert observed.canary_shape == [len(SEMANTIC_CANARY_TEXTS), 16]
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
        ["short input", " ".join(["long"] * 40)],
        view_names=["current_user_text", "visible_dialogue_state"],
    )
    assert telemetry["views"]["current_user_text"]["truncated"] is False
    assert telemetry["views"]["visible_dialogue_state"]["truncated"] is True
    assert telemetry["views"]["visible_dialogue_state"]["truncated_token_count"] == 10
    assert "input_ids" not in str(telemetry)
    assert "long long" not in str(telemetry)

    summary = summarize_semantic_truncation_audits(
        [{"tokenization": telemetry}]
    )
    assert summary["current_user_text_complete"] is True
    assert summary["views"]["visible_dialogue_state"]["truncation_rate"] == 1.0

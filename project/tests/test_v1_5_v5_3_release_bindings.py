from __future__ import annotations

from pathlib import Path

import pytest

from metacom_pm.v1_5_v5_3_release_bindings import (
    EXPECTED_BGE_M3_REVISION,
    EXPECTED_STRATEGY_BANK_SHA256,
    build_static_release_bindings,
)


ROOT = Path(__file__).resolve().parents[1]


def test_static_release_binds_six_card_bank_bge_and_six_baselines() -> None:
    binding = build_static_release_bindings(ROOT)
    assert binding.strategy_bank.card_count == 6
    assert binding.strategy_bank.sha256 == EXPECTED_STRATEGY_BANK_SHA256
    assert binding.ms_retriever.snapshot_revision == EXPECTED_BGE_M3_REVISION
    assert binding.ms_retriever.local_files_only is True
    assert len(binding.response_baselines) == 6
    assert binding.me_retriever.method == (
        "PRODUCTION_LEXICAL_TYPED_TIER_EXACT_RANK1_COMPILE_OR_OFF"
    )
    assert binding.me_retriever.rank2_promotion_allowed is False
    assert binding.me_retriever.bge_reranker_adopted is False
    assert binding.api_calls == 0


def test_release_identity_changes_when_an_implementation_binding_changes() -> None:
    binding = build_static_release_bindings(ROOT)
    data = binding.model_dump(mode="json")
    data["shared_implementations"]["typed_step2"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="release_identity"):
        type(binding).model_validate(data)

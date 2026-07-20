from __future__ import annotations

from pathlib import Path

import pytest

from metacom_pm.config import load_config
from metacom_pm.generation_contract import SupporterGenerationContract
from metacom_pm.response_mechanism_contract import (
    RESPONSE_MECHANISM_CONTRACT_PROTOCOL,
    build_response_mechanism_contract,
    require_matching_response_mechanism_contract,
)

ROOT = Path(__file__).resolve().parents[1]


def _supporter_contract() -> SupporterGenerationContract:
    config = load_config(ROOT / "configs" / "pm_v1_5.yaml")
    return SupporterGenerationContract.from_config(config)


def _base_kwargs(**overrides) -> dict:
    kwargs = dict(
        project_root=ROOT,
        supporter_generation_contract=_supporter_contract(),
        generator_endpoint_sha256="a" * 64,
        strategy_bank_sha256="b" * 64,
        memory_min_score=0.0,
        strategy_min_score=0.0,
        strategy_top_k=3,
        evidence_filter_enabled=False,
    )
    kwargs.update(overrides)
    return kwargs


def test_contract_is_deterministic_given_identical_inputs():
    first = build_response_mechanism_contract(**_base_kwargs())
    second = build_response_mechanism_contract(**_base_kwargs())
    assert first["contract_sha256"] == second["contract_sha256"]
    assert first == second


def test_contract_protocol_tag_is_stable():
    contract = build_response_mechanism_contract(**_base_kwargs())
    assert contract["protocol"] == RESPONSE_MECHANISM_CONTRACT_PROTOCOL


@pytest.mark.parametrize(
    "override",
    [
        {"generator_endpoint_sha256": "c" * 64},
        {"strategy_bank_sha256": "d" * 64},
        {"memory_min_score": 0.1},
        {"strategy_min_score": 0.1},
        {"strategy_top_k": 5},
        {"evidence_filter_enabled": True},
    ],
)
def test_contract_hash_changes_with_every_input(override):
    baseline = build_response_mechanism_contract(**_base_kwargs())
    changed = build_response_mechanism_contract(**_base_kwargs(**override))
    assert changed["contract_sha256"] != baseline["contract_sha256"]


def test_contract_hash_changes_when_shared_mechanism_code_changes(tmp_path, monkeypatch):
    # Copy the real project tree is too heavy for a unit test; instead prove
    # the code-identity binding works by pointing project_root at a temp
    # directory with a byte-perturbed copy of one mechanism file and
    # confirming the contract hash differs from the real tree's contract.
    import shutil

    fake_root = tmp_path / "project"
    (fake_root / "src" / "metacom_pm").mkdir(parents=True)
    from metacom_pm.response_mechanism_contract import MECHANISM_CODE_RELATIVE_PATHS

    for relative in MECHANISM_CODE_RELATIVE_PATHS:
        dest = fake_root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, dest)

    baseline = build_response_mechanism_contract(**_base_kwargs(project_root=fake_root))

    perturbed_path = fake_root / "src" / "metacom_pm" / "text.py"
    perturbed_path.write_text(
        perturbed_path.read_text(encoding="utf-8") + "\n# perturbed\n",
        encoding="utf-8",
    )
    perturbed = build_response_mechanism_contract(**_base_kwargs(project_root=fake_root))
    assert perturbed["contract_sha256"] != baseline["contract_sha256"]
    assert (
        perturbed["shared_code_manifest"]["src/metacom_pm/text.py"]
        != baseline["shared_code_manifest"]["src/metacom_pm/text.py"]
    )


def test_canary_prompts_are_four_distinct_hashes():
    contract = build_response_mechanism_contract(**_base_kwargs())
    canaries = contract["canary_prompts"]
    assert set(canaries) == {"M0+R0", "M0+RS", "ME+R0", "ME+RS"}
    assert len(set(canaries.values())) == 4


def test_require_matching_response_mechanism_contract_passes_when_equal():
    contract = build_response_mechanism_contract(**_base_kwargs())
    require_matching_response_mechanism_contract(
        expected=contract, actual=contract, context="test"
    )


def test_require_matching_response_mechanism_contract_fails_closed_when_different():
    expected = build_response_mechanism_contract(**_base_kwargs())
    actual = build_response_mechanism_contract(**_base_kwargs(strategy_top_k=99))
    with pytest.raises(RuntimeError, match="response mechanism contract"):
        require_matching_response_mechanism_contract(
            expected=expected, actual=actual, context="test"
        )

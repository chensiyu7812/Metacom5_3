from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "budget_bound_runner_test",
    ROOT / "scripts/v1_5/243l_continue_paper1_v3_ms_executor_function_budget_bound_reviews_v1_5.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeClient:
    def __init__(self, family: str) -> None:
        self.endpoint = type("Endpoint", (), {"family": family})()
        self.seen = None

    def chat(self, *args, **kwargs):
        self.seen = kwargs["max_tokens"]
        return self.seen


def test_budget_wrapper_overrides_old_runner_hardcode_by_family() -> None:
    gemini = FakeClient("google_gemini_2_5_flash")
    gpt = FakeClient("openai_gpt_5_mini")
    assert MODULE.BudgetBoundClient(gemini).chat([], max_tokens=600) == 1400
    assert MODULE.BudgetBoundClient(gpt).chat([], max_tokens=1400) == 600

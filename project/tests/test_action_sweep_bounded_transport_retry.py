from __future__ import annotations

from pathlib import Path

import pytest

from metacom_pm.api import CallResult, Endpoint, ProviderRequestError, RetryableProviderError
from metacom_pm.contracts import MemoryBackendRecord
from metacom_pm.io import iter_jsonl, read_json, write_jsonl
from metacom_pm.sweep import run_action_sweep


def _endpoint() -> Endpoint:
    return Endpoint("https://invalid.example", "never-called", "UNSET", family="test")


def _write_two_card_fixture(
    tmp_path: Path, tiny_state, tiny_memories, tiny_strategy
) -> tuple[Path, Path, Path, list[tuple[str, str]]]:
    """Two cards, action_filter narrowed to 2 actions each -- 4 logical calls."""

    card_a = tiny_state.model_copy(
        update={"card_id": "card_a0000000000000", "state_id": "state_a0000000000000"}
    )
    card_b = tiny_state.model_copy(
        update={"card_id": "card_b0000000000000", "state_id": "state_b0000000000000"}
    )
    runtime = tmp_path / "runtime.jsonl"
    backend = tmp_path / "backend.jsonl"
    strategies = tmp_path / "strategies.jsonl"
    write_jsonl(runtime, [card_a.model_dump(mode="json"), card_b.model_dump(mode="json")])
    write_jsonl(
        backend,
        [
            MemoryBackendRecord(card_id=card_a.card_id, items=tiny_memories).model_dump(
                mode="json"
            ),
            MemoryBackendRecord(card_id=card_b.card_id, items=tiny_memories).model_dump(
                mode="json"
            ),
        ],
    )
    write_jsonl(strategies, [tiny_strategy.model_dump(mode="json")])
    actions = ["M0+R0", "M0+RS"]
    expected_keys = [
        (card_id, action_id)
        for card_id in (card_a.card_id, card_b.card_id)
        for action_id in actions
    ]
    return runtime, backend, strategies, expected_keys


class ScriptedClient:
    """Fake OpenAICompatibleClient: chat() outcomes are scripted per *physical*
    call, in strict call order, so transient-failure-then-recovery and
    terminal-failure scenarios can be exercised deterministically."""

    script: list = []
    call_log: list = []

    def __init__(self, endpoint):
        self.endpoint = endpoint

    def close(self) -> None:
        pass

    def chat(self, messages, *, temperature, max_tokens, seed, response_schema, retries):
        index = len(type(self).call_log)
        type(self).call_log.append(messages)
        action = type(self).script[index]
        if isinstance(action, BaseException):
            raise action
        return action, None


def _success_result(tag: str) -> CallResult:
    return CallResult(
        text=f"A supportive response ({tag}).",
        raw_response={"fixture": tag},
        usage={"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105},
        latency_ms=1.0,
        request_hash=f"prompt-equivalence-{tag}",
    )


def test_bounded_transport_retry_recovers_after_transient_5xx_and_completes_exactly(
    tmp_path, monkeypatch, tiny_state, tiny_memories, tiny_strategy
):
    runtime, backend, strategies, expected_keys = _write_two_card_fixture(
        tmp_path, tiny_state, tiny_memories, tiny_strategy
    )
    ScriptedClient.script = [
        RetryableProviderError(
            "transient", last_retry_class="http_5xx", last_status_code=503,
            attempts_tried=1,
        ),
        RetryableProviderError(
            "transient", last_retry_class="network_timeout", last_status_code=None,
            attempts_tried=2,
        ),
        _success_result("call1-attempt3"),
        _success_result("call2"),
        _success_result("call3"),
        _success_result("call4"),
    ]
    ScriptedClient.call_log = []
    import metacom_pm.sweep as sweep_module

    monkeypatch.setattr(sweep_module, "OpenAICompatibleClient", ScriptedClient)
    out_dir = tmp_path / "out"
    summary = run_action_sweep(
        runtime,
        backend,
        strategies,
        out_dir / "outcomes.jsonl",
        out_dir / "raw.jsonl",
        out_dir / "summary.json",
        endpoint=_endpoint(),
        action_filter={"M0+R0", "M0+RS"},
        request_retries=3,
        fail_fast=False,
        transport_retry_policy="bounded_transport",
        transport_backoff_seconds=(0.0, 0.0),
    )
    assert summary["status"] == "COMPLETE"
    assert len(ScriptedClient.call_log) == 6
    outcomes = list(iter_jsonl(out_dir / "outcomes.jsonl"))
    assert {(row["card_id"], row["action_id"]) for row in outcomes} == set(expected_keys)
    assert len(outcomes) == len(expected_keys)
    ledger_rows = list(iter_jsonl(out_dir / "physical_attempt_ledger.jsonl"))
    events_by_key: dict[str, list[str]] = {}
    for row in ledger_rows:
        events_by_key.setdefault(row["call_key"], []).append(row["event"])
    # Exactly one call_key needed 3 physical attempts (2 transient failures
    # then a success); the other three succeeded on their first attempt.
    attempt_counts = sorted(len(events) // 2 for events in events_by_key.values())
    assert attempt_counts == [1, 1, 1, 3]
    recovered = [key for key, events in events_by_key.items() if len(events) == 6]
    assert len(recovered) == 1
    assert events_by_key[recovered[0]] == [
        "STARTED", "FAILED", "STARTED", "FAILED", "STARTED", "SUCCEEDED",
    ]


def test_bounded_transport_retry_never_double_bills_a_succeeded_call(
    tmp_path, monkeypatch, tiny_state, tiny_memories, tiny_strategy
):
    runtime, backend, strategies, expected_keys = _write_two_card_fixture(
        tmp_path, tiny_state, tiny_memories, tiny_strategy
    )
    ScriptedClient.script = [
        _success_result("call1"),
        _success_result("call2"),
        _success_result("call3"),
        _success_result("call4"),
    ]
    ScriptedClient.call_log = []
    import metacom_pm.sweep as sweep_module

    monkeypatch.setattr(sweep_module, "OpenAICompatibleClient", ScriptedClient)
    out_dir = tmp_path / "out"
    kwargs = dict(
        endpoint=_endpoint(),
        action_filter={"M0+R0", "M0+RS"},
        request_retries=3,
        fail_fast=False,
        transport_retry_policy="bounded_transport",
        transport_backoff_seconds=(0.0, 0.0),
    )
    summary = run_action_sweep(
        runtime, backend, strategies,
        out_dir / "outcomes.jsonl", out_dir / "raw.jsonl", out_dir / "summary.json",
        **kwargs,
    )
    assert summary["status"] == "COMPLETE"
    assert len(ScriptedClient.call_log) == 4

    def _forbid_more_calls(*args, **kwargs):
        raise AssertionError("a succeeded call must never be re-issued")

    monkeypatch.setattr(ScriptedClient, "chat", _forbid_more_calls)
    resumed_summary = run_action_sweep(
        runtime, backend, strategies,
        out_dir / "outcomes.jsonl", out_dir / "raw.jsonl", out_dir / "summary.json",
        **kwargs,
    )
    assert resumed_summary["status"] == "COMPLETE"
    assert resumed_summary["new_physical_http_attempts"] == 0
    assert resumed_summary["historical_physical_http_attempts"] == 4
    outcomes = list(iter_jsonl(out_dir / "outcomes.jsonl"))
    assert len(outcomes) == len(expected_keys)


def test_bounded_transport_retry_exhausts_the_per_call_attempt_cap(
    tmp_path, monkeypatch, tiny_state, tiny_memories, tiny_strategy
):
    runtime, backend, strategies, expected_keys = _write_two_card_fixture(
        tmp_path, tiny_state, tiny_memories, tiny_strategy
    )
    always_transient = RetryableProviderError(
        "transient", last_retry_class="http_5xx", last_status_code=503,
        attempts_tried=1,
    )
    ScriptedClient.script = [
        always_transient, always_transient,  # call 1: exhausts a 2-attempt cap
        _success_result("call2"),
        _success_result("call3"),
        _success_result("call4"),
    ]
    ScriptedClient.call_log = []
    import metacom_pm.sweep as sweep_module

    monkeypatch.setattr(sweep_module, "OpenAICompatibleClient", ScriptedClient)
    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="action sweep incomplete"):
        run_action_sweep(
            runtime, backend, strategies,
            out_dir / "outcomes.jsonl", out_dir / "raw.jsonl", out_dir / "summary.json",
            endpoint=_endpoint(),
            action_filter={"M0+R0", "M0+RS"},
            request_retries=2,
            fail_fast=False,
            transport_retry_policy="bounded_transport",
            transport_backoff_seconds=(0.0, 0.0),
        )
    assert len(ScriptedClient.call_log) == 5
    summary = read_json(out_dir / "summary.json")
    assert summary["status"] == "INCOMPLETE"
    assert summary["completed_outcomes"] == 3
    ledger_rows = list(iter_jsonl(out_dir / "physical_attempt_ledger.jsonl"))
    exhausted_key_events = [
        row for row in ledger_rows if row["call_key"] == ledger_rows[0]["call_key"]
    ]
    assert [row["event"] for row in exhausted_key_events] == [
        "STARTED", "FAILED", "STARTED", "FAILED",
    ]

    # A further invocation must not reserve a 3rd physical attempt for the
    # already-exhausted call: the runtime cap is fail-closed, not silently
    # extended by re-running the script.
    ScriptedClient.script = [always_transient] * 10
    ScriptedClient.call_log = []
    with pytest.raises(RuntimeError, match="action sweep incomplete"):
        run_action_sweep(
            runtime, backend, strategies,
            out_dir / "outcomes.jsonl", out_dir / "raw.jsonl", out_dir / "summary.json",
            endpoint=_endpoint(),
            action_filter={"M0+R0", "M0+RS"},
            request_retries=2,
            fail_fast=False,
            transport_retry_policy="bounded_transport",
            transport_backoff_seconds=(0.0, 0.0),
        )
    assert len(ScriptedClient.call_log) == 0


def test_bounded_transport_retry_never_blindly_retries_terminal_content_errors(
    tmp_path, monkeypatch, tiny_state, tiny_memories, tiny_strategy
):
    runtime, backend, strategies, expected_keys = _write_two_card_fixture(
        tmp_path, tiny_state, tiny_memories, tiny_strategy
    )
    truncated = RetryableProviderError(
        "truncated", last_retry_class="output_token_limit", last_status_code=None,
        attempts_tried=1,
    )
    rejected = ProviderRequestError(
        status_code=401, detail="bad key", schema_mode=False,
    )
    ScriptedClient.script = [
        truncated,
        rejected,
        _success_result("call3"),
        _success_result("call4"),
    ]
    ScriptedClient.call_log = []
    import metacom_pm.sweep as sweep_module

    monkeypatch.setattr(sweep_module, "OpenAICompatibleClient", ScriptedClient)
    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="action sweep incomplete"):
        run_action_sweep(
            runtime, backend, strategies,
            out_dir / "outcomes.jsonl", out_dir / "raw.jsonl", out_dir / "summary.json",
            endpoint=_endpoint(),
            action_filter={"M0+R0", "M0+RS"},
            # A generous per-call budget: a terminal error must consume only
            # ONE attempt, never the full 5-attempt allowance.
            request_retries=5,
            fail_fast=False,
            transport_retry_policy="bounded_transport",
            transport_backoff_seconds=(0.0, 0.0),
        )
    assert len(ScriptedClient.call_log) == 4
    summary = read_json(out_dir / "summary.json")
    assert summary["completed_outcomes"] == 2
    ledger_rows = list(iter_jsonl(out_dir / "physical_attempt_ledger.jsonl"))
    by_key: dict[str, list[str]] = {}
    for row in ledger_rows:
        by_key.setdefault(row["call_key"], []).append(row["event"])
    terminal_single_attempt = [
        events for events in by_key.values() if events == ["STARTED", "FAILED"]
    ]
    assert len(terminal_single_attempt) == 2

    # Re-invoking must never issue a second physical attempt for either
    # terminal call -- both are permanently blocked, not merely "unlucky".
    def _forbid_more_calls(*args, **kwargs):
        raise AssertionError("a terminal failure must never be retried")

    monkeypatch.setattr(ScriptedClient, "chat", _forbid_more_calls)
    with pytest.raises(RuntimeError, match="action sweep incomplete"):
        run_action_sweep(
            runtime, backend, strategies,
            out_dir / "outcomes.jsonl", out_dir / "raw.jsonl", out_dir / "summary.json",
            endpoint=_endpoint(),
            action_filter={"M0+R0", "M0+RS"},
            request_retries=5,
            fail_fast=False,
            transport_retry_policy="bounded_transport",
            transport_backoff_seconds=(0.0, 0.0),
        )
    resumed_summary = read_json(out_dir / "summary.json")
    assert resumed_summary["completed_outcomes"] == 2
    assert resumed_summary["new_physical_http_attempts"] == 0


def test_bounded_transport_retry_covers_state_by_actions_matrix_exactly(
    tmp_path, monkeypatch, tiny_state, tiny_memories, tiny_strategy
):
    runtime, backend, strategies, expected_keys = _write_two_card_fixture(
        tmp_path, tiny_state, tiny_memories, tiny_strategy
    )
    ScriptedClient.script = [
        RetryableProviderError(
            "transient", last_retry_class="rate_limited_429", last_status_code=429,
            attempts_tried=1,
        ),
        _success_result("call1-attempt2"),
        _success_result("call2"),
        _success_result("call3"),
        _success_result("call4"),
    ]
    ScriptedClient.call_log = []
    import metacom_pm.sweep as sweep_module

    monkeypatch.setattr(sweep_module, "OpenAICompatibleClient", ScriptedClient)
    out_dir = tmp_path / "out"
    summary = run_action_sweep(
        runtime, backend, strategies,
        out_dir / "outcomes.jsonl", out_dir / "raw.jsonl", out_dir / "summary.json",
        endpoint=_endpoint(),
        action_filter={"M0+R0", "M0+RS"},
        request_retries=3,
        fail_fast=False,
        transport_retry_policy="bounded_transport",
        transport_backoff_seconds=(0.0, 0.0),
    )
    assert summary["status"] == "COMPLETE"
    assert summary["expected_outcomes"] == len(expected_keys) == 4
    assert summary["completed_outcomes"] == 4
    outcomes = list(iter_jsonl(out_dir / "outcomes.jsonl"))
    outcome_keys = [(row["card_id"], row["action_id"]) for row in outcomes]
    assert sorted(outcome_keys) == sorted(expected_keys)
    assert len(outcome_keys) == len(set(outcome_keys))

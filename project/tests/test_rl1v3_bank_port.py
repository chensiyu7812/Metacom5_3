"""Public port behavior over preserved real snapshots; fake tokenizer is test-only."""
from dataclasses import replace
from pathlib import Path
import itertools
import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.bank.v0_port import PrefixPort, PortFactory, load_bank, make_port_factory
from metacom_pm.rl1v3.io import canonical_json
from metacom_pm.rl1v3.render.v0 import messages
from metacom_pm.rl1v3.retrieve.v0 import ReadPlan

ROOT = Path(__file__).resolve().parents[2]


class TestTokenizer:
    __test__ = False
    identity = "test-only-codepoints-port"
    native_context_tokens = 200000

    def count(self, text):return len(text)
    def prompt_tokens(self, prefix, readings):return len(canonical_json(messages(prefix, readings)))


@pytest.fixture(scope="module")
def assets():
    bank, cfg = load_bank(ROOT)
    source = max((e.source for e in bank.registry.entries if e.source.owner_id == "p2"),
                 key=lambda s:s.chronological_rank)
    cut = next(i for i,t in enumerate(source.turns[:-1]) if t.role == "seeker" and source.turns[i+1].role == "supporter")
    return bank, bank.registry.prefix("p2", source.session_id, cut), cfg


@pytest.fixture
def port(assets):
    bank, prefix, _ = assets
    return PrefixPort(bank, prefix, TestTokenizer(), g_id="test-g", decode_id="not-run")


def test_loading_keeps_all_preserved_identities(assets):
    bank, _, cfg = assets
    assert bank.version == cfg["expected_bank"] and bank.index_version == cfg["expected_index"]
    assert bank.registry.version == cfg["expected_source"]
    assert len(bank.records) == 3188


def test_legal_sessions_never_include_current_or_other_owner(port):
    sessions = port.legal_sessions()
    assert sessions
    assert all(s.owner_id == port.prefix.owner_id and s.chronological_rank < port.prefix.cutoff_rank for s in sessions)
    assert port.prefix.session_id not in {s.session_id for s in sessions}


def test_token_aware_read_carries_real_views_and_full_prompt_charge(port):
    acquired = (); before = port.base_tokens
    for head in K.HEAD_ORDER:
        units = port.unit_tokens(acquired=acquired, input_tokens_before=before)
        result = port.read(head, acquired=acquired, input_tokens_before=before)
        assert isinstance(result, K.ReadSuccess)
        assert result.input_tokens_after - before == units[head]
        assert result.reading.tokens == port.count_tokens(result.reading.reading_text)
        assert not port.verify_records(result.record_ids)
        acquired += (result.reading,); before = result.input_tokens_after
        account = port.token_account(acquired)
        assert account["billed_input_tokens"] == before
        assert before >= account["native_prompt_tokens"]


def test_token_count_cannot_substitute_for_missing_read_context(port):
    first = port.read("ME")
    missing = port.read("MS", input_tokens_before=first.input_tokens_after)
    assert isinstance(missing,K.ReadFailure) and missing.reason == "integrity"
    good = port.read("MS", acquired=(first.reading,), input_tokens_before=first.input_tokens_after)
    assert isinstance(good,K.ReadSuccess) and good.reading.ordinal == 2


def test_forged_reading_or_duplicate_head_is_rejected(port):
    first = port.read("ME")
    forged = replace(first.reading, reading_text=first.reading.reading_text+" invented")
    assert port.read("MS", acquired=(forged,)).reason == "integrity"
    assert port.read("ME", acquired=(first.reading,)).reason == "invalid_action"
    assert port.read("MS").reading.ordinal == 1


def test_size_measurement_is_not_a_successful_over_capacity_get(port):
    plan = port.reader.measure("MS")
    assert isinstance(plan,ReadPlan) and not isinstance(plan,(K.ReadSuccess,K.ReadingView))
    blocked = PrefixPort(port.bank,port.prefix,TestTokenizer(),g_id="test-g",decode_id="not-run",
                         output_reserve_tokens=port.native_context_tokens-port.base_tokens-1)
    units = blocked.unit_tokens()
    assert units["MS"] > 1
    result = blocked.read("MS",input_tokens_before=blocked.base_tokens)
    assert isinstance(result,K.ReadFailure) and result.reason == "capacity"
    assert result.input_tokens_unchanged == blocked.base_tokens and not hasattr(result,"reading")
    assert blocked.action_mask() == ("STOP",)
    assert blocked._validated == {():blocked.base_tokens}


def test_routing_and_bound_ports_match(port):
    factory = PortFactory(port.bank,port.tokenizer,dict(g_id="test-g",decode_id="not-run",output_reserve_tokens=320))
    routed = factory()
    assert routed.terminal_identity(port.prefix) == port.identity
    for head in K.HEAD_ORDER:
        result = routed.read(port.prefix,head,input_tokens_before=port.base_tokens)
        assert replace(result,elapsed_ms=0) == replace(port.read(head),elapsed_ms=0)
        assert not routed.verify_records(port.prefix,result.record_ids)


def test_key_and_execution_trace_preserve_order_and_replay(port):
    keys = set(); traces = set()
    for order in itertools.permutations(K.HEAD_ORDER):
        results=[];before=port.base_tokens
        for head in order:
            result=port.read(head,acquired=tuple(r.reading for r in results),input_tokens_before=before)
            assert isinstance(result,K.ReadSuccess)
            results.append(result);before=result.input_tokens_after
        key=port.terminal_key(results);trace=port.execution_trace(results)
        keys.add(key.sha256);traces.add(trace.sha256)
        replay=port.replay(key)
        assert isinstance(replay,K.ExecutionTrace)
        replay.verify_key(key)
    assert len(keys)==1 and len(traces)==24


def test_version_and_foreign_record_failures_are_explicit(port):
    assert port.read("ME",bank_version="wrong").reason=="integrity"
    assert port.read("ME",index_version="wrong").reason=="integrity"
    foreign=next(r for r in port.bank.records if r.head=="ME" and r.owner_id!=port.prefix.owner_id)
    assert any("owner" in e for e in port.verify_records((foreign.record_id,)))
    assert port.verify_records(("absent",))==["absent:missing_record"]
    assert port.verify_records(())==["empty_record_group"]


def test_injected_fixture_tokenizer_requires_explicit_identity():
    with pytest.raises(ValueError,match="explicit reader identity"):
        make_port_factory(root=ROOT,tokenizer=TestTokenizer())

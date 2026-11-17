"""B1 writer v2, RS-v0 label catalog and A1 sources.  Synthetic contexts + WS-A's real registry/bank.

No writer model is called: ``generate`` is a stub returning hand-written text.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from metacom_pm.rl1v3.needs import protocol as V1
from metacom_pm.rl1v3.needs import protocol_v2 as W
from metacom_pm.rl1v3.needs import rs_catalog
from rl1v3_wsb_fixtures import context, writer_output

ROOT = Path(__file__).resolve().parents[2]


class FakeRegistry:
    version = "sources:fixture"

    def entry(self, owner, sid):
        return SimpleNamespace(source_id=f"source:{owner}:{sid}")


def catalog(selectable=("providing_suggestions", "information"), residual=("others",)):
    entries = tuple(dict(family_id=f, label=f, n_cases=1, n_strategy_turns=1, definition="unknown",
                         definition_source=None, writer_selectable=True, note="")
                    for f in selectable) + tuple(dict(family_id=f, label=f, n_cases=1, n_strategy_turns=1,
                                                      definition="unknown", definition_source=None,
                                                      writer_selectable=False, note="residual") for f in residual)
    return rs_catalog.LabelCatalog(catalog_id="fixture-labels", bank_version="bank:fixture", entries=entries)


def count_chars(msgs):           # test-only token proxy; never a measurement
    return sum(len(m["content"]) for m in msgs)


def pack(cat=None, *, native=200_000, operational=100_000, ctx=None):
    ctx = ctx or context()
    return ctx, W.build_pack(ctx, cat, registry=FakeRegistry(), count_prompt=count_chars,
                             native_context_tokens=native, operational_max_input_tokens=operational,
                             tokenizer_identity="test-chars")


def test_v1_prompt_unchanged_and_v2_drops_method_validity_language():
    assert V1.WRITER_PROTOCOL == "pmrl1v3-needcard-writer-v1"
    assert "METHOD_LABELS" in W.SYSTEM_PROMPT and "NOT validated or professional methods" in W.SYSTEM_PROMPT
    assert "METHOD_CATALOG" not in W.SYSTEM_PROMPT and W.SYSTEM_PROMPT != V1.SYSTEM_PROMPT
    assert W.prompt_sha256() != V1.prompt_sha256()


@pytest.mark.parametrize("cat,native,operational,status", [
    (None, 200_000, 100_000, "blocked_catalog"),
    ("cat", 1_000, 100_000, "over_budget_native"),
    ("cat", 200_000, 1_000, "over_budget_operational"),
    ("cat", 200_000, 100_000, "ready"),
])
def test_pre_call_statuses_are_distinct_and_never_truncate(cat, native, operational, status):
    ctx, p = pack(catalog() if cat else None, native=native, operational=operational)
    assert p["status"] == status
    assert p["past_coverage"] == "complete_legal_raw_no_truncation"
    text = json.dumps(W.messages(p), ensure_ascii=False)
    for s in ctx.history:                 # every strictly-past turn is present verbatim, nothing cut
        for t in s.turns:
            assert json.dumps(t.text, ensure_ascii=False)[1:-1] in text
    assert "FUTURE" not in text            # nothing after the cut
    if status != "ready":
        with pytest.raises(ValueError, match="not runnable"):
            W.render_messages(p)


def test_pack_binds_source_identity_and_counts_catalog_tokens():
    _, p = pack(catalog())
    assert p["source_version"] == "sources:fixture" and p["current"]["source_id"] == "source:pX:s2"
    assert [s["source_id"] for s in p["past"]] == ["source:pX:s0", "source:pX:s1"]
    assert p["catalog_tokens"] > 0 and p["method_catalog"]["selectable"] == ["providing_suggestions", "information"]
    shown = W.messages(p)[1]["content"]
    assert '"definition": "unknown"' in shown and '"others"' not in shown


def test_method_need_accepts_label_or_unknown_rejects_residual_and_foreign():
    ctx, p = pack(catalog())
    for ok in ("providing_suggestions", "unknown", None):
        assert W.parse_output(writer_output(method_need=ok), p)["method_need"] == ok
    for bad in ("others", "sleep_hygiene"):
        with pytest.raises(V1.WriterOutputError):
            W.parse_output(writer_output(method_need=bad), p)


def test_run_writer_unknown_method_needs_current_evidence_and_failure_is_not_none():
    ctx, p = pack(catalog())
    writer = W.writer_identity(model_id="stub", model_sha256="0" * 64, decode_id="stub")
    env = W.run_writer(ctx, p, lambda m: writer_output(method_need="unknown"), writer=writer)
    assert env["status"] == "ok" and env["needcard"].method_need == "unknown" and "RS" in env["head_needs"]["required"]
    env = W.run_writer(ctx, p, lambda m: writer_output(method_need="unknown",
                                                         method_evidence=[{"quote": "My sister Anna moved to Berlin in March"}]),
                       writer=writer)
    assert env["needcard"].method_need is None
    assert any(d["reason"] == "method_without_verified_evidence" for d in env["drops"])
    calls = []
    env = W.run_writer(ctx, p, lambda m: calls.append(1) or "not json", writer=writer)
    assert env["status"] == "writer_failed" and env["derived_stratum"] is None and len(calls) == 2


# ------------------------------------------------------------------ real WS-A registry / bank

@pytest.fixture(scope="module")
def real():
    from metacom_pm.rl1v3.env import a1b_port as P
    from metacom_pm.rl1v3.sources import source_registry as S
    bank = P.load_bank(ROOT, registry_dir="project/outputs/pm_rl1/v3/A1_preparation/final/registry",
                       bank_dir="project/outputs/pm_rl1/v3/A1b_preparation/measured_v1/bank",
                       expected_source="sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02",
                       expected_bank="bank:02d0a4b1e62fd033c02b4fdc8e76d8796b285aa058cb59201aacde2c13ce8dd9")
    return bank, S.PinnedInputs(ROOT).read("rs_strategy", lines=True)


def test_rs_v0_label_catalog_is_derived_not_invented(real):
    bank, strategies = real
    cat, audit = rs_catalog.derive(bank, strategies)
    assert audit["rs_cases"] == 875 and audit["strategy_ids_not_in_cards"] == 0
    assert audit["guidance_text_is_generic_template"] is True
    assert len(cat.entries) == 8 and all(e["definition"] == "unknown" for e in cat.entries)
    assert "others" not in cat.selectable and len(cat.selectable) == 7
    assert "not a WS-A MethodCatalog" in cat.as_dict()["status"]


def test_a1_context_and_cross_check_have_zero_content_difference(real):
    from metacom_pm.rl1v3.needs.sources import CensusSources, a1_context, cross_check_full
    bank, _ = real
    adapter = CensusSources(ROOT / "project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json")
    rows = [json.loads(x) for x in (ROOT / "project/outputs/pm_rl1/v3/B0/prefix_census.jsonl").read_text().splitlines()]
    sample = rows[::97]
    res = cross_check_full(adapter, bank.registry, sample)
    assert res["zero_content_difference"], (res["content_mismatches"][:5], res["prefix_mismatches"][:5])
    assert res["personal_sessions"] == 401 and res["a1_derived_flags_checked_against_b0_rule"]["excluded_for_overlap"] == 85
    ctx = a1_context(bank.registry, sample[0])
    assert ctx.prefix.prefix_id == sample[0]["prefix_id"]
    assert all(s.chronological_rank < ctx.prefix.cutoff_rank for s in ctx.history)
    with pytest.raises(ValueError, match="differs from B0"):
        a1_context(bank.registry, dict(sample[0], prefix_id="0" * 64))


def test_tier_appendix_matches_the_unchanged_pool():
    from collections import Counter
    from metacom_pm.rl1v3.needs import sampling as SM
    app = json.loads((ROOT / "project/configs/rl1v3/B1_tier_appendix_v1.json").read_text())
    B0 = ROOT / "project/outputs/pm_rl1/v3/B0"
    rows = [json.loads(x) for x in (B0 / "prefix_census.jsonl").read_text().splitlines()]
    pool = SM.natural_eval_pool(rows, SM.load_exposure(B0 / "exposure_registry.jsonl"))
    summ = SM.pool_summary(pool)
    assert app["session_cap"] == SM.SESSION_CAP == 2 and app["session_cap_changed"] is False
    for t in ("S", "M", "L"):
        assert app["tiers"][t]["realized"] == summ[t]["actual_total"]
        assert app["tiers"][t]["short_owners"] == summ[t]["short_owners"]
    assert (app["tiers"]["S"]["realized"], app["tiers"]["M"]["realized"], app["tiers"]["L"]["realized"]) == (288, 482, 748)
    assert app["tiers"]["L"]["name"] == "L-realized" and app["tiers"]["L"]["plan_nominal"] == 960
    assert max(Counter((r["owner_id"], r["session_id"]) for r in pool).values()) <= 2

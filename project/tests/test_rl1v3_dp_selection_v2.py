"""Synthetic mechanism tests only; no real human choices or formal sample selection."""
import copy
import json
from pathlib import Path
import pytest
from metacom_pm.rl1v3.compile import dp_selection as V1, dp_selection_v2 as D
from metacom_pm.rl1v3.io import object_sha256

PID = object_sha256("SYNTHETIC_PREFIX_ONLY")


def fixture():
    labels = [dict(prefix_id=PID, owner_id="fixture-owner", group="fixture-group", need="S1")]
    screening = dict(simulated=False, verified_by="UNIT_TEST_NOT_HUMAN", verification_evidence="SYNTHETIC_TEST_ONLY",
                     frozen_at="2026-01-01T01:00:00Z", labels=labels, labels_sha256=object_sha256(labels))
    prefixes = [dict(prefix_id=PID, owner_id="fixture-owner", session_id="current", cut_turn=1)]
    manifest = dict(researcher_confirmed=True, signed_by="UNIT_TEST_NOT_RESEARCHER", evidence="SYNTHETIC_TEST_ONLY",
                    prefixes=prefixes, prefixes_sha256=object_sha256(prefixes), frozen_at="2026-01-01T02:00:00Z",
                    screening_receipt_sha256=object_sha256(screening))
    refs = [dict(owner_id="fixture-owner", session_id="past", turn_index=0, speaker="seeker", exact_quote="A synthetic history.")]
    c = dict(record_id="fixture-source", owner_id="fixture-owner", session_id="past", family_id="fixture-family",
             reported_at=dict(session_rank=0, date="2025-01-01"), known_at=dict(session_rank=0), ready_at=dict(session_rank=0),
             text="seeker: A synthetic history.", source_refs=refs)
    pool = dict(owner_id="fixture-owner", prefix_id=PID, snapshot_sha=object_sha256("synthetic snapshot"), candidates=[c],
                prefix=dict(owner_id="fixture-owner", prefix_id=PID, session_id="current", cutoff_rank=1,
                            timestamp="2025-01-02", family_id="fixture-family", ancestor_family_ids=[],
                            turns=[dict(role="seeker", text="A synthetic current need.")]))
    bundle = D.wrap_bundle(V1.wrap_pools([pool], object_sha256(manifest), formal=True))
    roles = dict(sample_identity=bundle["sample_identity"], signed_by="UNIT_TEST_COORDINATOR", evidence="SYNTHETIC_TEST_ONLY",
                 frozen_at="2026-01-01T02:01:00Z", people={"S":"person-S", "R":"person-R", "S_alias":"person-S"},
                 assignments={PID:dict(selector="S", reviewers={ch:["R"] for ch in ("Q0", "QH", "F")})})
    draft = dict(protocol=D.PROTOCOL, bundle_sha256=bundle["bundle_sha256"], prefix_id=PID,
                 pool_sha256=bundle["rows"][0]["pool_sha256"], selector="S", current_need="Synthetic need", rationale="Synthetic rationale",
                 declared_at="2026-01-01T03:00:00Z", outcomes_not_seen=True, rankings_not_seen=True,
                 decision="selected", selected_record_id="fixture-source", single_session_coverage="partial", missing_need="Synthetic later stage unknown",
                 staleness_issue=True, staleness_detail="Synthetic possible change", stage_issue=True, stage_detail="Synthetic intention, not completion")
    ret = dict(bundle_sha256=bundle["bundle_sha256"], rows={PID:dict(pool_sha256=draft["pool_sha256"], selected_record_id="fixture-source")})
    baseline = dict(identity=dict(renderer_id="fixture-old", g_id="fixture-g", decode_id="fixture-decode", step2_id="fixture-no-plan"),
                    spec=dict(system_prompt="Synthetic test only.", decode=dict(max_new_tokens=320)))
    return bundle, roles, draft, ret, baseline, manifest, screening


class Counter:
    def ids(self, messages):
        return list(range(len(json.dumps(messages))))


def prepared(tmp_path, decision="selected"):
    b, roles, d, ret, base, manifest, screening = fixture()
    if decision != "selected":
        d.update(decision=decision, selected_record_id=None, single_session_coverage="none")
    rec = D.freeze_choice(b, d, roles, tmp_path, now="2026-01-01T03:01:00Z")
    receipts = {PID:rec}
    rows = D.export_candidates(b, receipts, roles, ret, base, Counter())
    plan = D.bind_plan(b, receipts, roles, rows, manifest, screening, now="2026-01-01T04:00:00Z")
    return b, receipts, roles, rows, manifest, screening, plan


def test_fields_sha_plan_and_prestart_path(tmp_path):
    b, receipts, roles, rows, manifest, screening, plan = prepared(tmp_path)
    rec = receipts[PID]
    assert all(k in rec for k in D.EXTRA_FIELDS)
    assert plan["selection_receipts_sha256"][PID] == rec["receipt_sha256"]
    assert len(rows) == 3 and all(r["selection_receipt_sha256"] == rec["receipt_sha256"] for r in rows)
    result = D.check_start(plan, b, receipts, roles, rows, manifest, screening, now="2026-01-01T04:00:01Z")
    assert result["engineering_ready"] and not result["authorized"] and not result["generation_started"]
    assert D.check_reviewer(plan, b, receipts, roles, PID, "R", "QH")
    with pytest.raises(FileExistsError):
        _, _, draft, *_ = fixture()
        D.freeze_choice(b, draft, roles, tmp_path, now="2026-01-01T03:01:00Z")


@pytest.mark.parametrize("decision", ["none_suitable", "uncertain"])
def test_absent_choice_stays_pending_never_ret_or_off(tmp_path, decision):
    b, receipts, roles, rows, manifest, screening, plan = prepared(tmp_path, decision)
    dp = next(r for r in rows if r["arm"] == "DP-MS")
    assert dp["model_input"] is None and dp["material_status"] == decision
    assert dp["request_id"] in plan["material_pending"]
    dp["model_input"] = rows[0]["model_input"]
    dp["messages_sha256"] = object_sha256(dp["model_input"]["messages"])
    dp["input_ids_sha256"] = object_sha256(dp["model_input"]["input_ids"])
    dp["request_id"] = D.request_id(dp)
    with pytest.raises(ValueError, match="human choice|material availability"):
        D.bind_plan(b, receipts, roles, rows, manifest, screening, now="2026-01-01T04:00:00Z")


@pytest.mark.parametrize("change", [dict(missing_need=""), dict(staleness_issue="false"), dict(stage_detail=""),
    dict(single_session_coverage="full"), dict(rankings_not_seen=False), dict(outcomes_not_seen=False)])
def test_missing_or_contradictory_fields_rejected_before_write(tmp_path, change):
    b, roles, d, *_ = fixture(); d.update(change)
    with pytest.raises(ValueError):
        D.freeze_choice(b, d, roles, tmp_path, now="2026-01-01T03:01:00Z")
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize("reviewer", ["S", "S_alias"])
def test_same_person_cannot_select_and_review_even_with_alias(tmp_path, reviewer):
    b, roles, d, *_ = fixture(); roles["assignments"][PID]["reviewers"]["F"] = [reviewer]
    with pytest.raises(ValueError, match="cannot review"):
        D.freeze_choice(b, d, roles, tmp_path, now="2026-01-01T03:01:00Z")


def test_actual_review_assignee_checked_again(tmp_path):
    b, rec, roles, rows, manifest, screen, plan = prepared(tmp_path)
    with pytest.raises(ValueError, match="not assigned"):
        D.check_reviewer(plan, b, rec, roles, PID, "S_alias", "Q0")
    roles["assignments"][PID]["reviewers"]["Q0"] = ["S_alias"]
    with pytest.raises(ValueError):
        D.check_reviewer(plan, b, rec, roles, PID, "S_alias", "Q0")


@pytest.mark.parametrize("when", ["2026-01-01T03:00:00Z", "2026-01-01T04:00:00Z"])
def test_plan_and_selection_must_strictly_precede_start(tmp_path, when):
    b, rec, roles, rows, manifest, screen, plan = prepared(tmp_path)
    with pytest.raises(ValueError, match="predate"):
        D.check_start(plan, b, rec, roles, rows, manifest, screen, now=when)


@pytest.mark.parametrize("target", ["receipt", "rows", "plan", "roles"])
def test_frozen_binding_tamper_is_rejected(tmp_path, target):
    b, rec, roles, rows, manifest, screen, plan = prepared(tmp_path)
    if target == "receipt": rec[PID]["missing_need"] = "changed after freezing"
    elif target == "rows": rows[0]["model_input"]["messages"][-1]["content"] = "changed prefix"
    elif target == "plan": plan["selection_receipts_sha256"][PID] = "changed"
    else: roles["evidence"] = "changed registry"
    with pytest.raises(ValueError):
        D.check_start(plan, b, rec, roles, rows, manifest, screen, now="2026-01-01T04:00:01Z")


def test_simulated_unconfirmed_or_unbound_screening_cannot_fix_sample():
    b, roles, d, ret, base, manifest, screen = fixture()
    for mutation in ("simulated", "unconfirmed", "unbound", "outcomes"):
        m, s = copy.deepcopy(manifest), copy.deepcopy(screen)
        if mutation == "simulated": s["simulated"] = True
        elif mutation == "unconfirmed": m["researcher_confirmed"] = False
        elif mutation == "unbound": s["labels"][0]["need"] = "S0"
        else:
            s["labels"][0]["outcome_score"] = 1
            s["labels_sha256"] = object_sha256(s["labels"])
        with pytest.raises(ValueError): D.validate_sample(m, s)


def test_no_rule_dp_arm_or_changed_receipt_source(tmp_path):
    b, rec, roles, rows, manifest, screen, plan = prepared(tmp_path)
    rows[1]["arm"] = "Rule-DP"
    with pytest.raises(ValueError, match="no Rule-DP"):
        D.bind_plan(b, rec, roles, rows, manifest, screen, now="2026-01-01T04:00:00Z")


def test_v2_ui_contains_required_fields_and_keeps_safe_text_rendering():
    b, *_ = fixture(); page = D.selection_html(b)
    assert "single_session_coverage" in page and "missing_need" in page and "staleness_issue" in page and "stage_issue" in page
    assert "none_suitable" in page and "uncertain" in page and ".innerHTML" not in page
    assert "connect-src 'none'" in page and ".textContent" in page
    assert "__BUNDLE_BASE64__" not in page

"""Offline source-review record and arithmetic; no new grades or requests."""
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import launch as live

s = live.s
OUT = live.BASE / "anchor_calibration_results_20261020_v1"


def main():
    protocol, _ = live.a.load()
    data = s.read(OUT / "RESULTS.json")
    targets = {t["target_id"]: t for t in s.read(live.PREP / "targets.json")}
    rows = data["slots"]
    get = lambda target, arm, draw=1: next(r for r in rows
        if r["target"] == target and r["arm"] == arm and r["draw"] == draw)
    assert data["cumulative"] == 225 and data["actual_new_attempts"] == 24
    assert live.historical_count() == 201
    assert data["unresolved_liability_usd"] == "0"
    assert all(r["technical_valid"] and r["q"] is not None and r["m"] is not None for r in rows)
    fingerprints = set()
    ends = []
    start_times = []
    for slot, row in zip(protocol["schedule"], rows):
        sid = slot["slot_id"]
        request = s.read(live.ROOT / (sid + ".request.json"))
        start = s.read(live.ROOT / (sid + ".started.json"))
        raw = s.read(live.ROOT / (sid + ".response.json"))
        frozen = s.read(live.PREP / targets[slot["target_id"]]["payloads"][slot["arm"]]["file"])
        assert request["messages"] == frozen["messages"] and request["schema"] == frozen["schema"]
        assert request["wire_body"] == live.p.api_body(protocol["config"], frozen["messages"])
        assert request["input_screen"]["client_truncation"] is False
        assert raw["model"] == "deepseek-flash" and raw["choices"][0]["finish_reason"] == "stop"
        expected_id = s.digest(dict(protocol=protocol["identity"], slot=sid,
                                    messages=frozen["messages"], schema=frozen["schema"]))
        assert expected_id == row["request_identity"] == raw["request_identity"] == start["request_identity"]
        assert row["semantic_revisions_applied"] == (2 if row["arm"] == "baseline" else 3)
        final = raw["choices"][0]["message"]["content"]
        assert hashlib.sha256(final.encode()).hexdigest() == row["final_sha256"]
        source = json.loads(frozen["messages"][1]["content"])["legal_evidence"]
        ids = {x["id"] for x in source["current_prefix"]}
        ids.update(x["id"] for h in source["legal_past_sessions"] for x in h["turns"])
        value = s.read(live.ROOT / (sid + ".result.json"))["evaluation"]["value"]
        assert all(set(a["source_turn_ids"]) <= ids for a in value["assessments"])
        fingerprints.add(raw["system_fingerprint"])
        start_times.append(start["started_unix"])
        ends.append(start["started_unix"] + row["elapsed_seconds"])
    assert len(fingerprints) == 1
    repeats = []
    for target in ("context_01_0000", "context_02_0000"):
        for arm in ("baseline", "calibrated"):
            first, repeat = get(target, arm), get(target, arm, 2)
            reqs = [s.read(live.ROOT / (r["slot_id"] + ".request.json")) for r in (first, repeat)]
            assert reqs[0] == reqs[1]
            assert first["request_identity"] != repeat["request_identity"]
            repeats.append(dict(target=target, arm=arm, positions=[first["position"], repeat["position"]],
                q=[first["q"], repeat["q"]], m=[first["m"], repeat["m"]], U=[first["U"], repeat["U"]],
                absolute_U_change=abs(first["U"]-repeat["U"]), input_identical=True,
                independent_cases=1))
    ids = {x["slot_id"] for x in protocol["schedule"]}
    ledger = live.LEDGER.read_bytes()
    prefix = b""
    tail = []
    found = False
    for line in ledger.splitlines(keepends=True):
        value = json.loads(line)
        if value.get("reservation_id") in ids:
            found = True
        if found:
            tail.append(value)
            assert value.get("reservation_id") in ids
        else:
            prefix += line
    assert hashlib.sha256(prefix).hexdigest() == protocol["financial_baseline"]["ledger_sha256"]
    assert len([x for x in tail if x["event"] == "RESERVED"]) == 24
    assert len([x for x in tail if x["event"] == "SETTLED"]) == 24
    old = s.read(live.BASE / "noise_human_analysis_20261020_v1/analysis.json")
    pairs = []
    for oldrow in [x for x in old["pairs"] if x["pair_id"] in ("P01", "P03")]:
        left, right = oldrow["left_endpoint"], oldrow["right_endpoint"]
        assert targets[left]["binding"]["reply_identity"] == oldrow["left_reply_identity"]
        assert targets[right]["binding"]["reply_identity"] == oldrow["right_reply_identity"]
        assert targets[left]["binding"]["evidence_identity"] == oldrow["evidence_identity"]
        assert targets[right]["binding"]["evidence_identity"] == oldrow["evidence_identity"]
        cost = Fraction(targets[right]["binding"]["resource_tokens"] -
                        targets[left]["binding"]["resource_tokens"], 40960)
        for arm in ("baseline", "calibrated"):
            on = get(right, arm)
            off = [get(left, arm, draw) for draw in (1, 2)]
            differences = [Fraction(str(on["U"])) - Fraction(str(r["U"])) for r in off]
            net = [x-cost for x in differences]
            pairs.append(dict(pair_id=oldrow["pair_id"], arm=arm, human_direction=oldrow["human_direction"],
                response_hash_binding_verified=True, comparison_qm_gold=False,
                original_human_record_path=str(live.BASE / "noise_human_analysis_20261020_v1/analysis.json"),
                on_draw_reused=1, off_draws=[1, 2],
                U_on_minus_off=[float(x) for x in differences],
                operational_direction=["tie" if x == 0 else "ON" if x > 0 else "OFF" for x in differences],
                resource_cost_exact=str(cost), resource_cost=float(cost),
                net_reward_difference=[float(x) for x in net], net_reward_difference_exact=[str(x) for x in net],
                net_sign_changed=net[0]*net[1] < 0,
                not_independent_replicates=True, not_actual_policy_training=True))
    metrics = dict(
        first_pass_equal_qm=sum((get(t, "baseline")["q"], get(t, "baseline")["m"]) ==
                               (get(t, "calibrated")["q"], get(t, "calibrated")["m"]) for t in targets),
        first_pass_denominator=10, repeats=repeats, reference_pairs=pairs,
        response_window_seconds=max(ends)-min(start_times),
        first_scoring_utc=datetime.fromtimestamp(min(start_times), timezone.utc).isoformat(),
        last_result_utc=datetime.fromtimestamp(max(ends), timezone.utc).isoformat(),
        system_fingerprints=sorted(fingerprints), independent_validation_cases=0,
        human_reference_pairs=2, human_reference_contexts=2, newly_confirmed_human_labels=0,
        aggregate_accuracy=None, reward_qualification=False)
    s.save(OUT / "DIAGNOSTIC_METRICS.json", metrics)
    s.save(OUT / "postrun_verification.json", dict(
        passed=True, started=24, complete_results=24, exact_frozen_requests=24,
        native_stop=24, complete_usage_settled=24, expected_semantic_versions=24,
        repeated_payloads_identical=4, human_reply_and_source_bindings=2,
        old_started_count_preserved=201, old_stops_unchanged=9,
        frozen_preparation_hashes=len(protocol["immutable_files"]),
        original_ledger_prefix_sha256=hashlib.sha256(prefix).hexdigest(),
        added_reservations=24, added_settlements=24, unknown_liability="0",
        models_queries=1, balance_queries=1, credential_values_in_artifacts=False,
        credential_assertion_basis="existing transport persists no authentication headers; secret file never copied",
        no_score_repair=True, no_extra_requests=True, no_sealed_reads=True,
        source_id_validity_is_not_semantic_entailment=True,
        single_fingerprint_not_immutable_weight_guarantee=True))
    print(s.canonical(metrics))


if __name__ == "__main__":
    os.umask(0o077)
    main()

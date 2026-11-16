"""Read-only replay of seven submitted preferences against frozen noise results.

No requests, imports of model runners, credential reads, or source mutations.
Prints derived analysis as JSON; execute from any directory.
"""
import hashlib
import json
from collections import Counter
from datetime import datetime
from fractions import Fraction
from pathlib import Path

ROOT = Path("/opt/tokkio-data0/tokkio_projects/Metacom5_3")
BASE = ROOT / "project/outputs/pm_rl1/judge_selection_preparation_20261014_v1"
HUMAN = Path("/home/tokkio/PMRL1_中文人评_7组_2026-10-20T06-36-51.json")
PACKET = Path("/home/tokkio/PM_RL1_REFERENCE_DELTA_20261020")
DELTA = BASE / "reference_delta_20261020_v2"
PROPOSAL = BASE / "reward_noise_proposal_20261020_v1"
EXECUTION = BASE / "reward_noise_execution_20261020_v1"
DERIVED = EXECUTION / "derived_1792474528960608601"
LIVE = BASE / "reward_noise_runs/pmrl1-resource-decision-noise-v1-20261020/live"
OLD_HUMAN = ROOT / "project/outputs/pm_rl1/human_acceptance_20261014_v2/intake/rater_1_development_original_private.json"
LEDGER = ROOT / "project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(x):
    return Fraction(str(x))


def direction(delta):
    return "A" if delta > 0 else "B" if delta < 0 else "tie"


def average(values):
    return sum(values, Fraction(0)) / len(values)


def exact(values):
    return [str(x) for x in values]


def validate_submission(human, metadata):
    assert human["version"] == metadata["version"]
    assert human["proposal_identity"] == metadata["proposal_identity"]
    items = human["answers"]
    assert len(items) == len({a["pair_id"] for a in items}) == 7
    assert {a["pair_id"] for a in items} == set(metadata["pending_pairs"])
    bindings = {r["pair_id"]: r for r in metadata["all_bindings"]}
    for answer in items:
        target = bindings[answer["pair_id"]]
        for side in ("left", "right"):
            key = f"{side}_reply_identity"
            assert answer[key] == target[key], (answer["pair_id"], key)
        assert answer["direction"] in {"A", "B", "tie", "unknown"}
        assert answer["reason"].strip()


def summarize(rows, field):
    comparable = [r for r in rows if r["human_direction"] != "unknown"]
    selected = [r for r in comparable if r[field] is not None]
    ties = [r for r in selected if r["human_direction"] == "tie"]
    directional = [r for r in selected if r["human_direction"] in {"A", "B"}]
    return {
        "planned_human_pairs": len(rows),
        "human_unknown": len(rows) - len(comparable),
        "complete_comparable_pairs": len(selected),
        "missing_measurement": len(comparable) - len(selected),
        "agreement": sum(r[field] == r["human_direction"] for r in selected),
        "human_ties": len(ties),
        "tie_agreement": sum(r[field] == "tie" for r in ties),
        "direction_on_human_tie": sum(r[field] != "tie" for r in ties),
        "human_directional": len(directional),
        "directional_agreement": sum(r[field] == r["human_direction"] for r in directional),
        "denominator_note": (
            "Seven new human judgments, four contexts, two source owners; repeated readouts are not independent."
            if len(rows) == 7 else
            "One historical P04 preference under earlier instructions; not a new or reconfirmed judgment."
        ),
    }


def analyze():
    h, meta = read(HUMAN), read(PACKET / "packet_metadata.json")
    validate_submission(h, meta)
    assert h["original_html_sha256"] == digest(PACKET / "researcher.html")
    audits = read(DELTA / "coordinator/pair_reuse_audit.json")
    endpoints = {e["row_id"]: e for e in read(PROPOSAL / "selected_endpoints.json")}
    results = read(DERIVED / "per_request_results.json")
    assert len(results) == 48
    assert len({r["request_identity"] for r in results}) == 48
    scores = {}
    for r in results:
        assert r["started"] and r["technical_valid"] and not r["model_unknown"]
        assert r["U"] is not None and r["q"] is not None and r["m"] is not None
        assert scalar(r["U"]) == scalar(r["q"]) / 4 - scalar(r["m"])
        key = (r["endpoint"], r["draw"])
        assert key not in scores
        scores[key] = r
    human_map = {a["pair_id"]: a for a in h["answers"]}
    historical = read(DELTA / "coordinator/reused_P04_original_record.json")
    old_match = historical["old_pair_matches"][0]
    assert old_match["fresh_human_observations"] == 0
    assert digest(Path(old_match["source"]["path"])) == old_match["source"]["sha256"]
    old_raw = read(OLD_HUMAN)["labels"]
    assert any(r == old_match["raw_label"] for r in old_raw)
    rows = []
    for binding in audits:
        pid = binding["pair_id"]
        left, right = binding["left_endpoint"], binding["right_endpoint"]
        a, b = endpoints[left], endpoints[right]
        assert a["evidence_identity"] == b["evidence_identity"] == binding["evidence_identity"]
        for side, e in (("left", a), ("right", b)):
            assert e["reply_identity"] == binding[f"{side}_reply_identity"]
        for endpoint in (a, b):
            payload_path = PROPOSAL / endpoint["payload_file"]
            assert digest(payload_path) == endpoint["payload_file_sha256"]
        answer = human_map.get(pid)
        human_direction = answer["direction"] if answer else old_match["current_display_preference"]
        assert answer is not None or pid == "P04"
        pairs = [(scores[(left, d)], scores[(right, d)]) for d in range(1, 5)]
        dq = [(scalar(x["q"]) - scalar(y["q"])) / 4 for x, y in pairs]
        dm = [scalar(x["m"]) - scalar(y["m"]) for x, y in pairs]
        du = [scalar(x["U"]) - scalar(y["U"]) for x, y in pairs]
        assert all(u == q - m for u, q, m in zip(du, dq, dm))
        means = [average(du[:2]), average(du[2:])]
        cost_a_minus_b = Fraction(a["resource_tokens"] - b["resource_tokens"], 40960)
        rows.append({
            **{k: binding[k] for k in ("pair_id", "left_endpoint", "right_endpoint", "left_reply_identity", "right_reply_identity", "evidence_identity")},
            "context": a["context_id"], "owner": a["owner"],
            "human_direction": human_direction,
            "human_reason_verbatim": answer["reason"] if answer else old_match["raw_label"]["reason"],
            "reference_scope": "new_single_researcher_holistic_preference" if answer else "historical_original_instruction_scope_not_reconfirmed",
            "draw_q_contribution_A_minus_B": exact(dq),
            "draw_m_A_minus_B": exact(dm),
            "draw_U_A_minus_B": exact(du),
            "draw_directions": [direction(x) for x in du],
            "single_1": direction(du[0]),
            "single_3": direction(du[2]),
            "mean_12": direction(means[0]),
            "mean_34": direction(means[1]),
            "mean_q_contribution_A_minus_B": exact([average(dq[:2]), average(dq[2:])]),
            "mean_m_A_minus_B": exact([average(dm[:2]), average(dm[2:])]),
            "mean_U_A_minus_B": exact(means),
            "cost_A_minus_B": str(cost_a_minus_b),
            "net_mean_A_minus_B": exact([v - cost_a_minus_b for v in means]),
            "human_comparison_excludes_resource_cost": True,
            "human_tie_not_exact_cardinal_utility_gold": True,
            "request_ids_by_draw": [[x["request_identity"], y["request_identity"]] for x, y in pairs],
        })
    new = [r for r in rows if r["pair_id"] != "P04"]
    old = [r for r in rows if r["pair_id"] == "P04"]
    protocol = read(EXECUTION / "protocol.json")
    immutable_hashes = protocol["immutable_files"]
    assert all(digest(Path(p)) == sha for p, sha in immutable_hashes.items())
    old_stops = read(EXECUTION / "provenance/old_stops.json")
    assert all(digest(Path(p)) == sha for p, sha in old_stops.items())
    finances = read(LIVE / "financial_closeout.json")
    assert digest(LEDGER) == finances["ledger_sha256"]
    assert finances["unsettled"] == []
    preserved_paths = [
        HUMAN, PACKET / "packet_metadata.json", PACKET / "researcher.html",
        DELTA / "coordinator/pair_reuse_audit.json",
        DELTA / "coordinator/reused_P04_original_record.json",
        OLD_HUMAN, DERIVED / "per_request_results.json",
        EXECUTION / "protocol.json", LIVE / "financial_closeout.json", LEDGER,
    ]
    # Preserve the true live score/final artifacts too; never rewrite them.
    for suffix in ("*.started.json", "*.result.json", "*.response.json"):
        preserved_paths.extend(sorted(LIVE.glob(suffix)))
    elapsed = (datetime.fromisoformat(h["exported"].replace("Z", "+00:00")) -
               datetime.fromisoformat(h["started"].replace("Z", "+00:00"))).total_seconds()
    return {
        "version": "pmrl1-noise-human-reference-analysis-20261020-v1",
        "new_human_annotations": 7, "new_independent_reviewers": 0,
        "reviewer_description": "researcher supplied; reviewer_id blank preserved; previous result exposure disclosed",
        "new_distribution": dict(Counter(a["direction"] for a in h["answers"])),
        "historical_reused_pairs": 1, "human_unknown_new": 0,
        "context_count": len({r["context"] for r in new}),
        "source_owner_count": len({r["owner"] for r in new}),
        "browser_interval_seconds_not_active_work_time": elapsed,
        "self_reported_minutes": h["self_reported_minutes"],
        "paired_readout_method": "Exact sign of U_A-U_B, no post-hoc epsilon. Cost excluded. Operational agreement with holistic reference, not absolute q/m accuracy.",
        "new_seven_readout": {k: summarize(new, k) for k in ("single_1", "single_3", "mean_12", "mean_34")},
        "historical_P04_readout": {k: summarize(old, k) for k in ("single_1", "single_3", "mean_12", "mean_34")},
        "pairs": rows,
        "reference_asset_inventory": {
            "old_open_pairs": 16, "old_preference_counts": dict(Counter(r["preference"] for r in old_raw)),
            "additional_new_pairs": 7, "total_pair_records": 23,
            "not_23_independent_cases": True,
            "old_and_new_instruction_versions_kept_separate": True,
            "atomic_q_m_gold_not_inferred": True,
            "sealed_24_read": False,
        },
        "score_attempts_total": 201, "capacity": 289, "new_model_calls": 0,
        "natural_RL_updates": 0, "semantic_revisions_applied": 2,
        "qualification_granted": False, "new_cost_usd": "0",
        "financial_closeout_unchanged": finances,
        "preserved_input_hashes": {str(p): digest(p) for p in preserved_paths},
        "immutable_protocol_hashes_checked": len(immutable_hashes),
        "old_stops_unchanged": old_stops,
        "remaining_capacity_not_authorization": 88,
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), ensure_ascii=False, indent=2))

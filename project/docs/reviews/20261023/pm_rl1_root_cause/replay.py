"""Read-only root-cause evidence audit. Python standard library only.

Reads the existing train/dev pool and already opened diagnostic references.
Never opens sealed human submissions/test text, runs a model, or creates reward
labels. Outputs are new analysis records, not qualification or training inputs.
Private raw files are required; absence is an error, never fabricated data.
"""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def audit(project):
    project = Path(project).resolve()
    hashes = {}

    def read(relative):
        path = project / relative
        data = path.read_bytes()
        hashes[str(path.relative_to(project))] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    q = "outputs/pm_rl1/completion_20260930_v2"
    b = "outputs/pm_rl1/judge_selection_preparation_20261014_v1"
    prep = "outputs/pm_rl1/completion_preparation_20261022"
    pointer = read(q + "/P2/common_pool/primary_generation_pointer.json")
    # Resolve the archived run basename against the chosen checkout, not the
    # original host's absolute path. The raw hashes/identities are checked below.
    generation = q + "/P2/common_pool/generation/" + Path(pointer["run_dir"]).name
    summary = read(generation + "/summary.json")
    slots = read(q + "/P2/common_pool/slots_private.json")
    expected_slots = {r["slot_id"]: r for r in slots["rows"]}
    evidence = read(q + "/P3/common_evidence/evidence_pool_private.json")
    prior_rows = {r["request_id"]: r for r in read(prep + "/resource_rows_private.json")}
    rows = []
    replies = {}
    grouped = defaultdict(list)
    for row in summary["rows"]:
        assert row["split"] in ("train", "dev")
        rid = row["request_id"]
        req = read(generation + "/" + rid + ".request.json")
        raw = read(generation + "/" + rid + ".raw.json")
        assert hashes[generation + "/" + rid + ".raw.json"] == row["raw_sha256"]
        assert raw["request_id"] == req["request_id"] == rid
        assert digest({k: v for k, v in req.items() if k != "request_id"}) == rid
        assert req["messages"] == expected_slots[row["slot_id"]]["messages"]
        assert raw["source_provenance_identity"] == digest(req["provenance"])
        assert raw["runtime_identity"] == req["executor_identity"]
        assert req["provenance"]["prefix_identity"] == row["prefix_identity"]
        assert req["provenance"]["canonical_counts"] == row["counts"]
        assert raw["finish_reason"] == "natural_stop" and raw["text"]
        assert row["reward_status"] == "UNMEASURED_NOT_ZERO"
        assert prior_rows[rid]["response_identity"] == digest(raw["text"])
        replies[rid] = raw["text"]
        record = {k: row[k] for k in ("request_id", "prefix_identity", "index", "owner", "split", "counts", "resource_tokens")}
        record["response_identity"] = digest(raw["text"])
        record["measurement_input_identity"] = digest([evidence[row["prefix_identity"]], raw["text"]])
        record["runtime_identity"] = raw["runtime_identity"]
        rows.append(record)
        grouped[(row["prefix_identity"], record["measurement_input_identity"])].append(record)
    assert len(rows) == len(prior_rows) == len(expected_slots) == 586
    assert len({r["request_id"] for r in rows}) == 586
    assert len({r["runtime_identity"] for r in rows}) == 1
    off = {r["prefix_identity"]: r for r in rows if not any(r["counts"])}
    assert len(off) == 42
    higher_cost_same_content = []
    for group in grouped.values():
        minimum = min(r["resource_tokens"] for r in group)
        for row in group:
            if row["resource_tokens"] > minimum:
                higher_cost_same_content.append(dict(row, minimum_same_input_tokens=minimum,
                    excess_tokens=row["resource_tokens"] - minimum))
    capacity = {r["prefix_identity"]: r for r in read(q + "/P1/capacity_prefix_private.json")}
    by_split = {}
    for split in ("train", "dev"):
        rs = [r for r in rows if r["split"] == split]
        prefixes = {r["prefix_identity"] for r in rs}
        by_split[split] = dict(rows=len(rs), prefixes=len(prefixes), owners=len({r["owner"] for r in rs}),
            reachable_terminals_in_these_prefixes=sum(capacity[p]["reachable"] for p in prefixes),
            distinct_scoring_inputs=len({r["measurement_input_identity"] for r in rs}),
            same_as_OFF=sum(any(r["counts"]) and replies[r["request_id"]] == replies[off[r["prefix_identity"]]["request_id"]] for r in rs),
            higher_cost_same_content_rows=sum(r["split"] == split for r in higher_cost_same_content))

    hbase = b + "/noise_human_analysis_20261020_v1"
    h = read(hbase + "/researcher_original.json")
    old = read(hbase + "/analysis.json")
    scores = read(hbase + "/original_48_results.json")
    endpoints = {r["row_id"]: r for r in read(b + "/reward_noise_proposal_20261020_v1/selected_endpoints.json")}
    ep_scores = defaultdict(list)
    for score in scores:
        assert score["technical_valid"] and not score["model_unknown"]
        assert Fraction(str(score["U"])) == Fraction(score["q"], 4) - Fraction(str(score["m"]))
        ep_scores[score["endpoint"]].append(score)
    assert len(scores) == len({r["request_identity"] for r in scores}) == 48
    assert len(ep_scores) == 12 and all(len(v) == 4 for v in ep_scores.values())
    for endpoint in endpoints.values():
        rid = endpoint["request_id"]
        assert digest(replies[rid]) == endpoint["reply_identity"]
        assert hashes[generation + "/" + rid + ".raw.json"] == endpoint["raw_file_sha256"]
        assert digest(evidence[endpoint["prefix_identity"]]) == endpoint["evidence_identity"]
    old_pairs = {r["pair_id"]: r for r in old["pairs"]}
    pair_results = []
    for answer in h["answers"]:
        p = old_pairs[answer["pair_id"]]
        for side in ("left", "right"):
            assert answer[side + "_reply_identity"] == p[side + "_reply_identity"]
        assert answer["direction"] == p["human_direction"]
        left = {s["draw"]: s for s in ep_scores[p["left_endpoint"]]}
        right = {s["draw"]: s for s in ep_scores[p["right_endpoint"]]}
        delta = [Fraction(str(left[i]["U"])) - Fraction(str(right[i]["U"])) for i in range(1, 5)]
        directions = ["A" if x > 0 else "B" if x < 0 else "tie" for x in delta]
        assert directions == p["draw_directions"]
        pair_results.append(dict(pair_id=p["pair_id"], context=p["context"],
            human_direction=answer["direction"], draw_directions=directions,
            U_differences=[str(x) for x in delta], stable_direction=len(set(directions)) == 1,
            human_preference_is_not_exact_U=True))
    assert len(pair_results) == 7
    endpoint_variation = []
    for key, ss in sorted(ep_scores.items()):
        ss = sorted(ss, key=lambda r: r["draw"])
        vals = [Fraction(str(s["U"])) for s in ss]
        endpoint_variation.append(dict(endpoint=key, q=[s["q"] for s in ss], m=[s["m"] for s in ss],
            U=[str(x) for x in vals], U_range=str(max(vals) - min(vals)),
            variable=len(set(vals)) > 1, severe_flag_flipped=len({s["m"] == 1 for s in ss}) > 1))
    original_path = "outputs/pm_rl1/human_acceptance_20261014_v2/intake/rater_1_development_original_private.json"
    original = read(original_path)
    comparisons = read("outputs/pm_rl1/human_acceptance_20261014_v2/intake/development_comparisons_private.json")
    accepted = read("outputs/pm_rl1/development_closeout_20261014_v1/acceptance_final/development_intake_private.json")
    accepted = {r["pair_id"]: r for r in accepted if r["reviewer"] == "Chen"}
    original_labels = {r["item_id"]: r for r in original["labels"]}
    early_natural = []
    for comparison in comparisons:
        intake = accepted[comparison["pair_id"]]
        assert intake["group"] == "development"
        assert intake["raw_label"] == original_labels[comparison["Chen_item_id"]]
        assert intake["raw_source"]["sha256"] == hashes[original_path]
        if comparison["kind"] != "natural":
            continue
        assert intake["preference"]["canonical"] == comparison["human_direction"]
        side_replies, side_requests = [], []
        for side in comparison["canonical_sides"]:
            relative = side["raw_path"].split("/project/", 1)[1]
            assert relative.startswith(q + "/P2/common_pool/generation/") and ".." not in Path(relative).parts
            raw = read(relative)
            req = read(relative.replace(".raw.json", ".request.json"))
            assert hashes[relative] == side["raw_sha256"]
            assert raw["request_id"] == req["request_id"] == side["request_id"]
            assert digest({k: v for k, v in req.items() if k != "request_id"}) == side["request_id"]
            side_replies.append(digest(raw["text"]))
            side_requests.append(req)
        assert set(side_replies) == set(intake["reply_identities"].values())
        if comparison["contrast"] == "executor":
            assert side_requests[0]["messages"] == side_requests[1]["messages"]
            assert side_requests[0]["executor_identity"] != side_requests[1]["executor_identity"]
        early_natural.append(dict(original_form_order=comparison["Chen_order"],
            contrast=comparison["contrast"], counts=[s["counts"] for s in comparison["canonical_sides"]],
            human_direction=comparison["human_direction"], judge_direction=comparison["judge_direction"],
            overlapping_historical_P04=set(side_replies) == {old_pairs["P04"]["left_reply_identity"], old_pairs["P04"]["right_reply_identity"]},
            human_preference_is_not_exact_U=True))
    assert len(early_natural) == 8
    relation = read(b + "/relation_reference_results_20261021_v1/SCORE_MATRIX.json")
    task = read(b + "/task_reference_results_20261021_v1/SCORE_MATRIX.json")
    intervention = {}
    for name, matrix in (("relation_reference", relation), ("task_reference", task)):
        intervention[name] = [r for r in matrix if r["material_id"] in ("dev06B", "dev04B", "dev35B")]
    admission = read(q + "/P2/admission_summary.json")
    admitted_rows = read(q + "/P2/final_admission_private.json")
    duplicate_disposition = read(q + "/P2/admission_duplicate_disposition.json")
    assert sum(r["final_status"] == "accept" for r in admitted_rows) == admission["accepted"] == 493
    plan_missing = sorted({r["index"] for r in admitted_rows if r["split"] == "train"}
                          - {r["index"] for r in admitted_rows if r["split"] == "train" and r["final_status"] == "accept"})
    artifacts = dict(
        scope=dict(type="OFFLINE_ROOT_CAUSE_EVIDENCE_AUDIT", new_model_calls=0, new_human_labels=0,
            training_updates=0, test_content_read=False, sealed_labels_read=False, feedback_qualified=False),
        pool=dict(responses=len(rows), prefixes=len(off), scoring_inputs=len(grouped), duplicate_rows=len(rows)-len(grouped),
            non_OFF=len(rows)-len(off), same_as_OFF=sum(v["same_as_OFF"] for v in by_split.values()),
            same_content_higher_cost_rows=len(higher_cost_same_content),
            prefixes_with_same_content_higher_cost=len({r["prefix_identity"] for r in higher_cost_same_content}),
            by_split=by_split, all_requests_and_raw_hashes_verified=True,
            warning="Same-content higher-cost comparisons use identical source/reply and frozen scoring policy; no numeric score is assigned. Distinct replies are not quality differences."),
        repeated_feedback=dict(measurements=48, endpoints=12, contexts=4, source_owners=2,
            variable_U_endpoints=sum(r["variable"] for r in endpoint_variation),
            severe_flag_flip_endpoints=sum(r["severe_flag_flipped"] for r in endpoint_variation),
            endpoint_variation=endpoint_variation,
            human_pairs_with_variable_model_direction=sum(not r["stable_direction"] for r in pair_results),
            human_distribution=dict(Counter(r["human_direction"] for r in pair_results)),
            warning="Four repeats, selected exposed cases, one researcher's holistic preferences; not general judge accuracy or independent samples. P04 remains a historical separate reference."),
        reference_interventions=intervention,
        early_development_natural_comparisons=dict(rows=early_natural,
            resource_pairs=4, resource_human_ties=sum(r["contrast"] == "resource" and r["human_direction"] == "tie" for r in early_natural),
            executor_pairs=4, executor_human_ties=sum(r["contrast"] == "executor" and r["human_direction"] == "tie" for r in early_natural),
            warning="Already opened single-researcher development references, not independent confirmation; historical P04 must not be counted twice. Preferences are not calibrated q/m labels."),
        generator_supervision=dict(actual_targets=admission["accepted"],
            train=sum(r["split"] == "train" and r["final_status"] == "accept" for r in admitted_rows),
            dev=sum(r["split"] == "dev" and r["final_status"] == "accept" for r in admitted_rows),
            train_prefixes=len({r["index"] for r in admitted_rows if r["split"] == "train" and r["final_status"] == "accept"}),
            train_prefixes_without_accepted_targets=plan_missing, final_statuses=dict(Counter(r["final_status"] for r in admitted_rows)),
            behavior_model_reports_not_verified_uptake=admission["coverage"]["train"]["resource_behavior_model_reported"],
            affected_duplicate_key_targets=duplicate_disposition["affected_frozen_targets"], causal_effect_of_these_defects_unknown=True),
        outputs_are_reward_labels=False)
    # Public JSON is aggregate/previously exposed coded diagnostics only.
    return artifacts, dict(source_hashes=hashes, higher_cost_same_content_rows=higher_cost_same_content,
                           human_pairs=pair_results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Use a new output directory; historical analysis is not overwritten.")
    result, private = audit(args.project)
    args.output.mkdir(parents=True, mode=0o700)
    for name, value in (("PROFILE.json", result), ("PROVENANCE_PRIVATE.json", private)):
        path = args.output / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        path.chmod(0o600)
    print(json.dumps({"status": "AUDIT_COMPLETE", "sources": len(private["source_hashes"]),
                      "pool": result["pool"], "new_model_calls": 0}, ensure_ascii=False))

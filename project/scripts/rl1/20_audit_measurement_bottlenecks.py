#!/usr/bin/env python3
"""Read-only pilot diagnosis; raw declarations are never usable reward labels.

Preserves duplicate JSON fields for inspection. Writes a separate audit, never
repairs/overwrites original scores or independently validates their semantics.
"""
import collections
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
PILOT = PROJECT / "outputs/pm_rl1/measurement_pilot_20260928_v1"
DEST = PROJECT / "outputs/pm_rl1/measurement_bottleneck_audit_20260929_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sources = {}

    def read(path):
        sources[str(path.relative_to(PROJECT))] = sha(path)
        return json.loads(path.read_text())

    pointer = read(PILOT / "judge_pointer.json")
    run = Path(pointer["run_dir"])
    assert sha(run / "summary.json") == pointer["summary_sha256"]
    summary = read(run / "summary.json")
    exam = read(PILOT / "exam_private.json")
    by_job = {j["job_id"]: j for j in exam["jobs"]}
    assert len(by_job) == len(summary["rows"]) == 55
    assert {r["job_id"] for r in summary["rows"]} == set(by_job)
    damage = []
    failure_counts = collections.Counter()
    for row in summary["rows"]:
        if row["measurement_status"] != "measured_candidate":
            failure_counts[row.get("error") or row["measurement_status"]] += 1
        if row["repeat"] != 0 or row["condition"] != "damage":
            continue
        raw = read(run / (row["request_id"] + ".raw.json"))
        final = raw["text"].strip()
        if "</think>" in final:
            assert final.count("</think>") == 1
            final = final.split("</think>", 1)[1].strip()
        if final.startswith("```json") and final.endswith("```"):
            final = final[7:-3].strip()
        # All object levels remain lists of pairs: duplicate keys never vanish.
        pairs = json.loads(final, object_pairs_hook=lambda values: values)
        counts = collections.Counter(k for k, _ in pairs)
        declared_m = [v for k, v in pairs if k == "m"]
        declared_q = [v for k, v in pairs if k == "q"]
        reasons = [v for k, v in pairs if k == "q_rationale"]
        damage.append(dict(
            pilot_index=row["pilot_index"], job_id=row["job_id"],
            strict_status=row["measurement_status"], strict_error=row.get("error"),
            declared_m_values=declared_m, declared_q_values=declared_q,
            duplicate_top_level_keys=[k for k, n in counts.items() if n > 1],
            model_reason=[v for obj in reasons for k, v in obj if k == "reason"],
            all_declared_m_positive=bool(declared_m) and all(
                type(v) in (int, float) and v > 0 for v in declared_m),
            semantic_correctness="NOT_ESTABLISHED", reward_eligible=False))
    damage.sort(key=lambda row: row["pilot_index"])
    typo = read(PILOT / "typographic_parser_v2/analysis.json")
    natural = [r for r in typo["rows"] if r["repeat"] == 0
               and r["condition"] in ("OFF", "ON")]
    valid_natural = [r for r in natural if r["measurement_status"] == "measured_candidate"]
    controls = read(PILOT / "coordinator_only/controls_and_missing.json")
    damages = [c for c in controls["controls"] if c["condition"] == "damage"]
    keys = read(PILOT / "coordinator_only/answer_key.json")
    review = read(PILOT / "independent_review_UNSCORED.json")
    pair_keys = {k["independent_item"]: k for k in keys if "independent_item" in k}
    pair_types = collections.Counter(pair_keys[i["item_id"]]["planned_pair_type"]
                                     for i in review["items"])
    material = read(PILOT / "review_material_size.json")
    smoke_pointer = read(PILOT / "indexed_transport_smoke_pointer.json")
    smoke_run = Path(smoke_pointer["run_dir"])
    assert sha(smoke_run / "summary.json") == smoke_pointer["summary_sha256"]
    smoke = read(smoke_run / "summary.json")
    primary = {r["job_id"] for r in smoke["rows"] if r["repeat"] == 0}
    smoke_repeat_pairs = sum(any(
        j["item_id"] == by_job[r["job_id"]]["item_id"] and j["repeat"] == 0
        and j["job_id"] in primary for j in exam["jobs"])
        for r in smoke["rows"] if r["repeat"] != 0)
    result = dict(
        status="OFFLINE_DIAGNOSIS_NO_NEW_SCORES_OR_HUMAN_REFERENCE",
        strict_failure_counts=dict(failure_counts),
        damage=dict(primary_cases=len(damage),
                    strict_valid=sum(r["strict_status"] == "measured_candidate" for r in damage),
                    cases_with_only_positive_declared_m=sum(r["all_declared_m_positive"] for r in damage),
                    rows=damage,
                    interpretation="Raw declarations identify a transport bottleneck; they are not detection accuracy or recovered training labels."),
        natural=dict(planned=len(natural), typographically_valid=len(valid_natural),
                     valid_q_counts=dict(collections.Counter(str(r["q"]) for r in valid_natural)),
                     interpretation="Selective valid subset; cannot distinguish true ties, task simplicity and score compression."),
        coverage=dict(damage_controls=len(damages),
                      current_context_damage=sum(c["source_id"].startswith("C:") for c in damages),
                      historical_only_damage=sum(c["source_id"].startswith("H") for c in damages),
                      style_scope="contraction expansion and paragraph breaks only",
                      independent_review_pair_types=dict(pair_types),
                      review_source_words=material["total_source_words"],
                      review_turns=material["total_turns"],
                      review_past_sessions=material["total_past_sessions"]),
        indexed_smoke=dict(calls=len(smoke["rows"]),
                           valid=sum(r["measurement_status"] == "measured_candidate" for r in smoke["rows"]),
                           complete_within_protocol_repeat_pairs=smoke_repeat_pairs,
                           qualifies_judge=False),
        next_run=dict(existing_exam_jobs=len(exam["jobs"]), new_generator_calls=0,
                      expected_api_calls=0,
                      scope="same exam and seeds, current indexed citation protocol; not executed by this audit",
                      reuse_smoke_only_if_full_request_and_runtime_identity_match=True),
        model_calls=0, paid_api_usd=0, human_submissions_created=0,
        reward_labels_created=0, training_updates=0, sources_sha256=sources,
        script_sha256=sha(Path(__file__)))
    assert len(damage) == 9
    assert result["damage"]["cases_with_only_positive_declared_m"] == 9
    assert all(sha(PROJECT / p) == h for p, h in sources.items())
    DEST.mkdir(parents=True, exist_ok=True)
    output = DEST / "audit.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(output=str(output), strict_damage_valid=result["damage"]["strict_valid"],
                         positive_raw_declarations=9, natural_q_counts=result["natural"]["valid_q_counts"],
                         pair_types=dict(pair_types), source_files_unchanged=len(sources),
                         model_calls=0), ensure_ascii=False))


if __name__ == "__main__":
    main()

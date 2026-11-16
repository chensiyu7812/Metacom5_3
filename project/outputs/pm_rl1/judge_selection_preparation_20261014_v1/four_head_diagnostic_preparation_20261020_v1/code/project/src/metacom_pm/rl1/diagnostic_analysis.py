"""Descriptive diagnostic reporting; never makes labels or qualification claims."""
from collections import Counter

from .schema import digest


def decision_sensitivity(q_on, m_on, q_off, m_off, penalty):
    """Algebraic stress cases, NOT new grades, confidence intervals or rewards."""
    def direction(x):
        return "positive" if x > 1e-12 else "negative" if x < -1e-12 else "zero"
    original = q_on / 4 - m_on - q_off / 4 + m_off - penalty
    variants = []
    for side in ("ON", "OFF"):
        q = q_on if side == "ON" else q_off
        for step in (-1, 1):
            if 0 <= q + step <= 4:
                value = original + step / 4 * (1 if side == "ON" else -1)
                variants.append(dict(kind="one_adjacent_q_step", side=side, step=step,
                                     return_value=value, direction=direction(value)))
        m = m_on if side == "ON" else m_off
        for alternate in (0, .25, 1):
            if alternate != m:
                value = original + (alternate - m) * (-1 if side == "ON" else 1)
                variants.append(dict(kind="unvalidated_m_stress", side=side, alternate=alternate,
                                     return_value=value, direction=direction(value)))
    return dict(original_direction=direction(original), cases=variants,
                grade_plausibility_validated=False, used_for_training=False)


def summarize_results(protocol, phase_results, feedback):
    """Use unique bound feedback records, and separately enumerate all rollouts.

    ``feedback`` contains raw record + coordinator review + disposition. A
    reused OFF is one measurement, even if it affects many policy comparisons.
    No accuracy or human agreement is inferred from coordinator review.
    """
    unique = {}
    for row in feedback:
        key = digest(row["record"])
        if key in unique and unique[key] != row:
            raise ValueError("conflicting reviews of one measurement")
        unique[key] = row
    category_counts, issue_types = Counter(), Counter()
    for row in unique.values():
        record, review = row["record"], row.get("review")
        if record["measurement_status"] == "technical_failure":
            category = "technical_failure"
        elif record["measurement_status"] == "semantic_uncertainty":
            category = "model_unknown"
        elif not review:
            category = "not_reviewed"
        elif review["confirmed_errors"]:
            category = "confirmed_checking_error"
        elif review["ambiguities"]:
            category = "reviewer_ambiguity"
        else:
            category = "reviewed_no_confirmed_issue"
        category_counts[category] += 1
        if review:
            for issue in review["ambiguities"]:
                issue_types[issue["type"]] += 1
    results = {r["trajectory_id"]:r for rows in phase_results.values() for r in rows}
    if len(results) != sum(len(x) for x in phase_results.values()):
        raise ValueError("a trajectory cannot be an independent repeat twice")
    trajectories = []
    for tid, slot in protocol["trajectory_manifest"].items():
        r = results.get(tid)
        row = dict(trajectory_id=tid, split=slot["split"], condition=slot["condition"],
                   prefix_identity=slot["prefix_identity"], started=r is not None,
                   state=r["phase"] if r else "unstarted", measured_return=None)
        if r:
            snapshot = r["private_audit_snapshot"]
            row.update(actions=snapshot["actions"], measured_return=r["return_value"],
                feedback_record_ids=list(r.get("feedback_diagnostics", {})))
            f = snapshot.get("feedback")
            if f:
                row.update(q_ON=f["on"]["q"], m_ON=f["on"]["misuse"],
                           q_OFF=f["off"]["q"], m_OFF=f["off"]["misuse"],
                           delta_U=f["stop_reward"])
                row["acquisition_cost_penalty"] = round(f["stop_reward"]-r["return_value"], 12)
                row["algebraic_sensitivity"] = decision_sensitivity(row["q_ON"], row["m_ON"],
                    row["q_OFF"], row["m_OFF"], row["acquisition_cost_penalty"])
        trajectories.append(row)
    comparisons = []
    dev = {x["prefix_identity"] for x in trajectories if x["split"] == "dev"}
    for pid in sorted(dev):
        group = {x["condition"]:x for x in trajectories if x["prefix_identity"] == pid}
        before, after = group.get("policy_initial"), group.get("policy_post32")
        complete = bool(before and after and before["state"] == after["state"] == "terminal")
        comparisons.append(dict(prefix_identity=pid, paired_complete=complete,
            proxy_return_change=after["measured_return"]-before["measured_return"] if complete else None,
            # Logical dependence is visible; this is NOT a fresh repeated J draw.
            shared_feedback_ids=sorted(set(before.get("feedback_record_ids", [])) &
                                       set(after.get("feedback_record_ids", []))) if before and after else [],
            independent_reward_validation=False))
    return dict(scope="DEVELOPMENT_DESCRIPTION_ONLY", planned_trajectories=len(trajectories),
        planned_training_trajectories=sum(x["split"] == "train" for x in trajectories),
        started_trajectories=sum(x["started"] for x in trajectories),
        terminal_trajectories=sum(x["state"] == "terminal" for x in trajectories),
        unique_feedback_records=len(unique), feedback_categories=dict(category_counts),
        ambiguity_issue_counts=dict(issue_types), trajectories=trajectories, dev_pairs=comparisons,
        human_comparable_pairs=None, independent_human_raters=0,
        reward_qualified=False, full_research_complete=False,
        warnings=["Cached scores remove resampling cost, not systematic bias or reward uncertainty.",
                  "Proxy-return improvement is not verified quality improvement.",
                  "Unstarted/missing cases remain explicit; do not treat them as failures or ties."])

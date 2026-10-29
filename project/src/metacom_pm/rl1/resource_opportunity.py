"""Offline opportunity diagnostics, not semantic labels or a new environment."""
from collections import defaultdict
from dataclasses import replace

from .schema import HEADS, PLANS, digest
from .temporal_evidence_ledger import words

VERSION = "pm-rl1-resource-opportunity-v1"


def capacity(spec, renderer):
    """Recompute all 70 costs and path reachability, including nonmonotonic cost."""
    reachable = set()
    rows = []
    for plan in PLANS:
        available = all(n <= len(items) for n, items in zip(plan, spec.inventory))
        cost = renderer.cost(spec, plan) if available else None
        fits = available and renderer.fits(spec, plan)
        predecessors = [tuple(n - (i == j) for i,n in enumerate(plan))
                        for j in range(4) if plan[j]]
        can_reach = fits and (not any(plan) or any(p in reachable for p in predecessors))
        if can_reach:
            reachable.add(plan)
        rows.append(dict(counts=list(plan), inventory_available=available, resource_tokens=cost,
                         fits=bool(fits), reachable=bool(can_reach)))
    return rows


def candidate_capacity(spec, renderer, plan_rows, head_index, rank):
    plans = [r for r in plan_rows if r["reachable"] and r["counts"][head_index] >= rank]
    required = tuple(rank if i == head_index else 0 for i in range(4))
    prefix_plan = next(r for r in plan_rows if tuple(r["counts"]) == required)
    # Hypothetical isolated cost is a diagnosis, NOT an accessible action.
    item = spec.inventory[head_index][rank-1]
    isolated = replace(spec, inventory=tuple((item,) if i == head_index else () for i in range(4)))
    one = tuple(int(i == head_index) for i in range(4))
    isolated_cost = renderer.cost(isolated, one)
    return dict(rank=rank, bge_similarity=item.similarity,
                ranking_method="frozen_bge_cosine_then_candidate_id",
                prefix_resource_tokens=prefix_plan["resource_tokens"],
                single_head_prefix_reachable=prefix_plan["reachable"],
                reachable_in_any_plan=bool(plans), reachable_plan_count=len(plans),
                minimum_reachable_resource_tokens=min((p["resource_tokens"] for p in plans), default=None),
                hypothetical_isolated_tokens=isolated_cost,
                hypothetical_isolated_is_legal_action=False,
                individually_over_budget=isolated_cost > spec.resource_budget,
                preceding_or_combined_budget_block=not plans and isolated_cost <= spec.resource_budget)


def lexical_overlap(text, prefix):
    a, b = words(text), words(prefix.query)
    return dict(unique_word_jaccard=len(a & b) / len(a | b) if a | b else 0,
                exact_text_in_prefix=bool(text.strip()) and text in prefix.query,
                interpretation="literal_overlap_only_not_semantic_redundancy")


def measured_contrasts(rows):
    """Only one added candidate, same prefix/G/renderer/evidence. No effect labels."""
    groups = defaultdict(dict)
    for row in rows:
        key = (row["prefix_identity"], row["executor_identity"], row["renderer_identity"], row["evidence_identity"])
        plan = tuple(row["counts"])
        if plan in groups[key]:
            raise ValueError("duplicate terminal in response pool")
        groups[key][plan] = row
    result = []
    for group in groups.values():
        for plan, upper in group.items():
            for h in range(4):
                if not plan[h]:
                    continue
                lower = group.get(tuple(n - (j == h) for j,n in enumerate(plan)))
                if lower is None:
                    continue
                result.append(dict(prefix_identity=upper["prefix_identity"], head=HEADS[h], rank=plan[h],
                    lower_request_id=lower["request_id"], upper_request_id=upper["request_id"],
                    lower_counts=lower["counts"], upper_counts=upper["counts"],
                    same_reply=upper["response_identity"] == lower["response_identity"],
                    resource_token_delta=upper["resource_tokens"]-lower["resource_tokens"],
                    quality_effect=None, semantic_uptake="unverified",
                    causal_scope="fixed_observed_generation_contrast_not_population_effect"))
    return result


def dominated_same_input(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["prefix_identity"], row["executor_identity"], row["renderer_identity"],
                row["evidence_identity"], row["response_identity"])].append(row)
    result = []
    for group in groups.values():
        cheapest = min(group, key=lambda r:(r["resource_tokens"], r["request_id"]))
        for row in group:
            if row["resource_tokens"] > cheapest["resource_tokens"]:
                result.append(dict(request_id=row["request_id"], alternative_request_id=cheapest["request_id"],
                    prefix_identity=row["prefix_identity"], split=row["split"], counts=row["counts"],
                    excess_tokens=row["resource_tokens"]-cheapest["resource_tokens"],
                    feedback_reuse_condition="same_complete_frozen_measurement_input_and_identity",
                    assigned_q=None, assigned_m=None))
    return result

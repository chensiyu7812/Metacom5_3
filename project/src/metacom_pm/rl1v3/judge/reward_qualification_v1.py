"""V3.2 reward qualification (``pmrl1v3-v32-reward-qualification-v1``).  CPU proposal; adopts nothing.

Nothing here changes checklist-template-v3, itemjudge-v3, aggregation-v3, ER-v3, NeedCard writer v2,
the pilot v2 plan (b1d3225b...) or any JudgeIdentity.  It provides:

1. ``ROLE_SEMANTICS``  - what required / relevant_optional / must_not_contradict mean for scoring,
   and the executable rule that an optional item never creates a positive requirement (checked
   against the frozen checklist v3 in tests);
2. ``classify_call`` / ``terminal_status`` - the J1 outcome registry: truncated, parse_failed,
   bad_evidence_ref, missing, uncertain, pre_call_blocked are kept apart; any incomplete terminal
   stays pending with an interval, never 0;
3. ``decode_budget`` - the j1-decode-v1 *candidate 2* per-terminal output budget (status PROPOSED;
   a JudgeIdentity built from it must not be used before the researcher approves it);
4. ``ISOLATION_RULES`` / ``check_isolation`` - training reward vs independent final evaluation;
5. ``H1_PACK`` - the small human calibration pack design.
"""
from __future__ import annotations

import math

from ..io import object_sha256

PROTOCOL = "pmrl1v3-v32-reward-qualification-v1"

ROLE_SEMANTICS = dict(
    required=dict(meaning="without this past fact a reply to the CURRENT explicit need would be wrong, misleading "
                          "or unresponsive (e.g. answers a question about the past, or would recommend something "
                          "the fact rules out)",
                  checklist="H+ item (take into account; explicit mention NOT required - consistent use passes)",
                  audit="required_is_indispensable: reviewer writes the counterfactual failure; none -> stratum_error"),
    relevant_optional=dict(meaning="related and true, but a good reply may leave it unmentioned",
                           checklist="no item at all: not mentioning it is never penalised; mentioning it "
                                     "wrongly is caught by the fixed I items",
                           audit="optional_not_mislabeled: an optional item promoted to required is stratum_error"),
    must_not_contradict=dict(meaning="known refusals, failures, corrections, time or person constraints",
                             checklist="H- item; contradiction = history_conflict owned by that item (L2)",
                             audit="state_not_confused + evidence_supports_claim"),
    rule="A legal source existing does not make it required; the NeedCard stratum and roles are evaluation-only.",
)

CALL_STATUSES = ("ok", "truncated", "parse_failed", "pre_call_blocked", "call_error")
ITEM_STATUSES = ("pass", "fail", "uncertain", "bad_evidence_ref", "missing")


def classify_call(*, finish_reason: str | None, parsed: bool, blocked: bool = False, error: str | None = None) -> str:
    """One J1 call -> exactly one call status.  ``finish_reason == 'length'`` is truncation, never a
    format error; a truncated or blocked call is not re-asked verbatim under greedy decoding."""
    if blocked:
        return "pre_call_blocked"
    if error:
        return "call_error"
    if finish_reason == "length":
        return "truncated"
    return "ok" if parsed else "parse_failed"


def item_status(verdict: str | None, flags=()) -> str:
    flags = tuple(flags)
    if verdict is None or "missing_after_retry" in flags:
        return "missing"
    if any(f.startswith("bad_evidence_ref") for f in flags):
        return "bad_evidence_ref" if verdict != "fail" else "fail"
    return verdict


def terminal_status(call_statuses, item_statuses: dict, *, weights: dict, safety_items=(), max_uncertain=1 / 3) -> dict:
    """Terminal-level registry row.  Bounds: unknown items count 0 in the lower and full weight in the
    upper bound; never filled with 0.  ``complete`` only if every call ok and nothing unknown."""
    calls = list(call_statuses)
    bad_calls = [c for c in calls if c != "ok"]
    unknown = {i: s for i, s in item_statuses.items() if s not in ("pass", "fail")}
    tot = sum(weights.values())
    passed = sum(weights[i] for i, s in item_statuses.items() if s == "pass")
    unk_w = sum(weights[i] for i in unknown)
    reasons = sorted({c for c in bad_calls} | {s for s in unknown.values()})
    status = "complete" if not bad_calls and not unknown else "pending"
    no_usable_output = not calls or calls[-1] != "ok"
    if status == "pending" and (unk_w / tot > max_uncertain or set(unknown) & set(safety_items) or no_usable_output):
        status = "refused_pending"          # ER is not computed; the terminal stays pending
    return dict(status=status, reasons=reasons, lower=passed / tot, upper=(passed + unk_w) / tot,
                unknown_weight_fraction=unk_w / tot, filled_with_zero=False,
                counts={s: sum(v == s for v in item_statuses.values()) for s in ITEM_STATUSES})


# ------------------------------------------------------------ decode budget candidate (PROPOSED)
DECODE_CANDIDATE = dict(
    decode_id_candidate="j1-decode-v1-candidate-2", status="PROPOSED_NOT_ADOPTED",
    unchanged=["itemjudge-v3 prompt", "ledger rules L1-L8", "greedy, no thinking", "stop tokens"],
    budget_rule="per terminal, after the checklist is frozen and the reply exists, before the call: "
                "B = ceil(1.25 * W / 256) * 256, W = native tokens of the worst admissible answer "
                "(every item quotes the longest reply sentence, every H-/I item fails with two quotes, "
                "indented JSON) + 1; capped at CAP",
    cap=8192,
    blocked_if=["B > CAP", "input_tokens + B > OPERATIONAL_CONTEXT"],
    operational_context=32768,
    retries=dict(truncated=0, parse_failed_after_stop=1, missing_items=1,
                 note="no verbatim greedy re-ask after truncation; v3 runner's second full call is replaced by "
                      "'record truncated, keep pending'"),
    record=["finish_reason", "output_tokens", "budget", "input_tokens", "wall_s"],
    approval="researcher approval + new JudgeIdentity frozen before the first J1 call; until then itemjudge-v3 "
             "with max_new_tokens=800 remains the only frozen identity and its capacity risk stays open",
)


def decode_budget(worst_tokens: int, *, input_tokens: int, cap: int = DECODE_CANDIDATE["cap"],
                  context: int = DECODE_CANDIDATE["operational_context"]) -> dict:
    b = int(math.ceil(1.25 * worst_tokens / 256) * 256)
    blocked = []
    if b > cap:
        blocked.append("budget_over_cap")
    if input_tokens + min(b, cap) > context:
        blocked.append("context_over_operational_limit")
    return dict(budget=min(b, cap), raw_budget=b, blocked=bool(blocked), reasons=blocked)


# ------------------------------------------------------------ training vs final evaluation
ISOLATION_RULES = (
    "R1 the final evaluator family differs from every training-reward judge (model family and prompt)",
    "R2 final rubric / pairwise protocol / human labels never enter training, checkpoint or hyper-parameter selection",
    "R3 final evaluation prefixes are owner/family held out from every training and tuning prefix (fold rule)",
    "R4 seeds, checkpoints and hyper-parameters are chosen on the training-reward dev split only; final eval runs once",
    "R5 a training reward is labelled engineering_only unless its own qualification report passed",
    "R6 report proxy-vs-independent divergence; proxy up with independent flat/down = reward-hacking flag",
    "R7 pending / refused terminals are never 0 in training or evaluation; trainable sets are identical across arms",
    "R8 every compared arm uses the same reward identity, the same feedback budget and the same prefixes",
)


def check_isolation(cfg: dict) -> list[str]:
    """``cfg``: train_reward {judge_family, judge_prompt_sha, qualified}, final_eval {judge_family,
    judge_prompt_sha, human}, train_owners, final_owners, selection_split, arms -> {reward_id, budget, prefixes}."""
    p = []
    tr, fe = cfg["train_reward"], cfg["final_eval"]
    if tr["judge_family"] == fe.get("judge_family") or tr["judge_prompt_sha"] == fe.get("judge_prompt_sha"):
        p.append("R1")
    if cfg.get("final_labels_used_in_training") or cfg.get("selection_split") == "final":
        p.append("R2/R4")
    if set(cfg["train_owners"]) & set(cfg["final_owners"]):
        p.append("R3")
    if not tr.get("qualified") and cfg.get("claim_tier") != "engineering_only":
        p.append("R5")
    if cfg.get("pending_as_zero"):
        p.append("R7")
    arms = cfg.get("arms", {})
    if len({(a["reward_id"], a["budget"], tuple(sorted(a["prefixes"]))) for a in arms.values()}) > 1:
        p.append("R8")
    return p


# ------------------------------------------------------------ H1 human calibration pack
H1_PACK = dict(
    purpose="calibrate J1 (and later J2) item verdicts and the reward direction against blind human judgement; "
            "not a training set",
    strata=["source correct / wrong", "time: current vs outdated", "subject: user vs third party vs external case",
            "negative: refused / failed suggestion repeated", "history truly not needed", "equal-quality pair",
            "support quality difference without any history", "safety"],
    size="2 items per stratum per prefix family, <= 48 items in total, drawn by a pre-registered seed from "
         "frozen terminals once they exist; until then the pack is a design only",
    blinding="reviewers see no J1/J2 output, no condition and no reward; left/right randomised",
    kept="every human-J1 disagreement is kept with both labels; no relabelling to agree",
    readiness="requires real terminals (G0) and NeedCards (writer) - both unauthorised now -> 0 items exist",
)


def manifest() -> dict:
    spec = dict(protocol=PROTOCOL, roles=ROLE_SEMANTICS, call_statuses=CALL_STATUSES, item_statuses=ITEM_STATUSES,
                decode_candidate=DECODE_CANDIDATE, isolation=ISOLATION_RULES, h1=H1_PACK)
    return dict(spec, sha256=object_sha256(spec))

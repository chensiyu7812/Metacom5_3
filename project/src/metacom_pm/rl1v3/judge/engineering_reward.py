"""``pmrl1v3-engineering-reward-v1`` (ER-v1): the B6e/B8e training signal.

Why it exists: C0 makes GSC ``(None, None)`` until both judges (or a human)
decide every item, so engineering PPO needs a separately named, versioned
signal (V3.1 §6.8.2 ``R_proxy``).  ER-v1 is that signal.  It is **not** GSC and
can never be research_qualified.

Depends on (all must hold, otherwise ``RewardUnavailable`` -> the terminal is
pending in the environment, never reward 0):
  1. a frozen checklist bound to this exact NeedCard, with ``evidence_validation
     == "verified"``;
  2. the ExecutionTrace reproduces the TerminalKey; the checklist belongs to the
     key's prefix;
  3. a non-empty reply that ended with ``natural_stop`` (no truncation/timeouts);
  4. a J1 verdict for EVERY checklist item from the one J1 identity registered
     for this experiment (all terminals of a prefix use the same judge);
  5. J1-uncertain weight <= ``max_uncertain_weight`` (too uncertain to train on).

Value (J1 only; J2 and human results are ignored by v1 by definition):
  lo = sum w[J1=pass] / W,  hi = sum w[J1!=fail] / W   (fixed denominator W)
  q  = lo + uncertain_value * (hi - lo)                 (midpoint convention)
  value = unsafe_value                if any hard_safety item has J1 = fail
          q - get_cost * n_gets       otherwise
A J1 safety failure is not traded against cost (it floors the value).
``get_cost`` is an engineering constant, not the B4 lambda; latency is not
priced because B4 has no validated model yet (latency_pred stays None).

Always reported next to the scalar: lo/hi, uncertain weight, J1 factual and
safety failures, n_gets, input tokens, J2 status and the reason codes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..io import object_sha256

PROTOCOL = "pmrl1v3-engineering-reward-v1"
TIER = "engineering_only"


@dataclass(frozen=True)
class ERConfig:
    get_cost: float = 0.01
    uncertain_value: float = 0.5
    max_uncertain_weight: float = 1 / 3
    unsafe_value: float = -1.0

    @property
    def sha256(self) -> str:
        return object_sha256(dict(protocol=PROTOCOL, **asdict(self)))


class RewardUnavailable(RuntimeError):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = tuple(reasons)


def compute(*, key, trace, checklist, needcard, evidence_validation: str, response: str,
            finish_reason: str, verdicts, j1_identity: str, expected_j1_identity: str,
            input_tokens: int | None = None, cfg: ERConfig = ERConfig()) -> dict:
    reasons = []
    try:
        checklist.verify_needcard(needcard)
    except ValueError:
        reasons.append("checklist_not_bound_to_needcard")
    if evidence_validation != "verified":
        reasons.append("evidence_not_verified")
    try:
        trace.verify_key(key)
    except ValueError:
        reasons.append("trace_does_not_reproduce_key")
    if checklist.prefix_id != key.prefix_id:
        reasons.append("checklist_for_another_prefix")
    if finish_reason != "natural_stop" or not response.strip():
        reasons.append("reply_incomplete")
    if j1_identity != expected_j1_identity:
        reasons.append("j1_identity_mismatch")
    by = {v.item_id: v for v in verdicts}
    if len(by) != len(verdicts) or set(by) != {i.item_id for i in checklist.items}:
        reasons.append("verdict_coverage_differs_from_checklist")
        by = {}
    elif any(v.J1 is None for v in verdicts):
        reasons.append("j1_incomplete")
    W = sum(i.weight for i in checklist.items)
    unc = sum(i.weight for i in checklist.items if by and by[i.item_id].J1 == "uncertain") / W
    if by and unc > cfg.max_uncertain_weight + 1e-12:
        reasons.append("too_uncertain")
    if reasons:
        raise RewardUnavailable(reasons)
    lo = sum(i.weight for i in checklist.items if by[i.item_id].J1 == "pass") / W
    hi = sum(i.weight for i in checklist.items if by[i.item_id].J1 != "fail") / W
    q = lo + cfg.uncertain_value * (hi - lo)
    safety_fail = [i.item_id for i in checklist.items
                   if i.constraint_type == "hard_safety" and by[i.item_id].J1 == "fail"]
    factual_fail = [i.item_id for i in checklist.items
                    if i.constraint_type == "hard_factual" and by[i.item_id].J1 == "fail"]
    n_gets = len(key.acquired)
    value = cfg.unsafe_value if safety_fail else q - cfg.get_cost * n_gets
    j2 = [v.J2 for v in verdicts]
    return dict(
        protocol=PROTOCOL, config_sha256=cfg.sha256, config=asdict(cfg), qualification_tier=TIER,
        is_gsc=False, key_sha256=key.sha256, checklist_sha256=checklist.sha256,
        needcard_sha256=needcard.sha256, j1_identity=j1_identity, value=value, q=q,
        j1_lower=lo, j1_upper=hi, j1_uncertain_weight=unc, n_gets=n_gets, input_tokens=input_tokens,
        j1_safety_fail_items=safety_fail, j1_factual_fail_items=factual_fail,
        j1_safety_uncertain=any(i.constraint_type == "hard_safety" and by[i.item_id].J1 == "uncertain"
                                for i in checklist.items),
        j2_status="not_run" if all(x is None for x in j2) else "complete" if all(x is not None for x in j2) else "partial",
        unverified_note="J1-only engineering signal; not GSC, not research_qualified")


def to_outcome(record: dict):
    """Environment ``TerminalOutcome`` for a TerminalTable row (reward = ER-v1 value)."""
    from ..env.finite_head import TerminalOutcome
    if record.get("protocol") != PROTOCOL or record.get("qualification_tier") != TIER:
        raise ValueError("only ER-v1 engineering records can enter an engineering terminal table")
    return TerminalOutcome(reward=float(record["value"]), key_sha256=record["key_sha256"],
                           detail={k: record[k] for k in ("q", "j1_lower", "j1_upper", "j1_uncertain_weight",
                                                          "j1_safety_fail_items", "j1_factual_fail_items",
                                                          "n_gets", "protocol", "config_sha256")})

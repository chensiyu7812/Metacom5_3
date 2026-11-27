"""``pmrl1v3-engineering-reward-v3`` (ER-v3).  ER-v1/ER-v2 and their tests are unchanged.

ER-v3 = ER-v2's computation and every researcher condition, unchanged:
J1 lo/hi midpoint (uncertain value 0.5), 0.01 per GET reported apart from the
measured token cost, -1 on a J1 hard_safety fail, refusal above 1/3 uncertain
weight, refusal when any hard_safety item is J1-uncertain, the same 12-point
sensitivity grid, every attempt recorded with subset and stratum.

Only the input binding changes (ER-v2 refuses any checklist that is not
template v2, by design):
* the checklist must be template v3 and the J1 run judge protocol v3
  (atomic-error ledger, rules L1-L6), so H-/I attribution never merges or
  double counts on text overlap alone;
* the J1 ledger summary (owners, re-attributions, overlap ambiguities, invalid
  entries) is stored with the record.
ER is never written into GSC and never research_qualified.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..checklist.writer_v3 import CHECKLIST_PROTOCOL
from ..io import object_sha256
from .engineering_reward import RewardUnavailable
from .engineering_reward_v2 import GET_PENALTY_LABEL, PRIMARY, SENSITIVITY_GRID, _value
from .protocol_v3 import JUDGE_PROTOCOL

PROTOCOL = "pmrl1v3-engineering-reward-v3"
TIER = "engineering_only"
REFUSAL_REASONS = ("checklist_not_bound_to_needcard", "checklist_protocol_not_v3", "j1_protocol_not_v3",
                   "evidence_not_verified", "trace_does_not_reproduce_key", "checklist_for_another_prefix",
                   "reply_incomplete", "j1_identity_mismatch", "verdict_coverage_differs_from_checklist",
                   "j1_incomplete", "hard_safety_uncertain", "too_uncertain")


@dataclass(frozen=True)
class ERConfigV3:
    get_penalty: float = PRIMARY["get_penalty"]
    uncertain_value: float = PRIMARY["uncertain_value"]
    max_uncertain_weight: float = 1 / 3
    unsafe_value: float = -1.0

    @property
    def sha256(self) -> str:
        return object_sha256(dict(protocol=PROTOCOL, grid=SENSITIVITY_GRID, **asdict(self)))


def preregistration() -> dict:
    """Frozen analysis plan; its sha256 is written before any real terminal."""
    spec = dict(protocol=PROTOCOL, computation_inherited_from="pmrl1v3-engineering-reward-v2",
                primary=PRIMARY, grid=SENSITIVITY_GRID, config=asdict(ERConfigV3()),
                refusal_reasons=REFUSAL_REASONS, checklist_protocol=CHECKLIST_PROTOCOL, judge_protocol=JUDGE_PROTOCOL,
                report=["value under every grid point per arm", "arm ranking stability across the grid",
                        "refusal rate overall / by subset / by stratum / by reason",
                        "computed-vs-attempted stratum and subset mix",
                        "get_penalty and measured tokens reported separately",
                        "J1 ledger: re-attributions, overlap ambiguities, invalid entries per terminal"])
    return dict(spec, sha256=object_sha256(spec))


def compute(*, key, trace, checklist, needcard, evidence_validation: str, response: str, finish_reason: str,
            verdicts, j1_identity: str, expected_j1_identity: str, input_tokens: int | None = None,
            prefix_tokens: int | None = None, j1_ledger: dict | None = None, cfg: ERConfigV3 = ERConfigV3()) -> dict:
    """``verdicts``: C0 ItemVerdicts built from the ledger-resolved J1 run (``protocol_v3.run``);
    ``j1_ledger``: ``protocol_v3.ledger_summary`` of that run (reported; never changes the denominator)."""
    reasons = []
    try:
        checklist.verify_needcard(needcard)
    except ValueError:
        reasons.append("checklist_not_bound_to_needcard")
    if not checklist.writer_identity.startswith(CHECKLIST_PROTOCOL + "|"):
        reasons.append("checklist_protocol_not_v3")
    if f"|{JUDGE_PROTOCOL}|" not in j1_identity:
        reasons.append("j1_protocol_not_v3")
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
        by = {}
    W = sum(i.weight for i in checklist.items)
    unc = sum(i.weight for i in checklist.items if by and by[i.item_id].J1 == "uncertain") / W
    if by and any(i.constraint_type == "hard_safety" and by[i.item_id].J1 == "uncertain" for i in checklist.items):
        reasons.append("hard_safety_uncertain")
    if by and unc > cfg.max_uncertain_weight + 1e-12:
        reasons.append("too_uncertain")
    if reasons:
        raise RewardUnavailable(reasons)
    lo = sum(i.weight for i in checklist.items if by[i.item_id].J1 == "pass") / W
    hi = sum(i.weight for i in checklist.items if by[i.item_id].J1 != "fail") / W
    safety_fail = [i.item_id for i in checklist.items if i.constraint_type == "hard_safety" and by[i.item_id].J1 == "fail"]
    factual_fail = [i.item_id for i in checklist.items if i.constraint_type == "hard_factual" and by[i.item_id].J1 == "fail"]
    n_gets = len(key.acquired)
    q = lo + cfg.uncertain_value * (hi - lo)
    reading_tokens = {r.head: r.tokens for r in trace.readings}
    sens = {f"u={u}|g={g}": _value(lo, hi, safety_fail, n_gets, u, g, cfg.unsafe_value)
            for u in SENSITIVITY_GRID["uncertain_value"] for g in SENSITIVITY_GRID["get_penalty"]}
    j2 = [v.J2 for v in verdicts]
    return dict(
        protocol=PROTOCOL, config_sha256=cfg.sha256, config=asdict(cfg), preregistration_sha256=preregistration()["sha256"],
        qualification_tier=TIER, is_gsc=False, key_sha256=key.sha256, checklist_sha256=checklist.sha256,
        needcard_sha256=needcard.sha256, j1_identity=j1_identity,
        value=_value(lo, hi, safety_fail, n_gets, cfg.uncertain_value, cfg.get_penalty, cfg.unsafe_value),
        quality=dict(q=q, j1_lower=lo, j1_upper=hi, j1_uncertain_weight=unc),
        get_penalty=dict(n_gets=n_gets, per_get=cfg.get_penalty, total=cfg.get_penalty * n_gets, label=GET_PENALTY_LABEL),
        cost_report=dict(input_tokens=input_tokens, prefix_tokens=prefix_tokens, reading_tokens_by_head=reading_tokens,
                         reading_tokens_total=sum(reading_tokens.values()), latency="not_priced_B4_pending"),
        sensitivity=sens, j1_safety_fail_items=safety_fail, j1_factual_fail_items=factual_fail,
        j1_ledger=dict(j1_ledger or {}),
        j2_status="not_run" if all(x is None for x in j2) else "complete" if all(x is not None for x in j2) else "partial",
        unverified_note="J1-only engineering signal; not GSC, not research_qualified")


def attempt(*, key, subset: str, stratum: str | None, **kw) -> dict:
    """Compute ER-v3 or record the refusal - every attempt is kept for the refusal report."""
    try:
        rec = compute(key=key, **kw)
        return dict(status="computed", key_sha256=key.sha256, subset=subset, stratum=stratum, record=rec)
    except RewardUnavailable as exc:
        return dict(status="refused", key_sha256=key.sha256, subset=subset, stratum=stratum, reasons=list(exc.reasons),
                    protocol=PROTOCOL, qualification_tier=TIER)


def to_outcome(record: dict):
    """Environment ``TerminalOutcome`` (reward = ER-v3 primary value); only ER-v3 records are accepted."""
    from ..env.finite_head import TerminalOutcome
    if record.get("protocol") != PROTOCOL or record.get("qualification_tier") != TIER or record.get("is_gsc") is not False:
        raise ValueError("only ER-v3 engineering records can enter an ER-v3 terminal table")
    return TerminalOutcome(reward=float(record["value"]), key_sha256=record["key_sha256"],
                           detail=dict(protocol=PROTOCOL, config_sha256=record["config_sha256"], **record["quality"],
                                       get_penalty=record["get_penalty"]["total"]))

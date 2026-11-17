"""``pmrl1v3-engineering-reward-v2`` (ER-v2).  ER-v1 (``engineering_reward.py``) and its tests are unchanged.

Researcher conditional approval (2026-11-18) for engineering_only preflight:
J1 lo/hi midpoint, 0.01 per GET, -1 on a J1 safety fail, refuse above 1/3
uncertain weight.  ER-v2 adds, before any real terminal exists:

1. any hard_safety item with J1 = uncertain -> refused (terminal stays pending),
   never trained on a midpoint;
2. the per-GET penalty is reported apart from the measured token overhead
   (``get_penalty`` vs ``cost_report``); 0.01/GET is an engineering constant,
   not a cost model, and is labelled so;
3. a pre-registered sensitivity grid (uncertain value lower/mid/upper x GET
   penalty 0/0.005/0.01/0.02), computed for every terminal from the same J1
   verdicts and frozen here, independent of any test result;
4. every attempt (computed or refused) is recorded with its subset and
   stratum so refusal rates can be reported by resource subset and need
   stratum (``evaluate.protocol_v2.refusal_report``);
5. the checklist must be template v2 (I = Resource Misuse / Integrity with the
   A1-A6 attribution) and verdicts are the post-attribution J1 items.
ER is never written into GSC and never research_qualified.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..checklist.writer_v2 import CHECKLIST_PROTOCOL
from ..io import object_sha256
from .engineering_reward import RewardUnavailable

PROTOCOL = "pmrl1v3-engineering-reward-v2"
TIER = "engineering_only"
SENSITIVITY_GRID = dict(uncertain_value=(0.0, 0.5, 1.0), get_penalty=(0.0, 0.005, 0.01, 0.02))
PRIMARY = dict(uncertain_value=0.5, get_penalty=0.01)
GET_PENALTY_LABEL = "engineering_constant_not_a_cost_model"


@dataclass(frozen=True)
class ERConfigV2:
    get_penalty: float = PRIMARY["get_penalty"]
    uncertain_value: float = PRIMARY["uncertain_value"]
    max_uncertain_weight: float = 1 / 3
    unsafe_value: float = -1.0

    @property
    def sha256(self) -> str:
        return object_sha256(dict(protocol=PROTOCOL, grid=SENSITIVITY_GRID, **asdict(self)))


def preregistration() -> dict:
    """Frozen analysis plan; its sha256 is written before any real terminal."""
    spec = dict(protocol=PROTOCOL, primary=PRIMARY, grid=SENSITIVITY_GRID, config=asdict(ERConfigV2()),
                refusal_reasons=REFUSAL_REASONS, checklist_protocol=CHECKLIST_PROTOCOL,
                report=["value under every grid point per arm", "arm ranking stability across the grid",
                        "refusal rate overall / by subset / by stratum / by reason",
                        "computed-vs-attempted stratum and subset mix",
                        "get_penalty and measured tokens reported separately"])
    return dict(spec, sha256=object_sha256(spec))


REFUSAL_REASONS = ("checklist_not_bound_to_needcard", "checklist_protocol_not_v2", "evidence_not_verified",
                   "trace_does_not_reproduce_key", "checklist_for_another_prefix", "reply_incomplete",
                   "j1_identity_mismatch", "verdict_coverage_differs_from_checklist", "j1_incomplete",
                   "hard_safety_uncertain", "too_uncertain")


def _value(lo, hi, safety_fail, n_gets, u, g, unsafe):
    return unsafe if safety_fail else lo + u * (hi - lo) - g * n_gets


def compute(*, key, trace, checklist, needcard, evidence_validation: str, response: str, finish_reason: str,
            verdicts, j1_identity: str, expected_j1_identity: str, input_tokens: int | None = None,
            prefix_tokens: int | None = None, j1_attributions=(), cfg: ERConfigV2 = ERConfigV2()) -> dict:
    """``verdicts``: C0 ItemVerdicts built from the post-attribution J1 run; ``j1_attributions``:
    that run's A3 re-attributions (reported, they never change the denominator)."""
    reasons = []
    try:
        checklist.verify_needcard(needcard)
    except ValueError:
        reasons.append("checklist_not_bound_to_needcard")
    if not checklist.writer_identity.startswith(CHECKLIST_PROTOCOL + "|"):
        reasons.append("checklist_protocol_not_v2")
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
        j1_attributions=[dict(a) for a in j1_attributions],
        j2_status="not_run" if all(x is None for x in j2) else "complete" if all(x is not None for x in j2) else "partial",
        unverified_note="J1-only engineering signal; not GSC, not research_qualified")


def attempt(*, key, subset: str, stratum: str | None, **kw) -> dict:
    """Compute ER-v2 or record the refusal - every attempt is kept for the refusal report."""
    try:
        rec = compute(key=key, **kw)
        return dict(status="computed", key_sha256=key.sha256, subset=subset, stratum=stratum, record=rec)
    except RewardUnavailable as exc:
        return dict(status="refused", key_sha256=key.sha256, subset=subset, stratum=stratum, reasons=list(exc.reasons),
                    protocol=PROTOCOL, qualification_tier=TIER)


def to_outcome(record: dict):
    """Environment ``TerminalOutcome`` (reward = ER-v2 primary value); only ER-v2 records are accepted."""
    from ..env.finite_head import TerminalOutcome
    if record.get("protocol") != PROTOCOL or record.get("qualification_tier") != TIER or record.get("is_gsc") is not False:
        raise ValueError("only ER-v2 engineering records can enter an ER-v2 terminal table")
    return TerminalOutcome(reward=float(record["value"]), key_sha256=record["key_sha256"],
                           detail=dict(protocol=PROTOCOL, config_sha256=record["config_sha256"], **record["quality"],
                                       get_penalty=record["get_penalty"]["total"]))

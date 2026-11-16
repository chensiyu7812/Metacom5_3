"""Per-slot payload adapter to paired.run; no transport, account or credential CLI."""
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE / "paired_diagnostic_20261019_v1"))
import paired as p
from paired import s

STUDY = "pmrl1-anchor-calibration-v1-20261020"


def load():
    protocol = s.read(HERE / "protocol.json")
    if s.digest({k: v for k, v in protocol.items() if k != "identity"}) != protocol["identity"]:
        raise ValueError("protocol identity mismatch")
    for name, sha in protocol["immutable_files"].items():
        if s.sha(name) != sha:
            raise ValueError("frozen preparation input changed")
    for name, sha in protocol["original_stop_hashes"].items():
        if s.sha(name) != sha:
            raise ValueError("old STOP changed")
    items = {}
    for target in s.read(HERE / "targets.json"):
        for arm, payload in target["payloads"].items():
            value = s.read(HERE / payload["file"])
            user = json.loads(value["messages"][1]["content"])
            items[f"{target['target_id']}__{arm}"] = dict(
                evidence=user["legal_evidence"], reply=user["reply"],
                file=payload["file"], sha256=payload["sha256"], arm=arm)
    return protocol, items


def approve(protocol, auth):
    # Future live launch still needs the existing locking/account/budget preflight.
    required = dict(status="APPROVED", study=STUDY, protocol_identity=protocol["identity"],
                    max_calls=24, cumulative_cap=225, stage_cap_usd="1.15",
                    trial_cap_usd="2", shared_cap_usd="20",
                    added_semantic_revision=1, exact_synthetic_examples_authorized=True,
                    old_stops_released=False, reward_eligible=False,
                    diagnostic_policy=protocol["diagnostic_policy"])
    if any(auth.get(k) != v for k, v in required.items()):
        raise ValueError("new bounded diagnostic approval required")
    if not auth.get("locked_live_preflight_receipt"):
        raise ValueError("existing live service/account/atomic budget preflight required")


def streaks(protocol, starts, results):
    overall = 0
    arms = {"baseline": 0, "calibrated": 0}
    for slot in protocol["schedule"]:
        sid, arm = slot["slot_id"], slot["arm"]
        if sid not in starts:
            continue
        row = results.get(sid)
        if row is None:
            return "started request unresolved; never retry", overall, arms
        if row.get("hard_stop"):
            return row["hard_stop"], overall, arms
        if not row["financial"]["settlement_confirmed"]:
            return "usage unresolved; preserve reservation", overall, arms
        if row["evaluation"].get("error") == "non-natural final":
            return "truncated final; no retry", overall, arms
        good = row["technical_valid"]
        overall = 0 if good else overall + 1
        arms[arm] = 0 if good else arms[arm] + 1
        if overall >= 2 or arms[arm] >= 2:
            return "two consecutive technical failures globally or within one arm", overall, arms
    return None, overall, arms


def summarize(protocol, root, baseline):
    starts, results = p.replay(root, protocol)
    slots = [dict(**slot, started=slot["slot_id"] in starts, result=results.get(slot["slot_id"]))
             for slot in protocol["schedule"]]
    return dict(started=len(starts), cumulative=baseline+len(starts), slots=slots,
                technical_complete=sum(r["technical_valid"] for r in results.values()),
                unknown=sum(r["evaluation"].get("model_unknown") is True for r in results.values()),
                unsettled=sum(s.nanodollars(r["financial"]["unsettled_reservation_usd"]) for r in results.values()),
                reward_eligible=False)


def runtime():
    # paired.run is serial. Bind result metadata to the actual arm at payload time.
    rt = dict(max_calls=24, cap=225, study=STUDY, version=STUDY, approve=approve,
              streaks=streaks, summarize=summarize, review=None)

    def payload(item, component, first=None):
        if component != "joint" or first is not None:
            raise ValueError("joint only")
        path = HERE / item["file"]
        if s.sha(path) != item["sha256"]:
            raise ValueError("frozen payload changed")
        data = s.read(path)
        rt["semantic_revisions_applied"] = 2 if item["arm"] == "baseline" else 3
        rt["joint_prompt_unchanged"] = item["arm"] == "baseline"
        return data["messages"], data["schema"]

    rt["payload"] = payload
    return rt


if __name__ == "__main__":
    raise SystemExit("Offline preparation only. No live launch, credentials or transport in this adapter.")

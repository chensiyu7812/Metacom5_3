#!/usr/bin/env python3
"""A/B adapter to paired.run. --check/--report are read-only and offline."""
import argparse
from contextlib import ExitStack
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/"src"))
BASE = PROJECT/"outputs/pm_rl1/judge_selection_preparation_20261014_v1"
PREP = BASE/"relation_reference_preparation_20261021_v2"
from metacom_pm.rl1 import relation_reference as r


def engine():
    sys.path.insert(0,str(BASE/"paired_diagnostic_20261019_v1"))
    import paired
    return paired


def load(prep=PREP):
    protocol = r.read(prep/"protocol.json")
    if r.digest({k:v for k,v in protocol.items() if k!="identity"}) != protocol["identity"]:
        raise ValueError("protocol identity mismatch")
    for path, expected in protocol["immutable_files"].items():
        if r.sha(path) != expected: raise ValueError("frozen input/code changed")
    for kind in ("historical_started_hashes", "old_stop_hashes"):
        for path, expected in protocol[kind].items():
            if r.sha(path) != expected:raise ValueError("old attempt or STOP changed")
    p=engine()
    items=r.read(prep/"inputs_private.json");refs=r.read(prep/"references.json")
    prompt=(prep/"BASELINE_PROMPT_EN.txt").read_text();payloads={};runtime_items={}
    for key,item in items.items():
        r.validate_reference(item,refs[key],p)
        for arm in ("A","B"):
            k=key+"__"+arm;payloads[k]=r.read(prep/"payloads"/(k+".json"))
            r.validate_payload(item,refs[key],arm,prompt,payloads[k],p)
            runtime_items[k]=dict(item,arm=arm)
    return protocol,items,refs,prompt,payloads,runtime_items


def historical_guard(protocol):
    # These are attempts, not output counts; management requests are separate.
    known={str(x) for name in ("live_runs","paired_diagnostic_runs","action_stage_runs",
        "reward_noise_runs","anchor_calibration_runs","four_head_diagnostic_runs")
        for x in (BASE/name).rglob("*.started.json") if "management" not in x.parts}
    if known != set(protocol["historical_started_hashes"]):
        raise ValueError("historical attempt set changed; reconcile, never reset")
    root=Path(protocol["run_dir"])
    if any(not x.is_relative_to(root) for x in (BASE/"relation_reference_runs").rglob("*.started.json") if "management" not in x.parts):
        raise ValueError("other reference version already started; no cross-version redispatch")
    return 66+len(known)


def check():
    protocol,*_=load();count=historical_guard(protocol)
    if count!=225:raise ValueError("baseline changed")
    return dict(status="OFFLINE_CHECK_PASSED_EXECUTION_NOT_AUTHORIZED",protocol_identity=protocol["identity"],
        planned=28,actual_historical=count,reference_semantics="3 bounded review groups pending",
        new_requests=0,credentials_read=False,account_queries=0,natural_updates=0)


def launch(approval_path,review_path):
    protocol,items,refs,prompt,payloads,runtime_items=load()
    approval=r.read(approval_path);review=r.read(review_path)
    r.require_approval(protocol,approval,review)  # BEFORE mkdir, credential imports or HTTP.
    p=engine();s=p.s
    from deepseek_access import read_key,credential_scope,management_once,visible_paid_writers
    from adapters import DeepSeekTransport
    from live import public_service_check
    root=Path(protocol["run_dir"]);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    ledger=Path(protocol["financial_baseline"]["ledger_path"])
    try:
        with ExitStack() as stack:
            locks=[BASE/"live_runs/.pool.lock",ledger.with_suffix(".lock")]+[
                BASE/name/".launch.lock" for name in ("paired_diagnostic_runs","action_stage_runs","reward_noise_runs",
                "anchor_calibration_runs","four_head_diagnostic_runs","relation_reference_runs")]
            for path in locks:
                path.parent.mkdir(exist_ok=True)
                lock=stack.enter_context(path.open("a"));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            historical_guard(protocol)
            starts,_=p.replay(root,protocol)
            if starts or (root/"STOP.json").exists():
                return dict(status="PRESERVED_NO_AUTOMATIC_RESTART",report=r.summarize(protocol,root,225,p))
            fin=protocol["financial_baseline"]
            if r.sha(ledger)!=fin["ledger_sha256"]:raise ValueError("shared ledger changed")
            original=ledger.read_bytes()
            if visible_paid_writers():raise ValueError("visible concurrent paid writer")
            mg=root/"management";mg.mkdir(exist_ok=True)
            if list(mg.iterdir()):raise ValueError("prior management attempt; no retry")
            # Unauthenticated official service/price check; actual startup only.
            public_service_check(mg,protocol["public_price_table_identity"])
            key=read_key()
            with credential_scope(key):
                models=management_once(mg,"models",key)
                if models["status"]!=200:raise ValueError("model-list query failed")
                model=next((x for x in models.get("body",{}).get("data",[]) if x.get("id")=="deepseek-flash"),{})
                if (not model or ("name" in model and model["name"] not in ("DeepSeek-V4.1-Flash","DeepSeek-V4.1-Flash-1017"))
                    or ("context_window" in model and model["context_window"]!=1048576)
                    or ("max_output_tokens" in model and model["max_output_tokens"]!=393216)):
                    raise ValueError("service identity/capability drift")
                balance=management_once(mg,"user/balance",key)
                if balance["status"]!=200 or not balance.get("body",{}).get("is_available"):
                    raise ValueError("balance unavailable")
                amounts={x["currency"]:Decimal(x["total_balance"]) for x in balance["body"]["balance_infos"]}
                available=amounts.get("USD",Decimal(0))+amounts.get("CNY",Decimal(0))*Decimal(".15")
                budget=p.DiagnosticBudget(ledger,trial=fin["financial_trial_identity"],study=r.VERSION,
                    stage_cap=s.nanodollars(protocol["limits"]["stage_usd"]),trial_cap=s.nanodollars(protocol["limits"]["trial_usd"]),
                    shared_cap=s.nanodollars(20),baseline=s.nanodollars("1.50724291"),opening=s.nanodollars(".03079930"),
                    account_opening=s.nanodollars(available),opening_trial=s.nanodollars(fin["trial_accounted_usd"]))
                total,trial,reserved,settled=budget._totals(budget.events())
                if set(reserved)-set(settled):raise ValueError("unresolved liabilities")
                if s.usd(trial)!=fin["trial_accounted_usd"]:raise ValueError("trial accounting changed")
                r.save_new(mg/"preflight.json",dict(protocol_identity=protocol["identity"],approval_identity=r.digest(approval),
                    reference_review_identity=r.digest(review),service=model,available_tariff_equivalent_usd=str(available),
                    tariff_basis="existing official USD/CNY tariff ratio, not market FX",known_unsettled=0,
                    visibility="known shared ledger and visible local writers; not guaranteed account-wide visibility"))
                def guard():
                    load();historical_guard(protocol)
                    if r.read(approval_path)!=approval or r.read(review_path)!=review:raise ValueError("authorization changed")
                    current=ledger.read_bytes()
                    if not current.startswith(original):raise ValueError("ledger prefix changed")
                    ids={x["slot_id"] for x in protocol["schedule"]}
                    if any(json.loads(line).get("reservation_id") not in ids for line in current[len(original):].decode().splitlines()):
                        raise ValueError("foreign paid writer")
                    if visible_paid_writers():raise ValueError("visible concurrent paid writer")
                rt=r.runtime(protocol,payloads,items,refs,prompt,p,lambda pp,aa:r.require_approval(pp,aa,review))
                result=p.run(protocol,runtime_items,root,DeepSeekTransport(protocol["config"]),budget,mode="live",auth=approval,
                    before_dispatch=guard,global_count=lambda:historical_guard(protocol),runtime=rt)
            del key
            r.save_new(root/"stage_result.json",result)
            total,trial,reserved,settled=budget._totals(budget.events())
            r.save_new(root/"financial_closeout.json",dict(trial_accounted_usd=s.usd(trial),
                stage_accounted_usd=s.usd(budget.stage_total(reserved,settled)),
                unsettled=[k for k in reserved if k not in settled],ledger_sha256=r.sha(ledger),
                original_prefix_preserved=ledger.read_bytes().startswith(original)))
            return result
    except Exception as exc:
        # Never log provider/credential exception details or authentication headers.
        receipt=dict(reason="launch/guard failure; sensitive exception details suppressed",error_type=type(exc).__name__,
            timestamp=time.time(),automatic_retry=False)
        r.save_new(root/("launch_failure_"+str(time.time_ns())+".json"),receipt)
        if not (root/"STOP.json").exists():r.save_new(root/"STOP.json",receipt)
        raise ValueError("Stopped; immutable local receipt retained, no retry") from None


def main():
    os.umask(0o077)
    a=argparse.ArgumentParser();g=a.add_mutually_exclusive_group(required=True)
    g.add_argument("--check",action="store_true");g.add_argument("--report",action="store_true");g.add_argument("--live",action="store_true")
    a.add_argument("--approval",type=Path);a.add_argument("--reference-review",type=Path)
    args=a.parse_args()
    if args.check:result=check()
    elif args.report:
        protocol,*_=load();result=r.summarize(protocol,protocol["run_dir"],historical_guard(protocol),engine())
    else:
        if not args.approval or not args.reference_review:raise SystemExit("Explicit approval and actual reference review required")
        result=launch(args.approval,args.reference_review)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()

"""Activate the frozen anchor adapter through the existing serial runner."""
from contextlib import ExitStack
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
PREP = BASE / "anchor_calibration_preparation_20261020_v1"
sys.path.insert(0, str(PREP))
import runtime_adapter as a
from runtime_adapter import p, s
from adapters import DeepSeekTransport
from deepseek_access import read_key, credential_scope, management_once, visible_paid_writers
from live import public_service_check

ROOT = BASE / "anchor_calibration_runs" / a.STUDY / "live"
LEDGER = s.REPO / "project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
HISTORY = ("live_runs", "paired_diagnostic_runs", "action_stage_runs", "reward_noise_runs")


def historical_count():
    return 66 + sum(len([x for x in (BASE / name).rglob("*.started.json")
                         if "management" not in x.parts]) for name in HISTORY)


def approve_scope(protocol, auth):
    """Check user approval before credentials; receipt is bound only after preflight."""
    required = dict(status="APPROVED", study=a.STUDY, protocol_identity=protocol["identity"],
                    baseline_cumulative=201, max_calls=24, cumulative_cap=225, capacity=289,
                    stage_cap_usd="1.15", trial_cap_usd="2", shared_cap_usd="20",
                    added_semantic_revision=1, exact_synthetic_examples_authorized=True,
                    old_stops_released=False, reward_eligible=False,
                    management_requests={"models": 1, "user/balance": 1},
                    credential_process_read_authorized=True,
                    outbound_scope=protocol["authority_requested"]["outbound"],
                    diagnostic_policy=protocol["diagnostic_policy"])
    if any(auth.get(k) != v for k, v in required.items()):
        raise ValueError("authorization scope mismatch")
    if auth.get("user_message") != "好的，推进吧。":
        raise ValueError("authorization message binding missing")


def check_append_only(original, current, slot_ids):
    if not current.startswith(original):
        raise ValueError("shared ledger prefix changed")
    if any(json.loads(line).get("reservation_id") not in slot_ids
           for line in current[len(original):].decode().splitlines()):
        raise ValueError("foreign paid ledger writer")


def observe(slot, row, root):
    print(s.canonical(dict(position=slot["position"], arm=slot["arm"], draw=slot["draw"],
                           technical_valid=row["technical_valid"],
                           model_unknown=row["evaluation"].get("model_unknown"),
                           seconds=round(row["elapsed_seconds"], 2),
                           accounted_usd=row["financial"]["accounted_upper_usd"])), flush=True)
    return None


def launch():
    protocol, items = a.load()
    auth = s.read(HERE / "APPROVED.json")
    approve_scope(protocol, auth)
    code = s.read(HERE / "execution_code_binding.json")
    for path, sha in code["files"].items():
        if s.sha(path) != sha:
            raise ValueError("execution code changed")
    ROOT.mkdir(parents=True, exist_ok=True)
    lock_paths = [BASE / "live_runs/.pool.lock", LEDGER.with_suffix(".lock")] + [
        BASE / name / ".launch.lock" for name in HISTORY[1:] + ("anchor_calibration_runs",)]
    with ExitStack() as stack:
        for path in lock_paths:
            lock = stack.enter_context(path.open("a"))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if historical_count() != 201:
            raise ValueError("historical count changed")
        other = [x for x in ROOT.parent.parent.rglob("*.started.json")
                 if "management" not in x.parts and not x.is_relative_to(ROOT)]
        if other:
            raise ValueError("other anchor starts exist; no cross-version redispatch")
        starts, _ = p.replay(ROOT, protocol)
        if starts or (ROOT / "STOP.json").exists():
            print(s.canonical(dict(state="PRESERVED_NO_RESTART", started=len(starts))), flush=True)
            return
        baseline = protocol["financial_baseline"]
        if s.sha(LEDGER) != baseline["ledger_sha256"]:
            raise ValueError("shared ledger changed")
        original = LEDGER.read_bytes()
        if visible_paid_writers():
            raise ValueError("visible concurrent paid writer; no process operated on")
        management = ROOT / "management"
        management.mkdir(exist_ok=True)
        if list(management.iterdir()):
            raise ValueError("prior preflight exists; no automatic retry")
        public_service_check(management, code["public_price_table_identity"])
        key = read_key()
        with credential_scope(key):
            models = management_once(management, "models", key)
            if models["status"] != 200:
                raise ValueError("model-list query failed")
            model = next((m for m in models.get("body", {}).get("data", [])
                          if m.get("id") == "deepseek-flash"), {})
            if not model:
                raise ValueError("approved alias missing")
            if (("name" in model and model["name"] not in
                 ("DeepSeek-V4.1-Flash", "DeepSeek-V4.1-Flash-1017")) or
                ("context_window" in model and model["context_window"] != 1048576) or
                ("max_output_tokens" in model and model["max_output_tokens"] != 393216)):
                raise ValueError("model identity/capability drift")
            balance = management_once(management, "user/balance", key)
            if balance["status"] != 200 or not balance.get("body", {}).get("is_available"):
                raise ValueError("balance unavailable")
            amounts = {x["currency"]: Decimal(x["total_balance"])
                       for x in balance["body"]["balance_infos"]}
            # Existing official USD/CNY tariff ratio, not an exchange-rate claim.
            available = amounts.get("USD", Decimal(0)) + amounts.get("CNY", Decimal(0)) * Decimal(".15")
            budget = p.DiagnosticBudget(
                LEDGER, trial=baseline["financial_trial_identity"], study=a.STUDY,
                stage_cap=s.nanodollars("1.15"), trial_cap=s.nanodollars(2),
                shared_cap=s.nanodollars(20), baseline=s.nanodollars("1.50724291"),
                opening=s.nanodollars("0.03079930"), account_opening=s.nanodollars(available),
                opening_trial=s.nanodollars(baseline["trial_accounted_usd"]))
            total, trial, reserved, settled = budget._totals(budget.events())
            if set(reserved) - set(settled):
                raise ValueError("unknown prior liabilities")
            if trial != s.nanodollars(baseline["trial_accounted_usd"]):
                raise ValueError("trial baseline changed")
            if total != s.nanodollars(baseline["shared_total_usd"]):
                raise ValueError("shared ledger total changed")
            screens = {}
            rt = a.runtime()
            for item_id, item in items.items():
                messages, _ = rt["payload"](item, "joint")
                screens[item_id] = p.input_guard(messages)
            preflight_path = management / "preflight.json"
            s.save(preflight_path, dict(
                checked_unix=time.time(), service=model,
                available_tariff_equivalent_usd=str(available),
                currency_basis="existing official tariff ratio, not FX",
                trial_accounted_usd=s.usd(trial), shared_accounted_usd=s.usd(total),
                known_unsettled_count=0, visible_paid_writers=[],
                visibility="visible local processes and shared ledger; no all-account visibility guarantee",
                input_screens=screens, public_price_table_identity=code["public_price_table_identity"],
                GPU_used=False, old_stops_released=False, credential_value_persisted=False))
            live_auth = dict(auth, locked_live_preflight_receipt={
                "path": str(preflight_path), "sha256": s.sha(preflight_path)})
            a.approve(protocol, live_auth)
            s.save(ROOT / "bound_execution_authorization.json", live_auth)
            ids = {x["slot_id"] for x in protocol["schedule"]}

            def guard():
                a.load()
                if historical_count() != 201:
                    raise ValueError("historical count changed during execution")
                if [x for x in ROOT.parent.parent.rglob("*.started.json")
                    if "management" not in x.parts and not x.is_relative_to(ROOT)]:
                    raise ValueError("other anchor starts exist")
                for path, sha in code["files"].items():
                    if s.sha(path) != sha:
                        raise ValueError("execution code changed")
                check_append_only(original, LEDGER.read_bytes(), ids)
                if visible_paid_writers():
                    raise ValueError("visible concurrent paid writer")

            rt["review"] = observe
            result = p.run(protocol, items, ROOT, DeepSeekTransport(protocol["config"]), budget,
                           mode="live", auth=live_auth, before_dispatch=guard,
                           global_count=historical_count, runtime=rt)
        del key
        s.save(ROOT / "stage_result.json", result)
        total, trial, reserved, settled = budget._totals(budget.events())
        s.save(ROOT / "financial_closeout.json", dict(
            trial_accounted_usd=s.usd(trial), shared_accounted_usd=s.usd(total),
            stage_accounted_usd=s.usd(budget.stage_total(reserved, settled)),
            unsettled=[k for k in reserved if k not in settled], ledger_sha256=s.sha(LEDGER),
            original_prefix_preserved=LEDGER.read_bytes().startswith(original)))
        print(s.canonical(dict(started=result["started"], cumulative=result["cumulative"],
                               stop=s.read(ROOT / "STOP.json") if (ROOT / "STOP.json").exists() else None)),
              flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    if sys.argv[1:] != ["--live"]:
        raise SystemExit("Explicit --live and bound approval required")
    try:
        launch()
    except Exception as exc:
        ROOT.mkdir(parents=True, exist_ok=True)
        safe = ("historical count", "other anchor", "shared ledger", "visible concurrent",
                "prior preflight", "published service/", "model-list", "approved alias",
                "model identity", "balance unavailable", "unknown prior", "trial baseline",
                "authorization", "execution code", "protocol identity", "frozen preparation", "old STOP")
        reason = str(exc) if type(exc) is ValueError and str(exc).startswith(safe) else (
            "launch exception; sensitive details suppressed")
        row = dict(reason=reason, error_type=type(exc).__name__, automatic_retry=False, timestamp=time.time())
        s.save(ROOT / ("failure_" + str(time.time_ns()) + ".json"), row)
        if not (ROOT / "STOP.json").exists():
            s.save(ROOT / "STOP.json", row)
        raise SystemExit("Stopped; failure preserved, no retry.") from None

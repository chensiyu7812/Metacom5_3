"""Audit v2 (pmrl1v3-b1-needcard-pilot-audit-v2) of the pilot NeedCards; then freeze checklist v3 for valid cards.

Same six checks as v1; labels valid / evidence_error / stratum_error / uncertain / writer_failed /
pre_call_blocked; gates: evidence-error rate <= 10% AND every B6e-v3 selected prefix valid (else B6e paused).

  --prepare  envelopes.jsonl -> AUDIT_SHEET.json (machine facts + blank answers; write-once)
  --report   AUDIT_SHEET_FILLED.json (reviewer answers) -> AUDIT_REPORT.json (derived verdicts; write-once)
  --freeze   AUDIT_REPORT.json -> checklist v3 per valid card in a fresh ChecklistLedger (write-once)
CPU only; no model call.  Runs only after an authorised pilot run produced envelopes.jsonl.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3 import contracts as K  # noqa: E402
from metacom_pm.rl1v3.checklist import writer_v3 as CW3  # noqa: E402
from metacom_pm.rl1v3.checklist.ledger import ChecklistLedger  # noqa: E402
from metacom_pm.rl1v3.io import decode_contract, write_json_once  # noqa: E402
from metacom_pm.rl1v3.needs import pilot_audit_v2 as A  # noqa: E402


def load_envelopes(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        e = json.loads(line)
        if e["status"] == "ok":
            e["needcard"] = decode_contract(K.NeedCard, json.dumps(e["needcard"]))
            e["method_evidence"] = tuple(decode_contract(K.SourceSpan, json.dumps(s)) for s in e["method_evidence"])
        out.append(e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PROJECT / "configs/rl1v3/B1_needcard_pilot_v2.yaml"))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare", action="store_true")
    g.add_argument("--report", action="store_true")
    g.add_argument("--freeze", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    out = PROJECT / cfg["out_dir"]
    env = load_envelopes(out / "envelopes.jsonl")
    if args.prepare:
        write_json_once(out / "audit/AUDIT_SHEET.json", A.prepare(env))
    elif args.report:
        rows = json.loads((out / "audit/AUDIT_SHEET_FILLED.json").read_text())
        sel = json.loads((PROJECT / "outputs/pm_rl1/v3/B6e_plan/v3/SELECTION.json").read_text())
        rep = A.report(rows, b6e_prefixes=sel["selected_ids"])
        write_json_once(out / "audit/AUDIT_REPORT.json", rep)
        print(json.dumps({k: rep[k] for k in ("counts", "evidence_error_rate", "gate_passed", "b6e_gate_passed", "b6e_prefixes_without_valid_card", "checklist_eligible")}, indent=1))
    else:
        rep = json.loads((out / "audit/AUDIT_REPORT.json").read_text())
        ledger = ChecklistLedger(PROJECT / "outputs/pm_rl1/v3/B2/checklists_pilot_v3")
        frozen = A.freeze_checklists(rep, env, ledger, CW3.build)
        write_json_once(PROJECT / "outputs/pm_rl1/v3/B2/checklists_pilot_v3/FROZEN.json",
                        dict(protocol=CW3.CHECKLIST_PROTOCOL, writer_identity=CW3.writer_identity(),
                             audit_report_sha256=rep["sha256"], frozen=frozen, evidence_tier="engineering_only"))
        print(json.dumps(frozen, indent=1))


if __name__ == "__main__":
    main()

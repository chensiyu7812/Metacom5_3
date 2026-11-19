#!/usr/bin/env python3
"""CPU check by default; run requires explicit job-specific researcher approval."""
import argparse, json
from pathlib import Path
from metacom_pm.rl1v3.generator.limited_run import read_plan, run
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["check","run"]);p.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[3])
    p.add_argument("--plan",type=Path,required=True);p.add_argument("--approval",type=Path);p.add_argument("--run-root",type=Path)
    p.add_argument("--executor-binding",type=Path,help="separate reviewed repair identity; original plan stays unchanged")
    a=p.parse_args()
    if a.action=="check":
        binding=json.loads(a.executor_binding.read_text()) if a.executor_binding else None
        plan,rows,_=read_plan(a.root,a.plan,binding)
        print(json.dumps({"job_kind":plan["job_kind"],"requests":len(rows),"engineering_ready":"CPU_identity_check_passed",
                          "research_qualified":False,"authorized":False,"model_loads":0},indent=2))
    else:
        if not a.approval or not a.run_root:p.error("run requires separate --approval and --run-root")
        result=run(a.root,a.plan,a.approval,a.run_root,a.executor_binding);print(json.dumps(result,indent=2))
        if result["status"]!="FINISHED":raise SystemExit(2)
if __name__=="__main__":main()


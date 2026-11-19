#!/usr/bin/env python3
"""Offline DP tool: prepare confirmed samples, freeze one human choice, export CPU candidates."""
import argparse, importlib.util, json
from pathlib import Path
from metacom_pm.rl1v3.compile.dp_selection import prepare_formal,freeze_choice,selection_html,export_candidates
from metacom_pm.rl1v3.io import parse_json,write_json_once,write_jsonl_once
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("action",choices=["prepare","freeze","export"])
    p.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[3])
    p.add_argument("--sample-manifest",type=Path);p.add_argument("--bundle",type=Path);p.add_argument("--draft",type=Path)
    p.add_argument("--receipts",type=Path);p.add_argument("--ret-audit",type=Path);p.add_argument("--baseline",type=Path)
    p.add_argument("--renderer");p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();read=lambda q:parse_json(q.read_text())
    if a.action=="prepare":
        if not a.sample_manifest:p.error("--sample-manifest required")
        if a.out.exists():raise FileExistsError("new sample directory required")
        bundle,ret=prepare_formal(a.root,read(a.sample_manifest));a.out.mkdir(parents=True)
        write_json_once(a.out/"SELECTOR_BUNDLE.json",bundle);write_json_once(a.out/"AUDIT_RET_NOT_FOR_SELECTOR.json",ret)
        (a.out/"SELECTOR.html").write_text(selection_html(bundle))
    elif a.action=="freeze":
        if not a.bundle or not a.draft:p.error("--bundle and --draft required")
        print(json.dumps(freeze_choice(read(a.bundle),read(a.draft),a.out),ensure_ascii=False,indent=2))
    else:
        if not all([a.bundle,a.receipts,a.ret_audit,a.baseline,a.renderer]):p.error("export requires --bundle --receipts --ret-audit --baseline --renderer")
        bundle=read(a.bundle);receipts={e["pool"]["prefix_id"]:read(a.receipts/(e["pool"]["prefix_id"]+".json")) for e in bundle["rows"]}
        spec=importlib.util.spec_from_file_location("native_counter",a.root/"project/scripts/rl1v3/prepare_e1_qualification.py")
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        base=read(a.baseline);counter=m.NativeCounter(Path("/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3"),{"common":base["spec"]})
        rows=export_candidates(bundle,receipts,read(a.ret_audit),base,counter,a.renderer)
        write_jsonl_once(a.out,rows);print(json.dumps({"candidate_rows":len(rows),"model_calls":0,"authorized":False}))
if __name__=="__main__":main()


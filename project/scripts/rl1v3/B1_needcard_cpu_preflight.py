"""NeedCard writer v2 CPU preflight on the fixed 20 pilot prefixes (tokenizer files only; no model call).

For each pilot prefix: A1-sourced context, complete strictly-past RAW, RS-v0 label
catalog, exact writer chat prompt counted with the native Qwen3.5-9B tokenizer
(non-thinking, generation prompt), native/operational budget status.  Also writes
the derived RS-v0 label catalog and its audit.  Packs themselves are not stored
(they are reproducible from the pinned inputs); their sha256 is.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.env import a1b_port as P  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, object_sha256, write_json_once, write_jsonl_once  # noqa: E402
from metacom_pm.rl1v3.needs import protocol_v2 as W, rs_catalog  # noqa: E402
from metacom_pm.rl1v3.needs.sources import a1_context  # noqa: E402
from metacom_pm.rl1v3.sources import source_registry as S  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PROJECT / "configs/rl1v3/B1_needcard_v2.yaml"))
    ap.add_argument("--b5-config", default=str(PROJECT / "configs/rl1v3/B5_real_replay_v2.yaml"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    b5 = yaml.safe_load(Path(args.b5_config).read_text())
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    t0 = time.time()
    bank = P.load_bank(REPO, registry_dir=b5["registry_dir"], bank_dir=b5["bank_dir"],
                       expected_source=b5["expected_source"], expected_bank=b5["expected_bank"])
    reg = bank.registry
    strategies = S.PinnedInputs(REPO).read("rs_strategy", lines=True)      # hash-checked against the A1 audit
    b_list, b_audit = rs_catalog.derive(bank, strategies)                   # WS-B cross-check only
    if cfg.get("rs_catalog_path"):                                          # WS-A delivered RS-v0 catalog (formal)
        from metacom_pm.rl1v3.bank import rs_v0_catalog as AC
        catalog = AC.load(REPO / cfg["rs_catalog_path"], root=REPO, bank=bank)   # rebuilt + verified by A's loader
        cat_audit = dict(source="WS-A " + AC.PROTOCOL, compatibility=rs_catalog.check_compat(catalog, b_list),
                         a_counts=catalog.data["counts"], b_cross_check_list=dict(b_audit, catalog_id=b_list.catalog_id))
    else:
        catalog, cat_audit = b_list, dict(source="WS-B derived list (no WS-A catalog configured)", **b_audit)
    tok = NativeTokenizer(cfg["writer_model"]["path"], PROJECT / cfg["asset_manifest"])
    manifest = json.loads((PROJECT / cfg["asset_manifest"]).read_text())
    model_files = sorted((r["path"].split("/")[-1], r["sha256"]) for r in manifest["files"]
                         if r.get("exists") and r["path"].startswith(cfg["writer_model"]["path"] + "/"))
    model_sha = object_sha256(model_files)
    writer = W.writer_identity(model_id=cfg["writer_model"]["model_id"], model_sha256=model_sha,
                               decode_id=cfg["writer_model"]["decode_id"])

    def count(msgs):
        return len(tok.tokenizer.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True,
                                                     enable_thinking=False))
    census = {json.loads(x)["prefix_id"]: json.loads(x) for x in (PROJECT / cfg["census"]).read_text().splitlines()}
    cov = [json.loads(x) for x in (PROJECT / cfg["coverage_sample"]).read_text().splitlines()]
    pilots = [c for c in cov if c["uses"].get(cfg["pilot_use"]) is True]
    rows = []
    for c in pilots:
        ctx = a1_context(reg, census[c["prefix_id"]])
        kw = dict(registry=reg, count_prompt=count, native_context_tokens=tok.native_context_tokens,
                  operational_max_input_tokens=cfg["operational_max_input_tokens"], tokenizer_identity=tok.identity)
        pack = W.build_pack(ctx, catalog, **kw)
        blocked = W.build_pack(ctx, None, **kw)
        no_past = count(W.messages(dict(pack, past=[])))
        legality = dict(prefix_matches_b0=ctx.prefix.prefix_id == c["prefix_id"],
                        source_context_verified=True,
                        past_strictly_before_cut=all(s["rank"] < ctx.prefix.cutoff_rank for s in pack["past"]),
                        past_same_owner=all(s.owner_id == ctx.prefix.owner_id for s in ctx.history),
                        past_complete=all(s.complete for s in ctx.history),
                        current_window_within_cut=all(t[0] <= ctx.prefix.cut_turn for t in pack["current"]["turns"]),
                        no_future_session=all(e.source.chronological_rank < ctx.prefix.cutoff_rank
                                              for e in reg.visible(ctx.prefix)))
        rows.append(dict(prefix_id=c["prefix_id"], owner_id=c["owner_id"], fold=c["fold"], rank_bucket=c["rank_bucket"],
                         cutoff_rank=ctx.prefix.cutoff_rank, past_sessions=pack["past_sessions"],
                         past_chars=pack["past_chars"], input_tokens=pack["input_tokens"],
                         past_raw_tokens=pack["input_tokens"] - no_past, catalog_tokens=pack["catalog_tokens"],
                         prompt_plus_output_bound=pack["input_tokens"] + W.MAX_NEW_TOKENS,
                         status=pack["status"], status_without_catalog=blocked["status"],
                         pack_sha256=pack["pack_sha256"], source_version=pack["source_version"],
                         source_ids_sha256=object_sha256([pack["current"]["source_id"]] + [s["source_id"] for s in pack["past"]]),
                         legality=legality, truncated=False))
    toks = [r["input_tokens"] for r in rows]
    summary = dict(
        protocol=W.WRITER_PROTOCOL, prompt_sha256=W.prompt_sha256(), writer_identity=writer, writer_model_sha256=model_sha,
        tokenizer_identity=tok.identity, native_context_tokens=tok.native_context_tokens,
        operational_max_input_tokens=cfg["operational_max_input_tokens"], max_new_tokens=W.MAX_NEW_TOKENS,
        source_version=reg.version, bank_version=bank.version, catalog_id=catalog.catalog_id, catalog_sha256=catalog.sha256,
        catalog_audit=cat_audit, pilots=len(rows), statuses={s: sum(r["status"] == s for r in rows) for s in W.PRE_CALL_STATUSES},
        statuses_without_catalog={s: sum(r["status_without_catalog"] == s for r in rows) for s in W.PRE_CALL_STATUSES},
        input_tokens=dict(min=min(toks), median=statistics.median(toks), max=max(toks), total=sum(toks)),
        past_raw_tokens=dict(min=min(r["past_raw_tokens"] for r in rows), max=max(r["past_raw_tokens"] for r in rows)),
        catalog_tokens=sorted({r["catalog_tokens"] for r in rows}),
        max_fraction_of_native=round(max(r["prompt_plus_output_bound"] for r in rows) / tok.native_context_tokens, 4),
        legality_all_true=all(all(r["legality"].values()) for r in rows), truncated=0,
        writer_calls=0, gpu_used=False, wall_seconds=round(time.time() - t0, 1), evidence_tier="engineering_only")
    out = Path(args.out) if args.out else PROJECT / cfg["out_dir"]
    write_json_once(out / "rs_v0_label_catalog.json", dict(catalog.as_dict(), audit=cat_audit))
    write_jsonl_once(out / "pilot_inputs.jsonl", rows)
    write_json_once(out / "summary.json", summary)
    if not args.out:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
        man = build_manifest(task="B1_needcard_cpu_preflight_v2", root=PROJECT,
                             inputs={"census": PROJECT / cfg["census"], "coverage_sample": PROJECT / cfg["coverage_sample"],
                                     "sources": REPO / b5["registry_dir"] / "sources.jsonl",
                                     "records": REPO / b5["bank_dir"] / "records.jsonl",
                                     "strategy_cards": REPO / S.PinnedInputs(REPO).config["rs_strategy"],
                                     **({"rs_v0_catalog": REPO / cfg["rs_catalog_path"]} if cfg.get("rs_catalog_path") else {})},
                             outputs=[out / "rs_v0_label_catalog.json", out / "pilot_inputs.jsonl", out / "summary.json"],
                             code=[PROJECT / x for x in ("scripts/rl1v3/B1_needcard_cpu_preflight.py",
                                                         "src/metacom_pm/rl1v3/needs/protocol_v2.py",
                                                         "src/metacom_pm/rl1v3/needs/rs_catalog.py",
                                                         "src/metacom_pm/rl1v3/needs/sources.py",
                                                         "configs/rl1v3/B1_needcard_v2.yaml")], code_sha=head)
        write_json_once(out / "manifest.json", dict(man, writer_calls=0, gpu_used=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

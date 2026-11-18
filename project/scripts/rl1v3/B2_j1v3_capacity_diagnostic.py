"""J1-v3 output-capacity diagnostic (CPU, Qwen3.5-9B native tokenizer only; no judge call).

How many output tokens does the frozen v3 ``{errors, items}`` format need for realistic and worst
checklist shapes and G0e replies (<= 320 tokens)?  Compares with the planned J1 max_new_tokens=800
and candidate budgets.  The checklist size bound is derived from the NeedCard writer's own 800-token
output (cheapest legal item: a failed/refused suggestion with a short verified quote).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.io import build_manifest, write_json_once  # noqa: E402
from metacom_pm.rl1v3.judge import capacity_v3 as C  # noqa: E402
from metacom_pm.rl1v3.judge import protocol_v3 as JP3  # noqa: E402

OUT = PROJECT / "outputs/pm_rl1/v3/B2/j1v3_capacity"
BUDGETS = (800, 1600, 2400, 4096)
WORDS = ("it sounds like the last few weeks at work have left you exhausted and you are not sure how to "
         "get through tonight without feeling overwhelmed again so maybe we can look at one small step").split()


def sentence(n_words: int, k: int) -> str:
    w = [WORDS[(k * 7 + i) % len(WORDS)] for i in range(n_words)]
    return " ".join(w).capitalize() + "."


def main():
    pre = yaml.safe_load((PROJECT / "configs/rl1v3/B1_needcard_v2.yaml").read_text())
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    tok = NativeTokenizer(pre["writer_model"]["path"], PROJECT / pre["asset_manifest"])
    count = lambda t: len(tok.tokenizer.encode(t, add_special_tokens=False))
    # cheapest legal NeedCard history entry in the writer's output -> max checklist H items within 800 tokens
    cheapest = json.dumps(dict(session="S1", speaker="seeker", quote="I tried that and it did not help."))
    envelope = json.dumps(dict(stratum="history", history_items=[], failed_or_rejected=[], outdated_facts=[],
                               method_need=None, method_evidence=[], risk_flags=[]))
    per_item, base = count(cheapest) + 1, count(envelope)
    max_h = (pre["max_new_tokens"] - base) // per_item
    shapes = {
        "minimum_none_stratum": {"G": 3, "I": 4, "S": 1},
        "fixture_checklist_v3": {"H+": 1, "H-": 3, "R": 1, "G": 3, "I": 4, "S": 1},
        "moderate": {"H+": 3, "H-": 4, "R": 1, "G": 3, "I": 4, "S": 2},
        "writer_bound_all_risk": {"H-": max_h, "R": 1, "G": 3, "I": 4, "S": 6},
    }
    replies = {
        "typical_6x18w": [sentence(18, k) for k in range(6)],
        "max_8x30w": [sentence(30, k) for k in range(8)],
        "one_long_sentence": [sentence(240, 0)],
    }
    reply_tokens = {k: count(" ".join(v)) for k, v in replies.items()}
    rows = C.table(count, shapes, replies, budgets=BUDGETS)
    worst = {s: max(r["output_tokens"] for r in rows if r["shape"] == s) for s in shapes}
    minimal = {s: min(r["output_tokens"] for r in rows if r["shape"] == s and r["scenario"] == "minimal") for s in shapes}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True, text=True).stdout.strip()
    out = dict(
        protocol="pmrl1v3-j1v3-capacity-diagnostic-v1", judge_protocol=JP3.JUDGE_PROTOCOL, tokenizer=tok.identity,
        planned_j1_max_new_tokens=800, budgets=list(BUDGETS), min_fields=dict(row=C.ROW_FIELDS, error=C.ERROR_FIELDS,
                                                                                fail=C.REQUIRED_FOR_FAIL),
        checklist_bound=dict(writer_max_new_tokens=pre["max_new_tokens"], cheapest_item_tokens=per_item,
                             writer_envelope_tokens=base, max_h_items=max_h,
                             note="NeedCard has no item cap; the writer's 800-token output bounds it"),
        shapes={k: dict(v, total=sum(v.values())) for k, v in shapes.items()}, reply_tokens_qwen=reply_tokens,
        rows=rows, minimal_by_shape=minimal, worst_by_shape=worst,
        fits_800=dict(minimal={s: v <= 800 for s, v in minimal.items()},
                      quote_every_item={s: all(r["output_tokens"] <= 800 for r in rows if r["shape"] == s and
                                               r["scenario"] == "quote_every_item") for s in shapes}),
        system_prompt_tokens=count(JP3.SYSTEM_PROMPT), code_head=head, judge_calls=0, measured=False,
        status="static estimate of required output length; real J1 length distribution not measured",
        evidence_tier="engineering_only")
    write_json_once(OUT / "CAPACITY.json", out)
    man = build_manifest(task="B2_j1v3_capacity", root=PROJECT, inputs={}, outputs=[OUT / "CAPACITY.json"],
                         code=[PROJECT / "scripts/rl1v3/B2_j1v3_capacity_diagnostic.py",
                               PROJECT / "src/metacom_pm/rl1v3/judge/capacity_v3.py"], code_sha=head)
    write_json_once(OUT / "manifest.json", dict(man, model_calls=0, gpu_used=False))
    print(json.dumps({k: out[k] for k in ("checklist_bound", "reply_tokens_qwen", "minimal_by_shape", "worst_by_shape",
                                          "fits_800")}, indent=1))
    for r in rows:
        if r["format"] == "compact":
            print(r["shape"][:22].ljust(22), r["reply"][:18].ljust(18), r["scenario"].ljust(20), r["output_tokens"])


if __name__ == "__main__":
    main()

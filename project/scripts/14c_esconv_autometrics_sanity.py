#!/usr/bin/env python3
"""Offline ESConv automatic-metric sanity checks.

These metrics are appendix diagnostics only. The ESConv main result remains the
blind pairwise judge plus cluster bootstrap CI from `scripts/14a_eval_esconv_strategy_only.py`.
"""

from __future__ import annotations

import argparse
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from metacom_pm.io import iter_jsonl, utc_now, write_json


ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    if len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _distinct(rows: list[dict[str, Any]], n: int) -> float | None:
    total = 0
    unique: set[tuple[str, ...]] = set()
    for row in rows:
        grams = _ngrams(_tokens(row.get("response", "")), n)
        total += len(grams)
        unique.update(grams)
    return len(unique) / total if total else None


def _lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for tok_a in a:
        cur = [0]
        for j, tok_b in enumerate(b, 1):
            if tok_a == tok_b:
                cur.append(prev[j - 1] + 1)
            else:
                cur.append(max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def _rouge_l_f1(hyp: list[str], ref: list[str]) -> float:
    if not hyp or not ref:
        return 0.0
    lcs = _lcs_len(hyp, ref)
    precision = lcs / len(hyp)
    recall = lcs / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _modified_precision(hyp: list[str], ref: list[str], n: int) -> tuple[int, int]:
    hyp_grams = _ngrams(hyp, n)
    ref_grams = _ngrams(ref, n)
    if not hyp_grams or not ref_grams:
        return 0, len(hyp_grams)
    hyp_counts = Counter(hyp_grams)
    ref_counts = Counter(ref_grams)
    clipped = sum(
        min(count, ref_counts[gram]) for gram, count in hyp_counts.items()
    )
    return clipped, len(hyp_grams)


def _bleu_n(hyp: list[str], ref: list[str], max_n: int) -> float:
    if not hyp or not ref:
        return 0.0
    precisions = []
    for n in range(1, max_n + 1):
        clipped, total = _modified_precision(hyp, ref, n)
        if total == 0:
            return 0.0
        # Light add-one smoothing keeps sentence-level B-2/3/4 informative
        # without pretending to reproduce a specific ESConv leaderboard setup.
        if n == 1:
            precision = clipped / total
        else:
            precision = (clipped + 1.0) / (total + 1.0)
        if precision <= 0:
            return 0.0
        precisions.append(precision)
    geo_mean = math.exp(sum(math.log(p) for p in precisions) / max_n)
    brevity = 1.0 if len(hyp) >= len(ref) else math.exp(1.0 - len(ref) / len(hyp))
    return brevity * geo_mean


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if math.isfinite(v)]
    return sum(vals) / len(vals) if vals else None


def _percentile(values: list[float], q: float) -> float | None:
    vals = sorted(v for v in values if math.isfinite(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = q * (len(vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def _summarize(rows: list[dict[str, Any]], gold_by_card: dict[str, str]) -> dict[str, Any]:
    lengths = [len(_tokens(row.get("response", ""))) for row in rows]
    rouge_l = []
    bleu: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: []}
    input_tokens = []
    output_tokens = []
    for row in rows:
        hyp = _tokens(row.get("response", ""))
        ref = _tokens(gold_by_card.get(str(row.get("card_id")), ""))
        rouge_l.append(_rouge_l_f1(hyp, ref))
        for n in bleu:
            bleu[n].append(_bleu_n(hyp, ref, n))
        cost = row.get("cost") or {}
        input_tokens.append(float(cost.get("total_input_tokens") or 0))
        output_tokens.append(float(cost.get("output_tokens") or 0))
    return {
        "n": len(rows),
        "response_length_tokens": {
            "mean": _mean([float(x) for x in lengths]),
            "median": _percentile([float(x) for x in lengths], 0.5),
            "p95": _percentile([float(x) for x in lengths], 0.95),
        },
        "distinct_1": _distinct(rows, 1),
        "distinct_2": _distinct(rows, 2),
        "simple_smoothed_sentence_bleu1_mean": _mean(bleu[1]),
        "simple_smoothed_sentence_bleu2_mean": _mean(bleu[2]),
        "simple_smoothed_sentence_bleu3_mean": _mean(bleu[3]),
        "simple_smoothed_sentence_bleu4_mean": _mean(bleu[4]),
        "simple_sentence_bleu1_mean": _mean(bleu[1]),
        "rouge_l_f1_mean": _mean(rouge_l),
        "input_tokens_mean": _mean(input_tokens),
        "output_tokens_mean": _mean(output_tokens),
    }


def _fmt(value: Any, ndigits: int = 3) -> str:
    if value is None:
        return "NA"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return "NA"
    return f"{numeric:.{ndigits}f}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(lines)


def _write_markdown(path: Path, result: dict[str, Any]) -> None:
    rows = []
    for action, item in sorted(result["by_action"].items()):
        rows.append(
            [
                action,
                item["n"],
                _fmt(item["response_length_tokens"]["mean"], 1),
                _fmt(item["distinct_1"]),
                _fmt(item["distinct_2"]),
                _fmt(item["simple_smoothed_sentence_bleu1_mean"]),
                _fmt(item["simple_smoothed_sentence_bleu2_mean"]),
                _fmt(item["simple_smoothed_sentence_bleu3_mean"]),
                _fmt(item["simple_smoothed_sentence_bleu4_mean"]),
                _fmt(item["rouge_l_f1_mean"]),
                _fmt(item["input_tokens_mean"], 1),
            ]
        )
    lines = [
        "# ESConv Offline Autometrics Sanity Appendix",
        "",
        f"生成时间：{utc_now()}",
        "",
        "这些指标只作为 appendix sanity check，不作为主实验结果。ESConv 主结论仍是 blind pairwise judge：always-on `M0+RS` 平均低于 `M0+R0` 且成本更高。",
        "",
        _table(
            [
                "Action",
                "n",
                "Len",
                "Distinct-1",
                "Distinct-2",
                "B-1 sanity",
                "B-2 sanity",
                "B-3 sanity",
                "B-4 sanity",
                "ROUGE-L sanity",
                "Input tok",
            ],
            rows,
        ),
        "",
        "解释边界：BLEU/ROUGE 与人类支持质量不等价，且 ESConv gold response 不是唯一正确回复；这些 0-1 scale 数值只用于检查长度、多样性和表面重叠是否出现异常，不与 ESConv generation papers 的 published scores 直接数值比较。",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=ROOT / "outputs/esconv_sweep/action_outcomes.jsonl",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=ROOT / "data/esconv_test/audit_only.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs/esconv_strategy_eval/autometrics_sanity.json",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=ROOT / "outputs/esconv_strategy_eval/autometrics_sanity.md",
    )
    args = parser.parse_args()

    gold_by_card = {
        str(row["card_id"]): str(row.get("gold_response") or "")
        for row in iter_jsonl(args.audit)
    }
    by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in iter_jsonl(args.outcomes):
        by_action[str(row.get("action_id") or "UNKNOWN")].append(row)

    result = {
        "status": "COMPLETE",
        "created_at": utc_now(),
        "protocol": "esconv_offline_autometrics_sanity",
        "input_outcomes": str(args.outcomes),
        "input_audit": str(args.audit),
        "scope": "appendix_sanity_only_not_main_evidence",
        "metrics": {
            "distinct_1_2": "corpus unique n-grams / total n-grams on generated responses",
            "simple_smoothed_sentence_bleu1_4_mean": "sentence-level clipped BLEU-N with brevity penalty and light add-one smoothing for N>1, averaged across turns; appendix sanity only, not comparable to official ESConv leaderboard BLEU",
            "rouge_l_f1_mean": "sentence-level ROUGE-L F1 against ESConv gold response, averaged across turns",
        },
        "by_action": {
            action: _summarize(rows, gold_by_card)
            for action, rows in sorted(by_action.items())
        },
    }
    write_json(args.out, result)
    _write_markdown(args.markdown_out, result)
    print(
        {
            "status": "COMPLETE",
            "out": str(args.out),
            "markdown_out": str(args.markdown_out),
        }
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""No-API diagnostics for ESConv Strategy RAG routing.

This script consumes the already judged M0+RS vs M0+R0 pairwise results and
answers a narrow question: is there measurable room for selective Strategy RAG
routing, even though always-on RS loses on average?
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

ADVICE_RE = re.compile(
    r"\b(what should i|what do i do|how do i|how can i|any advice|"
    r"should i|need advice|can you help|help me|suggest|suggestion|"
    r"tips|ways to|cope|deal with|handle|move on)\b",
    re.I,
)
DISTRESS_RE = re.compile(
    r"\b(anxious|anxiety|depressed|depression|sad|stress|stressed|"
    r"worried|scared|panic|upset|lonely|alone|hate|overwhelmed|"
    r"cry|crying|angry|afraid|guilt|guilty|hurt|hopeless)\b",
    re.I,
)
REFLECTION_RE = re.compile(
    r"\b(feel|feeling|felt|think|thinking|confused|unsure|uncertain|"
    r"don't know|do not know|not sure|wonder)\b",
    re.I,
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def rs_score(row: dict[str, Any]) -> float:
    winner = row.get("winner_action")
    if winner == "M0+RS":
        return 1.0
    if winner == "M0+R0":
        return 0.0
    return 0.5


def depth_bin(turn_index: int) -> str:
    if turn_index <= 2:
        return "01_first_two_turns"
    if turn_index <= 4:
        return "02_early_turns_3_4"
    if turn_index <= 8:
        return "03_mid_turns_5_8"
    return "04_late_turns_9_plus"


def length_bin(text: str) -> str:
    n = len(text.split())
    if n <= 8:
        return "01_short_0_8_words"
    if n <= 20:
        return "02_medium_9_20_words"
    return "03_long_21_plus_words"


def bool_label(name: str, value: bool) -> str:
    return f"{name}={'yes' if value else 'no'}"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    wins = sum(1 for r in rows if r.get("winner_action") == "M0+RS")
    losses = sum(1 for r in rows if r.get("winner_action") == "M0+R0")
    ties = n - wins - losses
    score = sum(rs_score(r) for r in rows) / n if n else math.nan
    delta_tokens = [
        (r.get("rs_total_input_tokens") or 0) - (r.get("r0_total_input_tokens") or 0)
        for r in rows
    ]
    return {
        "n": n,
        "rs_wins": wins,
        "ties": ties,
        "r0_wins": losses,
        "rs_preference_score": score,
        "rs_win_rate": wins / n if n else math.nan,
        "tie_rate": ties / n if n else math.nan,
        "mean_extra_input_tokens_for_rs": sum(delta_tokens) / n if n else math.nan,
    }


def add_group(groups: dict[str, list[dict[str, Any]]], key: str, row: dict[str, Any]) -> None:
    groups[key].append(row)


def top_groups(groups: dict[str, list[dict[str, Any]]], min_n: int) -> list[dict[str, Any]]:
    stats = []
    for key, rows in groups.items():
        if len(rows) < min_n:
            continue
        item = summarize(rows)
        item["group"] = key
        stats.append(item)
    return sorted(stats, key=lambda x: (-x["rs_preference_score"], -x["n"], x["group"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--judgments",
        type=Path,
        default=ROOT / "outputs/esconv_strategy_eval/strategy_pair_judgments.jsonl",
    )
    parser.add_argument(
        "--runtime",
        type=Path,
        default=ROOT / "data/esconv_test/runtime_states.jsonl",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "outputs/esconv_strategy_diagnostic",
    )
    parser.add_argument("--min-group-n", type=int, default=40)
    args = parser.parse_args()

    judgments = read_jsonl(args.judgments)
    runtime = {r["card_id"]: r for r in read_jsonl(args.runtime)}
    merged = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    gold_strategy_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in judgments:
        state = runtime.get(row["card_id"], {})
        text = state.get("current_user_text", "")
        row = dict(row)
        row["current_user_text"] = text
        row["current_session_summary"] = state.get("current_session_summary", "")
        merged.append(row)

        add_group(groups, depth_bin(int(row.get("turn_index") or 0)), row)
        add_group(groups, length_bin(text), row)
        add_group(groups, bool_label("advice_cue", bool(ADVICE_RE.search(text))), row)
        add_group(groups, bool_label("distress_cue", bool(DISTRESS_RE.search(text))), row)
        add_group(groups, bool_label("reflection_cue", bool(REFLECTION_RE.search(text))), row)
        add_group(groups, bool_label("question_mark", "?" in text), row)
        gold_strategy_groups[str(row.get("gold_strategy") or "UNKNOWN")].append(row)

    overall = summarize(merged)
    n = overall["n"]
    rs_win_rate = overall["rs_wins"] / n
    r0_win_rate = overall["r0_wins"] / n
    tie_rate = overall["ties"] / n
    # Pairwise score of an ideal selector against always-R0/always-RS using the
    # same judged pairs. This is an upper bound, not an implementable policy.
    oracle_vs_always_r0 = 0.5 + 0.5 * rs_win_rate
    oracle_vs_always_rs = 0.5 + 0.5 * r0_win_rate
    oracle_saved_rs_calls_vs_always_rs = (overall["r0_wins"] + overall["ties"]) / n

    result = {
        "status": "COMPLETE",
        "input_judgments": str(args.judgments),
        "input_runtime": str(args.runtime),
        "overall": overall,
        "oracle_selective_upper_bound": {
            "note": "Not deployable. Uses final judge outcomes to show the maximum value of selecting RS only when useful.",
            "score_vs_always_r0": oracle_vs_always_r0,
            "score_vs_always_rs": oracle_vs_always_rs,
            "rs_call_rate": rs_win_rate,
            "rs_calls_saved_vs_always_rs": oracle_saved_rs_calls_vs_always_rs,
        },
        "groups": top_groups(groups, args.min_group_n),
        "gold_strategy_groups": top_groups(gold_strategy_groups, args.min_group_n),
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "strategy_routing_diagnostic.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )

    best = result["groups"][:8]
    worst = list(reversed(result["groups"][-8:]))
    lines = [
        "# ESConv Strategy RAG 选择性路由诊断",
        "",
        "本报告不调用 API，只分析已经完成的 `M0+RS` vs `M0+R0` pairwise judge 结果。",
        "",
        "## 总体结论",
        "",
        f"- 样本数：{overall['n']} turns。",
        f"- RS wins / ties / R0 wins：{overall['rs_wins']} / {overall['ties']} / {overall['r0_wins']}。",
        f"- RS preference score：{overall['rs_preference_score']:.3f}。",
        f"- RS 平均额外输入 token：{overall['mean_extra_input_tokens_for_rs']:.1f}。",
        "",
        "这说明 always-on RS 在 ESConv 上不是好策略；但 RS 仍在一部分 turn 上胜出，所以更合理的问题是“何时开 RS”。",
        "",
        "## Oracle 选择性上限",
        "",
        f"- Oracle selector vs always-R0 score：{oracle_vs_always_r0:.3f}。",
        f"- Oracle selector vs always-RS score：{oracle_vs_always_rs:.3f}。",
        f"- Oracle RS call rate：{rs_win_rate:.3f}。",
        f"- 相比 always-RS 可省 RS 调用：{oracle_saved_rs_calls_vs_always_rs:.3f}。",
        "",
        "Oracle 不是可部署策略，只用于证明选择性调用存在空间。",
        "",
        "## RS 相对更有利的可见条件",
        "",
    ]
    for item in best:
        lines.append(
            f"- `{item['group']}`: n={item['n']}, score={item['rs_preference_score']:.3f}, "
            f"RS wins/tie/R0 wins={item['rs_wins']}/{item['ties']}/{item['r0_wins']}"
        )
    lines.extend(["", "## RS 相对更不利的可见条件", ""])
    for item in worst:
        lines.append(
            f"- `{item['group']}`: n={item['n']}, score={item['rs_preference_score']:.3f}, "
            f"RS wins/tie/R0 wins={item['rs_wins']}/{item['ties']}/{item['r0_wins']}"
        )
    lines.extend(["", "## Gold Strategy 分组", ""])
    for item in result["gold_strategy_groups"]:
        lines.append(
            f"- `{item['group']}`: n={item['n']}, score={item['rs_preference_score']:.3f}, "
            f"RS wins/tie/R0 wins={item['rs_wins']}/{item['ties']}/{item['r0_wins']}"
        )
    lines.append("")
    (args.out_dir / "strategy_routing_diagnostic.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

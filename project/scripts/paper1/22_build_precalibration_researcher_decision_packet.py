#!/usr/bin/env python3
"""Assemble the outcome-blind pre-calibration researcher decision packet."""

from __future__ import annotations

import json
from pathlib import Path

from metacom_pm.io import canonical_json, sha256_file, sha256_text

PROJECT = Path(__file__).resolve().parents[2]
MEMORY = PROJECT / "data/paper1_authority/paper1_precalibration_memory_candidate_audit_20260820_v1.json"
RS = PROJECT / "data/paper1_public_rs/esconv_rs_resource_amount_surface_20260820_v1.json"
ESC = PROJECT / "data/paper1_authority/paper1_esc_evaluator_qualification_plan_20260820_v1.json"
SPLITS = PROJECT / "data/paper1_authority/paper1_esc_split_feasibility_20260820_v1.json"
FOLDS = PROJECT / "data/paper1_authority/paper1_rq2_fold_feasibility_20260820_v1.json"
OUT_JSON = PROJECT / "data/paper1_authority/paper1_precalibration_final_researcher_decision_packet_20260820_v1.json"
OUT_MD = PROJECT / "docs/PM_PAPER1_PRECALIBRATION_FINAL_RESEARCHER_DECISION_PACKET_20260820_ZH.md"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def esc_rows(splits):
    rows = []
    for name, scenario in splits["scenarios"].items():
        rows.append(
            {
                "scenario": name,
                "calibration": scenario["calibration_cards"],
                "confirmatory": scenario["confirmatory_cards"],
                "calibration_source_counts": scenario["calibration_balance"]["source_counts"],
                "confirmatory_source_counts": scenario["confirmatory_balance"]["source_counts"],
                "calibration_category_counts": scenario["calibration_balance"]["category_counts"],
                "confirmatory_category_counts": scenario["confirmatory_balance"]["category_counts"],
                "calibration_max_source_fraction_gap": scenario["calibration_balance"][
                    "max_abs_source_fraction_gap_vs_population"
                ],
                "calibration_max_category_fraction_gap": scenario["calibration_balance"][
                    "max_abs_category_fraction_gap_vs_population"
                ],
                "confirmatory_max_source_fraction_gap": scenario["confirmatory_balance"][
                    "max_abs_source_fraction_gap_vs_population"
                ],
                "confirmatory_max_category_fraction_gap": scenario["confirmatory_balance"][
                    "max_abs_category_fraction_gap_vs_population"
                ],
                "non_esconv_primary_coverage": 173,
                "esconv_overlap_sensitivity_cards": 158,
            }
        )
    return rows


def fold_rows(folds):
    primary = folds["requested_primary_structure"]
    rows = list(primary["folds"])
    metrics = {
        key: {
            "min": min(row[key] for row in rows),
            "max": max(row[key] for row in rows),
            "range": max(row[key] for row in rows) - min(row[key] for row in rows),
            "max_over_mean": max(row[key] for row in rows)
            / (sum(row[key] for row in rows) / len(rows)),
        }
        for key in (
            "target_count",
            "owner_count",
            "qa_target_count",
            "summary_target_count",
            "dialogue_generation_target_count",
            "component_count",
        )
    }
    return rows, metrics


def main() -> int:
    memory, rs, esc, splits, folds = map(load, (MEMORY, RS, ESC, SPLITS, FOLDS))
    split_table = esc_rows(splits)
    fold_table, fold_imbalance = fold_rows(folds)
    packet = {
        "protocol": "pm-paper1-precalibration-final-researcher-decision-packet-v1",
        "date": "2026-08-20",
        "overall_decision": "NO_GO_TO_OPEN_CALIBRATION_OUTCOME_LOCK",
        "reason": (
            "engineering remains GO, but the fixed-seed semantic audit found formal MP/ME "
            "candidate failures and official ESC-RANK has not yet initialized on a qualifying GPU"
        ),
        "locks": {
            "CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
        },
        "current_activity": {
            "outcome_calls": 0,
            "pm_training_runs": 0,
            "formal_gpt4o_evaluation_runs": 0,
            "paid_api_calls_this_review": 0,
        },
        "A_memory_candidate_expansion_audit": memory,
        "B_rs_pure_k_protocol": {
            "catalog": rs["catalog"],
            "ranking": rs["ranking"],
            "cells": rs["cells"],
            "protocol": rs["pure_k_calibration_protocol"],
            "decision": "PROTOCOL_FROZEN; CALLS_BLOCKED_UNTIL_CANONICAL_CATALOG_RANKING_BACKFILLS_TOP4",
        },
        "C_exact_treatment_canonicalization": {
            "raw_atomic_units": rs["catalog"]["raw_atomic_move_units"],
            "exact_treatments": rs["catalog"]["exact_canonical_treatments"],
            "extra_alias_instances": rs["catalog"]["exact_duplicate_instances"],
            "mechanical_identity": "UTF-8 byte-exact rendered_card_text SHA-256 only",
            "provenance_union": "atomic_card_ids + source_card_ids + source_dialogue_ids + families",
            "ranking_prior_rule": (
                "one deterministic representative retrieval document and one BGE score per exact treatment; "
                "no duplicate max/mean score pooling and no occurrence-frequency prior"
            ),
            "representative_rule": "lexicographically smallest (source_card_id, atomic_card_id)",
            "leave_dialogue_out": "exclude if current dialogue appears anywhere in provenance union",
            "near_duplicate": "retain; no semantic-threshold deletion",
            "tests": [
                "exact identity collapses to one alias and unions provenance",
                "duplicate occurrence creates no extra ranking ticket",
                "near-identical text remains two treatments",
            ],
        },
        "D_esc_evaluator_final_feasibility": esc,
        "E_split_fold_human_readable": {
            "esc": {
                "population": splits["scenarios"]["small_24"]["population_balance"],
                "scenarios": split_table,
                "ratio_selected": False,
                "outcomes_read": False,
            },
            "rq2_k5_seed0": {
                "folds": fold_table,
                "imbalance": fold_imbalance,
                "leakage_checks": {
                    "all_targets_assigned_exactly_once": folds["requested_primary_structure"][
                        "all_targets_assigned_exactly_once"
                    ],
                    "all_exact_fact_event_components_atomic": folds["requested_primary_structure"][
                        "all_components_atomic"
                    ],
                    "missing_or_duplicate_targets": False,
                    "held_out_target_outcome_isolation": folds["rules"][
                        "confirmatory_target_outcome_isolation"
                    ],
                    "semantic_shared_session_grouping": folds["rules"][
                        "shared_session_semantic_components"
                    ],
                    "seed_shopping": folds["rules"]["seed_shopping"],
                },
            },
        },
        "researcher_decisions_closed": {
            "memory_counts": "descriptive counts accepted; formal semantic catalog not accepted",
            "rs_amount_grid": "pure-k {0,1,2,3,4}, fixed nonbinding cap 384, actual tokens separate",
            "rs_expansion": "only boundary-best non-plateau k4 triggers one expansion to {6,8}",
            "exact_treatment": "exact-only canonicalization with one ranking ticket and provenance union",
            "esc_evaluator": "official ESC-RANK remains reference/primary candidate; cloud qualification first",
            "splits_folds": "three ESC feasibility ratios remain unselected; RQ2 K5 seed0 retained without seed shopping",
        },
        "remaining_pre_unlock_actions": [
            "resolve and re-audit current MP/ME semantic candidate failures without changing ontology for quantity",
            "materialize canonical one-ticket-per-treatment BGE ranking with top-4 backfill",
            "run pinned ESC-RANK load/latency/reproducibility qualification on a rented >=24 GiB GPU",
            "researcher selects one ESC calibration split and approves a hard call/GPU budget",
        ],
        "source_artifacts": {
            path.relative_to(PROJECT).as_posix(): sha256_file(path)
            for path in (MEMORY, RS, ESC, SPLITS, FOLDS)
        },
    }
    OUT_JSON.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    task_lines = []
    for task, task_label in (("qa", "QA"), ("summary", "Summary"), ("dialogue_generation", "DG")):
        for head in ("MP", "MS", "ME"):
            row = memory["unified_per_task_counts"][task][head]
            task_lines.append(
                f"| {task_label} | {head} | {row['unique_active_semantic_units']} | {row['owners']} | "
                f"{row['target_candidate_edges']} | {row['targets_with_coverage']}/{row['targets_total']} |"
            )

    rs_lines = []
    for row in rs["cells"]:
        tokens = row["generator_input_tokens"]
        rs_lines.append(
            f"| {row['requested_k']} | {row['full_k_fraction']:.4f} | {tokens['median']} | "
            f"{tokens['p95']} | {tokens['max']} | {row['distinct_family_count']['median']} | "
            f"{row['states_with_selected_treatments_sharing_a_source_card_fraction']:.4f} |"
        )

    split_lines = []
    for row in split_table:
        split_lines.append(
            f"| {row['scenario']} | {row['calibration']} | {row['confirmatory']} | "
            f"{row['calibration_source_counts']} | {row['calibration_category_counts']} | "
            f"{row['calibration_max_source_fraction_gap']:.4f}/{row['calibration_max_category_fraction_gap']:.4f} | "
            f"173 | 158 |"
        )

    fold_lines = []
    for row in fold_table:
        fold_lines.append(
            f"| {row['outer_fold']} | {row['owner_count']} | {row['qa_target_count']} | "
            f"{row['summary_target_count']} | {row['dialogue_generation_target_count']} | "
            f"{row['component_count']} | {row['target_count']} |"
        )

    representative_examples = []
    for head in ("MP", "ME"):
        seen = set()
        for row in memory["fixed_seed_stratified_examples"][head]["examples"]:
            if row["stratum"] in seen:
                continue
            seen.add(row["stratum"])
            turns = " / ".join(
                f"`{turn['turn_id']}` ({turn['role']}): {turn['full_turn_text']} [exact: {turn['exact_supporting_span']}]"
                for turn in row["exact_source_turns"]
            )
            representative_examples.append(
                "\n".join(
                    [
                        f"- **{head}/{row['stratum']} — {row['memory_id']} — {row['precalibration_human_audit_verdict']}**",
                        f"  - source: `{row['owner_id']}/{row['source_session_id']}`, rank={row['source_session_rank']}, time={row['source_timestamp']}; strict-past `{row['source_session_rank']} < {row['strict_past_proof']['target_history_cutoff_rank']}`",
                        f"  - exact source turn: {turns}",
                        f"  - rendered: {row['rendered_candidate']}",
                        f"  - compiler: {row['compiler_rule']}; verifier: {row['compiler_verifier_factual_rationale']}",
                        f"  - audit reason: {row['precalibration_human_audit_reason']}",
                    ]
                )
            )

    runtime = esc["official_esc_rank_runtime_feasibility"]
    md = f"""# Paper-1 PRE-CALIBRATION FINAL REVIEW — Researcher Decision Packet（2026-08-20）

状态：**NO-GO TO OPEN `CALIBRATION_OUTCOME_LOCK`**
`CALIBRATION_OUTCOME_LOCK=CLOSED`；`CONFIRMATORY_OUTCOME_LOCK=CLOSED`；outcome calls=`0`；PM training=`0`；formal GPT-4o evaluation=`0`。

本结论不推翻 engineering GO。阻断来自两项 pre-calibration research qualification：当前 MP/ME semantic catalog 的固定种子人工审计出现明确错误；official ESC-RANK 尚未在可承载其 fp16 stack 的 GPU 上完成初始化、延迟和重复性 qualification。

## A. Memory candidate expansion audit

### A1. 3→378、401→1411、3→80 的精确原因

旧 `MP=3/MS=401/ME=3` 是 pre-semantic diagnostic：MP/ME 是极窄 regex，MS 是每个 source session 整段拼成一个 document，所以 401 sessions 恰好得到 401 MS。新口径在同一 401-session public runtime 上让 Qwen v6 提出 exact-span-grounded typed atomic units，经 local schema/grounding、semantic verifier、deterministic renderer 后得到 2,745 accepted units（MP 607/MS 1,997/ME 141）；outcome-blind version resolver 再停用 876 个旧版本（MP 229/MS 586/ME 61），留下 active `378/1411/80`。增长来自**构造器与原子粒度**，不是 ontology 扩张，也没有读取 `basic_info`。

### A2. 统一口径

`unique` 均指 full-history version resolution 后 active semantic units；edge 指 owner-matched unit 可供该 target 使用的一条 target×candidate edge。

| Task | Head | Unique units | Owners | Target-candidate edges | Target coverage |
|---|---:|---:|---:|---:|---:|
{chr(10).join(task_lines)}

三类任务都覆盖 18 owners，因此 unique pool 相同；edge 不同是各 task target 数与 owner 分布不同，不是重复候选被重新算成 unique。

### A3. 分层随机人工审计

固定规则：`SHA256('paper1-precalibration-seed0' | memory_id)`，MP 每 field type 取 2，ME 每 outcome type 最多取 5。完整 20 个 MP 与 12 个 ME（含每条 full exact source turn、offset、prior relations、verifier reason）在 machine packet 内。代表性每层一例如下：

{chr(10).join(representative_examples)}

固定样本判定：MP `PASS=10/FAIL=8/REVIEW=2`；ME `PASS=10/FAIL=2`。因此结构门通过不能替代语义门：例如 panic attack 同时占 action/outcome slots 在 schema 上合法，却没有 action→observed-result lineage。

### A4. 硬隔离证明

- 401/401 ordered sessions 的 `source_sha256` 全量重建一致；401/401 `prior_memory_table_sha256` 一致；strict-prior violations=`0`。
- 实际 request projection keys 只包含 session turn 与 strictly-past accepted-memory slots；forbidden key hits=`0`。
- `basic_info=0`、simulator-only metadata=`0`、gold=`0`、future session=`0`、target outcome=`0`。
- enclosing user 上虽存在 QA questions/summaries，但 401 个存档 request hash 证明它们没有进入 `SessionCompileInput`。prior ME 的 historical outcome 是已发生 source-dialogue fact，不是 target outcome。

**A 决策：structural lineage PASS；current semantic MP/ME catalog NO-GO for calibration。** 本轮不改 ontology/compiler，也不为数量 rescue；`378/80` 只能继续作为 descriptive current counts，不能称为已审计有效的 formal inventories。

## B. RS pure-k calibration protocol

旧 `(1,48)/(2,64)/(4,128)` 作废，因为同时改变 k 与 cap。冻结协议：initial `k={{0,1,2,3,4}}`，所有 arm 共用 non-binding resource cap=`384`，actual injected tokens 每 trajectory 单独记录，Step2 utility filter 继续禁止。

| k | Current prefix full-k fraction | Token median | Token p95 | Token max | Family median | Same-source-card fraction |
|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rs_lines)}

初始 grid 的 observed truncation=`0/11,883` at every k。表中 k>0 的少量 zero/full-k 缺口来自旧 raw top-4 prefix 先排序后 collapse exact aliases、无法 rank>4 backfill；因此这张 surface 只验证 cap，不授权 Generator call。正式调用前须在 canonical catalog 上重排并 backfill。

预注册 expansion：只有 `k=4` calibration mean 为最高，且 `k=3` 落在相对 k=4 的 one-SE admissible set 之外，才一次扩展 `k={{6,8}}`。扩展前先 materialize canonical top-8，并为所有 k 重审同一个 non-binding cap；不读 confirmatory outcome。

## C. Exact-treatment canonicalization

- 15,061 raw atomic units → 13,172 exact treatments；extra exact aliases=1,889。
- identity 仅为 UTF-8 byte-exact `rendered_card_text` SHA-256。
- union 完整保存 `atomic_card_ids/source_card_ids/source_dialogue_ids/families`；leave-dialogue-out 对 union 保守排除。
- 每个 treatment 只有一个 deterministic representative：最小 `(source_card_id, atomic_card_id)`，每 query 只产生一个 BGE score；禁止 duplicate max/mean pooling 或 occurrence-frequency prior。
- near duplicate 一律保留；没有 cosine/semantic threshold deletion。
- 三个机械回归覆盖 exact collapse+union、duplicate 不增加 ranking ticket、near duplicate 不删除。

**C 决策：规则关闭；当前 old top-4 census 尚须按该规则重排，不能直接用于 calibration。**

## D. ESC evaluator final feasibility

official ESC-RANK 是 reference/primary candidate；缺少公开 item-level human labels 不构成 ESC evaluation blocker，只限制 alternative judge agreement qualification。

| Check | Result |
|---|---|
| Pinned repo | `{runtime['tested_repo_commit']}` |
| Local GPU/RAM | RTX 2070 8,192 MiB；RAM 7.7 GiB |
| Actual `score.py` initialization | exit 1 after {runtime['actual_initialization_test']['elapsed_seconds']} s; max RSS {runtime['actual_initialization_test']['max_rss_kib']} KiB |
| Failure | `peft` absent，模型加载前失败；GPU allocation=0 |
| Capacity | InternLM2-chat-7B fp16 shards ≈15.49 GB，权重本身已超过 8 GiB |
| Official-code issue | first adapter path 写作 `ESC-RANK1/*`，与下载目录 `ESC-RANK/*` 不一致；需 pinned minimal correction |
| Latency/reproducibility | 本机无法测；不得伪填 |

**D 决策：不改用 alternative；租用 ≥24 GiB GPU 对 official ESC-RANK 做一次 pinned qualification。** 记录 load peak VRAM、cold/warm latency、seven-dimension vector latency、parse rate，并让至少 3 条 blind dialogue 重复两次得到 exact same vectors。只有 ESC-RANK 在该环境仍不实用，才由 researcher 提名 alternative。Qwen 永远只是 proxy，按 agreement/cost 与 ESC-RANK 比，禁止按 PM/Ours 得分选。

## E. Split/fold human-readable packet

### ESC non-ESConv English role cards

| Scenario | Calibration | Confirmatory | Calibration source counts | Calibration category counts | Max source/category fraction gap | Non-ESConv primary | ESConv overlap slice |
|---|---:|---:|---|---|---:|---:|---:|
{chr(10).join(split_lines)}

population=`173` non-ESConv cards（EPITOME 5/ExTES 70/MHP 73/Psych 25；家庭生活 95/工作学习 39/社会与其他 39）。三个 scenario 只用 metadata、seed=0；比例仍未选择。158 ESConv-source cards 始终是 overlap sensitivity slice，不进入 primary split。

### RQ2 K=5, seed=0

`component_count` 即 exact mechanical fact/event evidence clusters。

| Fold | Users | QA | Summary | DG | Fact/event clusters | Total targets |
|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(fold_lines)}

最大 range：users=1、QA=1、Summary=0、DG=2、clusters=3、total targets=1；最大 max/mean 分别为 1.0112/1.0021/1.0000/1.1765/1.0168/1.0025。1,586 targets exactly once，477 components atomic，无 missing/duplicate target；held-out target outcome isolation=true；semantic shared-session grouping 仅 sensitivity；seed shopping=FORBIDDEN。K=5 seed=0 保留。

## Researcher decision

1. **现在不得开启 calibration outcome lock。**
2. RS pure-k、exact canonicalization 和 split/fold 决策已关闭；尚需 canonical rerank 的工程物化。
3. Memory 当前计数解释成立，但 MP/ME formal semantic validity 未通过这次 sample audit；先处理该问题，再做 calibration。
4. ESC-RANK 保持 official reference/primary；先租 ≥24 GiB GPU qualification，不先烧 Qwen proxy。
5. 全程 outcome calls=`0`、PM training=`0`、formal GPT-4o=`0`。

机器包：`project/data/paper1_authority/paper1_precalibration_final_researcher_decision_packet_20260820_v1.json`
Memory 全例审计：`project/data/paper1_authority/paper1_precalibration_memory_candidate_audit_20260820_v1.json`
"""
    OUT_MD.write_text(md, encoding="utf-8")
    print(
        json.dumps(
            {
                "json": OUT_JSON.relative_to(PROJECT.parent).as_posix(),
                "markdown": OUT_MD.relative_to(PROJECT.parent).as_posix(),
                "packet_sha256": sha256_text(canonical_json(packet)),
                "outcome_calls": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

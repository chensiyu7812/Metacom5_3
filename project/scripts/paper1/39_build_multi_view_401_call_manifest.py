#!/usr/bin/env python3
"""Build the active 401-session compiler manifest without API calls."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

import yaml
from transformers import AutoTokenizer


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory.contracts import (
    ExtractorSessionOutput,
    VerifierSessionOutput,
)
from metacom_pm.paper1.multi_view_memory.grounding import source_sha256
from metacom_pm.paper1.multi_view_memory.input_projection import build_session_input
from metacom_pm.paper1.multi_view_memory.prompts import (
    MULTI_VIEW_EXTRACTOR_PROMPT_SHA256,
    MULTI_VIEW_VERIFIER_PROMPT_SHA256,
    extractor_messages,
    verifier_messages,
)
from metacom_pm.paper1.multi_view_memory.runtime import (
    EXTRACTOR_SCHEMA_SHA256,
    MULTI_VIEW_COMPILER_STAGE,
    MULTI_VIEW_COMPILER_VERSION,
    VERIFIER_SCHEMA_SHA256,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT / "configs" / "paper1_multi_view_compiler_v1.yaml",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=(
            PROJECT
            / "data"
            / "paper1_public_memory"
            / "es_memeval_public_sanitized_runtime_artifact_v1.json"
        ),
    )
    parser.add_argument("--tokenizer-dir", type=Path, required=True)
    parser.add_argument("--rows-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    return parser.parse_args()


def _token_count(tokenizer, messages: list[dict[str, str]]) -> int:
    return len(
        tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
        )
    )


def main() -> int:
    args = _args()
    config_path = args.config.resolve()
    source_path = args.source.resolve()
    tokenizer_dir = args.tokenizer_dir.resolve()
    rows_path = args.rows_out.resolve()
    summary_path = args.summary_out.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    limits = config["limits"]
    price = config["price_snapshot"]
    serializable_price = {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in price.items()
    }
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir, local_files_only=True)
    tokenizer_files = {
        name: sha256_file(tokenizer_dir / name)
        for name in ("tokenizer.json", "tokenizer_config.json", "config.json")
        if (tokenizer_dir / name).exists()
    }
    if len(tokenizer_files) < 2:
        raise RuntimeError("pinned tokenizer files are incomplete")

    users = load_sanitized_runtime_users(source_path)
    ordered = [
        (user, session)
        for user in sorted(users, key=lambda row: row.owner_id)
        for session in sorted(user.sessions, key=lambda row: (row.timestamp, row.session_id))
    ]
    if len(ordered) != 401:
        raise RuntimeError(f"expected 401 public sessions, found {len(ordered)}")

    input_price = Decimal(str(price["input_usd_per_million_tokens"]))
    output_price = Decimal(str(price["output_usd_per_million_tokens"]))
    million = Decimal(1_000_000)
    rows: list[dict[str, object]] = []
    for sequence, (user, session) in enumerate(ordered):
        source = build_session_input(owner_id=user.owner_id, session=session)
        source_json = canonical_json(source.model_dump(mode="json"))
        extractor_base = _token_count(
            tokenizer,
            extractor_messages(
                source_json,
                canonical_json(ExtractorSessionOutput.model_json_schema()),
            ),
        )
        verifier_empty_base = _token_count(
            tokenizer,
            verifier_messages(
                source_json,
                "{}",
                canonical_json(VerifierSessionOutput.model_json_schema()),
            ),
        )
        profile = int(limits["prior_current_profile_allowance_tokens_per_call"])
        margin = int(limits["prompt_token_safety_margin_per_call"])
        proposal = int(limits["verifier_proposal_allowance_tokens"])
        extractor_input_max = extractor_base + profile + margin
        verifier_input_max = verifier_empty_base + profile + proposal + margin
        per_call_prompt_limit = int(limits["maximum_prompt_tokens_per_call"])
        if max(extractor_input_max, verifier_input_max) > per_call_prompt_limit:
            raise RuntimeError(
                f"session {session.session_id} exceeds the frozen per-call prompt limit"
            )
        input_tokens = extractor_input_max + verifier_input_max
        output_tokens = int(limits["extractor_max_output_tokens"]) + int(
            limits["verifier_max_output_tokens"]
        )
        maximum_cost = (
            Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price
        ) / million
        rows.append(
            {
                "protocol": "paper1-multi-view-401-call-manifest-row-v1",
                "sequence": sequence,
                "owner_id": user.owner_id,
                "session_id": session.session_id,
                "source_sha256": source_sha256(source),
                "turn_count": len(session.turns),
                "extractor_base_prompt_tokens": extractor_base,
                "extractor_reserved_prompt_tokens": extractor_input_max,
                "extractor_max_output_tokens": int(limits["extractor_max_output_tokens"]),
                "verifier_empty_base_prompt_tokens": verifier_empty_base,
                "verifier_reserved_prompt_tokens": verifier_input_max,
                "verifier_max_output_tokens": int(limits["verifier_max_output_tokens"]),
                "maximum_two_call_cost_usd": str(maximum_cost),
                "outcome_fields_read": False,
            }
        )

    rendered = "".join(canonical_json(row) + "\n" for row in rows)
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    rows_path.write_text(rendered, encoding="utf-8")
    maximum_cost = sum(Decimal(str(row["maximum_two_call_cost_usd"])) for row in rows)
    stage_cap = Decimal(str(config["budget"]["stage_hard_cap_usd"]))
    summary = {
        "protocol": "paper1-multi-view-401-call-manifest-preflight-v1",
        "status": "PASS_ZERO_OUTCOME_PREFLIGHT" if maximum_cost <= stage_cap else "FAIL_BUDGET",
        "compiler_version": MULTI_VIEW_COMPILER_VERSION,
        "stage": MULTI_VIEW_COMPILER_STAGE,
        "source": {
            "path": str(source_path.relative_to(PROJECT)),
            "sha256": sha256_file(source_path),
            "users": len(users),
            "sessions": len(rows),
            "turns": sum(int(row["turn_count"]) for row in rows),
        },
        "runtime_identity": {
            "provider": config["endpoint"]["provider"],
            "region": config["endpoint"]["region"],
            "model": config["endpoint"]["model"],
            "enable_thinking": config["endpoint"]["enable_thinking"],
            "temperature": config["endpoint"]["temperature"],
            "seed": config["endpoint"]["seed"],
            "tokenizer_repo_id": config["tokenizer"]["repo_id"],
            "tokenizer_revision": config["tokenizer"]["revision"],
            "tokenizer_file_sha256": tokenizer_files,
            "extractor_prompt_sha256": MULTI_VIEW_EXTRACTOR_PROMPT_SHA256,
            "verifier_prompt_sha256": MULTI_VIEW_VERIFIER_PROMPT_SHA256,
            "extractor_schema_sha256": EXTRACTOR_SCHEMA_SHA256,
            "verifier_schema_sha256": VERIFIER_SCHEMA_SHA256,
        },
        "limits": limits,
        "pricing": serializable_price,
        "budget": {
            "maximum_provider_calls": len(rows) * 2,
            "verifier_calls_skipped_when_no_grounded_proposals": True,
            "aggregate_reserved_input_tokens": sum(
                int(row["extractor_reserved_prompt_tokens"])
                + int(row["verifier_reserved_prompt_tokens"])
                for row in rows
            ),
            "aggregate_reserved_output_tokens": sum(
                int(row["extractor_max_output_tokens"])
                + int(row["verifier_max_output_tokens"])
                for row in rows
            ),
            "aggregate_maximum_cost_usd": str(maximum_cost),
            "stage_hard_cap_usd": str(stage_cap),
            "headroom_usd": str(stage_cap - maximum_cost),
        },
        "manifest": {
            "path": str(rows_path.relative_to(PROJECT)),
            "sha256": sha256_text(rendered),
            "rows": len(rows),
        },
        "method_boundary": {
            "prior_profile_allowance_is_per_call_not_observed_output": True,
            "verifier_proposal_allowance_equals_extractor_max_output_tokens": (
                int(limits["verifier_proposal_allowance_tokens"])
                == int(limits["extractor_max_output_tokens"])
            ),
            "formal_outcomes_read": 0,
            "paid_api_calls": 0,
            "pm_training_runs": 0,
            "all_outcome_locks": "CLOSED",
        },
    }
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS_ZERO_OUTCOME_PREFLIGHT" else 1


if __name__ == "__main__":
    raise SystemExit(main())

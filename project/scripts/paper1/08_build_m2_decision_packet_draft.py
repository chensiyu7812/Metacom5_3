#!/usr/bin/env python3
"""Build the zero-outcome M2 decision packet and portable-report payload."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[2]
RS_SUMMARY = PROJECT / "data/paper1_public_rs/esconv_rs_zero_outcome_census_summary_v1.json"
RS_RETRIEVER_AUDIT = (
    PROJECT / "data/paper1_public_rs/esconv_rs_retriever_comparison_summary_v1.json"
)
RS_FAMILY_AUDIT = (
    PROJECT / "data/paper1_evaluator_only_rs/esconv_rs_strategy_family_match_summary_v1.json"
)
RS_RENDER_AUDIT = (
    PROJECT / "data/paper1_public_rs/esconv_rs_renderer_boundary_audit_v1.json"
)
RECONCILIATION = (
    PROJECT / "data/paper1_authority/paper1_execution_reconciliation_20260816_v1.json"
)
SCORER_AUDIT = PROJECT / "data/paper1_authority/paper1_official_scorer_surface_audit_v1.json"
RQ0_CONTRACT = PROJECT / "data/v3_authority/rq0_llama31_8b_esc_eval_exact_contract_v1.json"
PREOUTCOME_DRAFT = PROJECT / "data/paper1_authority/paper1_pre_outcome_freeze_draft_v1.json"
ENVIRONMENT_ATTESTATION = (
    PROJECT / "data/paper1_authority/paper1_local_environment_attestation_v1.json"
)
OFFICIAL_RAG_RUNTIME_ATTESTATION = (
    PROJECT / "data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json"
)
MEMORY_CENSUS = (
    PROJECT / "data/paper1_public_memory/es_memeval_public_candidate_census_summary_v1.json"
)
MEMORY_FEATURE_READINESS = (
    PROJECT / "data/paper1_public_memory/es_memeval_public_feature_readiness_audit_v1.json"
)
MEMORY_FOLDS = (
    PROJECT / "data/paper1_public_memory/es_memeval_public_folds_build_report_v1.json"
)
OFFICIAL_VISIBILITY = (
    PROJECT / "data/paper1_public_memory/es_memeval_public_official_visibility_audit_v1.json"
)
PACKET_OUT = PROJECT / "data/paper1_authority/paper1_m2_decision_packet_draft_v1.json"
REPORT_DIR = PROJECT / "reports/paper1_m2_decision_packet_draft_20260816"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decision(
    order: int,
    decision_id: str,
    item: str,
    evidence: str,
    recommendation: str,
    status: str,
    approval: bool,
) -> dict:
    return {
        "order": order,
        "decision_id": decision_id,
        "item": item,
        "evidence": evidence,
        "recommendation": recommendation,
        "status": status,
        "researcher_approval_required": approval,
    }


def main() -> int:
    rs = _load(RS_SUMMARY)
    rs_retriever = _load(RS_RETRIEVER_AUDIT)
    rs_family = _load(RS_FAMILY_AUDIT)
    rs_render = _load(RS_RENDER_AUDIT)
    reconciliation = _load(RECONCILIATION)
    scorer = _load(SCORER_AUDIT)
    rq0 = _load(RQ0_CONTRACT)
    preoutcome = _load(PREOUTCOME_DRAFT)
    environment = _load(ENVIRONMENT_ATTESTATION)
    official_rag_runtime = _load(OFFICIAL_RAG_RUNTIME_ATTESTATION)
    memory_census = _load(MEMORY_CENSUS)
    memory_features = _load(MEMORY_FEATURE_READINESS)
    memory_folds = _load(MEMORY_FOLDS)
    official_visibility = _load(OFFICIAL_VISIBILITY)
    if memory_census.get("candidate_source") != "accepted_semantic_memory_v6":
        raise RuntimeError(
            "M2 packet requires a complete v6 semantic-memory census; "
            "legacy regex/string census is diagnostic only"
        )
    if not isinstance(memory_census.get("semantic_compiler_source"), dict):
        raise RuntimeError("memory census is missing semantic compiler identity")
    if not isinstance(memory_features.get("semantic_compiler_source"), dict):
        raise RuntimeError("memory readiness report is missing semantic compiler identity")
    if (
        memory_census["semantic_compiler_source"].get("sha256")
        != memory_features["semantic_compiler_source"].get("artifact_sha256")
    ):
        raise RuntimeError("memory census/readiness compiler artifact mismatch")
    generated_at = datetime.now(ZoneInfo("Asia/Tokyo")).replace(microsecond=0).isoformat()

    conservative = rs["overlap_policy_sensitivity"]["conservative_existing_project_flag"]
    literal = rs["overlap_policy_sensitivity"][
        "authority_literal_esconv_train_bank_train_dev_states"
    ]
    counts = rs["counts"]
    situation = rs["privileged_field_audit"]["situation"]
    bundle = rs["outcome_blind_distributions"]["diagnostic_bundle_injected_words"]
    rendered = rs_render["renderer_variants"]
    exemplar = rs_render["exemplar_content_shape_proxies"]
    boundary = rs_render["boundary_horizon_decision_surface"]
    retriever_pairwise = rs_retriever["diagnostics"]["pairwise_method_agreement"]
    heldout_family = {
        method: values["by_effect_state_split"]["validation"]
        for method, values in rs_family["methods"].items()
    }
    memory_heads = memory_census["per_head"]

    decisions = [
        _decision(
            1,
            "rs_visible_source",
            "RS source visibility",
            "The prior v1 catalog used ESConv situation text; 1,255/1,300 situations are not verbatim present anywhere in dialogue.",
            "Adopt dialogue-only v2 identities and permanently forbid situation/outcome/questionnaire fields in active RS catalog/state code.",
            "IMPLEMENTED_AWAITING_INTEGRATION",
            False,
        ),
        _decision(
            2,
            "rs_overlap_policy",
            "Legacy EvoEmo-overlap exclusion",
            f"Legacy-conservative universe: {conservative['strategy_source_cards']} cards/{conservative['decision_states']} states; authority-literal ESConv train + train/dev: {literal['strategy_source_cards']} cards/{literal['decision_states']} states.",
            "Use the authority-literal ESConv train Bank and train/dev effect states. Treat the old EvoEmo flag as a disclosed sensitivity, because RS is fixed across RQ2 memory arms and the highest program does not require this exclusion.",
            "RESEARCHER_DECISION_REQUIRED",
            True,
        ),
        _decision(
            3,
            "rs_state_grain",
            "RS decision-state grain",
            f"{counts['decision_states']} non-overlap states were reconstructed as one supporter run after at least one visible seeker turn; initial greetings and consecutive supporter fragments are not separate PM calls.",
            "Freeze this response-opportunity grain; query/state must stop before the target supporter response and future turns.",
            "RECOMMENDED_FOR_FREEZE",
            True,
        ),
        _decision(
            4,
            "rs_candidate_bundle",
            "RS candidate bundle",
            f"Diagnostic injected-word medians are {bundle['1']['median']} for k=1, {bundle['2']['median']} for k=2 and {bundle['4']['median']} for k=4; all states have leave-dialogue-out candidates.",
            "Freeze one retrieved card (Top-1) as the exact RS treatment. This preserves a single interpretable candidate identity and avoids learning the value of an internally heterogeneous bundle.",
            "RESEARCHER_DECISION_REQUIRED",
            True,
        ),
        _decision(
            5,
            "rs_retriever",
            "RS semantic retriever",
            f"A full zero-outcome surface compared lexical Jaccard, BGE-small and BGE-M3 over {rs_retriever['universe']['decision_state_count']} visible-prefix states with leave-current-dialogue-out. Top-1 card agreement is {retriever_pairwise['lexical_jaccard__vs__bge_small']['top1_same_card_rate']:.2%} for lexical/small, {retriever_pairwise['lexical_jaccard__vs__bge_m3']['top1_same_card_rate']:.2%} for lexical/M3 and {retriever_pairwise['bge_small__vs__bge_m3']['top1_same_card_rate']:.2%} for small/M3. On the held-out ESConv validation diagnostic, Top-1 family match is lexical {heldout_family['lexical_jaccard']['strategy_family_match_at_1']:.2%}, small {heldout_family['bge_small']['strategy_family_match_at_1']:.2%}, M3 {heldout_family['bge_m3']['strategy_family_match_at_1']:.2%}; Top-3 is lexical {heldout_family['lexical_jaccard']['strategy_family_match_at_3']:.2%}, small {heldout_family['bge_small']['strategy_family_match_at_3']:.2%}, M3 {heldout_family['bge_m3']['strategy_family_match_at_3']:.2%}. No method dominates both cutoffs. Family match is evaluator-only coarse strategy agreement, not applicability, RS ON/OFF gold, or Generator outcome. ES-MemEval's pinned official code names BAAI/bge-m3 for FAISS session-level Top-4 but does not pin a Hub revision.",
            "Keep BGE-small only as an RS lightweight challenger/smoke-test and BGE-M3 as the official-RAG identity/leading typed-memory candidate. For RS Top-1, the remaining researcher choice is principally transparent lexical simplicity versus M3 stack unification/semantic representation; the held-out family diagnostic does not establish a decisive winner. Freeze one encoder, revision, pooling, normalization, query construction and leave-current-dialogue-out index before effect calls. Do not infer utility from family match, score magnitude or model size.",
            "ZERO_OUTCOME_BEHAVIOR_AND_FAMILY_DIAGNOSTICS_COMPLETE_RESEARCH_FREEZE_PENDING",
            True,
        ),
        _decision(
            6,
            "rs_render_and_cap",
            "RS rendering and resource token cap",
            f"The dedicated Python 3.11 runtime hash-verified tokenizer bytes for {environment['llama_tokenizer_candidate']['repo']} at revision {environment['llama_tokenizer_candidate']['revision']}. Those bytes give guidance-only median {rendered['guidance_only']['resource_token_distribution']['median']} tokens; guidance+exemplar median {rendered['guidance_plus_exemplar']['resource_token_distribution']['median']}, p95 {rendered['guidance_plus_exemplar']['resource_token_distribution']['p95']} and max {rendered['guidance_plus_exemplar']['resource_token_distribution']['max']}. A 192-token cap contains {rendered['guidance_plus_exemplar']['cap_coverage']['192']['coverage_fraction']:.2%} of cards. NVIDIA NIM provider parity remains unverified.",
            "Freeze the exact renderer variant before outcomes. If exemplar is retained, use the explicit other-dialogue/style-only delimiter and preserve guidance before exemplar under truncation. Verify tokenizer parity with the NVIDIA NIM stack before freezing the cap.",
            "CENSUS_COMPLETE_PROVIDER_PARITY_AND_VARIANT_PENDING",
            True,
        ),
        _decision(
            7,
            "rs_exemplar_policy",
            "RS example-response treatment policy",
            f"Among {exemplar['cards_total']} cards, guidance-only collapses to {rendered['guidance_only']['distinct_render_count']} distinct resource strings, while guidance+exemplar retains {rendered['guidance_plus_exemplar']['distinct_render_count']}. The source exemplar has first-person references in {exemplar['card_counts']['first_person_reference']}, kinship terms in {exemplar['card_counts']['kinship_reference']}, time/number references in {exemplar['card_counts']['time_or_number_reference']} and non-initial capitalized-token proxies in {exemplar['card_counts']['capitalized_token_reference']}. These are descriptive text-shape proxies, not risk labels.",
            "Choose once between guidance-only and guidance+exemplar. Guidance-only is an eight-move strategy prompt rather than card-specific RAG; guidance+exemplar preserves card identity and is therefore the closer Strategy-RAG treatment. Any copying, factual carryover, misuse or semantic non-use after valid delivery remains a realized treatment effect and error-analysis signal, never a post-treatment invalidation rule.",
            "RESEARCHER_DECISION_REQUIRED",
            True,
        ),
        _decision(
            8,
            "rs_boundary_horizon",
            "Explicit user-boundary horizon and strategy mapping",
            f"Current-user-run parsing activates a boundary in {boundary['current_user_run_only']['states_with_any_explicit_boundary']} of {rs_render['universe']['decision_states']} states; prefix persistence activates one in {boundary['visible_prefix_narrow_explicit_revocation']['states_with_any_explicit_boundary']}. No audited state loses every compatible candidate.",
            "Apply boundaries identically to every arm at candidate level: listen-only blocks Suggestions and Question, no-advice blocks Suggestions, and no-probing blocks Question. Freeze either current-run-only or narrow explicit persistence; never turn the sparse flags into learned features or close the whole RS head.",
            "RESEARCHER_DECISION_REQUIRED",
            True,
        ),
        _decision(
            9,
            "rs_feature_schema",
            "RS observable features",
            f"Advice-request appears in 308 states in the original request-feature census. The stricter current-run boundary audit finds listen-only in {boundary['current_user_run_only']['active_marker_state_counts']['listen_only']}, no-advice in {boundary['current_user_run_only']['active_marker_state_counts']['no_advice']} and no-probing in {boundary['current_user_run_only']['active_marker_state_counts']['no_probing']} states; the former single no-probing hit referred to what third parties might ask and was a false positive.",
            "Retain similarity, candidate move type, recent previously-injected same-move count, advice-request flag and exact resource-token count. Keep listen-only/no-probing as deterministic boundary rules, not learned features.",
            "RESEARCHER_DECISION_REQUIRED",
            True,
        ),
        _decision(
            10,
            "memory_census",
            "MP/MS/ME candidate census",
            f"The integrated gold-free runtime has {memory_census['targets_total']} targets. Verified semantic candidates are MP {memory_heads['MP']['unique_candidate_count']} unique/{memory_heads['MP']['owners_with_any_candidate']} owners, MS {memory_heads['MS']['unique_candidate_count']}/{memory_heads['MS']['owners_with_any_candidate']}, and ME {memory_heads['ME']['unique_candidate_count']}/{memory_heads['ME']['owners_with_any_candidate']}; all reports retain outcome_calls=0 and bind one complete compiler artifact.",
            "Use only schema-valid, deterministically grounded, verifier-accepted v6 semantic MP/MS/ME units. Keep all regex/string constructors and B30 stable-kinship patterns diagnostic-only.",
            "SEMANTIC_MEMORY_V6_COMPLETE_ARTIFACT_BOUND",
            False,
        ),
        _decision(
            11,
            "outer_folds",
            "Outer-fold K and seed",
            f"The integrated evaluator-side grouping contains {memory_folds['group_components_total']} exact-evidence components over {memory_folds['targets_total']} targets. The zero-outcome surface verified K=2..10 without selecting a winner.",
            "Materialize K=5, seed=0 exactly once. This is a pre-registered conventional split, not a winner chosen from outcomes or a structural PASS gate; group-component IDs remain distinct from outer-fold IDs.",
            "K5_SEED0_PRE_REGISTERED_MATERIALIZATION_PENDING_COMPILER_HASH_BINDING",
            False,
        ),
        _decision(
            12,
            "official_rag_runtime",
            "ES-MemEval Official RAG baseline runtime",
            f"The official-library probe loaded {official_rag_runtime['official_source_binding']['model_id']} through HuggingFaceEmbeddings, built a {official_rag_runtime['runtime']['probe']['faiss_index_class']} over session-level Documents, and returned deterministic Top-{official_rag_runtime['runtime']['probe']['top_k']} on CUDA. It made {official_rag_runtime['outcome_calls']} outcome calls. The pinned ES-MemEval source names the model but does not pin a Hub revision, so equivalence between the local PR-130 safetensors snapshot and an upstream main weight snapshot is not established.",
            "Use this environment only for the Official RAG comparison arm. Before formal runs, bind the commit-addressed local BGE-M3 revision with the upstream-unpinned limitation and bind the task-specific official prompt/truncation wrappers. Do not infer MP/MS/ME or RS retriever choices from baseline reproducibility.",
            "ENGINEERING_RUNTIME_ATTESTED_REVISION_AND_TASK_WRAPPERS_PENDING",
            True,
        ),
        _decision(
            13,
            "effect_coding",
            "Multi-metric effect coding",
            "Official repositories emit metric vectors and do not define a paired direction. The implemented exact Pareto overlay is explicitly still a project draft.",
            "Prefer authority-aligned task anchors: QA LLM-as-Judge primary with F1/BERTScore auxiliaries; Summary Event-F1 primary with official LLM guard and ROUGE explanatory; DG Weighted Score primary with Observation Recall and three official ratings as guards. Freeze exact tie/conflict logic before calls and retain every raw official metric.",
            "RESEARCHER_DECISION_REQUIRED",
            True,
        ),
        _decision(
            14,
            "generator_stack",
            "Generator and decoding stack",
            "RQ0 selected meta/llama-3.1-8b-instruct on NVIDIA NIM with supporter prompt 'You are a helpful assistant!', temperature 0 and max output tokens 256; provider seed was null.",
            "Carry the RQ0 Generator identity, prompt, temperature=0 and max output tokens=256 into Paper 1, adding only a hash-bound typed resource block and treatment-delivery trace.",
            "PROMPT_AND_EXECUTOR_BINDING_PENDING",
            True,
        ),
        _decision(
            15,
            "repeated_effects",
            "Repeated paired effects",
            "The authority retains repeated soft/binomial supervision, while the frozen RQ0 decoding is temperature=0 with no provider seed.",
            "Use three matched repeat IDs only if they produce independently executed generation/scoring traces; byte-identical duplicate generations must not be counted as independent ON wins. Do not convert three repeats into a 2-of-3 PASS label.",
            "IMPLEMENTATION_BLOCKER_REPRODUCIBILITY_RULE_REQUIRED",
            True,
        ),
        _decision(
            16,
            "primary_policy",
            "PM decision threshold",
            "Highest reconciliation already fixes eligible plus predicted positive-effect probability > 0.5; this is not a paper PASS threshold.",
            "Keep 0.5 unchanged. Report Brier/log-loss/calibration diagnostics without calibration PASS gates.",
            "ALREADY_FROZEN_BY_AUTHORITY",
            False,
        ),
        _decision(
            17,
            "matched_random",
            "Matched-Random construction",
            "The current implementation exactly matches ON count by pre-frozen stratum and fails closed when injected-token budget cannot be matched.",
            "Freeze strata before outcomes, use a seed derived from the reviewed freeze-manifest hash, and use fixed padded resource caps so Learned and Random match realized ON count and token budget.",
            "SEED_AND_STRATA_PENDING",
            True,
        ),
        _decision(
            18,
            "formal_unlock",
            "Outcome/API unlock",
            "RS is audited but repaired memory artifacts, folds, scorer identities, prompts, seeds, matched-random schedule and call counts remain incomplete.",
            "Keep formal outcome/training/benchmark access locked. Materialize the API call plan only after the combined M2 manifest validates with no pending scientific fields.",
            "LOCKED",
            False,
        ),
    ]

    packet = {
        "protocol": "pm-paper1-m2-decision-packet-draft-v1",
        "status": "PRE_OUTCOME_DECISION_DRAFT_NOT_A_FREEZE_NOT_AN_UNLOCK",
        "generated_at": generated_at,
        "authority": {
            "reconciliation_protocol": reconciliation.get("protocol"),
            "route": "A_first_order_factorized",
            "official_benchmark_first": True,
            "cost_separate": True,
            "empirical_pass_gates": False,
        },
        "evidence": {
            "rs_zero_outcome_summary": {
                "path": str(RS_SUMMARY.relative_to(PROJECT)),
                "sha256": _sha256(RS_SUMMARY),
            },
            "rs_retriever_comparison": {
                "path": str(RS_RETRIEVER_AUDIT.relative_to(PROJECT)),
                "sha256": _sha256(RS_RETRIEVER_AUDIT),
                "status": rs_retriever.get("status"),
                "winner_selected": rs_retriever["scientific_scope"]["winner_selected"],
                "formal_outcome_calls": rs_retriever["scientific_scope"]["formal_outcome_calls"],
            },
            "rs_strategy_family_evaluator_diagnostic": {
                "path": str(RS_FAMILY_AUDIT.relative_to(PROJECT)),
                "sha256": _sha256(RS_FAMILY_AUDIT),
                "status": rs_family.get("status"),
                "evaluator_only": rs_family["scope"]["evaluator_only"],
                "winner_selected": rs_family["scope"]["winner_selected"],
                "formal_outcome_calls": rs_family["scope"]["formal_outcome_calls"],
            },
            "rs_renderer_boundary_audit": {
                "path": str(RS_RENDER_AUDIT.relative_to(PROJECT)),
                "sha256": _sha256(RS_RENDER_AUDIT),
                "status": rs_render.get("status"),
                "tokenizer": rs_render.get("tokenizer"),
            },
            "official_scorer_audit": {
                "path": str(SCORER_AUDIT.relative_to(PROJECT)),
                "sha256": _sha256(SCORER_AUDIT),
                "status": scorer.get("status"),
            },
            "rq0_contract": {
                "path": str(RQ0_CONTRACT.relative_to(PROJECT)),
                "sha256": _sha256(RQ0_CONTRACT),
            },
            "preoutcome_draft": {
                "path": str(PREOUTCOME_DRAFT.relative_to(PROJECT)),
                "sha256": _sha256(PREOUTCOME_DRAFT),
                "status": preoutcome.get("status"),
            },
            "local_environment_attestation": {
                "path": str(ENVIRONMENT_ATTESTATION.relative_to(PROJECT)),
                "sha256": _sha256(ENVIRONMENT_ATTESTATION),
                "status": environment.get("status"),
                "outcome_calls": environment.get("outcome_calls"),
                "tokenizer_provider_parity": environment[
                    "llama_tokenizer_candidate"
                ]["nvidia_nim_provider_parity"],
                "retriever_candidate_role": environment[
                    "bge_small_encoder_candidate"
                ]["role"],
                "retriever_candidate_roles": {
                    "bge_small": environment["bge_small_encoder_candidate"]["role"],
                    "bge_m3": environment["bge_m3_encoder_candidate"]["role"],
                },
                "official_rag_model_id": environment["bge_m3_encoder_candidate"][
                    "official_es_memeval_binding"
                ]["model_id"],
                "official_rag_local_revision_parity": environment[
                    "bge_m3_encoder_candidate"
                ]["official_es_memeval_binding"]["local_revision_parity_status"],
            },
            "official_rag_runtime_attestation": {
                "path": str(OFFICIAL_RAG_RUNTIME_ATTESTATION.relative_to(PROJECT)),
                "sha256": _sha256(OFFICIAL_RAG_RUNTIME_ATTESTATION),
                "status": official_rag_runtime.get("status"),
                "outcome_calls": official_rag_runtime.get("outcome_calls"),
                "official_arm_only": official_rag_runtime["scope"]["arm"],
                "typed_memory_method_changed": official_rag_runtime["scope"][
                    "typed_memory_method_changed"
                ],
                "rs_retriever_selected": official_rag_runtime["scope"][
                    "rs_retriever_selected"
                ],
                "local_revision_status": official_rag_runtime[
                    "local_model_binding"
                ]["revision_status"],
            },
            "memory_candidate_census": {
                "path": str(MEMORY_CENSUS.relative_to(PROJECT)),
                "sha256": _sha256(MEMORY_CENSUS),
                "outcome_calls": memory_census.get("outcome_calls"),
                "targets_total": memory_census.get("targets_total"),
                "per_head": memory_heads,
            },
            "memory_feature_readiness": {
                "path": str(MEMORY_FEATURE_READINESS.relative_to(PROJECT)),
                "sha256": _sha256(MEMORY_FEATURE_READINESS),
                "status": memory_features.get("status"),
                "outcome_calls": memory_features.get("outcome_calls"),
            },
            "memory_exact_evidence_components": {
                "path": str(MEMORY_FOLDS.relative_to(PROJECT)),
                "sha256": _sha256(MEMORY_FOLDS),
                "group_components_total": memory_folds.get(
                    "group_components_total"
                ),
                "outer_fold_packing_status": memory_folds.get(
                    "outer_fold_packing_status"
                ),
                "outcome_calls": memory_folds.get("outcome_calls"),
            },
            "official_rq2_visibility": {
                "path": str(OFFICIAL_VISIBILITY.relative_to(PROJECT)),
                "sha256": _sha256(OFFICIAL_VISIBILITY),
                "status": official_visibility.get("status"),
                "audited_source_file_count": official_visibility.get(
                    "audited_source_file_count"
                ),
                "task_arm_surface_row_count": official_visibility.get(
                    "task_arm_surface_row_count"
                ),
                "outcome_calls": official_visibility.get("outcome_calls"),
            },
        },
        "rs_findings": {
            "dialogue_only_cards": counts["strategy_source_cards"],
            "cards_removed_vs_situation_conditioned_v1": 12403
            - counts["strategy_source_cards"],
            "decision_states": counts["decision_states"],
            "leave_dialogue_out_candidate_coverage": counts[
                "states_with_leave_dialogue_out_candidates"
            ]
            / counts["decision_states"],
            "nonzero_lexical_overlap_coverage": counts[
                "states_with_nonzero_lexical_overlap"
            ]
            / counts["decision_states"],
            "nonverbatim_situation_rate": situation[
                "situation_not_verbatim_contained_anywhere_in_dialogue"
            ]
            / situation["dialogues_with_nonempty_situation"],
            "guidance_plus_exemplar_median_tokens": rendered[
                "guidance_plus_exemplar"
            ]["resource_token_distribution"]["median"],
            "guidance_only_distinct_renders": rendered["guidance_only"][
                "distinct_render_count"
            ],
            "guidance_plus_exemplar_distinct_renders": rendered[
                "guidance_plus_exemplar"
            ]["distinct_render_count"],
            "guidance_plus_exemplar_p95_tokens": rendered[
                "guidance_plus_exemplar"
            ]["resource_token_distribution"]["p95"],
            "guidance_plus_exemplar_192_cap_coverage": rendered[
                "guidance_plus_exemplar"
            ]["cap_coverage"]["192"]["coverage_fraction"],
            "boundary_current_run_states": boundary["current_user_run_only"][
                "states_with_any_explicit_boundary"
            ],
            "boundary_narrow_persistent_states": boundary[
                "visible_prefix_narrow_explicit_revocation"
            ]["states_with_any_explicit_boundary"],
            "retriever_top1_same_card_rates": {
                pair: values["top1_same_card_rate"]
                for pair, values in retriever_pairwise.items()
            },
            "retriever_heldout_validation_strategy_family_match": {
                method: {
                    "at_1": values["strategy_family_match_at_1"],
                    "at_3": values["strategy_family_match_at_3"],
                    "macro_at_1": values["macro_strategy_family_match_at_1"],
                    "macro_at_3": values["macro_strategy_family_match_at_3"],
                }
                for method, values in heldout_family.items()
            },
        },
        "decisions": decisions,
        "researcher_decision_ids": [
            row["decision_id"] for row in decisions if row["researcher_approval_required"]
        ],
        "integration_order": [
            "complete_v6_semantic_memory_compiler_artifact",
            "bind_v6_candidate_identity_into_K5_seed0_artifacts",
            "rebuild_combined_zero_outcome_artifacts_and_hashes",
            "resolve_researcher_decisions_once",
            "materialize_and_validate_M2_freeze",
            "only_then_unlock_effect_calls",
        ],
        "report_chart_map": [
            {
                "segment": "Bundle cost shape",
                "question": "How quickly does bundle size consume a fixed diagnostic word cap?",
                "family": "comparison",
                "type": "grouped_bar",
                "dataset": "bundle_cap_coverage",
                "fields": ["cap_words", "bundle_size", "coverage"],
                "supported_claim": "Larger bundles consume the resource budget faster; the chart does not measure outcome quality.",
                "palette_policy": "relaxed_multi_category_three_roots",
                "delivery": "portable_html_native_artifact_chart",
            }
        ],
        "formal_outcome_calls": 0,
        "formal_unlock": False,
    }
    PACKET_OUT.parent.mkdir(parents=True, exist_ok=True)
    PACKET_OUT.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    source_dir = REPORT_DIR / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    copies = {
        RS_SUMMARY: source_dir / "rs_zero_outcome_summary.json",
        RS_RETRIEVER_AUDIT: source_dir / "rs_retriever_comparison.json",
        RS_FAMILY_AUDIT: source_dir / "rs_strategy_family_diagnostic.json",
        RS_RENDER_AUDIT: source_dir / "rs_renderer_boundary_audit.json",
        RECONCILIATION: source_dir / "execution_reconciliation.json",
        SCORER_AUDIT: source_dir / "official_scorer_audit.json",
        RQ0_CONTRACT: source_dir / "rq0_generator_contract.json",
        OFFICIAL_RAG_RUNTIME_ATTESTATION: source_dir
        / "official_rag_runtime_attestation.json",
        MEMORY_CENSUS: source_dir / "memory_candidate_census.json",
        MEMORY_FEATURE_READINESS: source_dir / "memory_feature_readiness.json",
        MEMORY_FOLDS: source_dir / "memory_exact_evidence_components.json",
        OFFICIAL_VISIBILITY: source_dir / "official_rq2_visibility.json",
        PACKET_OUT: source_dir / "m2_decision_packet.json",
    }
    for source, destination in copies.items():
        shutil.copyfile(source, destination)

    source_specs = [
        {
            "id": "rs-census",
            "label": "ESConv RS zero-outcome census",
            "path": "sources/rs_zero_outcome_summary.json",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_json_auto('sources/rs_zero_outcome_summary.json')",
                "description": "Load the reviewed text-free RS Phase-1 summary generated by script 06; report shaping is implemented in script 08.",
                "tables_used": ["sources/rs_zero_outcome_summary.json"],
                "filters": [
                    "ESConv train-only Strategy Bank",
                    "train+validation decision states",
                    "legacy EvoEmo-overlap exclusion in conservative primary audit",
                    "leave-current-dialogue-out retrieval",
                ],
                "metric_definitions": [
                    "Candidate coverage = states with at least one fold-exclusive source card / audited states.",
                    "Word-cap coverage = states whose diagnostic retrieved guidance+example bundle is at or below the named word cap / audited states.",
                ],
            },
        },
        {
            "id": "rs-retriever-comparison",
            "label": "RS zero-outcome retriever behavior comparison",
            "path": "sources/rs_retriever_comparison.json",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_json_auto('sources/rs_retriever_comparison.json')",
                "description": "Load the text-free lexical/BGE-small/BGE-M3 behavior surface generated by script 11.",
                "tables_used": ["sources/rs_retriever_comparison.json"],
                "filters": [
                    "formal_outcome_calls = 0",
                    "winner_selected = false",
                    "leave-current-dialogue-out",
                    "target response and target strategy annotation unread",
                ],
                "metric_definitions": [
                    "Top-1 agreement is the fraction of states where two methods return the same source-card identity first.",
                    "Top-k set Jaccard is method agreement, not candidate relevance, utility, or official benchmark performance.",
                ],
            },
        },
        {
            "id": "rs-strategy-family-diagnostic",
            "label": "Evaluator-only ESConv strategy-family match diagnostic",
            "path": "sources/rs_strategy_family_diagnostic.json",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_json_auto('sources/rs_strategy_family_diagnostic.json')",
                "description": "Load held-out retriever family-match sanity metrics generated by script 12.",
                "tables_used": ["sources/rs_strategy_family_diagnostic.json"],
                "filters": [
                    "evaluator_only = true",
                    "formal_outcome_calls = 0",
                    "winner_selected = false",
                    "validation split reported separately",
                ],
                "metric_definitions": [
                    "Strategy-family match@k asks whether any of the first k retrieved source cards shares the coarse target supporter strategy annotation.",
                    "It is a retriever sanity diagnostic, not applicability, PM ON/OFF gold, or Generator benefit.",
                ],
            },
        },
        {
            "id": "rs-render-audit",
            "label": "ESConv RS renderer and explicit-boundary audit",
            "path": "sources/rs_renderer_boundary_audit.json",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_json_auto('sources/rs_renderer_boundary_audit.json')",
                "description": "Load the zero-outcome exact-token renderer and mechanical boundary decision surface generated by script 09.",
                "tables_used": ["sources/rs_renderer_boundary_audit.json"],
                "filters": [
                    "formal_outcome_calls = 0",
                    "candidate-level boundary mapping",
                    "no composite exemplar risk score",
                ],
                "metric_definitions": [
                    "Resource tokens are tokenizer.json encodings of the delimited resource substring with special tokens disabled.",
                    "Boundary prevalence counts deterministic high-precision markers; it is not a utility label.",
                ],
            },
        },
        {
            "id": "m2-packet",
            "label": "Paper 1 M2 decision packet draft",
            "path": "sources/m2_decision_packet.json",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT unnest(decisions) AS decision FROM read_json_auto('sources/m2_decision_packet.json')",
                "description": "Load the ordered M2 decision register built from reviewed zero-outcome evidence and active authorities; report shaping is implemented in script 08.",
                "tables_used": ["sources/m2_decision_packet.json"],
                "filters": ["formal_outcome_calls = 0", "formal_unlock = false"],
                "metric_definitions": [
                    "Researcher approval is required only for pre-outcome choices not fixed by the highest authority."
                ],
            },
        },
        {
            "id": "reconciliation",
            "label": "Highest Paper 1 execution reconciliation",
            "path": "sources/execution_reconciliation.json",
        },
        {
            "id": "scorer-audit",
            "label": "Official scorer surface audit",
            "path": "sources/official_scorer_audit.json",
        },
        {
            "id": "rq0-contract",
            "label": "Frozen RQ0 Generator contract",
            "path": "sources/rq0_generator_contract.json",
        },
        {
            "id": "official-rag-runtime",
            "label": "ES-MemEval Official RAG runtime attestation",
            "path": "sources/official_rag_runtime_attestation.json",
        },
        {
            "id": "memory-census",
            "label": "ES-MemEval public memory candidate census",
            "path": "sources/memory_candidate_census.json",
        },
        {
            "id": "memory-feature-readiness",
            "label": "Memory feature-readiness inventory",
            "path": "sources/memory_feature_readiness.json",
        },
        {
            "id": "memory-components",
            "label": "Exact-evidence group components",
            "path": "sources/memory_exact_evidence_components.json",
        },
        {
            "id": "official-rq2-visibility",
            "label": "Pinned RQ2 task-arm visibility contract",
            "path": "sources/official_rq2_visibility.json",
        },
    ]

    cap_cells = rs["diagnostic_word_cap_grid"]["cells"]
    cap_rows = [
        {
            "cap_words": str(cap),
            "bundle_size": f"Top-{k}",
            "coverage": cap_cells[f"k{k}_cap{cap}"]["rate"],
            "states": counts["decision_states"],
            "states_within_cap": cap_cells[f"k{k}_cap{cap}"]["states_within_cap"],
            "unit": "diagnostic words, not model tokens",
        }
        for cap in (64, 128, 256, 512)
        for k in (1, 2, 4)
    ]
    headline = packet["rs_findings"] | {
        "authority_literal_states": literal["decision_states"],
        "conservative_states": conservative["decision_states"],
        "situation_count": situation["dialogues_with_nonempty_situation"],
        "nonverbatim_situation_count": situation[
            "situation_not_verbatim_contained_anywhere_in_dialogue"
        ],
    }

    title = "Paper 1 M2 预冻结决策包（零 outcome 草案）"
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": title,
            "description": "Route A 的 Phase-1 证据、阻断项与待确认 M2 决策。",
            "generatedAt": generated_at,
            "sources": source_specs,
            "cards": [
                {
                    "id": "rs-cards",
                    "dataset": "headlines",
                    "sourceId": "rs-census",
                    "description": "去除 privileged situation 后的 train-only、去重 source cards。",
                    "metrics": [
                        {"label": "Dialogue-only cards", "field": "dialogue_only_cards", "format": "compact"},
                        {"label": "vs v1", "field": "cards_removed_vs_situation_conditioned_v1", "format": "number", "signed": True},
                    ],
                },
                {
                    "id": "rs-states",
                    "dataset": "headlines",
                    "sourceId": "rs-census",
                    "description": "保守 non-overlap train/dev response opportunities。",
                    "metrics": [
                        {"label": "Decision states", "field": "decision_states", "format": "compact"},
                        {"label": "All train/dev gain", "field": "authority_literal_state_gain", "format": "number", "signed": True},
                    ],
                },
                {
                    "id": "rs-coverage",
                    "dataset": "headlines",
                    "sourceId": "rs-census",
                    "description": "每个 state 排除自身 dialogue 后仍有候选；非零 overlap 是 lexical diagnostic。",
                    "metrics": [
                        {"label": "Candidate coverage", "field": "leave_dialogue_out_candidate_coverage", "format": "percent"},
                        {"label": "Nonzero lexical", "field": "nonzero_lexical_overlap_coverage", "format": "percent"},
                    ],
                },
                {
                    "id": "situation-leakage",
                    "dataset": "headlines",
                    "sourceId": "rs-census",
                    "description": "ESConv situation 未逐字出现在完整 dialogue 的比例。",
                    "metrics": [
                        {"label": "Non-verbatim situation", "field": "nonverbatim_situation_rate", "format": "percent"},
                        {"label": "Dialogues", "field": "nonverbatim_situation_count", "format": "compact"},
                    ],
                },
            ],
            "charts": [
                {
                    "id": "bundle-cap-coverage",
                    "title": "Diagnostic bundle word-cap coverage",
                    "subtitle": "11,883 conservative RS states; words are a proxy, not Llama tokens",
                    "intent": "comparison",
                    "question": "How quickly does bundle size consume a fixed resource word cap?",
                    "rationale": "Grouped bars compare discrete cap coverage across Top-1, Top-2 and Top-4 without implying an outcome threshold.",
                    "comparisonContext": {
                        "denominator": "11,883 conservative RS decision states",
                        "grain": "state × diagnostic retrieved bundle",
                        "unit": "coverage rate",
                    },
                    "type": "bar",
                    "dataset": "bundle_cap_coverage",
                    "sourceId": "rs-census",
                    "encodings": {
                        "x": {"field": "cap_words", "type": "ordinal", "label": "Diagnostic word cap"},
                        "y": {"field": "coverage", "type": "quantitative", "format": "percent", "label": "States within cap"},
                        "color": {"field": "bundle_size", "type": "nominal", "label": "Bundle size"},
                        "tooltip": [
                            {"field": "states_within_cap", "type": "quantitative", "format": "number", "label": "States within cap"},
                            {"field": "states", "type": "quantitative", "format": "number", "label": "Total states"},
                        ],
                    },
                    "layout": "full",
                    "labels": {"values": "auto"},
                    "legend": {"position": "bottom", "sort": "labelAsc"},
                    "palette": {"kind": "categorical"},
                    "settings": {"groupMode": "grouped", "sort": "none"},
                    "surface": {"surface": "export", "viewMode": "both"},
                }
            ],
            "tables": [
                {
                    "id": "decision-register",
                    "title": "M2 decision register",
                    "subtitle": "Implementation repairs, researcher choices and current blockers before formal outcome calls",
                    "dataset": "decisions",
                    "sourceId": "m2-packet",
                    "defaultSort": {"field": "order", "direction": "asc"},
                    "density": "dense",
                    "layout": "full",
                    "columns": [
                        {"field": "order", "label": "#", "format": "number"},
                        {"field": "item", "label": "Decision", "type": "text"},
                        {"field": "evidence", "label": "Zero-outcome evidence", "type": "text"},
                        {"field": "recommendation", "label": "Recommendation", "type": "text"},
                        {"field": "status", "label": "Status", "type": "text"},
                        {"field": "approval_label", "label": "Researcher approval", "type": "text"},
                    ],
                }
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": f"# {title}"},
                {
                    "id": "technical-summary",
                    "type": "markdown",
                    "body": (
                        "## 技术结论：RS 已可审计，但整套 M2 仍不能解锁\n\n"
                        "- RS v1 确实混入了不可保证 runtime 可见的 `situation`；dialogue-only v2 已修复。\n"
                        "- RS 具备大量自然 state×candidate 机会，不需要人工制造 ON/OFF 或覆盖率 PASS 门。\n"
                        "- 当前最大不确定性不是 RS coverage，而是 overlap policy、正式 Retriever/renderer、task-specific effect coding、重复测量语义，以及冻结后的 memory feature/effect implementation。\n"
                        "- 本报告是决策草案，不是 freeze，也不解锁 outcome、训练或正式 benchmark。"
                    ),
                },
                {
                    "id": "rs-key-finding",
                    "type": "markdown",
                    "sourceId": "rs-census",
                    "body": (
                        "## 去掉 privileged situation 后，RS 仍有充分自然覆盖\n\n"
                        f"dialogue-only Bank 保留 {counts['strategy_source_cards']:,} 张卡和 875 个 train dialogue；保守 train/dev universe 产生 {counts['decision_states']:,} 个 response opportunities。"
                        f"全部 state 都有 leave-dialogue-out candidate，只有 1 个 state 的稀疏 lexical audit 为零 overlap。"
                        "因此 RS 的风险不是候选不足，而是必须冻结一个可复现的 semantic Retriever 和单一 treatment rendering。"
                    ),
                },
                {"id": "headline-strip", "type": "metric-strip", "cardIds": ["rs-cards", "rs-states", "rs-coverage", "situation-leakage"]},
                {
                    "id": "bundle-interpretation",
                    "type": "markdown",
                    "sourceId": "rs-census",
                    "body": (
                        "## Bundle 越大，处理对象越难解释且成本迅速上升\n\n"
                        f"Top-1 的 diagnostic injected length 中位数为 {bundle['1']['median']} words；Top-4 为 {bundle['4']['median']} words。"
                        "下图只展示结构性成本形状。独立 renderer census 使用本地 SHA-verified tokenizer bytes（远端 mirror/revision 由调用参数声明）："
                        f"guidance+exemplar 中位数 {rendered['guidance_plus_exemplar']['resource_token_distribution']['median']} tokens，"
                        f"192-token cap 覆盖 {rendered['guidance_plus_exemplar']['cap_coverage']['192']['coverage_fraction']:.2%}。"
                        "该 tokenizer 与 NVIDIA NIM 的实际 parity 仍需在 freeze 前确认。"
                    ),
                },
                {"id": "bundle-chart", "type": "chart", "chartId": "bundle-cap-coverage", "layout": "full"},
                {
                    "id": "scope-definitions",
                    "type": "markdown",
                    "body": (
                        "## 范围与测量定义\n\n"
                        "`Decision state` 是至少出现一条 seeker 消息后、下一段 supporter response 开始前的可见前缀。连续 supporter 句属于同一 response opportunity。"
                        "`Candidate coverage` 只表示排除当前 dialogue 后 Bank 仍有合法来源卡，不表示注入有收益。"
                        "Lexical Jaccard、word counts 与 request regex 全部是 Phase-1 diagnostics；正式 embedding revision、model-token cap 和 feature schema 尚未冻结。"
                    ),
                },
                {
                    "id": "methodology",
                    "type": "markdown",
                    "body": (
                        "## 方法：只验证可见性、grain、覆盖和方差\n\n"
                        "构建器只读取 speaker/content 与 source-card strategy annotation；不读取 survey、feedback、questionnaire、target response、future turns 或正式 outcomes。"
                        "每个训练 state 的检索都 leave-current-dialogue-out。高 document-frequency token 只在 diagnostic lexical index 中被移除，以避免停用词让全库成为候选；该 scorer 不进入正式 runner。"
                    ),
                },
                {
                    "id": "decision-heading",
                    "type": "markdown",
                    "body": (
                        "## 需要一次性确认的 M2 决策\n\n"
                        "表中 `RESEARCHER_DECISION_REQUIRED` 项必须在任何正式 outcome 调用前一次性确认。Memory runtime 已合入；B30-FINAL 只完成已授权的 stable-kinship MP 与 K=5/seed=0 物化，不能用旧 coverage 或旧 synthetic 数据填空。"
                    ),
                },
                {"id": "decision-table", "type": "table", "tableId": "decision-register", "layout": "full"},
                {
                    "id": "limitations",
                    "type": "markdown",
                    "body": (
                        "## 限制与稳健性边界\n\n"
                        "RS 结果描述的是 availability，不是 positive-effect prevalence，也不能证明 PM 可学习。"
                        "当前 lexical ranking 不能支持正式 retrieval claim。`listen-only` 和 `no-probing` 在训练 state 中为零或近零，因此不得作为可学习特征。"
                        "它们只能作为所有 arms 共享的 candidate-level 机械边界。Exemplar 中的人称、关系、时间与实体形状仅作诊断；"
                        "有效交付后的复制、误用或不采用都属于 realized treatment effect，不得事后删样本。"
                        "Memory census、outer folds 和 combined API volume 仍取决于 B 的 runtime-boundary 修复。"
                    ),
                },
                {
                    "id": "next-steps",
                    "type": "markdown",
                    "body": (
                        "## 下一步：先集成完整 Phase-1，再冻结一次\n\n"
                        "1. 提交 A 的 dialogue-only RS census 与 CI。\n"
                        "2. 等待并审计 B 的 sanitized memory runtime/census 修复。\n"
                        "3. 在 A 分支集成 B，重建 combined manifests。\n"
                        "4. 你确认 decision register 中的研究项。\n"
                        "5. 物化唯一 M2 freeze；验证无 pending scientific fields 后才生成 matched effects。"
                    ),
                },
                {
                    "id": "further-questions",
                    "type": "markdown",
                    "body": (
                        "## 仍需回答的问题\n\n"
                        "- legacy EvoEmo-overlap exclusion 是否继续作为 primary，还是只保留 sensitivity？\n"
                        "- 是否接受 Top-1 single-card RS treatment，并选择 guidance-only 或明确分隔的 guidance+exemplar？\n"
                        "- 显式 boundary 采用 current-run-only，还是只允许明确撤销的窄 persistence？\n"
                        "- provider tokenizer parity 核验后，是否采用 192-token resource cap？\n"
                        "- 是否用 authority-aligned task anchors/guards 替换当前 exact Pareto draft？\n"
                        "- temperature=0、seed=null 的 NIM 调用如何定义真正独立的 repeated effect？"
                    ),
                },
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": {
                "headlines": [
                    headline
                    | {
                        "authority_literal_state_gain": literal["decision_states"]
                        - conservative["decision_states"]
                    }
                ],
                "bundle_cap_coverage": cap_rows,
                "decisions": [
                    row
                    | {
                        "approval_label": (
                            "Required" if row["researcher_approval_required"] else "No"
                        )
                    }
                    for row in decisions
                ],
            },
        },
        "sources": source_specs,
    }
    artifact_path = REPORT_DIR / "artifact.json"
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "packet": str(PACKET_OUT.relative_to(PROJECT)),
                "packet_sha256": _sha256(PACKET_OUT),
                "report_artifact": str(artifact_path.relative_to(PROJECT)),
                "formal_outcome_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

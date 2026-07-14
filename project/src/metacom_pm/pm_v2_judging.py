from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Sequence

import numpy as np
from pydantic import Field

from .api import Endpoint, make_client
from .io import canonical_json, sha256_text
from .pm_v2_contracts import (
    ActionLabel,
    PMV2State,
    ResponseDimensions,
    RiskDimensions,
    StrictModel,
)


class ResponseJudgeOutput(StrictModel):
    emotional_support: float = Field(ge=1.0, le=5.0)
    personalization: float = Field(ge=1.0, le=5.0)
    memory_appropriateness: float = Field(ge=1.0, le=5.0)
    factual_grounding: float = Field(ge=1.0, le=5.0)
    temporal_consistency: float = Field(ge=1.0, le=5.0)
    non_intrusiveness: float = Field(ge=1.0, le=5.0)
    rationale: str = Field(min_length=1, max_length=800)


class RiskJudgeOutput(StrictModel):
    selected_context_misuse: float = Field(ge=0.0, le=3.0)
    unnecessary_exposure: float = Field(ge=0.0, le=3.0)
    stale_or_conflicting_use: float = Field(ge=0.0, le=3.0)
    unsupported_personal_claim: float = Field(ge=0.0, le=3.0)
    memory_omission: float = Field(ge=0.0, le=3.0)
    strategy_overuse: float = Field(ge=0.0, le=3.0)
    strategy_omission: float = Field(ge=0.0, le=3.0)
    rationale: str = Field(min_length=1, max_length=800)


@dataclass(frozen=True)
class JudgeResult:
    family: str
    model: str
    response: ResponseJudgeOutput
    risk: RiskJudgeOutput
    response_request_hash: str
    risk_request_hash: str


def build_response_messages(
    *,
    state: PMV2State,
    authorized_user_context: str,
    candidate_response: str,
) -> list[dict[str, str]]:
    system = """You are an impartial evaluator of one emotional-support reply.
Score six independent dimensions. Do not infer which policy generated the reply.
Do not produce an overall score. Treat each dimension independently and use the
full 1-5 scale. Authorized user context is reference material for checking
personalization, grounding and temporal consistency; it is not evidence that the
generator actually saw that context."""
    user = f"""CURRENT SEEKER TURN
{state.current_user_text}

RECENT DIALOGUE
{canonical_json([turn.model_dump(mode='json') for turn in state.current_session_history])}

AUTHORIZED USER CONTEXT
{authorized_user_context}

ANONYMOUS SUPPORTER RESPONSE
{candidate_response}

SCORING RULES
- emotional_support: empathy, validation, emotional attunement, and helpful support.
- personalization: specifically tailored to the seeker's current situation and known history; generic warmth alone is not personalization.
- memory_appropriateness: any use or non-use of history is appropriate. Penalize both unjustified recall and omission of clearly material history.
- factual_grounding: claims about the user are supported by the authorized context or current dialogue.
- temporal_consistency: events and current states are represented in the correct order and tense.
- non_intrusiveness: does not expose irrelevant private details, over-personalize, or pressure the seeker.
Return strict JSON matching the schema. Do not add `overall`."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_risk_messages(
    *,
    state: PMV2State,
    authorized_user_context: str,
    selected_context: str,
    candidate_response: str,
) -> list[dict[str, str]]:
    system = """You are an evidence-risk auditor for emotional-support dialogue.
The resource policy and action name are hidden. Score observed risks on 0-3,
where 0 means no issue and 3 means a major issue. Distinguish selected-context
quality from actual misuse in the final response. Do not reward or penalize token
cost; cost is measured separately from logs."""
    user = f"""CURRENT SEEKER TURN
{state.current_user_text}

RECENT DIALOGUE
{canonical_json([turn.model_dump(mode='json') for turn in state.current_session_history])}

AUTHORIZED USER CONTEXT
{authorized_user_context}

SELECTED CONTEXT SHOWN TO GENERATOR
{selected_context or '[none]'}

ANONYMOUS SUPPORTER RESPONSE
{candidate_response}

RISK RULES
- selected_context_misuse: selected evidence is actually misapplied in the response.
- unnecessary_exposure: irrelevant or overly private information is surfaced.
- stale_or_conflicting_use: outdated or contradicted information affects the response.
- unsupported_personal_claim: the response invents personal facts.
- memory_omission: clearly material available history was omitted and the omission harms the reply. Do not penalize harmless non-use.
- strategy_overuse: retrieved support guidance makes the reply formulaic, premature, overly directive, or repetitive.
- strategy_omission: strategy guidance was clearly needed and its absence harms the reply.
Return strict JSON matching the schema."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def judge_one(
    *,
    endpoint: Endpoint,
    state: PMV2State,
    authorized_user_context: str,
    selected_context: str,
    candidate_response: str,
    seed: int = 17,
) -> JudgeResult:
    if not endpoint.family:
        raise ValueError("judge endpoint must declare a model family")
    client = make_client(endpoint)
    try:
        response_messages = build_response_messages(
            state=state,
            authorized_user_context=authorized_user_context,
            candidate_response=candidate_response,
        )
        response_call, response_score = client.chat(
            response_messages,
            temperature=0.0,
            max_tokens=600,
            seed=seed,
            response_schema=ResponseJudgeOutput,
        )
        assert response_score is not None
        risk_messages = build_risk_messages(
            state=state,
            authorized_user_context=authorized_user_context,
            selected_context=selected_context,
            candidate_response=candidate_response,
        )
        risk_call, risk_score = client.chat(
            risk_messages,
            temperature=0.0,
            max_tokens=700,
            seed=seed + 1,
            response_schema=RiskJudgeOutput,
        )
        assert risk_score is not None
        return JudgeResult(
            family=endpoint.family,
            model=endpoint.model,
            response=response_score,
            risk=risk_score,
            response_request_hash=response_call.request_hash,
            risk_request_hash=risk_call.request_hash,
        )
    finally:
        client.close()


def _median_model(cls, outputs: Sequence[StrictModel], fields: Iterable[str]):
    values = {
        name: float(median(float(getattr(output, name)) for output in outputs))
        for name in fields
    }
    return cls(**values)


def aggregate_judges(
    results: Sequence[JudgeResult],
    *,
    minimum_families: int = 2,
    reliable_mad_threshold: float = 0.75,
) -> tuple[ResponseDimensions, RiskDimensions, dict[str, Any]]:
    if len(results) < minimum_families:
        raise ValueError(f"need at least {minimum_families} independent judge results")
    families = {result.family for result in results}
    if len(families) < minimum_families:
        raise ValueError("judge results do not contain enough independent model families")
    response_fields = tuple(ResponseDimensions.model_fields)
    risk_fields = tuple(RiskDimensions.model_fields)
    response = _median_model(
        ResponseDimensions, [result.response for result in results], response_fields
    )
    risk = _median_model(RiskDimensions, [result.risk for result in results], risk_fields)
    mads: dict[str, float] = {}
    for name in response_fields:
        values = np.asarray([float(getattr(result.response, name)) for result in results])
        mads[f"response.{name}"] = float(np.median(np.abs(values - np.median(values))))
    for name in risk_fields:
        values = np.asarray([float(getattr(result.risk, name)) for result in results])
        mads[f"risk.{name}"] = float(np.median(np.abs(values - np.median(values))))
    max_mad = max(mads.values(), default=0.0)
    audit = {
        "judge_count": len(results),
        "judge_families": sorted(families),
        "judge_models": sorted({result.model for result in results}),
        "dimension_mad": mads,
        "max_dimension_mad": max_mad,
        "label_reliable": max_mad <= reliable_mad_threshold,
        "response_request_hashes": sorted(result.response_request_hash for result in results),
        "risk_request_hashes": sorted(result.risk_request_hash for result in results),
    }
    return response, risk, audit


def build_action_label(
    *,
    state: PMV2State,
    action_id: str,
    observed_input_tokens: int,
    retrieval_calls: int,
    results: Sequence[JudgeResult],
    provenance: dict[str, Any] | None = None,
) -> ActionLabel:
    response, risk, audit = aggregate_judges(results)
    return ActionLabel(
        state_id=state.state_id,
        card_id=state.card_id,
        user_id=state.user_id,
        semantic_family=state.semantic_family,
        action_id=action_id,
        response=response,
        risk=risk,
        observed_input_tokens=observed_input_tokens,
        retrieval_calls=retrieval_calls,
        judge_families=audit["judge_families"],
        judge_count=audit["judge_count"],
        max_dimension_mad=audit["max_dimension_mad"],
        label_reliable=audit["label_reliable"],
        provenance={**(provenance or {}), "judge_audit": audit},
    )


def _dimension_health(
    matrix: np.ndarray,
    field_names: Sequence[str],
    *,
    prefix: str,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    duplicate_pairs: list[dict[str, Any]] = []
    for left in range(len(field_names)):
        for right in range(left + 1, len(field_names)):
            exact_rate = float(np.mean(matrix[:, left] == matrix[:, right]))
            correlation = float(
                np.corrcoef(matrix[:, left], matrix[:, right])[0, 1]
                if np.std(matrix[:, left]) > 0 and np.std(matrix[:, right]) > 0
                else 1.0
            )
            if exact_rate >= 0.98:
                duplicate_pairs.append(
                    {
                        "left": f"{prefix}.{field_names[left]}",
                        "right": f"{prefix}.{field_names[right]}",
                        "exact_match_rate": exact_rate,
                        "correlation": correlation,
                    }
                )
    constants = [
        f"{prefix}.{field_names[index]}"
        for index in range(len(field_names))
        if float(np.std(matrix[:, index])) < 1e-9
    ]
    prevalence = {
        f"{prefix}.{field_names[index]}": {
            "mean": float(np.mean(matrix[:, index])),
            "std": float(np.std(matrix[:, index])),
            "nonzero_rate": float(np.mean(matrix[:, index] != 0.0)),
            "unique_values": sorted(float(value) for value in np.unique(matrix[:, index])),
        }
        for index in range(len(field_names))
    }
    return duplicate_pairs, constants, prevalence


def validate_judge_table(labels: Sequence[ActionLabel]) -> dict[str, Any]:
    """Fail closed on duplicated, constant, or unreliable response/risk labels."""

    if not labels:
        raise ValueError("empty judge table")
    response_fields = tuple(ResponseDimensions.model_fields)
    risk_fields = tuple(RiskDimensions.model_fields)
    response_matrix = np.asarray(
        [[float(getattr(label.response, name)) for name in response_fields] for label in labels],
        dtype=float,
    )
    risk_matrix = np.asarray(
        [[float(getattr(label.risk, name)) for name in risk_fields] for label in labels],
        dtype=float,
    )
    response_duplicates, response_constants, response_prevalence = _dimension_health(
        response_matrix, response_fields, prefix="response"
    )
    risk_duplicates, risk_constants, risk_prevalence = _dimension_health(
        risk_matrix, risk_fields, prefix="risk"
    )
    reliable_rate = float(np.mean([label.label_reliable for label in labels]))
    duplicate_pairs = [*response_duplicates, *risk_duplicates]
    constant_fields = [*response_constants, *risk_constants]
    report = {
        "n": len(labels),
        "duplicate_dimension_pairs": duplicate_pairs,
        "constant_dimensions": constant_fields,
        "response_dimension_prevalence": response_prevalence,
        "risk_dimension_prevalence": risk_prevalence,
        "reliable_label_rate": reliable_rate,
        "status": "PASS",
    }
    if duplicate_pairs or constant_fields or reliable_rate < 0.80:
        report["status"] = "FAIL"
        raise RuntimeError("PM-v2 judge quality gate failed: " + canonical_json(report))
    return report


def prompt_contract_hash() -> str:
    payload = {
        "response_schema": ResponseJudgeOutput.model_json_schema(),
        "risk_schema": RiskJudgeOutput.model_json_schema(),
        "version": "pmv2-judge-v1-no-overall",
    }
    return sha256_text(canonical_json(payload))

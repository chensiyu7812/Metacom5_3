from metacom_pm.evo_sampled_audit import _omission_messages, _selected_messages


def _item():
    return {
        "audit_item_id": "audit_v4_001",
        "unit_id": "unit_test",
        "unit_key": {
            "user_id": "p1",
            "topic_index": 1,
            "seed": 101,
            "simulator_id": "seeker_main",
            "interaction_mode": "fixed",
            "turn_index": 8,
        },
        "covered_strata": [
            "pm_vs_no_memory_quality_loss",
            "pm_quality_tie_or_win_with_savings",
        ],
        "stratum": "pm_vs_no_memory_quality_loss",
        "reason": "no_memory_r0 scores higher; audit whether PM's resource use was intrusive.",
        "audit_modules": [
            "selected_evidence_misuse",
            "unnecessary_exposure",
            "positive_control_resource_saving",
            "rare_pm_actions",
        ],
    }


def _target_turn():
    return {
        "condition": "pm",
        "action_id": "MSE+RS",
        "supporter_message": "It makes sense that this feels complicated.",
        "seeker_message": "I feel torn between my parents and my own plans.",
        "context_before_turn": [
            {"role": "supporter", "content": "I am here with you."},
            {"role": "seeker", "content": "Thanks."},
        ],
        "input_tokens": 123,
        "output_tokens": 45,
        "cost": {
            "total_input_tokens": 123,
            "memory_tokens": 50,
            "strategy_tokens": 20,
            "retrieval_calls": 2,
        },
        "selected_memory": [
            {
                "memory_id": "mem_abc123",
                "source": "MS",
                "timestamp": "2025-01-01",
                "created_session": 3,
                "text": "The seeker previously discussed family expectations.",
            }
        ],
        "selected_strategy": [
            {
                "strategy_id": "strat_abc123",
                "strategy_label": "Reflection of feelings",
                "guidance_text": "Reflect the user's mixed feelings without giving premature advice.",
                "example_response": "That sounds like a lot to hold.",
                "retrieval_text": "Example dialogue text.",
            }
        ],
    }


def _comparison_turn():
    return {
        "condition": "strong_rule",
        "action_id": "MPMSME+RS",
        "supporter_message": "A comparison response.",
    }


def _prompt_text(messages):
    return "\n".join(message["content"] for message in messages)


def _assert_no_measurement_leakage(text: str):
    forbidden = [
        "pm_vs_",
        "positive_control",
        "planner_reason",
        "covered_strata",
        "rare_pm_actions",
        '"condition":"pm"',
        '"condition":"strong_rule"',
        "strong_rule",
        "best_fixed",
        "session_rag_rs",
    ]
    for value in forbidden:
        assert value not in text


def test_selected_audit_prompt_hides_policy_and_selection_rationale():
    text = _prompt_text(
        _selected_messages(
            call_id="call_1",
            item=_item(),
            target_turn=_target_turn(),
            comparison_turns=[_comparison_turn()],
            max_memory_chars=1000,
            max_strategy_chars=700,
        )
    )

    _assert_no_measurement_leakage(text)
    assert '"response_id":"target"' in text
    assert '"comparison_id":"C1"' in text
    assert "MSE+RS" in text
    assert "MPMSME+RS" in text
    assert "selected_memory" in text
    assert "selected_strategy" in text
    assert "family expectations" in text
    assert "Reflection of feelings" in text
    assert "selected_evidence_misuse" in text
    assert "unnecessary_exposure" in text


def test_omission_audit_prompt_hides_policy_and_selection_rationale():
    text = _prompt_text(
        _omission_messages(
            call_id="call_2",
            item=_item(),
            target_turn=_target_turn(),
            comparison_turns=[_comparison_turn()],
            authorized_context={
                "user_profile": {"summary": "Profile text"},
                "current_topic": {"description": "Topic text"},
                "related_session_summaries": [],
                "evaluator_only": True,
            },
            max_memory_chars=1000,
            max_strategy_chars=700,
        )
    )

    _assert_no_measurement_leakage(text)
    assert "authorized_ground_truth" in text
    assert '"response_id":"target"' in text
    assert '"comparison_id":"C1"' in text
    assert "MSE+RS" in text
    assert "selected_memory" in text
    assert "selected_strategy" in text

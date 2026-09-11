import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reconciliation_base_removes_old_gates_and_is_scoped_by_later_authority():
    contract = json.loads(
        (ROOT / "data/paper1_authority/paper1_execution_reconciliation_20260816_v1.json").read_text()
    )
    assert contract["status"] == "ACTIVE_HIGHEST_PRECEDENCE_PRE_OUTCOME_OVERRIDE"
    assert contract["learning_route"]["primary_threshold"] == 0.5  # historical clause
    assert contract["learning_route"]["target"] == (
        "probability_of_materially_positive_realized_paired_effect"
    )
    assert contract["learning_route"]["cost_in_label_or_loss"] is False
    assert contract["repeated_effect"]["qualification_pass_gate"] is False
    assert contract["repeated_effect"]["outcome_coding"]["equivalent"] == 0
    assert "excluded_from_likelihood" in contract["repeated_effect"]["outcome_coding"]["uncertain"]
    assert "excluded_from_likelihood" in contract["repeated_effect"]["outcome_coding"]["invalid"]
    assert contract["measurement_validity"]["semantic_nonuse_is_valid_realized_effect"] is True
    assert contract["formal_evidence"]["binary_paper_pass_fail_forbidden"] is True
    assert contract["formal_evidence"]["matched_random_budget_constraint"] == (
        "same_realized_on_rate_and_exact_injected_token_budget"
    )
    assert len(contract["superseded_empirical_gates"]) == 7

    threshold = json.loads(
        (
            ROOT
            / "data/paper1_authority/"
            "paper1_threshold_policy_calibration_amendment_20260831_v1.json"
        ).read_text()
    )
    assert threshold["status"] == "ACTIVE_RESEARCHER_AUTHORIZED_SCOPED_AMENDMENT_PRE_OUTCOME"
    assert threshold["scoped_override"]["fixed_point_five_new_role"].startswith(
        "mandatory_transparent_reference"
    )
    assert threshold["preserved_research"]["cost_in_label_or_loss"] is False
    assert threshold["current_activity"]["formal_outcome_calls"] == 0


def test_agents_reads_current_stabilization_before_preserved_base_authority():
    agents = (ROOT.parent / "AGENTS.md").read_text()
    stabilization = agents.index("PM_PAPER1_PRE_EFFECT_STABILIZATION_20260904_ZH.md")
    latency_v2 = agents.index(
        "paper1_latency_constrained_selective_policy_amendment_20260904_v2.json"
    )
    effect_v2 = agents.index("paper1_task_effect_coding_v2.json")
    teacher_v2 = agents.index("paper1_pairwise_teacher_qualification_plan_v3.json")
    teacher_design = agents.index(
        "paper1_pairwise_teacher_human_reference_design_20260908_v2.json"
    )
    reconciliation = agents.index("PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md")
    old_program = agents.index("PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md")
    assert stabilization < latency_v2 < effect_v2 < teacher_v2 < teacher_design
    assert teacher_design < reconciliation
    assert reconciliation < old_program
    assert "Semantic adoption is diagnostic only" in agents
    assert "semantic-memory v7/v8/v9 code are historical DEV provenance" in agents
    assert "data/v3_authority`" in agents


def test_ci_blocks_on_current_paper1_and_omits_historical_suites():
    workflow = (ROOT.parent / ".github/workflows/pm-v2-tests.yml").read_text()
    assert "Run blocking public-only Paper-1 suite" in workflow
    assert 'pytest -q -m "not gpu" tests/test_paper1_*.py' in workflow
    assert "Run legacy V5.3" not in workflow
    assert "Run complete historical suite" not in workflow
    assert '"pm-v1.5-*"' not in workflow

    historical_tests = (
        "test_paper1_evidence.py",
        "test_paper1_prequalification_consolidation.py",
        "test_paper1_semantic_memory_runtime_v7.py",
        "test_paper1_semantic_memory_runtime_v8_dev.py",
        "test_paper1_semantic_memory_runtime_v9_dev.py",
        "test_paper1_semantic_memory_v8_data_quality_audit.py",
        "test_paper1_semantic_memory_v8_dev_artifact.py",
        "test_paper1_semantic_memory_v9_dev_artifact.py",
        "test_paper1_semantic_memory_v9_dev_package.py",
        "test_paper1_semantic_memory_v9_live.py",
        "test_paper1_nonhuman_qualification_progress.py",
        "test_paper1_resource_amount_calibration_amendment.py",
        "test_paper1_rq0_anchored_parser_v3.py",
    )
    for test_name in historical_tests:
        assert (ROOT / "tests/historical_paper1" / test_name).is_file()
        assert f"tests/{test_name}" not in workflow

    current_integrity = ROOT / "tests/test_paper1_current_artifact_integrity.py"
    assert current_integrity.is_file()
    validator = (ROOT / "scripts/paper1/00_validate_integration_base.py").read_text()
    assert "v3_authority" not in validator
    assert '"scripts" / "v3"' not in validator


def test_ci_never_runs_local_gpu_tests_on_github_cpu_runner():
    workflow = (ROOT.parent / ".github/workflows/pm-v2-tests.yml").read_text()
    pytest_commands = [
        line.strip()
        for line in workflow.splitlines()
        if line.strip().startswith(("run: pytest", "pytest "))
    ]
    assert pytest_commands
    assert all('-m "not gpu"' in command for command in pytest_commands)

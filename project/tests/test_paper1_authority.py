import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reconciliation_is_highest_precedence_and_removes_old_gates():
    contract = json.loads(
        (ROOT / "data/paper1_authority/paper1_execution_reconciliation_20260816_v1.json").read_text()
    )
    assert contract["status"] == "ACTIVE_HIGHEST_PRECEDENCE_PRE_OUTCOME_OVERRIDE"
    assert contract["learning_route"]["primary_threshold"] == 0.5
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


def test_agents_reads_reconciliation_first():
    agents = (ROOT.parent / "AGENTS.md").read_text()
    reconciliation = agents.index("PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md")
    old_program = agents.index("PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md")
    assert reconciliation < old_program
    assert "Semantic adoption is diagnostic only" in agents


def test_ci_blocks_on_paper1_and_demotes_legacy_v53_to_diagnostic():
    workflow = (ROOT.parent / ".github/workflows/pm-v2-tests.yml").read_text()
    paper1 = workflow.index("Run blocking public-only Paper-1 suite")
    legacy = workflow.index("Run legacy V5.3 clean-release suite (diagnostic only)")
    assert paper1 < legacy
    paper1_block = workflow[paper1:legacy]
    assert 'pytest -q -m "not gpu" tests/test_paper1_*.py' in paper1_block
    legacy_block = workflow[legacy : legacy + 180]
    assert "continue-on-error: true" in legacy_block


def test_ci_never_runs_local_gpu_tests_on_github_cpu_runner():
    workflow = (ROOT.parent / ".github/workflows/pm-v2-tests.yml").read_text()
    pytest_commands = [
        line.strip()
        for line in workflow.splitlines()
        if line.strip().startswith("run: pytest")
    ]
    assert pytest_commands
    assert all('-m "not gpu"' in command for command in pytest_commands)

#!/usr/bin/env python3
"""Validate plan navigation, work-package DAG and schema structure.

No production data, model, provider or training call is made. Passing this
checker does not prove scientific hypotheses, semantic truth or feasibility of
external resources. Run using the existing paper1-judges-py312 environment.
"""
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
MAIN = PROJECT / 'docs/PM_RL1_MASTER_EXECUTION_PLAN_20261116_ZH.md'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    package = read(HERE / 'WORK_PACKAGES.json')
    state = read(HERE / 'EXECUTION_STATE.json')
    tasks = package['tasks']
    assert len(tasks) == package['task_count'] == 18
    by_id = {t['id']: t for t in tasks}
    assert len(by_id) == len(tasks)
    assert set(by_id) == set(state['tasks'])
    visiting, visited = set(), set()

    def visit(ident):
        assert ident in by_id, f'Unknown dependency {ident}'
        assert ident not in visiting, f'Dependency cycle at {ident}'
        if ident in visited:
            return
        visiting.add(ident)
        for dep in by_id[ident]['depends_on']:
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)

    for task in tasks:
        visit(task['id'])
        for required in ('inputs', 'actions', 'expected_outputs', 'acceptance_checks',
                         'failure_branch', 'implementation_annex_sections'):
            assert task[required], (task['id'], required)
        assert task['output_paths_are_contracts_not_existing_files'] is True
        assert task['production_execution_status'] == 'not_started'
        assert state['tasks'][task['id']]['status'] in package['states']
    assert state['next_task'] == 'P00'
    assert state['research_complete'] is False
    assert state['expected_positive_objective_achieved'] is False

    draft = read(HERE / 'RUN_FREEZE_TEMPLATE.json')
    assert draft['status'] == 'TEMPLATE_NOT_EXECUTABLE'
    assert draft['run_id'] is None
    assert draft['analysis']['primary_comparisons'] == []

    links = []
    documents = [MAIN, *sorted(HERE.glob('*.md'))]
    for path in documents:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if target.startswith(('https:', 'http:', '#')):
                continue
            clean = target.split('#', 1)[0]
            if not clean:
                continue
            resolved = (path.parent / clean).resolve()
            assert resolved.exists(), (path, target)
            links.append({'from': str(path.relative_to(PROJECT)), 'target': target})

    for path in HERE.glob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
    schema_check = subprocess.run(
        [sys.executable, str(HERE / 'validate_resource_schema.py')],
        check=True, capture_output=True, text=True,
    )
    schema = json.loads(schema_check.stdout)
    assert schema['status'] == 'PASS_SCHEMA_STRUCTURE_ONLY'

    for path in (PROJECT.parent / 'AGENTS.md',
                 PROJECT / 'src/metacom_pm/rl1/AGENTS.md',
                 PROJECT / 'docs/PM_RL1_CURRENT_STATUS.md',
                 PROJECT / 'docs/PM_RL1_PROGRESS_INDEX_20260930_ZH.md'):
        assert MAIN.name in path.read_text(), path

    files = [MAIN, *sorted(p for p in HERE.iterdir()
                          if p.is_file() and p.name != 'VALIDATION.json')]
    result = {
        'status': 'PASS_PLAN_STRUCTURE_AND_SCHEMA_NOT_RESEARCH_VALIDATION',
        'task_count': len(tasks), 'dependency_graph': 'acyclic',
        'all_tasks_have_inputs_actions_outputs_acceptance_failure_paths': True,
        'local_links_checked': len(links), 'broken_local_links': 0,
        'navigation_entries_updated': 4,
        'schema_structure_checks': schema,
        'review_resolutions': [
            'direct OFF comparator identity bound in feedback schema',
            'private gold/evaluation never unlocked by GET',
            'pending versus completed_uncertain and one review limit',
            'terminal measured cost includes G with no double deduction',
            'repair_check separated from final_confirmation',
            'PPO snapshot/log-prob preserved while waiting for feedback',
            'explicit shared OneShot-Guarded capacity semantics',
            'Random calibrated only on development measurements',
        ],
        'new_production_runs': 0, 'new_model_calls': 0, 'new_paid_calls': 0,
        'remaining_scientific_and_external_dependencies':
            'See OPEN_QUESTIONS_ZH.md; structure checks do not resolve them',
        'artifact_sha256': {str(p.relative_to(PROJECT)): sha(p) for p in files},
    }
    (HERE / 'VALIDATION.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('artifact_sha256', 'schema_structure_checks')},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

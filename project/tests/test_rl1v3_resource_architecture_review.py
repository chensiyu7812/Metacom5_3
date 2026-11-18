"""The review must detect altered model inputs and never invent missing outcomes."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('resource_review', ROOT/'project/scripts/rl1v3/resource_architecture_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.fixture(scope='module')
def context():
    fixture = json.loads((ROOT/'project/tests/fixtures/rl1v3_resource_review/request_inputs.json').read_text())
    cfg = json.loads((ROOT/'project/configs/rl1v3/bank_v0_port.json').read_text())
    reg = review.source_registry.load(ROOT/cfg['registry_dir'])
    bank = review.bank_v0.load(ROOT/cfg['bank_dir'], reg)
    coverage = review.lines(ROOT/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl')
    p = next(p for p in coverage if p['prefix_id'] == fixture['cases'][0]['row']['prefix_id'])
    prefix = reg.prefix(p['owner_id'], p['session_id'], p['cut_turn'])
    return fixture, bank, prefix


def check(case, context):
    fixture, bank, prefix = context
    return review.check_request(case['row'], case['binding'], bank, prefix, fixture['system'], fixture['notes'])


@pytest.mark.parametrize('index', [0, 1])
def test_fixed_off_and_me_are_legal_visible_projections(context, index):
    case = context[0]['cases'][index]
    assert check(case, context).sha256 == case['row']['terminal_key_sha256']


@pytest.mark.parametrize('mutation', ['needcard', 'future_text', 'role', 'token_count', 'generated_status', 'reading'])
def test_altered_inputs_cannot_be_certified(context, mutation):
    case = copy.deepcopy(context[0]['cases'][1])
    row, binding = case['row'], case['binding']
    if mutation == 'needcard':
        row['messages'].append({'role':'user', 'content':'NeedCard: required history from the private evaluation.'})
    elif mutation == 'future_text':
        row['messages'][-1]['content'] += '\nUnseen later session: the problem was solved.'
    elif mutation == 'role':
        row['messages'][-1]['role'] = 'assistant'
    elif mutation == 'token_count':
        row['input_ids'] = row['input_ids'][:-1]
    elif mutation == 'generated_status':
        binding['terminal_status'] = 'complete'
    elif mutation == 'reading':
        binding['new_trace']['readings'][0]['reading_text'] += '\nUnverified inferred outcome.'
    with pytest.raises(ValueError):
        check(case, context)


def test_missing_arms_stay_unreachable_not_zero(context):
    plan = review.proposed_jobs([c['row'] for c in context[0]['cases']])
    assert {j['subset'] for j in plan['jobs']} == {'OFF', 'ME'}
    assert {r['subset'] for r in plan['unreachable']} == {'RS', 'MP', 'MS', 'MP+MS', 'ME+MS'}
    assert all(j['quality'] is None and j['result'] is None and j['generation_calls_executed'] == 0 for j in plan['jobs'])
    assert plan['approved_gpu_requests'] == 0


def test_design_rejects_duplicate_cells_and_missing_off(context):
    off, me = [c['row'] for c in context[0]['cases']]
    for rows in ([off, off], [me]):
        with pytest.raises(ValueError):
            review.proposed_jobs(rows)

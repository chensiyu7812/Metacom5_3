"""Synthetic offline tests. No private text, model, device or network access."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import pytest

from metacom_pm.rl1.schema import Resource, PrefixSpec, PublicTurn, EpisodeSpec, digest
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.rs_applicability import RSApplicabilityRenderer, adapt_messages, paired_request, INSTRUCTION
from metacom_pm.rl1.rs_development import execute_jobs, save_once, validate_authorization, validate_package
from metacom_pm.rl1.bound_generation import BoundResourceEnv, validate_and_project


def fixture():
    prefix = PrefixSpec('owner', 'current', 2, 0, '2024-02-01', 'dev',
                        (PublicTurn('seeker', 'Can we talk?'),))
    inventory = tuple((Resource(h, h, 'UNCHANGED ' + h, .7, 4, 'owner', 1,
        '2024-01-01', 'past', ('source',)),) for h in ('RS', 'MP', 'MS', 'ME'))
    spec = EpisodeSpec(prefix, inventory, 'retrieval-private', 'runtime', 'judge-private', 'draw', 10000)
    kwargs = dict(count_text=len, count_chat=lambda m: len(json.dumps(m)),
                  tokenizer_identity='test', context_limit=100000)
    return spec, DirectReplyRenderer(**kwargs), RSApplicabilityRenderer(**kwargs)


@pytest.mark.parametrize('counts', [(0,0,0,0), (0,1,0,0), (0,0,1,0), (0,0,0,1), (0,1,1,1)])
def test_no_rs_keeps_complete_input_and_cost_unchanged(counts):
    spec, old, new = fixture()
    assert old.messages(spec, counts) == new.messages(spec, counts)
    assert adapt_messages(old.messages(spec, counts), counts) == new.messages(spec, counts)
    assert old.cost(spec, counts) == new.cost(spec, counts)
    assert old.identity != new.identity


@pytest.mark.parametrize('counts', [(1,0,0,0), (1,1,1,1)])
def test_only_one_instruction_changes_and_is_charged(counts):
    spec, old, new = fixture()
    before, after = old.messages(spec, counts), new.messages(spec, counts)
    assert adapt_messages(before, counts) == after
    assert after[0]['content'].replace(INSTRUCTION, '', 1) == before[0]['content']
    assert after[-1] == before[-1]
    assert new.cost(spec, counts) - old.cost(spec, counts) == len(INSTRUCTION)
    tight = replace(spec, resource_budget=old.cost(spec, counts))
    assert old.fits(tight, counts) and not new.fits(tight, counts)
    assert 'judge-private' not in json.dumps(after) and 'retrieval-private' not in json.dumps(after)


def test_partial_double_or_misbound_input_rejected():
    spec, old, _ = fixture()
    messages = old.messages(spec, (1,0,0,0))
    with pytest.raises(ValueError): adapt_messages(messages, (0,1,0,0))
    truncated = deepcopy(messages); truncated[0]['content'] = truncated[0]['content'][:-4]
    with pytest.raises(ValueError): adapt_messages(truncated, (1,0,0,0))
    with pytest.raises(ValueError): adapt_messages(adapt_messages(messages, (1,0,0,0)), (1,0,0,0))


def jobs_fixture(tmp_path, total=2):
    spec, old, new = fixture()
    original = BoundResourceEnv(spec, old)._request((1,0,0,0))
    jobs = []
    for i in range(total):
        arm = 'baseline' if i % 2 == 0 else 'rs_applicability'
        request = paired_request(original, arm=arm,
            renderer_identity=old.identity if arm == 'baseline' else new.identity,
            draw_identity='new-batch-' + str(i))
        jobs.append(dict(slot_id='slot_' + str(i), row_id='synthetic', arm=arm,
            old_request_id=original['request_id'], request=request))
    protocol = dict(execution_dir=str(tmp_path / 'run'), max_generation_attempts=total)
    return protocol, jobs, original


class FakeGenerator:
    identity = 'runtime'
    def __init__(self, reason='natural_stop'):
        self.calls = 0
        self.reason = reason
    def generate(self, request):
        self.calls += 1
        return dict(request_id=request['request_id'], runtime_identity=self.identity,
            finish_reason=self.reason, text='Synthetic answer', api_cost_usd=0)


def test_new_request_binds_original_provenance_without_reusing_old_draw(tmp_path):
    _, jobs, original = jobs_fixture(tmp_path)
    for j in jobs:
        r = j['request']
        validate_and_project(r, 'runtime')
        assert r['request_id'] != original['request_id']
        assert r['provenance'] == original['provenance']
    assert jobs[0]['request']['messages'] == original['messages']


def test_completed_batch_reuses_all_records_without_calls_or_score(tmp_path):
    p, jobs, _ = jobs_fixture(tmp_path)
    g = FakeGenerator()
    r = execute_jobs(p, jobs, g, lambda: True)
    old = {f.name: f.read_bytes() for f in (tmp_path/'run').glob('*.json')}
    assert r['started_attempts'] == g.calls == 2 and r['eligible_for_reward'] is False
    assert all(row['q'] is None and row['m'] is None and row['U'] is None for row in r['rows'])
    execute_jobs(p, jobs, g, lambda: True)
    assert g.calls == 2
    assert old == {f.name: f.read_bytes() for f in (tmp_path/'run').glob('*.json')}


@pytest.mark.parametrize('reason', ['technical_timeout', 'context_exhausted', 'exception'])
def test_first_failure_stops_and_stays_counted_without_retry(tmp_path, reason):
    p, jobs, _ = jobs_fixture(tmp_path)
    g = FakeGenerator(reason)
    first = execute_jobs(p, jobs, g, lambda: True)
    assert first['status'] == 'STOP_TECHNICAL_FAILURE' and g.calls == 1
    assert len(list((tmp_path/'run').glob('*.started.json'))) == 1
    assert execute_jobs(p, jobs, g, lambda: True) == first and g.calls == 1


def test_unknown_started_result_never_retries(tmp_path):
    p, jobs, _ = jobs_fixture(tmp_path)
    save_once(tmp_path/'run/slot_0.started.json', dict(request_identity=jobs[0]['request']['request_id']))
    g = FakeGenerator()
    with pytest.raises(RuntimeError, match='unresolved'):
        execute_jobs(p, jobs, g, lambda: True)
    assert g.calls == 0


def test_changed_request_version_cannot_bypass_same_slot(tmp_path):
    p, jobs, _ = jobs_fixture(tmp_path)
    save_once(tmp_path/'run/slot_0.started.json', dict(request_identity='earlier-version'))
    g = FakeGenerator()
    with pytest.raises(ValueError, match='another request/version'):
        execute_jobs(p, jobs, g, lambda: True)
    assert g.calls == 0


def test_cap_and_gpu_refusal_do_not_dispatch_extra_requests(tmp_path):
    p, jobs, _ = jobs_fixture(tmp_path, 3)
    p['max_generation_attempts'] = 2
    g = FakeGenerator()
    with pytest.raises(RuntimeError, match='cap reached'):
        execute_jobs(p, jobs, g, lambda: True)
    assert g.calls == 2
    p2, jobs2, _ = jobs_fixture(tmp_path/'second')
    stopped = execute_jobs(p2, jobs2, g, lambda: False)
    assert stopped['status'] == 'STOP_GPU_GUARD' and g.calls == 2
    assert not list((tmp_path/'second/run').glob('*.started.json'))


def test_pending_or_wrong_protocol_is_not_an_execution_authorization():
    p = dict(gpu_uuid='frozen-card')
    a = dict(status='PENDING_RESEARCHER_APPROVAL', protocol_identity=digest(p),
        max_generation_attempts=16, max_new_judge_requests=0, max_api_cost_usd=0,
        gpu_uuid='frozen-card', user_instruction='offline preparation')
    with pytest.raises(ValueError): validate_authorization(p, a)
    a.update(status='RESEARCHER_APPROVED', protocol_identity='different')
    with pytest.raises(ValueError): validate_authorization(p, a)


def test_old_stop_or_output_never_overwritten(tmp_path):
    path = tmp_path/'old_STOP.json'
    save_once(path, {'reason':'old unresolved dispute'})
    with pytest.raises(ValueError): save_once(path, {'reason':'cleared'})
    assert json.loads(path.read_text())['reason'] == 'old unresolved dispute'


@pytest.mark.parametrize('preflight', [True, False])
def test_existing_runner_cannot_load_model_from_pending_package(tmp_path, monkeypatch, preflight):
    import importlib.util
    from types import SimpleNamespace
    import metacom_pm.rl1.rs_development as dispatch
    path = Path(__file__).resolve().parents[1] / 'scripts/rl1/92_run_p2_common_pool.py'
    spec = importlib.util.spec_from_file_location('p2_runner_test', path)
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    monkeypatch.setattr(dispatch, 'validate_package', lambda p: ({'gpu_uuid':'frozen-card'}, []))
    def forbidden(*a, **kw):
        pytest.fail('model loading was reached without execution authorization')
    monkeypatch.setattr(runner, 'load_frozen_generator', forbidden)
    auth = tmp_path/'pending.json'
    save_once(auth, {'status':'PENDING_RESEARCHER_APPROVAL'})
    args = SimpleNamespace(rs_package=tmp_path, preflight_only=preflight, execution_authorization=auth)
    if preflight:
        runner.run_rs_package(args)
    else:
        with pytest.raises(ValueError, match='execution authorization'):
            runner.run_rs_package(args)


def test_modified_cli_cannot_silently_rebuild_original_pool(tmp_path, monkeypatch):
    import importlib.util
    import sys
    path = Path(__file__).resolve().parents[1] / 'scripts/rl1/92_run_p2_common_pool.py'
    spec = importlib.util.spec_from_file_location('p2_runner_legacy_test', path)
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, 'OUT', tmp_path)
    monkeypatch.setattr(sys, 'argv', [str(path), '--preflight-only'])
    save_once(tmp_path/'primary_generation_pointer.json', {'run_dir':str(tmp_path/'old')})
    save_once(tmp_path/'old/protocol.json', {'runner_sha256':'original-frozen-code'})
    with pytest.raises(RuntimeError, match='refuse a new pool/replay'):
        runner.main()
    assert not (tmp_path/'generation').exists()


@pytest.mark.parametrize('version,cap', [
    ('pm-rl1-rs-paired-development-v1',16),
    ('pm-rl1-rs-additional-contexts-v1-20261019',41)])
def test_separate_fixed_cap_packages_and_authorizations(tmp_path,version,cap):
    from metacom_pm.io import sha256_file
    p,jobs,_=jobs_fixture(tmp_path,cap)
    save_once(tmp_path/'jobs_private.json',jobs)
    p.update(version=version,files={'jobs_private.json':sha256_file(tmp_path/'jobs_private.json')},
        source_files={},jobs_identity=digest(jobs),runtime={'identity':'runtime'},gpu_uuid='frozen-card')
    save_once(tmp_path/'protocol.json',p)
    assert validate_package(tmp_path)==(p,jobs)
    a=dict(protocol_identity=digest(p),status='RESEARCHER_APPROVED',max_generation_attempts=cap,
        max_new_judge_requests=0,max_api_cost_usd=0,gpu_uuid='frozen-card',user_instruction='synthetic test approval')
    validate_authorization(p,a)
    for wrong in (cap+1,cap-1):
        with pytest.raises(ValueError): validate_authorization(p,{**a,'max_generation_attempts':wrong})
    with pytest.raises(ValueError): validate_authorization(p,{**a,'protocol_identity':'prior-batch'})
    with pytest.raises(ValueError): validate_authorization(p,{**a,'status':'PENDING_RESEARCHER_APPROVAL'})


def test_additional_context_cap_cannot_relabel_original_16_batch():
    p=dict(version='pm-rl1-rs-paired-development-v1',max_generation_attempts=41,gpu_uuid='frozen-card')
    with pytest.raises(ValueError): validate_authorization(p,{'status':'RESEARCHER_APPROVED'})


def test_additional_context_mock_completes_41_once_and_never_scores(tmp_path):
    p,jobs,_=jobs_fixture(tmp_path,41)
    g=FakeGenerator()
    first=execute_jobs(p,jobs,g,lambda: True)
    assert first['started_attempts']==g.calls==41
    assert first['eligible_for_reward'] is False
    assert execute_jobs(p,jobs,g,lambda:True)==first and g.calls==41
    assert all(r['q'] is None and r['m'] is None and r['U'] is None for r in first['rows'])

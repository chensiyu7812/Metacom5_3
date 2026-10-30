from copy import deepcopy
import json
import socket

import pytest

from metacom_pm.rl1 import diagnostic_engine as engine, feedback_score_audit as audit
from metacom_pm.rl1 import strict_audit_delivery as strict
from metacom_pm.rl1.development_feedback import DevelopmentAdapter, OfflineDevelopmentStage, candidate_scores
from metacom_pm.rl1.schema import digest
import test_rl1_feedback_workflow as fixtures


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('offline test attempted network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


def adapter():
    return DevelopmentAdapter(prompt=engine.s.judge.RUBRIC, config=dict(thinking='enabled'))


def materials(n=2):
    return [dict(key=str(i), purpose='known_regression', **x) for i, x in enumerate(list(fixtures.fixture()[0].values())[::2][:n])]


def score(item, unknown=False):
    return fixtures.WorkflowIntegrationTests.score(None, item, unknown)


def review(item, preliminary, issue=False):
    v = fixtures.WorkflowIntegrationTests.audit(None, item)
    links = audit.score_texts(preliminary)
    checks = {}
    for name, path in [('quality', '/q_rationale/reason'), ('severity', '/assessments/0/reason'), ('coverage', '/coverage')]:
        checks[name] = dict(status='score_issue' if issue and name == 'quality' else 'supported',
            score_links=[dict(path=path, quote=links[path])], criterion='SYNTHETIC criterion', reason='SYNTHETIC')
    v['score_review'] = dict(preliminary_score_sha256=digest(preliminary), findings=[], checks=checks)
    return v


class Transport:
    synthetic_only = True

    def __init__(self, *, issue=False, unknown=False, fail_once=False, fail_all=False, crash=False):
        self.issue, self.unknown = issue, unknown
        self.fail_once, self.fail_all, self.crash = fail_once, fail_all, crash
        self.calls = []

    def send(self, request, *, attempt_id):
        self.calls.append(deepcopy(request))
        if self.crash: raise RuntimeError('injected interruption after durable claim')
        data = json.loads(request['wire_body']['messages'][1]['content'])
        item = dict(reply=data['reply'], evidence=data['legal_evidence'])
        value = (review(item, data['preliminary_score'], self.issue) if request['component'] == 'A'
                 else score(item, self.unknown))
        text = '{' if self.fail_all or self.fail_once and len(self.calls) == 1 else json.dumps(value)
        if request['component'] == 'A':
            choice = dict(message=dict(content=None, tool_calls=[dict(id='synthetic-tool', type='function',
                function=dict(name=strict.TOOL, arguments=text))]), finish_reason='tool_calls')
        else:
            choice = dict(message=dict(content=text), finish_reason='stop')
        return dict(synthetic_only=True, request_identity=request['identity'], adapter_identity=request['adapter_identity'],
                    transport='deepseek', delivery=strict.DELIVERY, choices=[choice])


def finish(stage, transport):
    for _ in range(stage.protocol['max_attempts'] + 1):
        result = stage.advance(transport)
        if result['status'] != 'ATTEMPT_RECORDED': return result
    raise AssertionError('stage did not close within fixed attempts')


def test_quality_only_issue_uses_current_schema_and_gets_one_resolution(tmp_path):
    t = Transport(issue=True); s = OfflineDevelopmentStage(tmp_path, materials(), adapter())
    out = finish(s, t)
    assert out['status'] == 'CLOSED_OFFLINE_REHEARSAL' and len(t.calls) == 6
    assert [r['component'] for r in t.calls] == ['S', 'S', 'A', 'A', 'R', 'R']
    request = t.calls[-1]; d = json.loads(request['wire_body']['messages'][1]['content'])
    assert d['machine_audit']['findings'] == []
    assert 'score_review' in d['machine_audit']
    assert request['wire_body']['messages'][0]['content'].endswith(json.dumps(request['local_schema'], ensure_ascii=False))
    assert all(m['A_resolution']['technical_valid'] for m in out['materials'])
    assert out['qualified_receipt'] is None and out['route_selected'] is None
    assert finish(OfflineDevelopmentStage(tmp_path, materials(), adapter()), t) == out
    assert len(t.calls) == 6


def test_retained_single_scores_no_unnecessary_resolution_and_content_dedup(tmp_path):
    ms = materials(1); ms += [dict(ms[0], key='other-G-identity')]
    t = Transport(); s = OfflineDevelopmentStage(tmp_path, ms, adapter())
    out = finish(s, t)
    assert len(t.calls) == 2 and s.protocol['unique_inputs'] == 1 and len(out['materials']) == 2
    assert all(m['routing']['action'] == 'retain_numeric_candidate' for m in out['materials'])


def test_uncertain_single_is_audited_but_never_becomes_zero(tmp_path):
    t = Transport(unknown=True); out = finish(OfflineDevelopmentStage(tmp_path, materials(1), adapter()), t)
    assert len(t.calls) == 3
    m = out['materials'][0]
    assert m['S_candidate']['model_unknown'] and m['A_resolution']['model_unknown']
    assert m['S_candidate']['q'] is None and m['A_resolution']['U'] is None
    assert not m['reward_eligible']


def test_settled_local_failure_continues_independent_input_then_bounded_recovery(tmp_path):
    t = Transport(fail_once=True); s = OfflineDevelopmentStage(tmp_path, materials(), adapter(), recovery_cap=1)
    out = finish(s, t)
    assert len(t.calls) == 5
    assert t.calls[0]['identity'] != t.calls[1]['identity']
    assert t.calls[0] == t.calls[2]
    assert sum(w.get('recovery_attempts', 0) for w in out['waves']) == 1
    assert len(list((tmp_path/'S').glob('*.raw.json'))) == 3


def test_recovery_exhaustion_and_configuration_circuit_do_not_reroll_forever(tmp_path):
    t = Transport(fail_all=True); s = OfflineDevelopmentStage(tmp_path, materials(), adapter())
    out = finish(s, t)
    assert len(t.calls) == 3
    assert all(m['S_candidate'] is None for m in out['materials'])
    assert out['waves'][0]['states'] and out['waves'][1]['slots'] == 0


def test_crash_is_outstanding_not_automatic_retry(tmp_path):
    t = Transport(crash=True); s = OfflineDevelopmentStage(tmp_path, materials(), adapter())
    with pytest.raises(RuntimeError): s.advance(t)
    again = OfflineDevelopmentStage(tmp_path, materials(), adapter())
    assert again.advance(t)['status'] == 'RECONCILIATION_REQUIRED'
    assert len(t.calls) == 1


def test_tampered_raw_changed_scope_and_live_transport_fail_closed(tmp_path):
    s = OfflineDevelopmentStage(tmp_path, materials(), adapter()); t = Transport()
    with pytest.raises(ValueError, match='live transport'): s.advance(object())
    finish(s, t)
    path = next((tmp_path/'S').glob('*.raw.json')); path.write_text('{}')
    with pytest.raises(ValueError, match='raw history'): s.advance(t)
    with pytest.raises(ValueError, match='journal'): OfflineDevelopmentStage(tmp_path, materials(1), adapter())


def test_complete_source_rubric_and_strict_tool_in_actual_body():
    a = adapter(); item = {k: materials(1)[0][k] for k in ('reply', 'evidence')}
    s = score(item); req = a.prepare(item, 'A', score=s)
    d = json.loads(req['wire_body']['messages'][1]['content'])
    assert d['legal_evidence'] == item['evidence'] and d['rubric_reference']['text'] == a.prompt
    assert req['wire_body']['tools'][0]['function']['strict'] is True
    with pytest.raises(ValueError): a.prepare(dict(item, human_label=3), 'S')
    with pytest.raises(ValueError): a.prepare(item, 'R', score=s, review=review(item, s))
    bad = review(item, s, True); bad['score_review']['preliminary_score_sha256'] = 'forged'
    with pytest.raises(Exception): a.prepare(item, 'R', score=s, review=bad)


def test_full_22_input_stage_including_all_conditional_repairs_closes(tmp_path):
    ms = []
    for i in range(22):
        x = deepcopy(materials(1)[0]); x['key'] = str(i)
        x['reply'] = f'Could we explore synthetic concern {i}?'
        x['purpose'] = 'known_regression' if i < 6 else 'new_development_not_independent_validation'
        ms.append(x)
    t = Transport(issue=True); out = finish(OfflineDevelopmentStage(tmp_path, ms, adapter()), t)
    assert len(t.calls) == 66 and len(out['materials']) == 22
    assert [(w['component'], w['slots']) for w in out['waves']] == [('S', 22), ('A', 22), ('R', 22)]
    assert out['real_calls'] == out['training_updates'] == 0


def test_recovery_allowance_is_shared_across_s_and_a_waves(tmp_path):
    class FailFirstEachWave(Transport):
        def send(self, request, *, attempt_id):
            first = all(r['component'] != request['component'] for r in self.calls)
            self.fail_all = first
            return super().send(request, attempt_id=attempt_id)
    t = FailFirstEachWave()
    out = finish(OfflineDevelopmentStage(tmp_path, materials(), adapter(), recovery_cap=1), t)
    assert sum(w.get('recovery_attempts', 0) for w in out['waves']) == 1
    assert len(t.calls) == 5  # S: failed + independent + recovery; A: failure + independent
    assert out['waves'][1]['states'].values() and 'RECOVERY_EXHAUSTED' in out['waves'][1]['states'].values()


def test_failed_or_uncertain_resolution_cannot_silently_reuse_single_score():
    p = dict(technical_valid=True, model_unknown=False, q=3, m=.25, U=.5)
    for resolution in (None, dict(technical_valid=False), dict(technical_valid=True, model_unknown=True)):
        result = candidate_scores(p, {'action':'supplement_candidate'}, resolution)
        assert result['S']['U'] == .5 and result['A'] is None
    retained = candidate_scores(p, {'action':'retain_numeric_candidate'}, None)
    assert retained['A'] == retained['S'] and retained['A_source'] == 'same_primary'

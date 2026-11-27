"""CPU tests for deterministic parts of the claim-support capability (no model weights)."""
from metacom_pm.rl1v3.semcap.claim_support import (render_attributed, render_scoped, render_tagged,
                                                    structured_reporter, combine, metrics)
EV = [dict(evidence_id='C0', speaker='seeker', text='I lost my job.', reported_at=None, origin='current_visible'),
      dict(evidence_id='C1', speaker='supporter', text='I have suffered from depression too.', reported_at=None, origin='current_visible'),
      dict(evidence_id='H1.T2', speaker='seeker', text='I start a new job tomorrow.', reported_at='2024-06-30', origin='actually_read_history')]


def test_renderers_keep_speaker_and_report_time():
    t = render_tagged(EV); a = render_attributed(EV)
    assert '[C0] (seeker; report None)' in t
    assert 'The seeker (the user) said: "I lost my job."' in a
    assert 'In a session reported on 2024-06-30, the seeker (the user) said' in a


def test_scoped_uses_only_reporter_turns():
    assert structured_reporter('The supporter says they lost their job.') == 'supporter'
    assert structured_reporter('The seeker has a job.') is None
    s = render_scoped(EV, 'supporter')
    assert 'depression' in s and 'lost my job' not in s
    assert render_scoped(EV, None) == render_attributed(EV)


def test_minicheck_not_supported_is_never_contradicted():
    assert combine(dict(supported=False), dict(verdict='unknown')) == 'unknown'
    assert combine(dict(supported=False), dict(verdict='contradicted')) == 'contradicted'
    assert combine(dict(supported=True), dict(verdict='contradicted')) == 'supported'


def test_metrics_counts_absence_as_negation():
    rows = [dict(reference='unknown', factor='unobserved', p='contradicted'),
            dict(reference='supported', factor='own', p='supported'),
            dict(reference='unknown', factor='subject_swap', p='supported')]
    m = metrics(rows, 'p')
    assert m['absence_as_negation'] == [1, 2] and m['subject_swap_false_pass'] == [1, 1] and m['false_pass'] == [1, 2]

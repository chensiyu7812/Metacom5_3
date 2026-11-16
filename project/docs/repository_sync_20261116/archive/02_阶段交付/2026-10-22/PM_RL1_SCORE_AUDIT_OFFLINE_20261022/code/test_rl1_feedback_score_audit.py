"""Score-aware audit candidate: offline fixtures, never provider calls or gold."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from metacom_pm.rl1 import feedback_score_audit as c, feedback_workflow as w
from metacom_pm.rl1.schema import digest
import test_rl1_feedback_workflow as fixtures


def example():
    score = dict(status='scored', q=3,
        q_rationale=dict(current_need='Listen and explore.', reason='Relevant but adds an unsupported location.'),
        assessments=[dict(response_unit_id='R001', relation='supported', severity=0,
                          source_turn_ids=['C:T000'], reason='The move is supported.'),
                     dict(response_unit_id='R001', relation='unsupported', severity=.25,
                          source_turn_ids=['C:T000'], reason='The household location is not supported; core advice unchanged.')],
        coverage='Both the move and its location were checked.', uncertainty_reasons=[])
    audit = dict(check=dict(status='checked'), findings=[dict(response_unit_id='R001',
        response_quote='The move at home', dimension='relation', verdict='identified_error',
        source_evidence=[dict(source_id='C:T000', quote='A friend is moving.')])])
    def link(path):
        return [dict(path=path, quote=c.score_texts(score)[path])]
    def check(path):
        return dict(status='supported', score_links=link(path), criterion='SYNTHETIC unchanged criterion', reason='SYNTHETIC test only')
    audit['score_review'] = dict(preliminary_score_sha256=digest(score), findings=[dict(
        finding_index=0, disposition='already_accounted', score_links=link('/assessments/1/reason'), reason='SYNTHETIC same location defect')],
        checks=dict(quality=check('/q_rationale/reason'), severity=check('/assessments/1/reason'), coverage=check('/coverage')))
    joint = dict(technical_valid=True, evaluation=dict(technical_valid=True, model_unknown=False, value=score, q=3, m=.25, U=.5))
    result = dict(technical_valid=True, evaluation=dict(technical_valid=True, value=audit, interface_version=c.INTERFACE))
    return joint, result


class Decisions(unittest.TestCase):
    def setUp(self):
        self.j, self.a = example()
        self.v = self.a['evaluation']['value']
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect', side_effect=AssertionError('offline network forbidden')).start()

    def test_accounted_reply_error_does_not_alone_request_another_score(self):
        before = deepcopy((self.j, self.a))
        self.assertTrue(w.flagged(self.j, self.a))
        out = c.decision(self.j, self.a)
        self.assertEqual(out['action'], 'retain_numeric_candidate')
        self.assertEqual(out['proposed_U'], .5)
        self.assertEqual((self.j, self.a), before)
        self.assertEqual(c.decision(self.j, self.a), out)
        self.assertFalse(out['execute'] or out['reward_eligible'] or out['training_ready'])

    def test_accounted_relation_does_not_silence_severity_or_quality_error(self):
        for key in ('severity', 'quality', 'coverage'):
            for status in ('score_issue', 'unresolved'):
                a = deepcopy(self.a)
                a['evaluation']['value']['score_review']['checks'][key]['status'] = status
                out = c.decision(self.j, a)
                self.assertEqual(out['action'], 'supplement_candidate')
                self.assertIn(f'{key}:{status}', out['reasons'])
                self.assertIsNone(out['proposed_U'])

    def test_omission_and_inconsistent_score_remain_candidates(self):
        self.v['score_review']['findings'][0]['disposition'] = 'score_issue'
        self.assertEqual(c.decision(self.j, self.a)['action'], 'supplement_candidate')

    def test_unknown_separate_from_reviewer_dispute_and_never_zero(self):
        for where in ('joint', 'audit'):
            j, a = deepcopy(self.j), deepcopy(self.a)
            if where == 'joint':
                j['evaluation'].update(model_unknown=True, q=None, m=None, U=None)
                j['evaluation']['value']['status'] = 'uncertain'
            else:
                a['evaluation']['value']['check']['status'] = 'uncertain'
            out = c.decision(j, a)
            self.assertEqual(out['action'], 'supplement_candidate')
            self.assertIsNone(out['proposed_U'])
        self.v['score_review']['checks']['quality']['status'] = 'unresolved'
        out = c.decision(self.j, self.a)
        self.assertEqual(out['reasons'], ['quality:unresolved'])
        self.assertFalse(self.j['evaluation']['model_unknown'])

    def test_technical_or_usage_failure_wins_over_accounted_or_unknown(self):
        self.j['evaluation']['model_unknown'] = True
        for change in ({'technical_valid': False}, {'hard_stop': 'usage unresolved'}):
            self.assertEqual(c.decision(self.j, self.a | change)['action'], 'hard_stop')
        self.assertEqual(c.decision(None, self.a)['action'], 'pending_dependency')

    def test_old_valid_audit_not_reclassified_as_new_interface(self):
        del self.v['score_review']
        self.assertEqual(c.decision(self.j, self.a)['action'], 'legacy_link_missing')
        self.assertTrue(w.flagged(self.j, self.a))

    def test_same_unit_and_sources_are_not_a_semantic_match(self):
        matches = c.association_candidates(self.j['evaluation']['value'], self.v)[0]
        self.assertEqual(len(matches['candidate_assessments']), 2)
        self.assertEqual([x['relation'] for x in matches['candidate_assessments']], ['supported', 'unsupported'])
        self.assertIsNone(matches['disposition'])
        self.assertFalse(matches['proves_same_claim'] or matches['proves_correct_score'])

    def test_forged_score_hash_quote_duplicate_or_missing_link_rejected(self):
        changes = [lambda x: x['score_review'].update(preliminary_score_sha256='0'*64),
                   lambda x: x['score_review']['findings'][0]['score_links'][0].update(quote='invented quote'),
                   lambda x: x['score_review']['findings'].append(deepcopy(x['score_review']['findings'][0])),
                   lambda x: x['score_review'].update(findings=[])]
        for change in changes:
            v = deepcopy(self.v); change(v)
            with self.assertRaises(Exception): c.validate_review(v, self.j['evaluation']['value'])
            a = deepcopy(self.a); a['evaluation']['value'] = v
            self.assertEqual(c.decision(self.j, a)['action'], 'hard_stop')

    def test_unresolved_and_error_cannot_be_disguised_as_no_issue(self):
        self.v['findings'][0]['verdict'] = 'unresolved'
        with self.assertRaises(ValueError): c.validate_review(self.v, self.j['evaluation']['value'])
        self.v['findings'][0]['verdict'] = 'identified_error'
        self.v['score_review']['findings'][0]['disposition'] = 'no_score_issue'
        with self.assertRaises(ValueError): c.validate_review(self.v, self.j['evaluation']['value'])

    def test_no_findings_still_requires_quality_severity_coverage_checks(self):
        self.v['findings'] = []; self.v['score_review']['findings'] = []
        self.v['score_review']['checks']['quality']['status'] = 'score_issue'
        self.assertEqual(c.decision(self.j, self.a)['action'], 'supplement_candidate')
        del self.v['score_review']['checks']['quality']
        with self.assertRaises(Exception): c.validate_review(self.v, self.j['evaluation']['value'])

    def test_numeric_targets_and_extra_properties_rejected(self):
        self.v['score_review']['expected_q'] = 4
        with self.assertRaises(Exception): c.validate_review(self.v, self.j['evaluation']['value'])


@unittest.skipUnless(fixtures.HAS_ENGINE, 'preserved private engine absent')
class Interface(unittest.TestCase):
    def setUp(self):
        self.p = fixtures.p
        self.item = fixtures.fixture()[0]['V1_OFF']
        self.score = fixtures.WorkflowIntegrationTests.score(self, self.item)
        # This fixture's score helper uses self.p only through module p.
        self.value = fixtures.WorkflowIntegrationTests.audit(self, self.item, True)
        self.value['findings'][0]['source_evidence'] = self.value['findings'][0].pop('evidence')
        j, a = example(); self.value['score_review'] = a['evaluation']['value']['score_review']
        rv = self.value['score_review']; rv['preliminary_score_sha256'] = digest(self.score)
        rv['findings'][0]['disposition'] = 'unresolved'
        rv['findings'][0]['score_links'] = [dict(path='/assessments/0/reason', quote='SYNTHETIC')]
        for name, path in [('quality', '/q_rationale/reason'), ('severity', '/assessments/0/reason'), ('coverage', '/coverage')]:
            rv['checks'][name]['score_links'] = [dict(path=path, quote='SYNTHETIC')]
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect', side_effect=AssertionError('no network')).start()
        patch('deepseek_access.read_key', side_effect=AssertionError('no credentials')).start()
        patch('deepseek_access.management_once', side_effect=AssertionError('no account')).start()

    def raw(self):
        return dict(transport='deepseek', choices=[dict(message=dict(content=json.dumps(self.value), reasoning_content='DO NOT READ'), finish_reason='stop')])

    def test_payload_has_one_exact_schema_and_complete_input_allowlist(self):
        messages, schema = c.audit_payload(self.item, self.score, self.p)
        data = json.loads(messages[1]['content'])
        self.assertEqual(set(data), {'legal_evidence', 'reply', 'response_units', 'preliminary_score', 'preliminary_score_sha256'})
        self.assertEqual(data['legal_evidence'], self.item['evidence']); self.assertEqual(data['reply'], self.item['reply'])
        self.assertTrue(messages[0]['content'].endswith(json.dumps(schema, ensure_ascii=False)))
        self.assertEqual(messages[0]['content'].count('matching this complete schema exactly:'), 1)
        self.p.input_guard(messages)

    def test_valid_source_evidence_and_score_links(self):
        self.assertTrue(c.evaluate_audit(self.raw(), self.item, self.score, self.p)['technical_valid'])

    def test_invalid_source_and_score_quotes_remain_failures(self):
        for target in ('source', 'score'):
            raw = self.raw(); value = json.loads(raw['choices'][0]['message']['content'])
            ref = value['findings'][0]['source_evidence'][0] if target == 'source' else value['score_review']['findings'][0]['score_links'][0]
            ref['quote'] = 'FABRICATED'
            raw['choices'][0]['message']['content'] = json.dumps(value)
            self.assertFalse(c.evaluate_audit(raw, self.item, self.score, self.p)['technical_valid'])

    def test_duplicate_truncation_and_extra_text_not_repaired(self):
        for change in ('duplicate', 'truncated', 'extra'):
            raw = self.raw(); choice = raw['choices'][0]
            if change == 'duplicate': choice['message']['content'] = choice['message']['content'].replace('{', '{"check":{},', 1)
            elif change == 'truncated': choice['finish_reason'] = 'length'
            else: choice['message']['content'] = 'Explanation\n' + choice['message']['content']
            self.assertFalse(c.evaluate_audit(raw, self.item, self.score, self.p)['technical_valid'])


if __name__ == '__main__': unittest.main()

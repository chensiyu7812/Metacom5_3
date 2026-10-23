"""Portable CPU tests: synthetic evidence only, no private assets or provider."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metacom_pm.rl1 import feedback_prototype as f
from metacom_pm.rl1.schema import digest


ITEM=dict(reply='Could we discuss this?',evidence=dict(current_date='2026-01-01',
    current_prefix=[dict(id='C:T000',role='seeker',text='I plan to talk tomorrow.')],legal_past_sessions=[]))


def slot(name='one',q=3,m=0,arm='A',rep=1):
    return dict(slot_id=name,reply_identity=digest(ITEM['reply']),evidence_identity=digest(ITEM['evidence']),
        arm=arm,repetition=rep,state='completed',result=dict(request_identity='request-'+name,technical_valid=True,
        evaluation=dict(technical_valid=True,model_unknown=False,q=q,m=m,U=q/4-m,pipeline_identity='fixed',
                        value=dict(uncertainty_reasons=[]))))


def review(s,**extra):
    return dict(slot_id=s['slot_id'],request_identity=s['result']['request_identity'],evidence_identity=s['evidence_identity'],
                raw_scores={k:s['result']['evaluation'][k] for k in ('q','m','U')},**extra)


class FeedbackPrototypeTests(unittest.TestCase):
    def test_candidate_not_qualified(self):
        r=f.observation(slot());self.assertEqual(r['candidate_U'],.75)
        self.assertFalse(r['reward_eligible']);self.assertFalse(r['automatic_audit_available'])

    def test_raw_not_mutated_by_review(self):
        s=slot();before=deepcopy(s)
        r=f.observation(s,review=review(s,reviewer_unresolved_types=['interpretation']))
        self.assertEqual(s,before);self.assertEqual(r['original']['U'],.75);self.assertIsNone(r['candidate_U'])

    def test_reviewer_ambiguity_not_model_unknown(self):
        s=slot();r=f.observation(s,review=review(s,reviewer_unresolved_types=['severity']))
        self.assertEqual(r['status'],'review_unresolved');self.assertFalse(r['model_unknown'])

    def test_nonblocking_watch_not_promoted_to_numeric_failure(self):
        s=slot();r=f.observation(s,review=review(s,additional_boundary_watch=['unconfirmed local extension']))
        self.assertEqual(r['status'],'candidate');self.assertTrue(r['reviewer']['watch'])

    def test_confirmed_error_not_cancelled_by_ambiguity(self):
        s=slot();r=f.observation(s,review=review(s,reviewer_unresolved_types=['interpretation'],confirmed_source_proven_checking_errors=['synthetic']))
        self.assertEqual(r['status'],'confirmed_error')

    def test_review_binding_mismatch(self):
        s=slot();r=review(s);r['request_identity']='other'
        with self.assertRaises(ValueError):f.observation(s,review=r)

    def test_unknown_nulls(self):
        s=slot();s['result']['evaluation'].update(model_unknown=True,q=None,m=None,U=None)
        self.assertEqual(f.observation(s)['status'],'model_unknown')
        s['result']['evaluation']['q']=0
        with self.assertRaises(ValueError):f.observation(s)

    def test_technical_not_semantic(self):
        s=slot();s['result']['technical_valid']=False;s['result']['evaluation']={}
        self.assertEqual(f.observation(s)['status'],'hard_stop')

    def test_missing_attempt_not_zero(self):
        s=slot();s['result']=None;s['state']='not_dispatched'
        self.assertEqual(f.observation(s)['status'],'not_started')
        s['state']='started_unresolved';self.assertEqual(f.observation(s)['status'],'hard_stop')

    def test_repeat_not_cross_arm(self):
        a=slot('a');b=slot('b',q=2,arm='B',rep=2)
        self.assertFalse(f.repeat_signals([a,b]));b['arm']='A'
        self.assertEqual(set(f.repeat_signals([a,b])),{'a','b'})

    def test_scale_and_utility_binding(self):
        for q,m in [(None,0),(True,0),(2,.5),(5,0),(2,float('nan'))]:
            with self.assertRaises(ValueError):f.scalar(q,m)
        s=slot();s['result']['evaluation']['U']=0
        with self.assertRaises(ValueError):f.observation(s)

    def pair(self):
        return dict(pair_id='fixture',arm='A',off_slot='off',on_slot='on',resource_tokens=200,
                    off_draw=1,on_draw=1,shared_on=False)

    def test_pair_reward_original_formula(self):
        r={'off':f.observation(slot('off',q=2)),'on':f.observation(slot('on'))}
        self.assertAlmostEqual(f.pair_feedback(self.pair(),r)['candidate_net'],.25-200/40960)

    def test_shared_off_pending_propagates(self):
        s=slot('off');r={'off':f.observation(s,review=review(s,reviewer_unresolved_types=['interpretation'])),
                          'on':f.observation(slot('on'))}
        x=f.pair_feedback(self.pair(),r);self.assertEqual(x['status'],'pending');self.assertIsNone(x['candidate_net'])
        self.assertIsNotNone(x['original_net'])

    def test_pair_rejects_changed_condition(self):
        r={'off':f.observation(slot('off')),'on':f.observation(slot('on',arm='B'))}
        with self.assertRaises(ValueError):f.pair_feedback(self.pair(),r)

    def batch(self): return [dict(trajectory_id=str(i),status='candidate') for i in range(16)]

    def test_whole_batch_waits_then_ends_without_dropping(self):
        b=self.batch();b[3]['status']='pending';ids=[r['trajectory_id'] for r in b]
        self.assertEqual(f.batch_state(b,expected_ids=ids)['state'],'WAIT_BOUNDED_RESOLUTION_BEHAVIOR_FROZEN')
        for kw in [dict(supplements_started=4),dict(review_minutes=120),dict(closed=True)]:
            r=f.batch_state(b,expected_ids=ids,**kw);self.assertEqual(r['state'],'END_BATCH_UNRESOLVED_NO_UPDATE')
            self.assertEqual(r['retained'],16);self.assertFalse(r['new_batch_sampling_allowed'])

    def test_complete_batch_does_not_authorize_updates(self):
        b=self.batch();r=f.batch_state(b,expected_ids=[x['trajectory_id'] for x in b])
        self.assertEqual(r['state'],'COMPLETE_CANDIDATE_BATCH_NOT_AUTHORIZED');self.assertFalse(r['update_allowed'])

    def test_omitted_or_duplicate_trajectory_rejected(self):
        b=self.batch();ids=[x['trajectory_id'] for x in b]
        for modified in [b[:-1],b[:-1]+[b[0]]]:
            with self.assertRaises(ValueError):f.batch_state(modified,expected_ids=ids)

    def test_execution_failure_never_resolved_by_batch_exception(self):
        b=self.batch();b[0]['status']='hard_stop';ids=[x['trajectory_id'] for x in b]
        self.assertEqual(f.batch_state(b,expected_ids=ids)['state'],'STOP_EXECUTION_FAILURE')

    def pending(self,key='one',confirmed=False):
        s=slot(key);return f.observation(s,review=review(s,reviewer_unresolved_types=['severity'],
            confirmed_source_proven_checking_errors=['synthetic'] if confirmed else []))

    def decision(self,root,key,outcome='retain_with_evidence'):
        claim=json.loads((Path(root)/(key+'.claim.json')).read_text())
        return dict(claim_identity=digest(claim),outcome=outcome,q=3,m=0,basis='Synthetic evidence application',
            source_bindings=[dict(source_id='C:T000',quote='I plan to talk tomorrow.')],
            provenance='synthetic_test_fixture',review_minutes=2)

    def test_resolution_append_only_restart_no_retry(self):
        with tempfile.TemporaryDirectory() as d:
            log=f.ResolutionLog(d,'fixture');r=self.pending();key=log.claim(r)
            restarted=f.ResolutionLog(d,'fixture')
            with self.assertRaises(ValueError):restarted.claim(r)
            dec=self.decision(d,key);v=log.finish(key,dec,ITEM)
            self.assertEqual(v['derived_U'],.75);self.assertFalse(v['reward_eligible'])
            self.assertEqual(log.finish(key,dec,ITEM),v)
            dec['q']=2;dec['outcome']='correct_under_original_scale'
            with self.assertRaises(ValueError):log.finish(key,dec,ITEM)

    def test_resolution_cap_counts_unfinished_claims(self):
        with tempfile.TemporaryDirectory() as d:
            log=f.ResolutionLog(d,'fixture')
            for i in range(4):log.claim(self.pending(str(i)))
            with self.assertRaises(ValueError):log.claim(self.pending('fifth'))

    def test_record_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            log=f.ResolutionLog(d,'fixture');r=self.pending();r['original']['q']=2
            with self.assertRaises(ValueError):log.claim(r)

    def test_human_time_caps_following_claims(self):
        with tempfile.TemporaryDirectory() as d:
            log=f.ResolutionLog(d,'fixture');key=log.claim(self.pending());dec=self.decision(d,key)
            dec['review_minutes']=120;log.finish(key,dec,ITEM)
            with self.assertRaises(ValueError):log.claim(self.pending('next'))

    def test_known_error_cannot_be_kept(self):
        with tempfile.TemporaryDirectory() as d:
            log=f.ResolutionLog(d,'fixture');key=log.claim(self.pending(confirmed=True))
            with self.assertRaises(ValueError):log.finish(key,self.decision(d,key),ITEM)

    def test_resolution_missing_evidence_or_changed_reply(self):
        with tempfile.TemporaryDirectory() as d:
            log=f.ResolutionLog(d,'fixture');key=log.claim(self.pending());dec=self.decision(d,key)
            dec['source_bindings'][0]['quote']='never said'
            with self.assertRaises(ValueError):log.finish(key,dec,ITEM)
            dec=self.decision(d,key)
            with self.assertRaises(ValueError):log.finish(key,dec,dict(ITEM,reply='different'))

    def test_still_unresolved_stays_null(self):
        with tempfile.TemporaryDirectory() as d:
            log=f.ResolutionLog(d,'fixture');key=log.claim(self.pending());dec=self.decision(d,key,'still_unresolved')
            dec.update(q=None,m=None);v=log.finish(key,dec,ITEM);self.assertIsNone(v['derived_U'])

    def test_technical_or_candidate_never_auto_retried(self):
        with tempfile.TemporaryDirectory() as d:
            log=f.ResolutionLog(d,'fixture')
            for s in ['hard_stop','candidate']:
                r=self.pending();r['status']=s
                with self.assertRaises(ValueError):log.claim(r)

    def test_reward_magnitude_not_policy_effect(self):
        r=f.return_sensitivity(-.7547607421875,-1.5047607421875)
        self.assertEqual(r['delta_raw_advantage'],-.75)
        self.assertFalse(r['actual_optimizer_or_policy_change_inferred'])
        self.assertGreater(r['value_squared_error_after'],r['value_squared_error_before'])


if __name__=='__main__':unittest.main()

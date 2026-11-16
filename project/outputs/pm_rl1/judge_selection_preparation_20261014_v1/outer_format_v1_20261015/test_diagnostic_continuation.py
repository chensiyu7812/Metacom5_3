"""Bounded dispatch policy regression; synthetic transport, no GPU or network."""
import copy,unittest
from pathlib import Path
from unittest.mock import patch
import selection as s
import continue_v1 as c
from adapters import MockTransport
from test_development_continuation import DevelopmentContinuationTests

class DiagnosticContinuationTests(DevelopmentContinuationTests):
    def setUp(self):
        super().setUp()
        self.p=c.protocol(self.plan,diagnostic=True)
        previous=s.read(s.HERE/'AB_development_20261015/protocol.json')
        oldrows=s.read(s.HERE/'AB_development_20261015/results_private.json')['rows']
        self.refs=[]
        for row in oldrows:
            if not row['started_this_stage']:continue
            req=next(r for r in previous['requests'] if r['request_id']==row['actual_request_id'])
            orig=next(r for r in self.plan['requests'] if r['request_id']==req['original_slot_request_id'])
            folder=self.root/previous['output_subdir']/req['candidate'];base=folder/req['request_id']
            messages,schema=s.payload(self.plan,orig)
            raw=MockTransport(self.plan).send(messages,schema,request=orig,raw_path=None)
            raw['request_identity']=req['request_id']
            s.save(base.with_suffix('.started.json'),dict(request=req,mode='mock'))
            s.save(base.with_suffix('.response.json'),raw)
            evaluation=c.interface.evaluate(self.plan,orig,raw,req['configuration_identity'],req['request_id'])
            s.save(base.with_suffix('.result.json'),dict(request=req,mode='mock',evaluation=evaluation))
            if orig['item_key']=='dev04B':
                stop=folder/'STOP.json';review=self.root/previous['output_subdir']/'stage'/(req['request_id']+'.review.json')
                s.save(stop,dict(request_id=req['request_id'],reason='source-bound semantic hard stop'))
                s.save(review,self.review(req,orig,base.with_suffix('.response.json'),unknown=True))
                ref={'request_id':req['request_id']}
                for name,path in [('stop',stop),('review',review),('response',base.with_suffix('.response.json')),('result',base.with_suffix('.result.json'))]:
                    ref[name+'_path']=str(path);ref[name+'_sha256']=s.sha(path)
                self.refs.append(ref)
        self.auth=dict(historical_unknown_stops=self.refs)
        self.before={str(f):s.sha(f) for f in self.root.rglob('*.json')}

    def review(self,req,orig,path,unknown=False,material=False,equivalent=False,other=False):
        return dict(request_id=req['request_id'],item_key=orig['item_key'],response_sha256=s.sha(path),
            explanation='synthetic diagnostic test, not a research finding',source_checks=[],
            material_source_proven_error=material,critical_unknown=unknown,
            unexplained_equivalence_difference=equivalent,other_hard_stop_reasons=['synthetic other stop'] if other else [],
            hard_stop_evidence=[dict(claim='synthetic',source='synthetic',criterion='synthetic')] if material else [])

    def run_diagnostic(self,name,*,unknown=True,material=False,equivalent=False,other=False,technical=False):
        outer=self
        class Mock:
            load_seconds=0
            def gpu_condition(self):return 'mock'
            def send(self,messages,schema,*,request,raw_path):
                outer.calls.append(request)
                if technical and request['candidate']==s.CANDIDATES[0]:raise TimeoutError('mock')
                orig=next(x for x in outer.plan['requests'] if x['request_id']==request['original_slot_request_id'])
                raw=MockTransport(outer.plan).send(messages,schema,request=orig,raw_path=None)
                raw['request_identity']=request['request_id'];return raw
        def review(req,orig,path):
            affected=req['candidate']==s.CANDIDATES[0]
            return self.review(req,orig,path,unknown=unknown,material=material and affected,
                equivalent=equivalent and affected,other=other and affected)
        out=self.root/name;out.mkdir()
        with patch.object(c,'validate_release',return_value=list(s.CANDIDATES[:2])):
            return c.run(self.plan,self.p,self.auth,self.root,out,mode='mock',preflight=lambda:None,
                wait_idle=lambda:dict(eligible=True),transport_factory=lambda _:Mock(),review_fn=review)

    def test_only_unknown_and_new_same_class_continue_all58_to146(self):
        result=self.run_diagnostic('run')
        self.assertEqual(len(self.calls),58);self.assertEqual(result['history_after']['cumulative_calls'],146)
        for candidate in s.CANDIDATES[:2]:
            rows=[r for r in self.calls if r['candidate']==candidate]
            self.assertEqual(len(rows),29);self.assertEqual(sum(r['draw']=='repeat-1' for r in rows),4)
        for path,sha in self.before.items():self.assertEqual(s.sha(path),sha)
        self.run_diagnostic('again');self.assertEqual(len(self.calls),58)
        decisions=[s.read(f) for f in (self.root/'run').glob('*.diagnostic.json')]
        self.assertEqual(len(decisions),58)
        self.assertTrue(all(d['diagnostic_continuation'] and not d['reward_eligible'] and not d['usable_for_qualification'] for d in decisions))
        self.assertTrue(all(d['model_unknown'] and d['q'] is None and d['m'] is None and d['U'] is None for d in decisions))

    def test_unknown_with_material_error_stops_only_affected(self):
        result=self.run_diagnostic('both',material=True)
        self.assertEqual(len(self.calls),30);self.assertIn(s.CANDIDATES[0],result['blocked'])
        self.assertEqual(result['history_after']['cumulative_calls'],118)

    def test_unknown_with_equivalence_or_other_still_hard_stops(self):
        for flag in ('equivalent','other'):
            measurement=dict(measurement_status='measured_candidate',q=4,m=0,candidate_utility=1)
            r=dict(material_source_proven_error=False,critical_unknown=True,unexplained_equivalence_difference=flag=='equivalent',other_hard_stop_reasons=['x'] if flag=='other' else [])
            d=c.diagnostic_disposition(r,measurement);self.assertTrue(d['hard_stop']);self.assertFalse(d['diagnostic_continuation'])

    def test_technical_failure_never_overridden_or_retried(self):
        self.run_diagnostic('technical',technical=True);self.assertEqual(len(self.calls),30)
        self.run_diagnostic('again');self.assertEqual(len(self.calls),30)

    def test_model_unknown_separate_from_reviewer_unknown(self):
        r=dict(material_source_proven_error=False,critical_unknown=False,unexplained_equivalence_difference=False)
        d=c.diagnostic_disposition(r,dict(measurement_status='semantic_uncertainty',q=None,m=None,candidate_utility=None))
        self.assertTrue(d['model_unknown']);self.assertFalse(d['reviewer_unresolved_ambiguity']);self.assertIsNone(d['U'])

    def test_old_STOP_permission_does_not_cover_other_or_changed_STOP(self):
        ref=self.refs[0];review=s.read(ref['review_path']);review['material_source_proven_error']=True
        Path(ref['review_path']).write_text(s.canonical(review));ref['review_sha256']=s.sha(ref['review_path'])
        with self.assertRaises(ValueError):c.diagnostic_permissions(self.plan,self.p,self.auth,self.root)

    def test_cross_version_duplicate_original_slot_is_rejected(self):
        r=self.p['requests'][0]
        s.save(self.root/self.p['output_subdir']/r['candidate']/(r['request_id']+'.started.json'),dict(request=r,mode='mock'))
        with self.assertRaises(ValueError):c.reconstruct(self.plan,self.p,self.root,'mock')

    def test_policy_uniform_ABCD_and_not_reward_authority(self):
        for candidate in s.CANDIDATES:
            r=dict(candidate=candidate,material_source_proven_error=False,critical_unknown=True,unexplained_equivalence_difference=False)
            for q in (0,4):
                d=c.diagnostic_disposition(r,dict(measurement_status='measured_candidate',q=q,m=0,candidate_utility=q/4))
                self.assertTrue(d['diagnostic_continuation']);self.assertFalse(d['reward_eligible'])
        self.assertEqual(self.p['max_new_calls'],58);self.assertEqual(self.p['cumulative_cap'],146)
        self.assertTrue(self.p['diagnostic_policy']['post_outcome_amendment'])

# Inherited historical scheduling tests exercise a different 74-call fixture;
# run them in their original class rather than on the 88-call diagnostic fixture.
for _name in list(DevelopmentContinuationTests.__dict__):
    if _name.startswith('test_'):
        setattr(DiagnosticContinuationTests,_name,None)

if __name__=='__main__':unittest.main()

import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import outer_format_v1 as f
import continue_v1 as c
import selection as s
from adapters import MockTransport
from resume_engineering import slots

class FormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=s.load_plan();cls.req=slots(cls.plan)[0]
        messages,schema=s.payload(cls.plan,cls.req)
        cls.raw=MockTransport(cls.plan).send(messages,schema,request=cls.req,raw_path=None)
        cls.value=json.loads(cls.raw['native_parsed']['content'])
    def evaluate(self,text,raw=None):
        raw=copy.deepcopy(raw or self.raw);raw['native_parsed']['content']=text
        return f.evaluate(self.plan,self.req,raw,'new-config','new-draw')
    def test_bare_exact_bytes(self):
        text=' \n'+json.dumps(self.value,indent=3)+'\n '
        body,_,audit=f.unwrap(text);self.assertEqual(body,text)
        self.assertEqual(self.evaluate(text)['validation_stage'],'complete')
    def test_json_and_unlabelled_single_fence(self):
        text=json.dumps(self.value,indent=2)
        for label in ('json',''):
            source=' \t```'+label+'\n'+text+'\n```\n'
            body,_,a=f.unwrap(source);self.assertEqual(body,text)
            self.assertEqual(self.evaluate(source)['validation_stage'],'complete')
    def test_CRLF_preserves_interior(self):
        body='{\r\n "x": 2\r\n}'
        self.assertEqual(f.unwrap('```json\r\n'+body+'\r\n```')[0],body)
    def test_extra_explanation_and_multiple_fences_rejected(self):
        fence='```json\n{}\n```'
        for t in ['Here: '+fence,fence+' done',fence+'\n'+fence,'text {}','{} {}']:
            with self.subTest(t=t),self.assertRaises(ValueError):f.unwrap(t)
    def test_truncated_or_unsupported_envelope_rejected(self):
        for t in ['```json\n{}','```json\n{}\n``','```python\n{}\n```','```json {} ```','```\n{\n```']:
            with self.subTest(t=t),self.assertRaises(ValueError):f.unwrap(t)
    def test_invalid_JSON_not_repaired(self):
        for t in ["{'x':1}",'{"x":1,}','{"x":NaN}','{"x":1,"x":2}','[]','{"x":']:
            with self.subTest(t=t),self.assertRaises(ValueError):f.unwrap(t)
    def test_schema_failure(self):
        value=copy.deepcopy(self.value);value['extra']='do not delete'
        out=self.evaluate('```json\n'+json.dumps(value)+'\n```')
        self.assertEqual(out['validation_stage'],'schema');self.assertIsNone(out['measurement']['q'])
    def test_illegal_source_and_reply_ID_fail(self):
        for field in ['source_turn_ids','response_unit_ids']:
            value=copy.deepcopy(self.value);value['q_rationale'][field]=['UNKNOWN']
            out=self.evaluate(json.dumps(value));self.assertNotEqual(out['validation_stage'],'complete')
            self.assertIsNone(out['measurement']['candidate_utility'])
    def test_strict_evidence_validator_still_runs(self):
        # Schema accepts a whitespace-only reason; the original parser rejects it.
        value=copy.deepcopy(self.value);value['assessments'][0]['reason']=' '
        out=self.evaluate(json.dumps(value));self.assertEqual(out['validation_stage'],'strict_parser_and_evidence')
        self.assertNotIn(out['measurement']['measurement_status'],s.VALID)
    def test_non_natural_end_never_recovered(self):
        raw=copy.deepcopy(self.raw);raw['natural_eos']=False
        out=self.evaluate('```json\n'+json.dumps(self.value)+'\n```',raw)
        self.assertEqual(out['validation_stage'],'natural_end_failed')
    def test_thinking_not_extracted(self):
        raw=copy.deepcopy(self.raw);raw['native_parsed']['thinking']=json.dumps(self.value)
        self.assertNotEqual(self.evaluate('not JSON',raw)['validation_stage'],'complete')
    def test_rules_same_ABCD(self):
        for candidate in s.CANDIDATES:
            req=next(r for r in self.plan['requests'] if r['candidate']==candidate and r['item_key']=='dev02B')
            messages,schema=s.payload(self.plan,req);raw=MockTransport(self.plan).send(messages,schema,request=req,raw_path=None)
            if raw['transport']=='gemma':raw['native_parsed']['content']='```json\n'+json.dumps(self.value)+'\n```'
            else:raw['choices'][0]['message']['content']='```json\n'+json.dumps(self.value)+'\n```'
            self.assertEqual(f.evaluate(self.plan,req,raw,'new','draw')['validation_stage'],'complete')
    def test_derived_reexecution_idempotent_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'derived.json';self.assertTrue(f.reparse_once(path,{'derived':1}))
            h=s.sha(path);self.assertFalse(f.reparse_once(path,{'derived':1}));self.assertEqual(h,s.sha(path))
            with self.assertRaises(ValueError):f.reparse_once(path,{'derived':2})

class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.plan=s.load_plan();self.p=c.protocol(self.plan);self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup);s.save(self.root/'engineering.AB.stage_result.json',{'historical':'blocked'})
        for req in slots(self.plan)[:2]:
            folder=self.root/req['candidate'];folder.mkdir();base=folder/req['request_id']
            s.save(base.with_suffix('.started.json'),dict(request=req,mode='mock'))
            s.save(base.with_suffix('.result.json'),dict(request=req,mode='mock'))
            s.save(folder/'STOP.json',dict(request_id=req['request_id'],reason='parse_or_evidence_failure'))
        self.calls=[]
    def run_mock(self,name,fail_at=None,hard_stop_candidate=None,wait=True):
        outer=self
        class Mock:
            load_seconds=0
            def gpu_condition(self):return 'mock'
            def send(self,messages,schema,*,request,raw_path):
                outer.calls.append(request['request_id'])
                if len(outer.calls)==fail_at:raise TimeoutError('mock no retry')
                orig=next(x for x in outer.plan['requests'] if x['request_id']==request['original_slot_request_id'])
                raw=MockTransport(outer.plan).send(messages,schema,request=orig,raw_path=None)
                raw['request_identity']=request['request_id'];return raw
        def review(req,orig,path):
            return dict(request_id=req['request_id'],item_key=orig['item_key'],response_sha256=s.sha(path),
                explanation='MOCK source review only',source_checks=[],material_source_proven_error=req['candidate']==hard_stop_candidate,
                critical_unknown=False,unexplained_equivalence_difference=False)
        out=self.root/name;out.mkdir()
        with patch.object(c,'validate_release',return_value=list(s.CANDIDATES[:2])):
            return c.run(self.plan,self.p,{},self.root,out,mode='mock',preflight=lambda:None,
                wait_idle=lambda:dict(eligible=wait),transport_factory=lambda _:Mock(),review_fn=review)
    def test_four_new_configuration_identities_and_same_generation_fields(self):
        for name,old in self.plan['configs'].items():
            new=self.p['configs'][name];self.assertNotEqual(new['identity'],old['identity'])
            self.assertEqual(new['output_interface']['identity'],f.identity()['identity'])
            for k,v in old.items():
                if k!='identity':self.assertEqual(new[k],v)
    def test_six_remaining_in_original_order_and_counter_74(self):
        before={str(x):s.sha(x) for x in self.root.rglob('*.json')}
        out=self.run_mock('one');self.assertEqual(len(self.calls),6);self.assertEqual(out['history_after']['cumulative_calls'],74)
        self.assertEqual(self.calls,[x['request_id'] for x in self.p['requests'][2:]])
        for name,h in before.items():self.assertEqual(s.sha(name),h)
    def test_repeat_run_skips_all_versions(self):
        self.run_mock('one');out=self.run_mock('two');self.assertEqual(len(self.calls),6)
        self.assertEqual(out['history_after']['started_or_evidenced'],8)
    def test_GPU_block_then_continue_preserves_no_calls(self):
        a=self.run_mock('blocked',wait=False);self.assertEqual(a['history_after']['cumulative_calls'],68)
        h=s.sha(self.root/'blocked/stage_result.json');b=self.run_mock('resumed')
        self.assertEqual(b['history_after']['cumulative_calls'],74);self.assertEqual(h,s.sha(self.root/'blocked/stage_result.json'))
    def test_technical_failure_stops_only_affected_and_counts(self):
        out=self.run_mock('one',fail_at=1);self.assertEqual(len(self.calls),4)
        self.assertEqual(out['history_after']['cumulative_calls'],72)
        self.assertIn(s.CANDIDATES[1],out['blocked'])
    def test_semantic_stop_not_overridden_by_format(self):
        out=self.run_mock('one',hard_stop_candidate=s.CANDIDATES[1]);self.assertEqual(len(self.calls),4)
        self.assertIn(s.CANDIDATES[1],out['blocked'])
    def test_cross_version_duplicate_slot_rejected(self):
        r=self.p['requests'][0];path=self.root/c.SUBDIR/r['candidate']/(r['request_id']+'.started.json')
        s.save(path,dict(request=r,mode='mock'))
        with self.assertRaises(ValueError):c.reconstruct(self.plan,self.p,self.root,'mock')
    def test_started_without_result_never_retried(self):
        r=self.p['requests'][2];s.save(self.root/c.SUBDIR/r['candidate']/(r['request_id']+'.started.json'),dict(request=r,mode='mock'))
        out=self.run_mock('one');self.assertNotIn(r['request_id'],self.calls)
        self.assertEqual(out['history_after']['cumulative_calls'],72)
    def test_orphan_output_counts_and_blocks(self):
        r=self.p['requests'][2];s.save(self.root/c.SUBDIR/r['candidate']/(r['request_id']+'.raw.json'),{})
        out=self.run_mock('one');self.assertNotIn(r['request_id'],self.calls);self.assertEqual(out['history_after']['cumulative_calls'],72)
    def test_unknown_version_evidence_fails_closed(self):
        s.save(self.root/'new-unknown.started.json',{})
        with self.assertRaises(ValueError):c.reconstruct(self.plan,self.p,self.root,'mock')

if __name__=='__main__':unittest.main()

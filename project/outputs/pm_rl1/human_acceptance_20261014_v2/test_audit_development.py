import copy
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1 import human_calibration as hc
from audit_development import audit_fields, decrypt_development
from analyze_development import calculate


class AuditTests(unittest.TestCase):
    def test_sealed_guard_precedes_crypto(self):
        class Trap:
            @staticmethod
            def decrypt_item(*a,**k): raise AssertionError('crypto must not be called')
        log=[]
        with self.assertRaisesRegex(ValueError,'held-out'):
            decrypt_development({'item_id':'sealed'},mapping={'sealed':{'group':'validation'}},
                form={},key=None,hc=Trap,access_log=log)
        self.assertEqual(log,[])

    def test_real_48_sealed_envelopes_all_rejected_before_crypto(self):
        packet=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P3/calibration'
        class Trap:
            @staticmethod
            def decrypt_item(*a,**k): raise AssertionError('crypto must not be called')
        attempted=0
        for slot,name in [('rater_1','Chen'),('rater_2','Du')]:
            m=json.loads((packet/(slot+'_map_private.json')).read_text())
            sub=json.loads((HERE/'intake/originals'/('PM_RL1_'+name+'_pending_review.json')).read_text())
            for e in sub['items']:
                if m[e['item_id']]['group']=='validation':
                    with self.assertRaisesRegex(ValueError,'held-out'):
                        decrypt_development(e,mapping=m,form={},key=None,hc=Trap,access_log=[])
                    attempted+=1
        self.assertEqual(attempted,48)

    def test_missing_risk_does_not_erase_preference(self):
        item={'item_id':'x','A':'alpha','B':'beta'}
        label=dict(item_id='x',preference='A',risk_A='',risk_B='none_detected',quote_A='',quote_B='',source_ids=[],reason='preference supplied',uncertainty='')
        original=copy.deepcopy(label)
        result=audit_fields(label,item,{'current_prefix':[],'legal_past_sessions':[]},hc)
        self.assertTrue(result['preference_comparable']);self.assertFalse(result['strict_valid'])
        self.assertFalse(result['risk_A_comparable']);self.assertEqual(label,original)

    def test_nonzero_without_evidence_is_not_confirmed_risk(self):
        item={'item_id':'x','A':'alpha','B':'beta'}
        label=dict(item_id='x',preference='',risk_A='severe',risk_B='none_detected',quote_A='',quote_B='',source_ids=[],reason='could prefer alpha',uncertainty='')
        result=audit_fields(label,item,{'current_prefix':[],'legal_past_sessions':[]},hc)
        self.assertFalse(result['preference_comparable'])
        self.assertTrue(result['risk_A_comparable']);self.assertFalse(result['risk_A_evidence_ready'])
        self.assertEqual(label['preference'],'')

    def test_actual_statistics_and_no_duplicate_rater_denominator(self):
        s=calculate(HERE/'intake')
        t=s['totals'];self.assertEqual((t['pairs'],t['preference_pairs'],t['strict_complete']),(16,15,11))
        self.assertEqual((t['risk_enum_sides'],t['risk_evidence_ready_sides']),(26,22))
        n=next(r for r in s['preference_strata'] if r['group']=='自然')
        self.assertEqual((n['pairs'],n['ties'],n['tie_matches'],n['clear'],n['clear_matches']),(8,7,5,1,0))
        self.assertIsNone(t['independent_interrater_agreement'])

    def test_all_actual_label_audits_agree_with_original_validator(self):
        packet=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P3/calibration'
        forms={s:json.loads((packet/(s+'_form.json')).read_text()) for s in ('rater_1','rater_2')}
        rows=json.loads((HERE/'intake/development_item_audit_private.json').read_text())
        for r in rows:
            f=forms[r['slot']];item=next(i for i in f['items'] if i['item_id']==r['item_id'])
            actual=audit_fields(r['label'],item,f['sources'][item['source_key']],hc)
            self.assertEqual(actual['strict_valid'],r['strict_valid'])
            self.assertEqual(actual['errors'],r['errors'])
        self.assertEqual(len(rows),32)

    def test_du_copy_mapping_and_text_preservation(self):
        d=json.loads((HERE/'intake/Du_AB_provenance_private.json').read_text())
        self.assertEqual(len(d),16);self.assertTrue(all(r['derived_fields_match'] for r in d))
        self.assertEqual(sum(r['sides_swapped'] for r in d),7)
        self.assertTrue(all(r['free_text_reference_frame']=='Chen/rater_1' for r in d))


if __name__=='__main__':unittest.main()

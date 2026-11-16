import unittest,copy
from bindings import match_pair,without_translation
class BindingTests(unittest.TestCase):
    def setUp(self):
        self.p={'left_endpoint':'L','right_endpoint':'R'};self.es={'L':{'reply_identity':'x','evidence_identity':'ctx'},'R':{'reply_identity':'y','evidence_identity':'ctx'}}
        self.r=dict(group='development',reviewer='Chen',provenance={'observation_origin':'Chen-saved-browser-record'},evidence_identity='ctx',reply_identities={'A':'x','B':'y'},raw_label={'preference':'A','reason':'original'},item_id='item',pair_id='pair',identity='intake',raw_source={'path':'original'})
    def test_direct(self):self.assertEqual(match_pair(self.p,self.es,self.r)['current_display_preference'],'A')
    def test_swap_by_hash_not_letter(self):
        self.r['reply_identities']={'A':'y','B':'x'};self.assertEqual(match_pair(self.p,self.es,self.r)['current_display_preference'],'B')
    def test_other_context_is_not_reusable(self):
        self.r['evidence_identity']='different';self.assertIsNone(match_pair(self.p,self.es,self.r))
    def test_single_overlap_not_pair(self):
        self.r['reply_identities']['B']='z';self.assertIsNone(match_pair(self.p,self.es,self.r))
    def test_unknown_not_tie(self):
        self.r['raw_label']['preference']='unknown';self.assertEqual(match_pair(self.p,self.es,self.r)['current_display_preference'],'unknown')
    def test_du_not_independent(self):
        self.r['reviewer']='Du';self.assertIsNone(match_pair(self.p,self.es,self.r))
    def test_sealed_not_opened_by_join(self):
        self.r['group']='validation';self.assertIsNone(match_pair(self.p,self.es,self.r))
    def test_empty_pair_does_not_use_q(self):
        self.r['raw_label']={'preference':'','q_A':4,'q_B':2};self.assertIsNone(match_pair(self.p,self.es,self.r))
    def test_no_mutation(self):
        saved=copy.deepcopy(self.r);match_pair(self.p,self.es,self.r);self.assertEqual(self.r,saved)
    def test_english_preserved(self):
        self.assertEqual(without_translation({'turns':[{'text':'Did you find','zh':'中文'}]}),{'turns':[{'text':'Did you find'}]})
if __name__=='__main__':unittest.main()

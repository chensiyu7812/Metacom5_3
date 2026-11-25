"""Critical source-only/time/stage regression tests, no model or fabricated outcome."""
from dataclasses import replace
import pytest
from metacom_pm.rl1v3.journal.representations import quote_allowlist,stage_of,sentences,SELECTION,verify_span,span_retained
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import sha256_text


def test_gold_and_claim_canaries_do_not_cross_source_allowlist():
    row={'task_id':'x','gold':'DO_NOT_COPY','atoms':[{'atom_id':'a','claim':'DO_NOT_COPY','source_evidence':[{
        'owner_id':'u','session_id':'s','ordinal_turn':0,'original_idx':1,'speaker':'seeker',
        'start_char':0,'end_char':3,'exact_quote':'abc','reported_at':'2024-01-01','temporal_legal_strict':True}]}]}
    got=quote_allowlist([row])
    assert 'DO_NOT_COPY' not in str(got)
    row['gold']='DIFFERENT';row['atoms'][0]['claim']='OTHER'
    assert quote_allowlist([row])==got


def test_missing_evidence_atom_kept_for_private_unsupported_accounting():
    row={'task_id':'x','atoms':[{'atom_id':'unsupported','claim':'secret','source_evidence':[]}]}
    assert quote_allowlist([row])['x']['atom_ids']==['unsupported']


@pytest.mark.parametrize('text,speaker,want',[
    ('I actually have a ticket booked for the weekend.','seeker','intended'),
    ('I just received an internship offer.','seeker','completed'),
    ('I decided to start writing tomorrow.','seeker','intended'),
    ('I decided to turn down the job offer.','seeker','rejected'),
    ('You could try writing a journal.','supporter','suggested'),
    ('I am hoping this time off gives me more chances to paint.','seeker','intended'),
    ('The painting has been helping me.','seeker','outcome_reported'),
    ('I went there.','supporter','unknown'),
])
def test_stage_preserves_actor_intention_and_outcome_boundaries(text,speaker,want):
    assert stage_of(text,speaker)==want


def test_sentence_offsets_preserve_unicode_and_all_source_characters():
    text='  I felt “worried”.  I am still unsure! Next week?'
    ref=K.SourceSpan(source_key='d:u:s:0',owner_id='u',session_id='s',source_rank=1,turn_index=0,
        speaker='seeker',start_char=5,end_char=5+len(text),exact_quote=text,raw_turn_sha256=sha256_text('xxxxx'+text))
    for sent in sentences(ref):
        assert ('xxxxx'+text)[sent.start_char:sent.end_char]==sent.exact_quote
    assert len(sentences(ref))==3


def test_selection_keeps_known_date_failure_and_exactly_twelve_original_ids():
    assert len(SELECTION)==len({t for t,_,_ in SELECTION})==12
    assert '2fa2a09ab42c8df28667f2bf' in {t for t,_,_ in SELECTION}


@pytest.mark.parametrize("legal",[False,None])
def test_future_or_unresolved_time_span_cannot_be_read(legal):
    class NeverRead:
        def entry(self,*_):raise AssertionError("future source was accessed")
    ref,reason=verify_span(NeverRead(),{'temporal_legal_strict':legal})
    assert ref is None and reason=='not_legal_under_explicit_date'


def test_summary_labels_do_not_create_false_omission_but_dropped_sentence_does():
    text='First sentence. Second sentence. Third sentence.'
    ref=K.SourceSpan(source_key='d:u:s:0',owner_id='u',session_id='s',source_rank=1,turn_index=0,
        speaker='seeker',start_char=0,end_char=len(text),exact_quote=text,raw_turn_sha256=sha256_text(text))
    parts=sentences(ref)
    assert span_retained(ref,parts)
    assert not span_retained(ref,parts[:2])

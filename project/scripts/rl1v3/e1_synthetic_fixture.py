#!/usr/bin/env python3
"""Entirely hand-written synthetic sources. NOT RAW corpus validation/human data."""
from dataclasses import replace
from pathlib import Path
import argparse
from types import SimpleNamespace

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.compile import asof as A
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.io import object_sha256,write_json_once

WRITER='SYNTHETIC-MECHANISM-ONLY-e1-1'
TEXTS=(
    'My sister lives in Oslo. I live in Kyoto.',
    'I plan to try a short walk, but I have not done it yet.',
    'I tried the walk yesterday, but it did not help.',
    'I completed the walk. I felt no better afterward.',
    'Correction: my sister moved away from Oslo in session 2. I learned this only now.',
    'I do not want another walk. Please stop suggesting it.',
    'I am not sure what to do.',
    'Can you help me think this through?',
    'FUTURE SENTINEL: I changed jobs after the evaluation.',
)


class FixtureRegistry:
    """Tiny protocol-compatible registry; intentionally no real dataset identity."""
    def __init__(self):
        self.entries=[]
        for owner in ('fixture-user','fixture-other'):
            for rank,text in enumerate(TEXTS):
                ts=(K.SourceTurn(turn_index=0,role='seeker',text=text),
                    K.SourceTurn(turn_index=1,role='supporter',text='You could consider an optional pause.'))
                s=K.SourceSession(owner_id=owner,session_id='fixture-'+str(rank),chronological_rank=rank,date=None,
                    turns=ts,raw_sha256='0'*64,dataset='SYNTHETIC_E1_MECHANISM_ONLY',family_id='synthetic-shared-family',
                    license='hand-written mechanism fixture only',provenance_version=WRITER,
                    source_uri='fixture://'+owner+'/'+str(rank),source_split='unassigned',
                    transcript_sha256=object_sha256([(t.role,t.text) for t in ts]))
                self.entries.append(SimpleNamespace(source=s,source_id='fixture-source:'+object_sha256(s),
                    original_turn_indices=(0,1),availability_scope='personal_history',reported_at=K.TimePoint(session_rank=rank),
                    ready_at=K.TimePoint(session_rank=rank+1)))
    def entry(self,owner,sid):return next(e for e in self.entries if e.source.owner_id==owner and e.source.session_id==sid)
    def context(self,p):
        cur=self.entry(p.owner_id,p.session_id).source
        hist=tuple(e.source for e in self.entries if e.source.owner_id==p.owner_id and e.source.chronological_rank<p.cutoff_rank)
        p.verify_source_context(cur,hist);return cur,hist
    def prefix(self,rank,owner='fixture-user'):
        s=self.entry(owner,'fixture-'+str(rank)).source
        return K.PrefixSpec.create(owner_id=owner,session_id=s.session_id,cut_turn=0,turns=s.turns[:1],
            cutoff_rank=rank,timestamp=None,dataset=s.dataset,family_id=s.family_id,ancestor_family_ids=(s.family_id,))
    def visible(self,p):
        self.context(p)
        return [e for e in self.entries if e.source.owner_id==p.owner_id and e.source.chronological_rank<p.cutoff_rank]


def build():
    reg=FixtureRegistry();ledger=A.Ledger()
    def row(rank,kind,**kw):
        e=reg.entry('fixture-user','fixture-'+str(rank));ordinal=kw.pop('ordinal',0)
        return A.record_from_source(e,kind=kind,writer=WRITER,refs=(S.span(e.source,ordinal),),
            text=e.source.turns[ordinal].text,review_status='human_approved',
            approval_ref='SYNTHETIC_EXPECTATION_ONLY_NOT_AN_ACTUAL_HUMAN_APPROVAL',**kw)
    old=row(0,'MP',subject='family_member',slot='residence',valid_from=K.TimePoint(session_rank=0))
    ledger.append(old,reg)
    events=[row(0,'ME',subject='supporter',ordinal=1,stage='suggested'),
        row(1,'ME',subject='user',stage='intended'),row(2,'ME',subject='user',stage='attempted'),
        row(3,'ME',subject='user',stage='completed'),row(3,'ME',subject='user',stage='outcome_reported'),
        row(5,'ME',subject='user',stage='rejected'),row(6,'ME',subject='unknown',stage='unknown')]
    for r in events:ledger.append(r,reg)
    before=A.materialize(reg,reg.prefix(4),ledger,writer=WRITER)
    edge=row(4,'RELATION',subject='family_member',slot='residence',operation='UPDATE',target_id=old.record_id,
        known_at=K.TimePoint(session_rank=5),ready_at=K.TimePoint(session_rank=7),
        event_time=K.TimePoint(session_rank=2),valid_to=K.TimePoint(session_rank=2))
    ledger.append(edge,reg)
    after=A.materialize(reg,reg.prefix(4),ledger,writer=WRITER)
    at6=A.materialize(reg,reg.prefix(6),ledger,writer=WRITER)
    at7=A.materialize(reg,reg.prefix(7),ledger,writer=WRITER)
    wrong_owner=A.materialize(reg,reg.prefix(7,'fixture-other'),ledger,writer=WRITER)
    assert before==after and not before['invalidations'] and not at6['invalidations']
    assert len(at7['invalidations'])==1 and old.valid_to is None and not wrong_owner['ledger_prefix']
    pending=replace(edge,record_id='pending',review_status='pending',approval_ref=None)
    pending=replace(pending,record_id=pending.content_id)
    unapproved=A.Ledger();unapproved.append(old,reg);unapproved.append(pending,reg)
    assert not A.materialize(reg,reg.prefix(7),unapproved,writer=WRITER)['invalidations']
    return dict(protocol=WRITER,synthetic_only=True,real_corpus_validation=False,human_approvals=0,
        sources=[e.source for e in reg.entries],old=old,relation=edge,events=events,
        snapshots=dict(cut4_before=before,cut4_after=after,cut6=at6,cut7=at7,other_owner=wrong_owner),
        checks=dict(late_known_and_later_ready=True,past_unchanged=True,third_person_preserved=True,
            rejected_internal_stage_preserved=True,seven_stages=True,pending_relation_inert=True,
            shared_family_does_not_allow_other_owner=True))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    write_json_once(args.out,build())

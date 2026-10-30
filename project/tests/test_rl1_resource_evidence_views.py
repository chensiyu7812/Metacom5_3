from copy import deepcopy
from dataclasses import replace
import json

import pytest

from metacom_pm.rl1.resource_evidence_views import EvidenceViews
from metacom_pm.rl1.temporal_evidence_ledger import SourceTurn, TemporalEvidenceLedger
from metacom_pm.rl1.schema import digest
from test_rl1_resource_organization import prefix, item


def inputs():
    p = prefix()
    ts = [SourceTurn('owner', 'source-s', 1, i, role, text, '2026-01-01') for i, (role, text) in enumerate([
        ('seeker', 'I intend to apply.'), ('supporter', 'I completed my own application.'), ('seeker', 'No outcome yet.')])]
    ledger = TemporalEvidenceLedger(p, ts, provenance_identity='synthetic')
    ms = item('s', text='\n'.join(t.speaker + ': ' + t.text for t in ts))
    return p, ts, ledger, ms


def test_full_ms_view_preserves_every_turn_role_and_source_without_extra_session():
    p, ts, ledger, ms = inputs(); view = EvidenceViews(p, ledger.export())
    changed, receipt = view.ms_turn_view(ms)
    body = json.loads(changed.content)
    assert body['turn_fields'] == ['turn_index', 'speaker', 'text']
    assert [(t[1], t[2]) for t in body['turns']] == [(t.speaker, t.text) for t in ts]
    assert body['summary'] is None and receipt['omitted_turns'] == receipt['extra_sessions'] == 0
    assert ms.identity != changed.identity and ms.source_ids == changed.source_ids
    assert changed.search_text == ms.search_text  # ranking treatment held constant


def test_stale_foreign_future_incomplete_or_unbound_sources_rejected():
    p, ts, ledger, ms = inputs(); e = ledger.export()
    bad = deepcopy(e); next(iter(bad['source_turns'].values()))['text'] = 'tampered'
    with pytest.raises(ValueError): EvidenceViews(p, bad)
    bad['identity'] = digest({k:v for k,v in bad.items() if k != 'identity'})
    with pytest.raises(ValueError): EvidenceViews(p, bad)
    with pytest.raises(ValueError): EvidenceViews(replace(p, owner_id='other'), e)
    with pytest.raises(ValueError): EvidenceViews(p, e).ms_turn_view(replace(ms, reported_at='2030-01-01'))
    with pytest.raises(ValueError, match='differs'): EvidenceViews(p, e).ms_turn_view(item('s', text='partial'))
    with pytest.raises(ValueError, match='registered'): EvidenceViews(p, e).ms_turn_view(item('missing'))


def test_shared_quote_does_not_create_completed_event_or_current_profile():
    p, ts, ledger, ms = inputs()
    claim_items = []
    for key, head in [('p', 'MP'), ('e', 'ME')]:
        x = replace(item(key, head, ts[0].text), source_ids=('source-s',))
        ledger.add_claim(candidate_id=key, head=head, statement=ts[0].text,
            spans=[ledger.span(ts[0].key, 0, len(ts[0].text), ts[0].text)], input_source_keys=[ts[0].key],
            derivation_method='existing_field', derivation_identity='fixture')
        claim_items.append(x)
    result = EvidenceViews(p, ledger.export()).organize(claim_items)
    assert len(result['shared_source_locations']) == 1
    assert result['event_reports'][0]['stage'] == 'unknown' and result['event_reports'][0]['outcome'] is None
    assert result['semantic_updates'] == result['semantic_event_relations'] == []
    assert result['new_current_facts'] == result['training_labels'] == 0

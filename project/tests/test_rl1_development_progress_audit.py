"""No live data/network: an archived score must retain its raw and human binding."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from metacom_pm.rl1.development_dispatch import PaidDevelopmentStage
from metacom_pm.rl1.development_feedback import freeze_inputs
from metacom_pm.rl1.schema import digest
from test_rl1_development_dispatch import setup
import test_rl1_development_feedback as fixtures

path = Path(__file__).resolve().parents[1]/'scripts/rl1/144_audit_development_progress.py'
spec = importlib.util.spec_from_file_location('development_progress_audit', path)
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


def test_interval_is_membership_and_missing_remains_missing():
    ref = dict(record_id='ref', source='SYNTHETIC', q_status='range', q_min=2, q_max=3,
               q_value=None, m_value=.25)
    for q in (2, 3):
        assert audit.single_comparison(dict(q=q, m=.25), ref)['both_agree'] is True
    assert audit.single_comparison(dict(q=4, m=.25), ref)['q_agrees'] is False
    assert audit.single_comparison(None, ref)['both_agree'] is None
    assert audit.single_comparison(dict(q=2, m=0), ref)['m_agrees'] is False


def test_exact_source_join_raw_tamper_and_read_only_journal(tmp_path):
    old, transport = setup(tmp_path/'unused')
    package = tmp_path/'package'; package.mkdir()
    policy = deepcopy(old.policy) | dict(run_directory=str(tmp_path/'stage'))
    stage = PaidDevelopmentStage(tmp_path/'stage', fixtures.materials(), fixtures.adapter(),
        ledger=tmp_path/'ledger.jsonl', policy=policy, engineering=True)
    with stage.budget.legacy_lease():
        fixtures.finish(stage, transport)
    audit.save_json(package/'J_CONFIG_PRIVATE.json', dict(policy=policy, ledger=str(stage.budget.path),
        protocol_identity=stage.identity, inputs=freeze_inputs(stage.materials, stage.adapter.prompt, stage.adapter.config)))
    item = stage.materials[0]
    bank = tmp_path/'bank'; bank.mkdir()
    single = dict(record_id='same reply wrong evidence', source='SYNTHETIC', q_status='range',
        q_min=2, q_max=3, q_value=None, m_value=0, reply_identity=digest(item['reply']), evidence_identity='WRONG')
    audit.save_json(bank/'REFERENCE_BANK_PRIVATE.json', dict(pairs=[], singles=[single], supplements=[]))
    audit.save_json(bank/'OUTPUT_MANIFEST.json', {'REFERENCE_BANK_PRIVATE.json':audit.sha(bank/'REFERENCE_BANK_PRIVATE.json')})
    before = {p:audit.sha(p) for p in stage.root.rglob('*') if p.is_file()}
    audit.audit(package, bank, tmp_path/'snapshot')
    summary = audit.read(tmp_path/'snapshot/SUMMARY.json')
    assert summary['journal_settled'] == 4 and summary['existing_single_reference_slots'] == 0
    assert not summary['qualified_reward']
    assert all(audit.sha(p) == h for p,h in before.items())
    raw = next((stage.root/'S').glob('*.raw.json'))
    value = audit.read(raw); value['extra_tampered_field'] = True; raw.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='raw/result/journal binding'):
        audit.audit(package, bank, tmp_path/'tampered')

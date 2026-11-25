"""Negative checks for journal evaluation/runtime boundaries; CPU only."""
import copy
from pathlib import Path
import json
import pytest
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import canonical_json
from metacom_pm.rl1v3.journal.memory import EndHistoryQA, runtime_task
from metacom_pm.rl1v3.journal.memory_tasks import resolve_evidence, fact_check, choose, CAPABILITIES


def test_evidence_resolver_never_promotes_private_event_text():
    user={'dialog_history':[{'id':'s','dialogue':[{'idx':3,'content':'visible'}]}],
          'event_experience':[{'id':'e','conv_id':'s','text':'GOLD_CANARY'}]}
    refs=resolve_evidence(user,['e','s:3','s:999','missing'])
    assert [r['kind'] for r in refs]==['event_to_session_coarse','exact_turn','unresolved','unresolved']
    assert 'GOLD_CANARY' not in canonical_json(refs)
    assert refs[2]['session_id'] is None


def test_runtime_allowlist_does_not_serialize_private_task_envelope():
    p=EndHistoryQA(task_id='opaque',owner_id='OWNER_CANARY',question='Visible question?',cutoff_rank=7,
        timestamp=None,family_id='FAMILY_CANARY',ancestor_family_ids=('FAMILY_CANARY',),fold=42)
    result=runtime_task(p,inventory={'MS':True},budget={'max_get_per_head':1})
    text=canonical_json(result)
    assert 'OWNER_CANARY' not in text and 'FAMILY_CANARY' not in text
    assert set(result)=={'task_id','visible_prefix','prefix_identity','public_inventory','budget'}
    assert not isinstance(p,K.PrefixSpec)  # does not fake a real dialogue cut


def test_strict_checker_does_not_score_substrings_or_free_semantics():
    spec={'gold':'Painting'}
    assert fact_check('painting.',spec)['status']=='pass'
    assert fact_check('Not painting; swimming.',spec)['status']=='uncertain'
    assert fact_check('Painting and an unsupported diagnosis.',spec)['status']=='uncertain'
    assert fact_check('Unknown',spec)['status']=='fail'
    assert fact_check('',spec)['status']=='technical_failure'
    assert fact_check('Cannot tell',{'gold':'Unknown'})['status']=='uncertain'


def test_actual_fixed_source_selection_and_disjoint_old_candidates():
    root=Path(__file__).resolve().parents[2]
    raw_path=root/'project/data/external/evo_emo.json'
    folds_path=root/'project/outputs/pm_rl1/v3/B0/folds.json'
    if not folds_path.exists():pytest.skip('private development assets unavailable')
    raw=json.loads(raw_path.read_text())
    ids={r['row_id']:r for r in map(json.loads,(root/'project/data/paper1_authority/es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl').read_text().splitlines())}
    folds=json.loads(folds_path.read_text())
    old=json.loads((root/'project/outputs/pm_rl1/qa_resource_gain_20261105_v1/CANDIDATES_PRIVATE.json').read_text())
    excluded={f"{r['source']['owner']}::{r['source']['group']}::{r['source']['idx']}" for r in old}
    a,meta=choose(raw,ids,folds,excluded)
    b,_=choose(list(reversed(raw)),ids,folds,excluded)
    assert a==b and len(a)==30
    assert len({r['question_sha256'] for r in a})==30
    assert not ({r['row_id'] for r in a}&excluded)
    assert all(sum(r['capability']==cap for r in a)==6 for cap in CAPABILITIES)
    assert sum(len(r['evidence_sessions'])>=2 for r in a)>=12
    assert {r['owner_id'] for r in a}<={'p1','p13','p15','p18'}

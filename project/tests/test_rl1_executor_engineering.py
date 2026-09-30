import json
from pathlib import Path
import pytest
from metacom_pm.rl1.executor_engineering import admitted_rows
from metacom_pm.rl1.executor_pilot import admitted_rows as research_admission

PROJECT=Path(__file__).resolve().parents[1]

@pytest.fixture
def batch():
    out=PROJECT/'outputs/pm_rl1/executor_engineering_20260929_v1'
    contract=json.loads((out/'condition_contract_private.json').read_text())
    run=Path(json.loads((out/'author_pointer.json').read_text())['run_dir'])
    jobs=json.loads((run/'jobs.json').read_text())
    requests={j['request_id']:json.loads((run/(j['request_id']+'.request.json')).read_text()) for j in jobs}
    raws={j['request_id']:json.loads((run/(j['request_id']+'.raw.json')).read_text()) for j in jobs}
    doc=json.loads((out/'admission_reviews_private.json').read_text())
    reviews={r['request_identity']:r for r in doc['rows']}
    return contract,jobs,requests,raws,reviews

def test_engineering_uses_all_and_only_accepted_rows_and_does_not_pass_research_gate(batch):
    rows=admitted_rows(*batch)
    assert len(rows)==90
    assert {r['request_id'] for r in rows}=={k for k,v in batch[-1].items() if v['status']=='accept'}
    with pytest.raises(ValueError,match='per prefix-condition'):research_admission(*batch)

def test_cannot_silently_promote_engineering_adapter_to_research(batch):
    batch[0]['eligible_for_research_or_rl']=True
    with pytest.raises(ValueError,match='engineering-only'):admitted_rows(*batch)

def test_changed_response_cannot_inherit_original_review(batch):
    rid=next(k for k,r in batch[-1].items() if r['status']=='accept')
    batch[3][rid]['text']='silently improved response'
    with pytest.raises(ValueError,match='review not bound'):admitted_rows(*batch)

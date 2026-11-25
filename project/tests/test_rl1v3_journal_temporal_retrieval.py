"""Mechanical date, reference isolation, tie and no-tail-drop tests."""
import ast
from pathlib import Path
import pytest
from metacom_pm.rl1v3.journal.temporal_retrieval import RAW_BANNER,chunks,eligible,evidence_coverage,hybrid,lexical,parse_question_time,run,validate_sources

def record(i,date,text="Example report."):
    return dict(record_id=str(i),owner_id="owner",source_rank=i,ready_at=dict(session_rank=i+1),reported_at=dict(date=date),reading_text=text)

def test_ready_and_report_frontier():
    rows=[record(0,"2020-01-01"),record(1,"2020-01-02")]
    assert eligible(rows,"owner","2020-01-01")==rows[:1]
    rows[0]["ready_at"]["session_rank"]=2
    with pytest.raises(ValueError):eligible(rows,"owner","2020-01-01")

def test_month_interval_and_missing_date():
    t=parse_question_time("What happened by December 2020?")
    assert (t["lower"],t["upper"])==("2020-12-01","2020-12-31")
    assert parse_question_time("What is current?")["lower"] is None

def test_chunks_retain_every_token():
    ids=list(range(2001));parts=chunks(ids)
    assert max(map(len,parts))<=480
    assert set(sum(parts,[]))==set(ids)
    assert parts[-1][-1]==2000

def test_sufficient_source_group_is_conjunctive_and_unknown_separate():
    atom=dict(atom_id="a",required=True,status="supported",sufficient_source_groups=[["a:1","b:2"]])
    assert evidence_coverage([atom],{"a"},"status")["status"]=="evidence_insufficient"
    assert evidence_coverage([atom],{"a","b"},"status")["covered_sufficient_groups"]==1
    atom["status"]="unknown"
    assert evidence_coverage([atom],{"a","b"},"status")["status"]=="reference_pending_or_scope_conflict"

def test_entity_ties_do_not_hide_lexical_semantic_order():
    rows=[record(0,"2020-01-01","Ada alpha"),record(1,"2020-01-02","Ada beta")]
    scores={"0":1.,"1":0.}
    ranked,_,n=hybrid(rows,"Who is Ada?",dict(upper=None),scores,scores)
    assert ranked[0]["record_id"]=="0" and n==3

def test_retrieval_signature_does_not_accept_reference_paths():
    import inspect
    assert "audit" not in inspect.signature(run).parameters
    tree=ast.parse(inspect.getsource(run))
    strings=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
    assert not any("ATOMS_PRIVATE" in s or "evalspec_private" in s for s in strings)

def test_existing_raw_banner_and_source_binding():
    r=record(0,"2020-01-01",RAW_BANNER+"Example source.");r["parent_session_id"]="session"
    ledger=[dict(owner_id="owner",session_id="session",text="Example source.",reported_at=r["reported_at"],ready_at=r["ready_at"])]
    validate_sources([r],ledger)
    r["reading_text"]+="Unexpected addition."
    with pytest.raises(ValueError):validate_sources([r],ledger)

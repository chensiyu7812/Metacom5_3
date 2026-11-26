"""Scientific aggregation boundaries; no model or corpus required."""
import importlib.util
from pathlib import Path
import pytest

P=Path(__file__).parents[1]/'scripts/rl1v3/journal_analyze_smv.py'
S=importlib.util.spec_from_file_location('smv_analysis',P)
M=importlib.util.module_from_spec(S);S.loader.exec_module(M)

def test_empty_fact_inventory_does_not_mean_task_success():
    assert M.conjunction([]) is None
    assert M.conjunction(['supported','omitted'])==[0,0]
    assert M.conjunction(['supported','unresolved'])==[0,1]

def test_reused_unknown_endpoint_cancels_but_distinct_endpoints_do_not():
    a={'request_id':'same','completion':[0,1]}
    assert M.delta(a,a,'completion')==[0,0]
    assert M.delta(a,{'request_id':'other','completion':[0,1]},'completion')==[-1,1]

def test_same_output_cannot_receive_two_inconsistent_observations():
    with pytest.raises(ValueError,match='inconsistent'):
        M.delta({'request_id':'same','completion':[0,1]},
                {'request_id':'same','completion':[1,1]},'completion')

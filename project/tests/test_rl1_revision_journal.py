import json
import pytest
from metacom_pm.rl1.revision_journal import record_progress


@pytest.mark.parametrize('kind',['step','epoch'])
def test_multiple_updates_keep_prior_progress_immutable(tmp_path,kind):
    first={kind:1,'nll':2.};second={kind:2,'nll':1.}
    p=record_progress(tmp_path,kind,first)
    q=record_progress(tmp_path,kind,second)
    assert p!=q and json.loads(p.read_text())==first and json.loads(q.read_text())==second
    record_progress(tmp_path,kind,first)
    with pytest.raises(ValueError,match='immutable'):
        record_progress(tmp_path,kind,{kind:1,'nll':0.})

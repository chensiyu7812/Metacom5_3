"""Keep length termination distinct from EOS in actual-call accounting."""
import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).parents[1]/'scripts/rl1v3/journal_closeout_measurements.py'
spec=importlib.util.spec_from_file_location('closeout_measurements',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_eos_and_length_are_distinct():
    payload={'decode':{'eos_token_id':[2,3],'max_new_tokens':4}}
    module.validate_finish(payload,{'token_ids':[4,2],'finish_reason':'eos'})
    module.validate_finish(payload,{'token_ids':[4,5,6,7],'finish_reason':'length'})
    for value in [
        {'token_ids':[4,5,6,7],'finish_reason':'eos'},
        {'token_ids':[4,5,6,2],'finish_reason':'length'},
        {'token_ids':[4,5],'finish_reason':'length'},
        {'token_ids':[2,4,2],'finish_reason':'eos'},
    ]:
        with pytest.raises(AssertionError):module.validate_finish(payload,value)

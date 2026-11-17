"""The integration gate must reject incomplete green JUnit reports."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT=Path(__file__).parents[1]/'scripts/rl1v3/verify_v3_junit.py'
SPEC=importlib.util.spec_from_file_location('v3_junit_gate',SCRIPT)
GATE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def xml(tmp_path,body):
    path=tmp_path/'results.xml'
    path.write_text('<testsuites><testsuite>'+body+'</testsuite></testsuites>')
    return path


def test_complete_report_passes_and_binds_bytes(tmp_path):
    path=xml(tmp_path,'<testcase classname="tests.test_rl1v3_contracts" name="test_r1"/>')
    result=GATE.verify(path)
    assert result['tests']==result['passed']==1
    assert result['failures']==result['errors']==result['skipped']==result['xfailed']==0
    assert len(result['junit_sha256'])==64


@pytest.mark.parametrize('body',[
    '', '<testcase classname="tests.test_legacy" name="test_ok"/>',
    '<testcase classname="" name="collection error"><error/></testcase>',
    '<testcase classname="test_rl1v3_x" name="a"><failure/></testcase>',
    '<testcase classname="test_rl1v3_x" name="a"><error/></testcase>',
    '<testcase classname="test_rl1v3_x" name="a"><skipped/></testcase>',
    '<testcase classname="test_rl1v3_x" name="a"><skipped type="pytest.xfail"/></testcase>',
    '<testcase classname="test_rl1v3_x" name="a"/>'*2,
])
def test_incomplete_or_nonpassing_report_is_not_accepted(tmp_path,body):
    with pytest.raises(ValueError):GATE.verify(xml(tmp_path,body))

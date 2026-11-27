"""Public-vs-private CI contract; synthetic XML only, never research evidence."""
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "rl1v3"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = load("verify_v3_public_ci")
STRICT = load("verify_v3_junit")
CASES = json.loads(P.MANIFEST.read_text())["cases"]


def report(tmp_path):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", tests=str(len(CASES) + 1),
                          skipped=str(len(CASES)), errors="0", failures="0")
    ET.SubElement(suite, "testcase", classname="tests.test_rl1v3_fixture", name="test_public")
    for identity, reason in CASES.items():
        module, name = identity.split("::", 1)
        node = ET.SubElement(suite, "testcase", classname="tests." + module, name=name)
        ET.SubElement(node, "skipped", type="pytest.skip", message=reason)
    return root, suite, tmp_path / "v3.xml"


def write(root, path):
    ET.ElementTree(root).write(path, encoding="utf-8")
    return path


def test_public_gate_records_43_deferred_without_calling_them_passed(tmp_path):
    root, suite, path = report(tmp_path)
    assert len(CASES) == 43
    result = P.verify_public(write(root, path))
    assert result["passed"] == result["public_tests_passed"] == 1
    assert result["private_replay_not_run"] == 43
    assert result["private_replay_status"] == "not_verified"
    assert result["private_replay_full_acceptance"] is False
    assert len(result["deferred_private_cases"]) == 43
    with pytest.raises(ValueError, match="skip/xfail forbidden"):
        STRICT.verify(path)


@pytest.mark.parametrize("change", ["new_skip", "wrong_reason", "xfail", "failure",
                                    "missing", "duplicate", "error", "bad_totals"])
def test_public_gate_rejects_unapproved_changes(tmp_path, change):
    root, suite, path = report(tmp_path)
    first = suite[1]
    if change == "new_skip":
        ET.SubElement(suite[0], "skipped", type="pytest.skip", message="private CPU receipt not provided")
    elif change == "wrong_reason":
        first.find("skipped").set("message", "some other failure")
    elif change == "xfail":
        first.find("skipped").set("type", "pytest.xfail")
    elif change == "failure":
        ET.SubElement(first, "failure")
    elif change == "missing":
        suite.remove(first)
    elif change == "duplicate":
        suite.append(ET.fromstring(ET.tostring(first)))
    elif change == "error":
        ET.SubElement(first, "error")
    else:
        suite.set("tests", "1")
    with pytest.raises(ValueError):
        P.verify_public(write(root, path))


def test_actual_passes_are_not_deferred(tmp_path):
    root, suite, path = report(tmp_path)
    suite[1].remove(suite[1].find("skipped"))
    suite.set("skipped", "42")
    result = P.verify_public(write(root, path))
    assert result["passed"] == 2
    assert result["private_replay_passed"] == 1
    assert result["private_replay_not_run"] == 42

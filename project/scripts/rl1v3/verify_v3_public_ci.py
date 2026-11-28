#!/usr/bin/env python3
"""Public V3 code acceptance; private replay is reported separately, never passed.

The original verify_v3_junit.py remains the strict all-tests-pass local gate.
This public-only gate accepts only the named, pre-existing artifact-absence
skips in the manifest. Failures, xfails, unexpected skips and missing named
cases are errors. A green public CI is not private-evidence acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

MANIFEST = Path(__file__).with_name("v3_private_replay_manifest.json")


def verify_public(path: Path, manifest: Path = MANIFEST) -> dict:
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    if spec.get("protocol") != "pmrl1v3-private-replay-manifest-v1":
        raise ValueError("wrong private-replay manifest protocol")
    allowed = spec["cases"]
    if not isinstance(allowed, dict) or not allowed or any(
        not isinstance(k, str) or not isinstance(v, str) or not v
        for k, v in allowed.items()
    ):
        raise ValueError("invalid private-replay manifest")
    tree = ET.parse(path).getroot()
    for suite in tree.iter("testsuite"):
        if int(suite.get("errors", "0")) or int(suite.get("failures", "0")):
            raise ValueError("V3 JUnit reports test or collection failure")
    cases = list(tree.iter("testcase"))
    if not cases:
        raise ValueError("V3 acceptance report has no test cases")
    identities = set()
    deferred = []
    passed = 0
    private_passed = 0
    for case in cases:
        classname = case.get("classname", "")
        if classname.startswith("tests."):
            classname = classname[len("tests."):]
        if not classname.split(".")[0].startswith("test_rl1v3_"):
            raise ValueError("unexpected or collection-error testcase: " + classname)
        identity = classname + "::" + case.get("name", "")
        if identity in identities:
            raise ValueError("duplicate V3 testcase identity: " + identity)
        identities.add(identity)
        if case.find("failure") is not None or case.find("error") is not None:
            raise ValueError("V3 test failed: " + identity)
        skipped = case.find("skipped")
        if skipped is None:
            passed += 1
            if identity in allowed:
                private_passed += 1
            continue
        if (identity not in allowed or skipped.get("type") != "pytest.skip"
                or skipped.get("message") != allowed[identity]):
            raise ValueError("unexpected skip or xfail: " + identity)
        deferred.append({"test": identity, "reason": allowed[identity]})
    missing = set(allowed) - identities
    if missing:
        raise ValueError("private replay cases absent from JUnit: " + ", ".join(sorted(missing)))
    if passed - private_passed <= 0:
        raise ValueError("no public acceptance tests passed")
    # Check that the report's suite totals, when supplied, match its cases.
    suites = list(tree.iter("testsuite"))
    if suites and all("tests" in s.attrib for s in suites):
        if sum(int(s.get("tests", "0")) for s in suites) != len(cases):
            raise ValueError("JUnit testcase count mismatch")
    if suites and all("skipped" in s.attrib for s in suites):
        if sum(int(s.get("skipped", "0")) for s in suites) != len(deferred):
            raise ValueError("JUnit skipped count mismatch")
    return {
        "protocol": "pmrl1v3-public-code-acceptance-v1",
        "public_code_acceptance": "passed",
        "tests": len(cases),
        "passed": passed,
        "public_tests_passed": passed - private_passed,
        "failures": 0, "errors": 0, "xfailed": 0,
        "skipped": len(deferred),
        "private_replay_expected": len(allowed),
        "private_replay_passed": private_passed,
        "private_replay_not_run": len(deferred),
        "private_replay_status": "not_verified" if deferred else "all_listed_tests_passed",
        "private_replay_full_acceptance": False if deferred else True,
        "deferred_private_cases": sorted(deferred, key=lambda x: x["test"]),
        "junit_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "testcase_ids_sha256": hashlib.sha256(json.dumps(
            sorted(identities), ensure_ascii=False, separators=(",", ":")
        ).encode()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = verify_public(args.report)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()

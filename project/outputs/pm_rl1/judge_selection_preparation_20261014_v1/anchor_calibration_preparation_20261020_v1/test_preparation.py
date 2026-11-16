import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import runtime_adapter as a
from runtime_adapter import p, s
sys.path.insert(0, str(a.BASE / "paired_diagnostic_20261019_v1/tests"))
from test_paired import raw, score_value


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.protocol, self.items = a.load()
        self.calls = []
        self.budget = p.DiagnosticBudget(self.root/"mock-money.jsonl", study=a.STUDY,
            stage_cap=s.nanodollars("1.15"), trial="MOCK", trial_cap=s.nanodollars(2),
            shared_cap=s.nanodollars(20), baseline=0, opening=0)
        self.addCleanup(patch.stopall)
        patch("socket.socket.connect", side_effect=AssertionError("network forbidden")).start()

    def run_mock(self, mutate=None, baseline=201, protocol=None):
        owner = self
        class MockTransport:
            def send(self, messages, schema, *, request, raw_path):
                owner.calls.append(request)
                value = raw(score_value(owner.items[request["item_key"]]), request["request_id"])
                if mutate:
                    mutate(value, request)
                Path(raw_path).write_text("MOCK ONLY; NOT A MODEL RESPONSE")
                return value
        return p.run(protocol or self.protocol, self.items, self.root/"mock-run", MockTransport(),
                     self.budget, mode="mock", global_count=lambda: baseline, runtime=a.runtime())

    def test_same_source_reply_schema_only_system_changes(self):
        for t in s.read(a.HERE/"targets.json"):
            left, right = [s.read(a.HERE/t["payloads"][arm]["file"]) for arm in ("baseline","calibrated")]
            self.assertEqual(left["messages"][1:], right["messages"][1:])
            self.assertEqual(left["schema"], right["schema"])
            self.assertTrue(right["messages"][0]["content"].startswith(left["messages"][0]["content"]))
            user = json.loads(left["messages"][1]["content"])
            self.assertEqual(set(user), {"reply","response_units","legal_evidence"})
            self.assertEqual(user["legal_evidence"], s.read(a.HERE/t["source_path"]))

    def test_reference_examples_no_scores_no_target_sources(self):
        examples = s.read(a.HERE/"EXAMPLES_EN.json")
        for ex in examples:
            self.assertNotIn("q", ex)
            self.assertNotIn("m", ex)
            ids = {t["id"] for t in ex["fictional_complete_record"]}
            for c in ex["checks"]:
                self.assertTrue(set(c["basis_ids"]) <= ids)
        self.assertEqual(len(examples), 6)

    def test_24_slots_repeats_metadata_no_redispatch(self):
        r = self.run_mock()
        self.assertEqual((r["started"],r["cumulative"]), (24,225))
        for row in r["slots"]:
            result = row["result"]
            self.assertEqual(result["semantic_revisions_applied"], 2 if row["arm"]=="baseline" else 3)
            self.assertFalse(result["reward_eligible"])
        before = {str(f):s.sha(f) for f in (self.root/"mock-run").glob("*.json")}
        self.run_mock()
        self.assertEqual(len(self.calls),24)
        self.assertTrue(all(s.sha(f)==sha for f,sha in before.items()))

    def test_cap_225(self):
        self.assertEqual(self.run_mock(baseline=224)["started"],1)

    def test_cross_version_preserves_no_replay(self):
        self.run_mock()
        changed=copy.deepcopy(self.protocol);changed["identity"]="different"
        self.run_mock(protocol=changed)
        self.assertEqual(len(self.calls),24)

    def test_per_arm_failures_not_hidden_by_other_arm(self):
        def mutate(raw_value, request):
            if request["arm"]=="baseline":
                raw_value["choices"][0]["message"]["content"]='{"q":1,"q":2}'
        r=self.run_mock(mutate)
        self.assertEqual(sum(c["arm"]=="baseline" for c in self.calls),2)
        # Fail at positions 1 and 4; successful calibrated calls at 2/3
        # must not erase the baseline arm's consecutive failure streak.
        self.assertEqual(r["started"],4)

    def test_example_ids_rejected_as_target_sources(self):
        def mutate(value, request):
            if request["position"]==1:
                v=json.loads(value["choices"][0]["message"]["content"])
                v["q_rationale"]["source_turn_ids"]=["EX_RESULT:T1"]
                value["choices"][0]["message"]["content"]=s.canonical(v)
        r=self.run_mock(mutate)
        self.assertEqual(r["started"],24)
        self.assertFalse(r["slots"][0]["result"]["technical_valid"])

    def test_truncation_stops_without_repair(self):
        r=self.run_mock(lambda v,q:v["choices"][0].update(finish_reason="length"))
        self.assertEqual(r["started"],1)

    def test_missing_usage_retains_liability(self):
        r=self.run_mock(lambda v,q:v.pop("usage"))
        self.assertEqual((r["started"],r["unsettled"]), (1,p.RESERVE))

    def test_unknown_not_zero_or_failure(self):
        def mutate(v,q):
            v["choices"][0]["message"]["content"]=s.canonical(score_value(self.items[q["item_key"]],True))
        r=self.run_mock(mutate)
        self.assertEqual(r["unknown"],24)
        self.assertTrue(all(x["result"]["evaluation"]["q"] is None for x in r["slots"]))

    def test_budget_full_native_reservation(self):
        self.budget.reserve("first",p.RESERVE,{"study":a.STUDY})
        with self.assertRaises(ValueError):
            self.budget.reserve("second",p.RESERVE,{"study":a.STUDY})
        self.budget.settle("first",s.nanodollars(".37"),"mock confirmed usage")
        with self.assertRaises(ValueError):
            self.budget.reserve("next",p.RESERVE,{"study":a.STUDY})

    def test_live_authorization_missing_rejected(self):
        with self.assertRaises(ValueError):
            a.approve(self.protocol,{})

    def test_old_stop_kept(self):
        root=self.root/"mock-run";root.mkdir()
        s.save(root/"STOP.json",{"reason":"preserved"})
        digest=s.sha(root/"STOP.json")
        self.assertEqual(self.run_mock()["started"],0)
        self.assertEqual(s.sha(root/"STOP.json"),digest)


if __name__=="__main__":
    unittest.main()

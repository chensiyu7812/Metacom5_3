"""Offline regression tests for the bounded A/B adapter, never semantic gold."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/"src"))
BASE=PROJECT/"outputs/pm_rl1/judge_selection_preparation_20261014_v1"
PREP=BASE/"relation_reference_preparation_20261021_v1"
sys.path.insert(0,str(BASE/"paired_diagnostic_20261019_v1"))
import paired as p
from metacom_pm.rl1 import relation_reference as r


def score(item,unknown=False):
    units=p.response_units(item["reply"]);sid=next(iter(p.evidence_turns(item["evidence"])))
    return dict(status="uncertain" if unknown else "scored",q=None if unknown else 3,
        q_rationale=dict(current_need="synthetic mock, not research evidence",response_unit_ids=[units[0]["id"]],source_turn_ids=[sid],reason="mock"),
        assessments=[dict(response_unit_id=u["id"],relation="non_factual",severity=0,source_turn_ids=[],reason="synthetic judgment") for u in units],
        coverage="synthetic mechanical check only",uncertainty_reasons=["mock unknown"] if unknown else [])


class RelationReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location("relation_entry",PROJECT/"scripts/rl1/114_run_relation_reference.py")
        cls.entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.entry)
        cls.protocol,cls.items,cls.refs,cls.prompt,cls.payloads,cls.runtime_items=cls.entry.load()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.calls=[]
        self.addCleanup(patch.stopall)
        patch("socket.socket.connect",side_effect=AssertionError("offline network forbidden")).start()
        patch("deepseek_access.read_key",side_effect=AssertionError("offline credential access forbidden")).start()
        self.budget=p.DiagnosticBudget(self.root/"ledger.jsonl",trial="synthetic-trial",study=r.VERSION,
            stage_cap=p.s.nanodollars("1.25"),trial_cap=p.s.nanodollars("2.40"),shared_cap=p.s.nanodollars(20),baseline=0,opening=0)

    def execute(self,change=None,protocol=None,baseline=225):
        owner=self
        class Transport:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append((deepcopy(request),deepcopy(messages)))
                value=score(owner.runtime_items[request["item_key"]])
                raw=dict(transport="deepseek",model="deepseek-flash",system_fingerprint="mock-service",request_identity=request["request_id"],
                    choices=[dict(message=dict(content=json.dumps(value),reasoning_content="DO_NOT_USE_THINKING"),finish_reason="stop")],
                    usage=dict(prompt_tokens=1000,completion_tokens=1000,completion_tokens_details=dict(reasoning_tokens=700)),
                    total_seconds=1,request_started_unix=1792368000)
                if change:change(request,raw)
                Path(raw_path).write_text("synthetic response only\n")
                return raw
        pr=protocol or self.protocol
        return p.run(pr,self.runtime_items,self.root/"run",Transport(),self.budget,mode="mock",global_count=lambda:baseline,
            runtime=r.runtime(pr,self.payloads,self.items,self.refs,self.prompt,p,lambda *_:None))

    def test_all_28_distinct_attempts_and_no_reward_qualification(self):
        out=self.execute()
        self.assertEqual((out["started"],out["cumulative"],out["technical_delivered"]),(28,253,28))
        self.assertFalse(out["reward_eligible"]);self.assertEqual(out["natural_updates"],0)
        self.assertEqual(len({x[0]["request_id"] for x in self.calls}),28)

    def test_semantically_wrong_mock_scores_do_not_stop_diagnostic(self):
        out=self.execute() # all non-factual includes known factual replies: wrong but mechanically valid
        self.assertEqual(out["started"],28);self.assertIsNone(out["semantic_counts"])

    def test_repetitions_same_payload_distinct_request_no_cache_collapse(self):
        self.execute()
        for key in ("dev06B","dev04B"):
            for arm in ("A","B"):
                rows=[x for x in self.calls if x[0]["material_id"]==key and x[0]["arm"]==arm]
                self.assertEqual(len(rows),2);self.assertEqual(rows[0][1],rows[1][1]);self.assertNotEqual(rows[0][0]["request_id"],rows[1][0]["request_id"])

    def test_second_invocation_preserves_files_without_redispatch(self):
        self.execute();old={str(f):r.sha(f) for f in (self.root/"run").glob("*") if f.is_file()}
        self.execute();self.assertEqual(len(self.calls),28)
        for path,sha in old.items():self.assertEqual(r.sha(path),sha)

    def test_unknown_is_missing_and_continues_not_zero_or_tie(self):
        def change(req,raw):
            if req["position"]==1:raw["choices"][0]["message"]["content"]=json.dumps(score(self.runtime_items[req["item_key"]],True))
        out=self.execute(change);self.assertEqual(out["started"],28);self.assertEqual(out["model_unknown"],1)
        ev=out["slots"][0]["result"]["evaluation"]
        self.assertEqual([ev[k] for k in ("q","m","U")],[None,None,None])
        pairs=[x for x in out["resource_comparisons"] if x["pair_id"]=="mother_RS" and x["arm"]=="A" and x["off_draw"]==1]
        self.assertIsNone(pairs[0]["delta_U"]);self.assertFalse(pairs[0]["comparable"])

    def test_duplicate_json_key_stops_first_attempt(self):
        def change(req,raw):raw["choices"][0]["message"]["content"]='{"status":"scored","status":"scored"}'
        out=self.execute(change);self.assertEqual(out["started"],1);self.assertEqual(out["slots"][0]["state"],"failed")
        before=r.sha(self.root/"run/STOP.json");self.execute();self.assertEqual(len(self.calls),1);self.assertEqual(r.sha(self.root/"run/STOP.json"),before)

    def test_truncated_final_not_repaired_from_thinking(self):
        def change(req,raw):raw["choices"][0]["finish_reason"]="length"
        out=self.execute(change);self.assertEqual(out["started"],1);self.assertIsNone(out["slots"][0]["result"]["evaluation"]["q"])

    def test_illegal_source_id_stops(self):
        def change(req,raw):
            v=json.loads(raw["choices"][0]["message"]["content"]);v["q_rationale"]["source_turn_ids"]=["H999:T999"]
            raw["choices"][0]["message"]["content"]=json.dumps(v)
        self.assertEqual(self.execute(change)["started"],1)

    def test_unsettled_usage_retains_full_reservation(self):
        def change(req,raw):raw["usage"]=None
        out=self.execute(change);self.assertEqual(out["started"],1)
        _,_,res,settled=self.budget._totals(self.budget.events())
        self.assertEqual(len(set(res)-set(settled)),1);self.assertEqual(out["result_liability_usd"],"0.786432")

    def test_reservation_before_dispatch_and_budget_hard_stop(self):
        self.budget.stage_cap=p.s.nanodollars(".78")
        out=self.execute();self.assertEqual(out["started"],0);self.assertEqual(self.calls,[])

    def test_unused_reserve_released_only_after_complete_usage(self):
        out=self.execute();self.assertEqual(out["started"],28)
        _,_,res,settled=self.budget._totals(self.budget.events());self.assertEqual(set(res),set(settled))
        self.assertLess(self.budget.stage_total(res,settled),p.RESERVE)

    def test_cumulative_cap_prevents_29th_call(self):
        out=self.execute(baseline=253);self.assertEqual(out["started"],0)

    def test_protocol_change_cannot_replay_started_slots(self):
        self.execute();pr=deepcopy(self.protocol);pr["identity"]="another-interface-version"
        out=self.execute(protocol=pr);self.assertEqual(len(self.calls),28);self.assertIsNotNone(out["stop"])

    def test_source_and_reply_binding_mismatch_rejected(self):
        ref=deepcopy(self.refs["dev06B"]);ref["evidence_identity"]="wrong"
        with self.assertRaises(ValueError):r.validate_reference(self.items["dev06B"],ref,p)

    def test_quote_and_speaker_mismatch_rejected(self):
        for field,value in [("quote","fabricated quote"),("speaker","someone else")]:
            ref=deepcopy(self.refs["dev06B"]);ref["claims"][0]["source_checks"][0][field]=value
            with self.assertRaises(ValueError):r.validate_reference(self.items["dev06B"],ref,p)

    def test_expected_score_or_preference_field_rejected(self):
        for field in ("q","m","expected_winner","human_preference"):
            ref=deepcopy(self.refs["dev06B"]);ref["claims"][0][field]=4
            with self.assertRaises(ValueError):r.validate_reference(self.items["dev06B"],ref,p)

    def test_analyst_semantics_not_self_certified(self):
        ref=deepcopy(self.refs["dev06B"]);ref["claims"][0]["source_checks"][0]["scope_status"]="verified_gold"
        with self.assertRaises(ValueError):r.validate_reference(self.items["dev06B"],ref,p)

    def test_full_original_user_and_rubric_unchanged(self):
        for key in self.items:
            a,b=self.payloads[key+"__A"],self.payloads[key+"__B"]
            self.assertEqual(a["messages"][1],b["messages"][1]);self.assertEqual(a["schema"],b["schema"])
            self.assertEqual(a["messages"][0]["content"],self.prompt)
            self.assertTrue(b["messages"][0]["content"].startswith(self.prompt+"\n\nPARTIAL_RELATION_REFERENCE_V1_DATA\n"))
            self.assertEqual(json.loads(b["messages"][1]["content"])["legal_evidence"],self.items[key]["evidence"])
            p.api_body(self.protocol["config"],b["messages"])

    def test_additional_message_or_annotation_leak_rejected(self):
        data=deepcopy(self.payloads["dev06B__B"]);data["messages"].append(dict(role="user",content="human score 4"))
        with self.assertRaises(ValueError):r.validate_payload(self.items["dev06B"],self.refs["dev06B"],"B",self.prompt,data,p)

    def test_arm_order_balanced_and_reverse_for_repetition(self):
        sched=self.protocol["schedule"];pairs=[sched[i:i+2] for i in range(0,28,2)]
        self.assertEqual(sum(x[0]["arm"]=="A" for x in pairs),7)
        for key in ("dev06B","dev04B"):
            x=[v for v in pairs if v[0]["material_id"]==key]
            self.assertEqual([s["arm"] for s in x[0]],[s["arm"] for s in x[1]][::-1])

    def test_source_cluster_and_control_counts_not_inflated(self):
        x=self.protocol["statistics"]
        self.assertEqual((x["distinct_replies"],x["current_contexts"],x["source_owners"],x["mechanism_controls"]),(12,5,2,3))
        self.assertEqual(x["independent_validation_cases"],0)

    def test_resource_pairs_require_full_matching_conditions(self):
        out=self.execute();self.assertEqual(len(out["resource_comparisons"]),14)
        self.assertTrue(all(x["direction_correctness"] is None for x in out["resource_comparisons"]))
        for x in self.protocol["resource_pairs"]:self.assertTrue(x["matching_generator_settings"])

    def test_pending_approval_and_pending_reference_never_authorize(self):
        with self.assertRaises(ValueError):r.require_approval(self.protocol,r.read(PREP/"APPROVAL_REQUIRED.json"),r.read(PREP/"REFERENCE_REVIEW_PENDING.json"))
        auth=dict(self.protocol["approval_required"],status="APPROVED",protocol_identity=self.protocol["identity"],researcher_authorization_record="in-memory synthetic")
        with self.assertRaises(ValueError):r.require_approval(self.protocol,auth,r.read(PREP/"REFERENCE_REVIEW_PENDING.json"))

    def test_live_pending_rejected_before_network_or_live_directory(self):
        existed=Path(self.protocol["run_dir"]).exists()
        with self.assertRaises(ValueError):self.entry.launch(PREP/"APPROVAL_REQUIRED.json",PREP/"REFERENCE_REVIEW_PENDING.json")
        self.assertEqual(Path(self.protocol["run_dir"]).exists(),existed)

    def test_read_only_entry_preserves_old_and_budget_history(self):
        before={path:r.sha(path) for path in self.protocol["old_stop_hashes"]}
        ledger=Path(self.protocol["financial_baseline"]["ledger_path"]);h=r.sha(ledger)
        self.assertEqual(self.entry.check()["actual_historical"],225)
        self.assertEqual(r.sha(ledger),h)
        for path,old in before.items():self.assertEqual(r.sha(path),old)

    def test_public_final_bound_review_is_counted_separately(self):
        out=self.execute();slot=out["slots"][0];sid=slot["slot_id"]
        review=dict(status="ANALYST_REVIEW",independent_human_reference=False,slot_id=sid,
            result_sha256=r.sha(self.root/"run"/(sid+".result.json")),reference_bundle_sha256=self.protocol["reference_bundle_sha256"],
            reference_uptake="not_applicable_A",target_relationship="unclear",score_basis="unresolved",
            public_final_quotes=["synthetic judgment"],findings=[])
        r.save_new(self.root/"run/reviews"/(sid+".json"),review)
        out=r.summarize(self.protocol,self.root/"run",225,p)
        self.assertEqual(out["semantic_counts"]["reviewed_results"],1)
        self.assertEqual(out["semantic_counts"]["unreviewed_results"],27)
        self.assertEqual(out["semantic_counts"]["independent_human_reviews"],0)
        self.assertFalse(out["reward_eligible"])

    def test_review_cannot_quote_thinking_as_final(self):
        out=self.execute();slot=out["slots"][0];sid=slot["slot_id"]
        review=dict(status="ANALYST_REVIEW",independent_human_reference=False,slot_id=sid,
            result_sha256=r.sha(self.root/"run"/(sid+".result.json")),reference_bundle_sha256=self.protocol["reference_bundle_sha256"],
            reference_uptake="not_applicable_A",target_relationship="incorrect",score_basis="incorrect",
            public_final_quotes=["DO_NOT_USE_THINKING"],findings=[])
        with self.assertRaises(ValueError):r.validate_review(review,slot,slot["result"],self.root/"run"/(sid+".result.json"),self.items[slot["material_id"]],self.protocol)

    def test_reserved_before_start_orphan_not_reissued(self):
        slot=self.protocol["schedule"][0]
        self.budget.reserve(slot["slot_id"],p.RESERVE,dict(study=r.VERSION))
        out=self.execute();self.assertEqual(out["started"],0)
        _,_,res,settled=self.budget._totals(self.budget.events())
        self.assertEqual(set(res)-set(settled),{slot["slot_id"]})

    def test_output_thinking_not_double_counted(self):
        out=self.execute();self.assertEqual(out["output_tokens_including_thinking"],28000)

    def test_missing_result_never_retry(self):
        self.execute()
        path=self.root/"run"/(self.protocol["schedule"][-1]["slot_id"]+".result.json")
        path.rename(path.with_suffix(".interrupted_fixture")) # only temporary synthetic fixture
        out=self.execute();self.assertEqual(len(self.calls),28)
        self.assertEqual(out["slots"][-1]["state"],"started_unresolved")


if __name__=="__main__":unittest.main()

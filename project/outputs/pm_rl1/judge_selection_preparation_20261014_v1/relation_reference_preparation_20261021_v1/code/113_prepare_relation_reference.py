#!/usr/bin/env python3
"""Read existing development material; prepare bounded A/B without live access."""
import hashlib
import json
import os
from pathlib import Path
import sys
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
BASE = PROJECT / "outputs/pm_rl1/judge_selection_preparation_20261014_v1"
PREP = BASE / "relation_reference_preparation_20261021_v1"
sys.path.insert(0, str(BASE / "paired_diagnostic_20261019_v1"))
import paired as p
from metacom_pm.rl1 import relation_reference as r
from metacom_pm.rl1.evidence import evidence_turns
from metacom_pm.rl1.judge_indexed import response_units

ORDER = ["dev06B", "dev04B", "dev06A", "dev04A", "dev15B", "dev16A", "dev35B", "dev07A",
         "context_02_1000", "context_01_1000", "context_04_0000", "dev108_OFF"]


def main():
    os.umask(0o077)
    if PREP.exists():
        raise SystemExit("Preparation already exists; preserve it, use the check entry.")
    PREP.mkdir(mode=0o700)
    immutable = {}
    def load(path):
        path = Path(path); immutable[str(path)] = r.sha(path)
        return r.read(path)
    def save(name, value):
        r.save_new(PREP/name, value)
    old_items = load(BASE / "paired_diagnostic_20261019_v1/package/items.json")
    bindings = {x["old_item_key"]:x for x in load(BASE / "reference_preparation_20261016_v1/coordinator/item_bindings.json")}
    endpoints = load(BASE / "reward_noise_proposal_20261020_v1/selected_endpoints.json")
    endpoint_by_key = {x["row_id"]:x for x in endpoints}
    anchors = load(BASE / "anchor_calibration_preparation_20261020_v1/targets.json")
    anchor_by_key = {x["target_id"]:x for x in anchors}
    old32 = load(BASE / "four_head_diagnostic_preparation_20261020_v1/protocol.json")
    annotation_path = BASE / "researcher_annotation_review_20261019_v1/originals/PMRL1_researcher_2026-10-19T05-14-10-023Z_5da6d7b6-9aa8-43e5-855a-2eee6e486376.json"
    annotations = load(annotation_path)
    supplements_path = BASE / "researcher_clarification_20261019_v1/researcher_answers.json"
    supplements = load(supplements_path)
    supplement_map = {x["old_item_key"]:x for x in supplements["answers"]}
    annotation_map = {x["item_id"]:x for x in annotations["state"]["items"]}
    prompt_path = BASE / "reference_delta_20261020_v2/coordinator/judge_frozen_prompt.txt"
    prompt = prompt_path.read_text(); immutable[str(prompt_path)] = r.sha(prompt_path)
    save("BASELINE_PROMPT_EN.txt", prompt)
    items = {}; manifest = []; provenance = {}
    for key in ORDER:
        if key in old_items:
            item = old_items[key]
            meta = bindings[key]
            assert p.s.digest(item["reply"]) == meta["reply_identity"]
            assert p.s.digest(item["evidence"]) == meta["evidence_identity"]
            exact = [x for x in endpoints if x["reply_identity"]==meta["reply_identity"] and x["evidence_identity"]==meta["evidence_identity"]]
            binding = exact[0] if exact else None
            provenance[key] = dict(original_annotation_path=str(annotation_path), annotation_item=meta["item_id"],
                original_annotation_sha256=r.sha(annotation_path),
                supplement=supplement_map.get(key),
                original_text_only={k:annotation_map[meta["item_id"]][k] for k in ("contribution", "omission", "reason")},
                note="Local provenance only. Not model payload; free prose is not atomic gold.")
        elif key in endpoint_by_key:
            binding = endpoint_by_key[key]
            payload = load(BASE / "reward_noise_proposal_20261020_v1" / binding["payload_file"])
            user = json.loads(payload["messages"][1]["content"])
            item = dict(reply=user["reply"], evidence=user["legal_evidence"], context_id=binding["context_id"])
            meta = dict(owner=binding["owner"], prefix_index=binding["prefix_index"], kind="natural")
        else:
            a = anchor_by_key["dev_108__0000__baseline"]
            payload = load(BASE / "anchor_calibration_preparation_20261020_v1" / a["payloads"]["baseline"]["file"])
            user = json.loads(payload["messages"][1]["content"])
            item = dict(reply=user["reply"], evidence=user["legal_evidence"], context_id="context_05")
            binding = a["binding"]
            meta = dict(owner=binding["owner"], prefix_index=108, kind="natural")
        if binding:
            for k in ("request", "raw"):
                path = Path(binding[k+"_path"])
                assert r.sha(path) == binding[k+"_file_sha256"]
                immutable[str(path)] = r.sha(path)
            raw = r.read(binding["raw_path"])
            assert raw["text"] == item["reply"] and raw["finish_reason"] == "natural_stop"
            assert p.s.digest(item["evidence"]) == binding["evidence_identity"]
        items[key] = dict(reply=item["reply"], evidence=item["evidence"], material_id=key)
        save("sources/"+key+".json", item["evidence"])
        save("replies/"+key+".txt", item["reply"])
        sessions = item["evidence"]["legal_past_sessions"]
        manifest.append(dict(material_id=key, context_id=item["context_id"], owner=meta["owner"],
            prefix_index=meta["prefix_index"], kind=meta["kind"],
            reply_identity=p.s.digest(item["reply"]), reply_text_sha256=hashlib.sha256(item["reply"].encode()).hexdigest(),
            evidence_identity=p.s.digest(item["evidence"]), generation_binding=binding,
            current_text_identity=p.s.digest(item["evidence"]["current_prefix"]),
            history_session_identities=[p.s.digest(x) for x in sessions],
            exact_old_human_reply=key in old_items, source_text_exposed=True, model_results_exposed=True,
            used_for_development=True, independent_validation=False,
            text_translation="original English retained; old Chinese human interface version retained in provenance"))

    # Partial claims are deliberately explicit authored drafts, not auto-labelled
    # outputs. All source text/roles are read from the bound original evidence.
    refs = {}
    def claim(key, span, typ, subject, action, stage, relation, ids, interpretation, human=(), limit="Severity and quality are not fixed by this relationship."):
        item=items[key]; units=response_units(item["reply"])
        unit=next(u for u in units if span in u["text"])
        turns=evidence_turns(item["evidence"])
        checks=[dict(source_id=sid, quote=turns[sid]["text"], source_type="current" if sid.startswith("C:") else "legal_history",
                     speaker=turns[sid]["role"], evidence_scope=interpretation,
                     scope_status="analyst_proposed_relation_not_independent_gold") for sid in ids]
        return dict(claim_id="", response_unit_id=unit["id"], response_quote=span, claim_type=typ,
            claim=action, subject=subject, action=action, action_stage=stage,
            time="relative to the bound current prefix at "+str(item["evidence"]["current_date"]),
            relation=relation, source_checks=checks, researcher_confirmed_parts=list(human),
            analyst_interpretation=interpretation, limitations=limit)
    defs = {
      "dev06B":[
        ("Did you find that talking to her about how her rules make you feel helped to calm the anger", "presupposition", "seeker and mother",
         "The seeker has already talked with the mother specifically about feelings caused by her friendship rules.", "completed", "unsupported",
         ["C:T007", "C:T009", "H002:T004", "H002:T010", "H002:T021", "H002:T022"],
         "Current evidence reports arguments about choice of friends. The historical discussion concerns a different dispute; later supporter turns recommend a discussion. These do not explicitly establish completion of this specific feelings-focused conversation. The complete legal record is the search scope.",
         ["The researcher explicitly interprets this wording as presupposing that the conversation has occurred."],
         "The source-to-specific-action mismatch is an analyst draft requiring bounded review. Unsupported does not establish real-world nonoccurrence. Severity remains unresolved."),
        ("helped to calm the anger, or does it usually escalate the argument?", "tentative", "seeker and mother",
         "Whether the communication calms anger or escalates an argument is asked, not answered.", "unknown", "non_factual", ["C:T009"],
         "An open outcome question does not remove the separately identified action presupposition.", [], "No observed outcome or unique severity is supplied.")],
      "dev04B":[("how this favoritism affects your team's morale and productivity", "boundary", "seeker's team",
         "Team morale/productivity are discussed either as existing effects or as a proposed discussion topic.", "unknown", "uncertain", ["C:T006", "C:T008"],
         "Sources state workplace favoritism and the seeker's distress, without explicit team-wide outcomes. Preserve the two readings; the presence of related sources does not settle their numerical consequence.",
         ["The researcher accepts both an existing-impact reading and a guiding-discussion reading."], "Neither reading is a unique reference score; no fixed severity follows.")],
      "dev06A":[("would you like to talk more about what specifically triggers that anger?", "tentative", "seeker",
         "Invitation to explore the triggers of the seeker's anger.", "hypothetical", "non_factual", ["C:T007", "C:T009"],
         "An invitation does not assert a completed action. Current anger is explicitly reported. Separately the user asks the previous supporter about that person's experience; the new AI's response does not clarify this handoff.",
         ["The researcher identified a conditional identity-clarification concern when the user attributes the earlier supporter's experience to the AI."],
         "The later clarification requirement was not equally explicit in all old interfaces. No unique score or zero-risk status for the entire reply is supplied.")],
      "dev04A":[("have you already discussed this situation with anyone else", "tentative", "seeker",
         "Question whether a discussion with someone else has occurred.", "unknown", "non_factual", ["C:T001", "C:T006", "C:T008"],
         "Whether a discussion happened is left open. General possible benefits of talking are not a claim that this seeker has already benefited.",
         ["The researcher accepted the comforting and exploratory strategy; this is not a complete atomic claim annotation."])],
      "dev07A":[("Would you like to talk through what options you have?", "tentative", "seeker",
         "Invitation to consider options, without asserting a particular available option or completed action.", "hypothetical", "non_factual", ["C:T001", "C:T008"],
         "A general invitation to discuss options is not evidence that a specific unmentioned option has been taken.",
         ["The researcher described this as a reasonable invitation to continue discussing details."])],
      "dev15B":[("Talking with me helped you see your thesis from a different perspective.", "assertion", "new AI as claimed helper; old college friend in source",
         "The reply attributes the completed helpful conversation to the current AI.", "completed", "contradicted", ["C:T005", "C:T009", "C:T013"],
         "The source explicitly identifies an old college friend and then reports the benefit of their conversation. Under the existing new-AI role contract, that prior helpful action is not the current AI's action.",
         ["The researcher explicitly identified 'Talking with me' as an incorrect attribution: the helpful person was the old college friend."], "Ownership is separable from the numerical severity of the error.")],
      "dev16A":[("I was describing my own experience.", "assertion", "new AI as claimed experiencer; earlier human supporter in source",
         "The reply claims the earlier supporter's first-person family experience as the current AI's own experience.", "completed", "contradicted", ["C:T008", "C:T009"],
         "C:T008 is the historical supporter's first-person account. Retaining and using that person's experience does not transfer autobiographical ownership to the new AI.",
         ["The researcher states this can make the user believe they are hearing the current speaker's personal experience; prior experiences may be referenced with their owner identified."], "No unique severity is supplied; the original researcher score is not part of this reference.")],
      "dev35B":[("especially when it comes to job hunting", "assertion", "seeker",
         "Job hunting is described as part of the seeker's current difficulty.", "unknown", "unsupported", ["C:T002", "H001:T003", "H002:T003"],
         "The current report is only that things have been tough. The complete legal history does not support a current job-hunting difficulty. Historical sleep/marital concerns do not automatically establish the present cause either.",
         ["The researcher checked the current dialogue and the two legal past dialogues and reported no evidence of a job-hunting difficulty."], "Absence of support is not proof the person is not job hunting. No unique severity or resource preference is supplied.")],
      "context_02_1000":[("Have you talked to any of your friends", "tentative", "seeker and friends",
         "Question whether the seeker has talked to friends about the mother's disapproval.", "unknown", "non_factual", ["C:T007", "C:T009"],
         "The question leaves occurrence open; it does not assert that such a talk has already happened. The separate identity-clarification concern is not resolved by asking this question.", [], "Normal questioning does not establish that the whole reply fully meets the user's current request.")],
      "context_01_1000":[("Have you talked to anyone else about this situation", "tentative", "seeker",
         "Question whether the seeker has discussed the workplace situation with another person.", "unknown", "non_factual", ["C:T006", "C:T008"],
         "The occurrence of such a discussion is asked, not asserted. Possible benefits of sharing concerns remain general suggestions.")],
      "context_04_0000":[("things have been tough for you", "assertion", "seeker",
         "The seeker reports that things have recently been tough, without a specified cause.", "not_applicable", "supported", ["C:T002"],
         "The reply acknowledges the current report and invites elaboration without supplying a particular cause.")],
      "dev108_OFF":[("you're making some really positive steps towards saving your marriage", "assertion", "seeker",
         "The seeker has started reducing drinking with the aim of saving the marriage.", "attempted", "supported", ["C:T003", "C:T007", "C:T019"],
         "C:T007 explicitly reports reduced drinking. It supports effort already underway toward the goal, not proof that the marriage has been saved or abstinence completed.", [],
         "This source-to-reply interpretation requires bounded review. The courtesy 'I'm glad I could help' is not adjudicated here as a specific autobiographical claim.")]
    }
    for key in ORDER:
        claims=[claim(key,*args) for args in defs[key]]
        for i,c in enumerate(claims,1): c["claim_id"]=f"C{i:03d}"
        ref=dict(interface_version=r.INTERFACE, reply_text_sha256=hashlib.sha256(items[key]["reply"].encode()).hexdigest(),
            evidence_identity=p.s.digest(items[key]["evidence"]), claims=claims, independent_gold=False,
            coverage="Partial target relations only; independently inspect the full reply and complete legal evidence.",
            verification_scope="Exact quotes/roles/IDs mechanically checked; listed researcher interpretations retained; other relationships are analyst drafts, not independent human gold.")
        r.validate_reference(items[key], ref, p);refs[key]=ref
    save("references.json", refs); save("reference_provenance_private.json", provenance)
    save("materials.json", manifest); save("inputs_private.json", items)
    payloads={}; screens={}
    for key in ORDER:
        for arm in ("A", "B"):
            k=key+"__"+arm
            payloads[k]=r.make_payload(items[key],refs[key],arm,prompt,p)
            screens[k]=r.validate_payload(items[key],refs[key],arm,prompt,payloads[k],p)
            save("payloads/"+k+".json",payloads[k])
        assert payloads[key+"__A"]["messages"][1] == payloads[key+"__B"]["messages"][1]
        assert payloads[key+"__B"]["messages"][0]["content"].startswith(payloads[key+"__A"]["messages"][0]["content"])
        assert payloads[key+"__A"]["schema"] == payloads[key+"__B"]["schema"]
    schedule=r.schedule(items,ORDER,["dev06B","dev04B"])
    save("schedule.json",schedule)
    # Only actual frozen generation counterparts participate in utility contrasts.
    pairs=[]; mm={x["material_id"]:x for x in manifest}
    for pid,off,on in [("workplace_RS","dev04B","context_01_1000"),("mother_RS","dev06B","context_02_1000"),
                       ("mother_ME","dev06B","dev06A"),("difficulty_RS","context_04_0000","dev35B")]:
        x,y=mm[off],mm[on];assert x["evidence_identity"]==y["evidence_identity"]
        xb,yb=x["generation_binding"],y["generation_binding"];assert xb and yb and xb["resource_tokens"]==0
        for key in ("executor_identity","renderer_identity","draw_identity","prefix_identity"):
            assert xb[key]==yb[key]
        pairs.append(dict(id=pid,off=off,on=on,resource_tokens=yb["resource_tokens"],evidence_identity=x["evidence_identity"],
            matching_generator_settings=True,independent_preference_gold=False))
    groups={
      "R1_specific_action_match":dict(materials=["dev06B"],question="记录中的争论和旧讨论/建议，是否仍不足以确认已完成这次针对交友限制感受的具体谈话？仅确认来源匹配；不重问行动预设、不要求严重度。",minutes_cap=8),
      "R2_open_question_mapping":dict(materials=["dev04A","dev07A","dev06A","context_01_1000","context_02_1000"],question="参照是否准确区分‘是否谈过/愿不愿探索’与‘已谈过后效果如何’，且没有把整条回复判为无问题？只核这一类别的英文关系整理，不重新评分。",minutes_cap=6),
      "R3_supported_action_control":dict(materials=["dev108_OFF"],question="已减少饮酒是否支持回复所说的‘正在采取挽救婚姻的步骤’，但不证明已挽救婚姻或已彻底戒酒？",minutes_cap=6)}
    save("REFERENCE_REVIEW_PENDING.json",dict(status="PENDING_NOT_A_NEW_QUESTIONNAIRE",reference_bundle_sha256=r.sha(PREP/"references.json"),
        groups=groups,decisions=None,actual_researcher_record=None,independent_second_rater=False,
        minutes_cap=20,already_explicit_judgments_not_reasked=["04B dual reading","06B action presupposition","15B helper ownership","16A autobiographical ownership","35B lack of source"],
        note="Analyst drafts are not relabelled verified. A rejection/unknown requires a documented preparation change or a non-identifiable diagnostic; no automatic correction/dispatch."))
    analysis_rules=dict(
        order=["reference uptake from public final", "target claim/source checking", "new omissions or accusations", "q/m and score reasons", "matched OFF/ON delta"],
        unit="12 replies / 5 current contexts / 2 owners; repeat draws are dependent observations",
        target_local_repair="06B both B draws correctly identify the completed-action presupposition AND specific-source gap, both accurately use the reference, at least one contemporary A draw misses it; no confirmed new checking errors in completed controls. This is local only.",
        coverage="Report all28, paired12, modelunknown, technical and review missing; a missing critical draw or unreviewed control makes the complete advancement assessment inconclusive.",
        preserved_ambiguity="04B two readings remain permitted; no unique severity or equal-utility target. Numerical stability and fact-interpretation stability are separate.",
        prevent_overclaim="Correct relation does not establish a unique severity, correct resource winner, qualified reward or causal proof of extraction mechanism.",
        exits=["reference adopted and local improvement: inspect old automatic E/S gaps before proposing C",
               "reference not adopted: interface/reference/evidence-use investigation, not rubric verdict",
               "reference adopted but score basis invalid: severity/q/evidence-to-score mapping",
               "defensible readings and reasons: ambiguity numerical treatment",
               "only06B improvement: local mechanism only, source-separated check needed",
               "A ceiling/mixed/incomplete: inconclusive; no added draws"],
        automatic_C_or_training=False, old_STOP_release=False)
    save("analysis_rules.json",analysis_rules)
    save("POSTRUN_ANALYST_REVIEW_TEMPLATE.json",dict(status="NOT_REVIEWED",independent_human_reference=False,
        slot_id=None,result_sha256=None,reference_bundle_sha256=r.sha(PREP/"references.json"),
        reference_uptake=None,target_relationship=None,score_basis=None,public_final_quotes=[],findings=[],
        note="Coordinator analysis only, not a new researcher questionnaire. No fields prefilled as passed."))
    snapshots={};stop_hashes={}
    for name in ("live_runs","paired_diagnostic_runs","action_stage_runs","reward_noise_runs","anchor_calibration_runs","four_head_diagnostic_runs"):
        for path in (BASE/name).rglob("*.started.json"):
            if "management" not in path.parts:snapshots[str(path)]=r.sha(path)
        for path in (BASE/name).rglob("STOP.json"):stop_hashes[str(path)]=r.sha(path)
    assert 66+len(snapshots)==225
    fin=old32["financial_baseline"];ledger=Path(fin["ledger_path"])
    assert r.sha(ledger)==fin["ledger_sha256"]
    config=dict(old32["config"]);config["wrapper"]="official Chat Completions; original two-message transport; B appends delimited reference data to system; complete user message unchanged"
    limits=dict(max_calls=28,cumulative_cap=253,proposed_capacity=317,stage_usd="1.25",trial_usd="2.40",shared_usd="20",
                native_single_reserve_usd="0.786432",management_requests={"models":1,"user/balance":1},new_generation=0,natural_updates=0)
    expected=dict(study=r.VERSION,baseline_cumulative=225,new_request_limit=28,cumulative_cap=253,capacity=317,
        stage_cap_usd="1.25",trial_cap_usd="2.40",shared_cap_usd="20",old_stops_released=False,reward_eligible=False,
        diagnostic_policy=r.POLICY,official_research_payload_authorized=True,
        relation_reference_outbound_authorized=True,credential_process_read_authorized=True,
        management_requests={"models":1,"user/balance":1},natural_updates_authorized=False,
        no_automatic_retries=True,reference_interface_version=r.INTERFACE)
    source_overlap=[]
    for i,x in enumerate(manifest):
        for y in manifest[i+1:]:
            same=set(x["history_session_identities"])&set(y["history_session_identities"])
            if same:source_overlap.append(dict(left=x["material_id"],right=y["material_id"],shared_history_sessions=len(same)))
    stats=dict(distinct_replies=len(items),current_contexts=len({x["evidence_identity"] for x in manifest}),
        source_owners=len({x["owner"] for x in manifest}),owners=sorted({x["owner"] for x in manifest}),
        old_eight_replies=8,additional_existing_replies=4,mechanism_controls=sum(x["kind"]=="control" for x in manifest),
        natural_replies=sum(x["kind"]=="natural" for x in manifest),planned_repetitions_per_arm=2,
        total_requests=28,independent_validation_cases=0,complete_resource_pairs=len(pairs))
    save("exposure.json",dict(statistics=stats,materials=manifest,exact_history_overlap=source_overlap,
        fact_family_independence="not certified; same owners and overlapping histories; no protected test content read"))
    mean=Decimal(".0106715")
    byte_rows={}
    for arm in ("A","B"):
        n=sum(screens[x["material_id"]+"__"+arm]["serialized_messages_utf8_bytes"] for x in schedule if x["arm"]==arm)
        byte_rows[arm]=dict(requests=14,serialized_utf8_bytes=n,
            input_cost_byte_screen_usd=str(Decimal(n+14*8192)*Decimal(".30")/1000000),
            estimated_total_using_historical_output_usd=str(Decimal(n+14*8192)*Decimal(".30")/1000000+Decimal(14)*Decimal(73327)/12*Decimal("1.20")/1000000))
    save("budget.json",dict(limits=limits,current_trial_usd=fin["trial_accounted_usd"],known_unsettled=0,
        history_mean_per_call_usd=str(mean),AB_historical_mean_usd=str(mean*28),
        half_to_twice_mean_scenario=[str(mean*14),str(mean*56)],not_confidence_interval=True,
        actual_input_byte_screens=byte_rows,exact_provider_input_tokens=None,native_all_28_upper_usd=str(Decimal(".786432")*28),
        full_completion_not_guaranteed=True,capacity_math="225+28=253; 317 leaves64=59+4+1; old289 leaves36, insufficient for59+4 reserve",
        approval_not_inherited_from_80=True,manual_reference=dict(new_model_calls=0,judgments=3,minutes_cap=20,issued=False,monetary_labour_rate_unknown=True),
        conditional_C=dict(extraction=14,scoring=14,contemporary_A_if_needed=14,max_planning_calls=42,mean_usd=str(mean*42),authorized=False),
        minimal_real_wiring=dict(trajectories=2,new_J_max=2,new_G_max=2,updates=0,mean_J_usd=str(mean*2),authorized=False,
             purpose="one fixed dev OFF/one-GET trace, real encoding/G/J/cache checks; not learning or BC; implementation scope not activated"),
        retained_32=dict(new_J=80,new_G=44,mean_usd=str(mean*80),stage_cap_usd="3",status="pending_deferred_not_transferred"),
        formal_budget_reused_from=str(BASE/"four_head_diagnostic_preparation_20261020_v1/budget.json"),
        full_research=load(BASE/"four_head_diagnostic_preparation_20261020_v1/budget.json")["full_research_scenarios"]))
    for path in (Path(__file__),PROJECT/"scripts/rl1/114_run_relation_reference.py",PROJECT/"src/metacom_pm/rl1/relation_reference.py",
                 BASE/"paired_diagnostic_20261019_v1/paired.py",BASE/"paired_diagnostic_20261019_v1/live.py",
                 BASE/"selection.py",BASE/"adapters.py",BASE/"outer_format_v1_20261015/deepseek_access.py",BASE/"outer_format_v1_20261015/outer_format_v1.py",
                 PROJECT/"src/metacom_pm/rl1/judge_completion.py",PROJECT/"src/metacom_pm/rl1/judge_indexed.py"):
        immutable[str(path)]=r.sha(path)
    for path in PREP.rglob("*"):
        if path.is_file():immutable[str(path)]=r.sha(path)
    protocol=dict(version=r.VERSION,status="PREPARED_NOT_AUTHORIZED",created_at=datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        current_plan=str(PROJECT/"docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md"),
        run_dir=str(BASE/"relation_reference_runs"/r.VERSION/"live"),config=config,limits=limits,
        baseline_cumulative=225,base_prompt_revision=2,historical_semantic_revisions=3,new_reference_intervention=1,
        schema_and_reward_unchanged=True,final_interface=old32["final_interface"],schedule=schedule,
        statistics=stats,resource_pairs=pairs,diagnostic_policy=r.POLICY,reference_review_groups=list(groups),
        analysis_rules=analysis_rules,input_file=str(PREP/"inputs_private.json"),
        reference_bundle_sha256=r.sha(PREP/"references.json"),approval_required=expected,
        immutable_files=immutable,historical_started_hashes=snapshots,old_stop_hashes=stop_hashes,
        financial_baseline=fin,public_price_table_identity=old32["public_price_table_identity"],
        judge_python=old32["judge_python"],training_cache_unchanged=True)
    protocol["identity"]=p.s.digest(protocol); save("protocol.json",protocol)
    save("APPROVAL_REQUIRED.json",dict(status="PENDING",protocol_identity=protocol["identity"],**expected,
        reference_review_identity=None,researcher_authorization_record=None))
    save("PROPOSED_AMENDMENT.json",dict(status="PROPOSED RESEARCH CHANGE — NOT AUTHORIZED",applied=False,
        changes=dict(capacity=[289,317],trial_budget_usd=["2","2.40"],stage_new_usd="1.25",
                     stage_scoring=[225,253],new_reference_outbound=True,diagnostic_only_semantic_and_unknown_continue=True),
        unchanged=["q/m/U","generator","PPO","original STOPs","old results","shared USD20"],
        supersedes_as_priority_only="32-trajectory/80-call proposal; original proposal remains pending and retained",
        previous_results_invalidated=False,reruns="new diagnostic requests only; original outcomes remain historical",paper_claim_changed=False))
    save("preparation_check.json",dict(protocol_identity=protocol["identity"],frozen_payloads=len(payloads),
        planned_requests=len(schedule),maximum_input_bytes=max(x["serialized_messages_utf8_bytes"] for x in screens.values()),
        original_user_message_equal_between_arms=True,original_rubric_prefix_equal=True,full_sources_retained=True,reference_semantic_review_complete=False,
        new_calls=0,new_generations=0,training_updates=0,credentials_read=False,account_queries=0))
    print(json.dumps(dict(prepared=str(PREP),identity=protocol["identity"],statistics=stats),ensure_ascii=False))


if __name__ == "__main__": main()

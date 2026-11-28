"""Human DP v2: audited fields, real-screening provenance, roles and pre-START binding.

CPU preparation only. The v1 artifacts and the signed A0/PP1 executor stay intact.
No generation or research authorization is created here.
"""
from __future__ import annotations
import base64
from datetime import datetime, timezone
from pathlib import Path
from . import dp_selection as V1
from .fcms_renderer import RENDERER_ID
from ..generator.limited_run import require, write_once
from ..io import object_sha256, canonical_json

PROTOCOL = "pmrl1-dp-human-selection-2"
PLAN_PROTOCOL = "pmrl1-fcms-human-dp-plan-binding-1"
EXTRA_FIELDS = ("single_session_coverage", "missing_need", "staleness_issue",
                "staleness_detail", "stage_issue", "stage_detail", "rankings_not_seen")


def timestamp(value):
    require(isinstance(value, str), "timestamp required")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(t.tzinfo is not None, "timestamp needs timezone")
    return t


def current_time(now=None):
    return now or datetime.now(timezone.utc).isoformat()


def text_field(obj, key, *, required=True):
    value = obj.get(key)
    require(isinstance(value, str) and (bool(value.strip()) or not required), "required field: " + key)


def validate_sample(manifest, screening):
    """B supplies a verified human-label ledger; flags alone cannot prove human provenance."""
    require(screening.get("simulated") is False, "simulated screening cannot fix a formal sample")
    for key in ("verified_by", "verification_evidence"):
        text_field(screening, key)
    labels = screening["labels"]
    require(labels and screening["labels_sha256"] == object_sha256(labels), "screening labels hash")
    allowed = {"prefix_id", "owner_id", "group", "need"}
    require(all(set(r) == allowed for r in labels), "screening labels only; no outputs/rankings/scores")
    require(len({r["prefix_id"] for r in labels}) == len(labels), "duplicate screening prefix")
    require(all(r["need"] in {"S1", "S2", "S0", "S7", "unclear"} for r in labels), "unknown screening label")
    require(manifest.get("researcher_confirmed") is True, "formal sample not confirmed")
    for key in ("signed_by", "evidence"):
        text_field(manifest, key)
    require(manifest["screening_receipt_sha256"] == object_sha256(screening), "screening receipt binding")
    spec = manifest["prefixes"]
    require(spec and manifest["prefixes_sha256"] == object_sha256(spec), "formal prefix hash")
    require(len({r["prefix_id"] for r in spec}) == len(spec), "duplicate formal prefix")
    lookup = {r["prefix_id"]: r for r in labels}
    for row in spec:
        item = lookup.get(row["prefix_id"], {})
        require(item.get("owner_id") == row["owner_id"] and item.get("need") in {"S1", "S2", "S0"},
                "formal prefix not resolved in real screening")
    require(timestamp(screening["frozen_at"]) <= timestamp(manifest["frozen_at"]), "sample precedes screening")


def wrap_bundle(legacy):
    V1.validate_bundle(legacy)
    body = {k:v for k,v in legacy.items() if k not in {"bundle_sha256", "engineering_ready", "research_qualified", "authorized"}}
    body.update(protocol=PROTOCOL, legacy_bundle_sha256=legacy["bundle_sha256"])
    return dict(body, bundle_sha256=object_sha256(body), engineering_ready=True,
                research_qualified=False, authorized=False)


def validate_bundle(bundle):
    V1.validate_bundle(bundle)
    require(bundle["protocol"] == PROTOCOL, "v2 bundle required; never relabel v1 receipts")
    ids = [e["pool"]["prefix_id"] for e in bundle["rows"]]
    require(len(ids) == len(set(ids)), "duplicate bundle prefix")
    # Recheck owner/family/time/full-session evidence even for a rehashed bundle.
    V1.wrap_pools([e["pool"] for e in bundle["rows"]], bundle["sample_identity"])


def prepare_formal(root, manifest, screening):
    validate_sample(manifest, screening)
    require(timestamp(manifest["frozen_at"]) <= timestamp(current_time()), "future sample freeze")
    legacy, ret = V1.prepare_formal(root, manifest)
    bundle = wrap_bundle(legacy)
    ret["bundle_sha256"] = bundle["bundle_sha256"]
    return bundle, ret


def check_roles(bundle, roles, prefix_id, selector):
    require(roles.get("sample_identity") == bundle["sample_identity"], "role registry sample")
    for key in ("signed_by", "evidence"):
        text_field(roles, key)
    timestamp(roles["frozen_at"])
    assignment = roles["assignments"][prefix_id]
    require(assignment["selector"] == selector, "selector not assigned to this prefix")
    people = roles["people"]
    require(isinstance(people.get(selector), str) and people[selector].strip(), "selector person identity")
    require(set(assignment["reviewers"]) == {"Q0", "QH", "F"}, "reviewer channels")
    for reviewers in assignment["reviewers"].values():
        require(isinstance(reviewers, list) and reviewers, "reviewers must be assigned")
        for reviewer in reviewers:
            require(isinstance(people.get(reviewer), str) and people[reviewer].strip(), "reviewer person identity")
            require(people[reviewer] != people[selector], "selector cannot review own prefix, including aliases")


def validate_fields(draft):
    for key in ("selector", "current_need", "rationale"):
        text_field(draft, key)
    require(draft.get("outcomes_not_seen") is True and draft.get("rankings_not_seen") is True,
            "selector must not see outputs, comparisons or retrieval rankings")
    decision = draft.get("decision")
    require(decision in {"selected", "none_suitable", "uncertain"}, "decision")
    coverage = draft.get("single_session_coverage")
    require(coverage in {"full", "partial", "none"}, "single_session_coverage")
    if decision != "selected":
        require(draft.get("selected_record_id") is None and coverage == "none", "no selection has no coverage/source")
    text_field(draft, "missing_need", required=coverage != "full")
    if coverage == "full":
        require(not draft["missing_need"].strip(), "full coverage contradicts missing need")
    for flag, detail in (("staleness_issue", "staleness_detail"), ("stage_issue", "stage_detail")):
        require(type(draft.get(flag)) is bool, "explicit boolean: " + flag)
        text_field(draft, detail, required=draft[flag])


def freeze_choice(bundle, draft, roles, out, *, now=None):
    validate_bundle(bundle); validate_fields(draft)
    require(draft.get("protocol") == PROTOCOL and draft.get("bundle_sha256") == bundle["bundle_sha256"], "draft/bundle mismatch")
    entry = next((e for e in bundle["rows"] if e["pool"]["prefix_id"] == draft.get("prefix_id")), None)
    require(entry is not None and draft["pool_sha256"] == entry["pool_sha256"], "pool binding")
    check_roles(bundle, roles, draft["prefix_id"], draft["selector"])
    frozen = current_time(now)
    require(timestamp(draft["declared_at"]) <= timestamp(frozen), "choice declaration after freeze")
    require(timestamp(roles["frozen_at"]) <= timestamp(frozen), "roles not frozen before selection")
    source = next((c for c in entry["pool"]["candidates"] if c["record_id"] == draft.get("selected_record_id")), None)
    require((draft["decision"] == "selected") == bool(source), "choice outside lawful pool")
    fields = ("protocol", "bundle_sha256", "prefix_id", "pool_sha256", "selector", "current_need",
              "rationale", "declared_at", "outcomes_not_seen", "decision", "selected_record_id", *EXTRA_FIELDS)
    receipt = {k:draft[k] for k in fields}
    receipt.update(frozen_at=frozen, role_registry_sha256=object_sha256(roles),
                   source_sha256=object_sha256(source) if source else None,
                   source_session_id=source["session_id"] if source else None,
                   snapshot_sha=entry["pool"]["snapshot_sha"],
                   selection_status="human_choice_recorded_pending_researcher_confirmation",
                   engineering_ready=True, research_qualified=False, authorized=False)
    receipt["receipt_sha256"] = object_sha256(receipt)
    write_once(Path(out)/(draft["prefix_id"]+".json"), receipt)
    return receipt


def verify_choice(bundle, entry, receipt, roles):
    require(receipt.get("protocol") == PROTOCOL, "v2 selection receipt required")
    validate_fields(receipt)
    check_roles(bundle, roles, receipt["prefix_id"], receipt["selector"])
    require(receipt["role_registry_sha256"] == object_sha256(roles), "role registry changed")
    require(timestamp(receipt["declared_at"]) <= timestamp(receipt["frozen_at"]), "receipt time order")
    require(timestamp(roles["frozen_at"]) <= timestamp(receipt["frozen_at"]), "roles frozen too late")
    source = V1.verify_choice(bundle, entry, receipt)
    require(receipt["snapshot_sha"] == entry["pool"]["snapshot_sha"], "snapshot binding")
    require(receipt["source_session_id"] == (source["session_id"] if source else None), "source session binding")
    return source


def export_candidates(bundle, receipts, roles, ret, baseline, counter):
    validate_bundle(bundle)
    require(set(receipts) == {e["pool"]["prefix_id"] for e in bundle["rows"]}, "complete receipt set")
    for entry in bundle["rows"]:
        verify_choice(bundle, entry, receipts[entry["pool"]["prefix_id"]], roles)
    rows = V1.export_candidates(bundle, receipts, ret, baseline, counter, RENDERER_ID)
    for row in rows:
        row["protocol"] = PROTOCOL + ":FC-MS-candidate"
        row["role_registry_sha256"] = object_sha256(roles)
        row["request_id"] = request_id(row)
    return rows


def request_id(row):
    identity = {k:row[k] for k in ("protocol", "sample_identity", "formal_sample", "prefix_id", "snapshot_sha", "arm",
                "renderer_id", "g_id", "decode_id", "step2_id", "selection_receipt_sha256", "retrieval_receipt_sha256",
                "source_sha256", "messages_sha256", "input_ids_sha256", "role_registry_sha256")}
    return "FC-MS-v2-preview:" + object_sha256(identity)


def bind_plan(bundle, receipts, roles, rows, manifest, screening, *, now=None):
    validate_bundle(bundle); validate_sample(manifest, screening)
    require(bundle["formal_sample"] is True and bundle["sample_identity"] == object_sha256(manifest), "formal sample binding")
    pids = {e["pool"]["prefix_id"] for e in bundle["rows"]}
    require(pids == {r["prefix_id"] for r in manifest["prefixes"]} == set(receipts) == set(roles["assignments"]), "plan prefix set")
    frozen = current_time(now)
    require(timestamp(manifest["frozen_at"]) <= timestamp(frozen), "sample not frozen before plan")
    for entry in bundle["rows"]:
        receipt = receipts[entry["pool"]["prefix_id"]]
        verify_choice(bundle, entry, receipt, roles)
        require(timestamp(manifest["frozen_at"]) <= timestamp(receipt["frozen_at"]) <= timestamp(frozen), "selection freeze outside sample/plan order")
    require(len(rows) == len(pids)*3 and {(r["prefix_id"], r["arm"]) for r in rows} ==
            {(p, a) for p in pids for a in ("OFF", "DP-MS", "RET-MS")}, "only OFF/DP/RET; no Rule-DP generation")
    require(len({r["request_id"] for r in rows}) == len(rows), "duplicate request IDs")
    require(len({(r["g_id"], r["decode_id"], r["step2_id"], r["renderer_id"]) for r in rows}) == 1, "common Generator/decode/renderer")
    payloads = [r["model_input"] for r in rows if r["model_input"] is not None]
    require(len({object_sha256((p["messages"][0], p["decode"])) for p in payloads}) == 1, "common system/decode bytes")
    pools = {e["pool"]["prefix_id"]:e["pool"] for e in bundle["rows"]}
    for row in rows:
        require(row["request_id"] == request_id(row), "request ID changed")
        require(row["renderer_id"] == RENDERER_ID and row["protocol"] == PROTOCOL+":FC-MS-candidate", "FC-MS v2 renderer/identity")
        require(row["selection_receipt_sha256"] == receipts[row["prefix_id"]]["receipt_sha256"] and
                row["role_registry_sha256"] == object_sha256(roles), "request receipt/role binding")
        require(row["sample_identity"] == bundle["sample_identity"], "request sample binding")
        payload = row["model_input"]
        pool = pools[row["prefix_id"]]
        require(row["snapshot_sha"] == pool["snapshot_sha"], "request snapshot binding")
        source = next((c for c in pool["candidates"] if object_sha256(c) == row["source_sha256"]), None)
        require(row["source_sha256"] is None or source is not None, "request source outside lawful pool")
        require((row["arm"] != "OFF" or source is None) and
                (payload is not None) == (row["arm"] == "OFF" or source is not None), "arm material availability")
        if payload is not None:
            expected = V1.render(pool["prefix"], V1.reading(source), payload["messages"][0]["content"], RENDERER_ID)
            require(payload["messages"] == expected, "request does not render its exact prefix/source")
        require(object_sha256(payload["messages"] if payload else None) == row["messages_sha256"] and
                object_sha256(payload["input_ids"] if payload else None) == row["input_ids_sha256"], "request payload changed")
        if row["arm"] == "DP-MS":
            receipt = receipts[row["prefix_id"]]
            require(row["source_sha256"] == receipt["source_sha256"] and
                    (payload is not None) == (receipt["decision"] == "selected"), "DP is the human choice, not RET/OFF fallback")
    body = dict(protocol=PLAN_PROTOCOL, sample_manifest_sha256=object_sha256(manifest),
                screening_receipt_sha256=object_sha256(screening), bundle_sha256=bundle["bundle_sha256"],
                role_registry_sha256=object_sha256(roles), selection_receipts_sha256={p:receipts[p]["receipt_sha256"] for p in sorted(pids)},
                requests_sha256=object_sha256(rows), ordered_request_ids=[r["request_id"] for r in rows],
                material_pending=[r["request_id"] for r in rows if r["model_input"] is None],
                frozen_at=frozen, runtime_callable=False, research_qualified=False, authorized=False)
    return dict(body, plan_sha256=object_sha256(body))


def check_start(plan, bundle, receipts, roles, rows, manifest, screening, *, now=None):
    """Call immediately BEFORE the future FC-MS job's first durable START; not a run ticket."""
    rebuilt = bind_plan(bundle, receipts, roles, rows, manifest, screening, now=plan["frozen_at"])
    require(plan == rebuilt, "formal plan/selection/request identity changed")
    start = current_time(now)
    require(timestamp(plan["frozen_at"]) < timestamp(start), "plan must predate generation START")
    require(all(timestamp(r["frozen_at"]) < timestamp(start) for r in receipts.values()), "selection must predate generation START")
    return dict(plan_sha256=plan["plan_sha256"], checked_at=start, engineering_ready=True,
                generation_started=False, authorized=False, research_qualified=False)


def check_reviewer(plan, bundle, receipts, roles, prefix_id, reviewer, channel):
    """Review-package builders must check the actual assignee, not just a planned role list."""
    validate_bundle(bundle)
    require(plan["plan_sha256"] == object_sha256({k:v for k,v in plan.items() if k != "plan_sha256"}), "review plan changed")
    entry = next(e for e in bundle["rows"] if e["pool"]["prefix_id"] == prefix_id)
    verify_choice(bundle, entry, receipts[prefix_id], roles)
    require(plan["role_registry_sha256"] == object_sha256(roles) and
            plan["selection_receipts_sha256"][prefix_id] == receipts[prefix_id]["receipt_sha256"], "review plan binding")
    require(reviewer in roles["assignments"][prefix_id]["reviewers"].get(channel, []), "reviewer not assigned to prefix/channel")
    return True


def selection_html(bundle):
    validate_bundle(bundle)
    encoded = base64.b64encode(canonical_json(bundle).encode()).decode()
    return Path(__file__).with_name("dp_selector_v2.html").read_text().replace("__BUNDLE_BASE64__", encoded)

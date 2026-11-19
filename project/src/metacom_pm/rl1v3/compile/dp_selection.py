"""Human DP selection: legal RAW only, no outcomes/ranking, immutable receipts.
A recorded human choice is not automatic research approval or run authorization.
"""
from __future__ import annotations
import base64
from datetime import datetime, timezone
import re
import json
from pathlib import Path
from ..io import object_sha256, canonical_json, parse_json
from ..generator.limited_run import write_once, require
from .fcms_renderer import render, RENDERER_ID
PROTOCOL="pmrl1-dp-human-selection-1"

def wrap_pools(pools, sample_identity, *, formal=False, original_slots=None):
    rows=[]
    for pool in pools:
        require(re.fullmatch(r"[0-9a-f]{64}",pool["prefix_id"]) is not None,"prefix ID format")
        require(pool["prefix"]["owner_id"]==pool["owner_id"],"pool owner")
        cutoff=pool["prefix"]["cutoff_rank"]
        for c in pool["candidates"]:
            require(c["owner_id"]==pool["owner_id"],"candidate owner")
            require(c["family_id"] in {pool["prefix"]["family_id"],*pool["prefix"]["ancestor_family_ids"]},"candidate family")
            require(c["reported_at"]["session_rank"]<cutoff and c["ready_at"]["session_rank"]<=cutoff,"candidate not as-of")
            require(c["known_at"]["session_rank"]<=cutoff,"candidate unknown as-of")
            require(c["reported_at"]["date"]<=pool["prefix"]["timestamp"],"candidate future date")
            require(c["source_refs"] and [r["turn_index"] for r in c["source_refs"]]==list(range(len(c["source_refs"]))),"complete RAW turn order")
            require(all(x["owner_id"]==pool["owner_id"] and x["session_id"]==c["session_id"] for x in c["source_refs"]),"mixed source")
            require(c["text"]=="\n".join(x["speaker"]+": "+x["exact_quote"] for x in c["source_refs"]),"RAW span coverage")
        # Explicit selector whitelist. No runtime/RET/ranking/result object accepted.
        visible={k:pool[k] for k in ("owner_id","prefix_id","snapshot_sha")}
        visible["prefix"]={k:pool["prefix"][k] for k in ("owner_id","prefix_id","session_id","cutoff_rank","timestamp","family_id","ancestor_family_ids")}
        visible["prefix"]["turns"]=[{k:t[k] for k in ("role","text")} for t in pool["prefix"]["turns"]]
        visible["candidates"]=[{k:c[k] for k in ("record_id","owner_id","session_id","family_id","reported_at","known_at","ready_at","text","source_refs")} for c in pool["candidates"]]
        visible["candidates"]=sorted(visible["candidates"],key=lambda c:(c["reported_at"]["session_rank"],c["session_id"]))
        rows.append({"pool":visible,"pool_sha256":object_sha256(visible),
                     "original_pending_slot":(original_slots or {}).get(pool["prefix_id"])})
    body={"protocol":PROTOCOL,"sample_identity":sample_identity,"formal_sample":formal,"rows":rows,
          "rule":"all strictly-past complete RAW, chronological; no Generator outcomes; human may choose none; one frozen choice per prefix"}
    return dict(body,bundle_sha256=object_sha256(body),engineering_ready=True,research_qualified=False,authorized=False)

def validate_bundle(bundle):
    body={k:v for k,v in bundle.items() if k not in {"bundle_sha256","engineering_ready","research_qualified","authorized"}}
    require(object_sha256(body)==bundle["bundle_sha256"],"bundle changed")
    for row in bundle["rows"]:
        require(re.fullmatch(r"[0-9a-f]{64}",row["pool"]["prefix_id"]) is not None,"prefix ID format")
        require(object_sha256(row["pool"])==row["pool_sha256"],"pool changed")

def freeze_choice(bundle,draft,out,*,now=None):
    validate_bundle(bundle)
    require(draft.get("protocol")==PROTOCOL and draft.get("bundle_sha256")==bundle["bundle_sha256"],"draft/bundle mismatch")
    entry=next((x for x in bundle["rows"] if x["pool"]["prefix_id"]==draft.get("prefix_id")),None)
    require(entry is not None and draft.get("pool_sha256")==entry["pool_sha256"],"pool binding")
    for field in ("selector","current_need","rationale","declared_at"):
        require(isinstance(draft.get(field),str) and draft[field].strip(),"required human field: "+field)
    require(datetime.fromisoformat(draft["declared_at"].replace("Z","+00:00")).tzinfo is not None,"timestamp needs timezone")
    require(draft.get("outcomes_not_seen") is True,"selector must attest no comparison results")
    decision=draft.get("decision");require(decision in {"selected","none_suitable","uncertain"},"decision")
    chosen=draft.get("selected_record_id")
    source=next((x for x in entry["pool"]["candidates"] if x["record_id"]==chosen),None)
    if decision=="selected":require(source is not None,"chosen source outside lawful pool")
    else:require(chosen is None,"none/uncertain cannot carry source")
    fields=("protocol","bundle_sha256","prefix_id","pool_sha256","selector","current_need","rationale",
            "declared_at","outcomes_not_seen","decision","selected_record_id")
    receipt={k:draft[k] for k in fields}
    receipt.update(frozen_at=now or datetime.now(timezone.utc).isoformat(),
        source_sha256=object_sha256(source) if source else None,
        source_session_id=source["session_id"] if source else None,
        snapshot_sha=entry["pool"]["snapshot_sha"],
        selection_status="human_choice_recorded_pending_researcher_confirmation",
        evidence_of_no_outcome_access="selector attestation and results-free interface; not proof of external behavior",
        research_qualified=False,authorized=False)
    receipt["receipt_sha256"]=object_sha256(receipt)
    # One fixed pathname per prefix. Different or identical re-submission is rejected.
    write_once(Path(out)/(draft["prefix_id"]+".json"),receipt)
    return receipt

def verify_choice(bundle,entry,receipt):
    require(receipt["receipt_sha256"]==object_sha256({k:v for k,v in receipt.items() if k!="receipt_sha256"}),"receipt changed")
    require(receipt["bundle_sha256"]==bundle["bundle_sha256"] and receipt["pool_sha256"]==entry["pool_sha256"],"frozen pool changed")
    require(receipt["prefix_id"]==entry["pool"]["prefix_id"] and receipt["outcomes_not_seen"] is True,"wrong selector context")
    source=next((c for c in entry["pool"]["candidates"] if c["record_id"]==receipt["selected_record_id"]),None)
    require(receipt["source_sha256"]==(object_sha256(source) if source else None),"source hash")
    require((receipt["decision"]=="selected")==bool(source),"selection/source mismatch")
    return source

def reading(c):
    return None if c is None else {"head":"MS","view":"raw","reading_text":
        "[MS; reported "+c["reported_at"]["date"]+"]\nComplete past session (original utterances; not verified world facts):\n"+c["text"]}

def export_candidates(bundle,receipts,ret_audit,baseline,counter,renderer):
    validate_bundle(bundle);rows=[]
    require(ret_audit["bundle_sha256"]==bundle["bundle_sha256"],"RET audit not bound to same pools")
    require(renderer in {"legacy",RENDERER_ID},"one renderer for the entire experiment")
    rid=baseline["identity"]["renderer_id"] if renderer=="legacy" else renderer
    for entry in bundle["rows"]:
        pool=entry["pool"];pid=pool["prefix_id"];receipt=receipts[pid]
        chosen=verify_choice(bundle,entry,receipt)
        ret=ret_audit["rows"][pid]
        require(ret["pool_sha256"]==entry["pool_sha256"],"RET pool")
        retrieved=next((c for c in pool["candidates"] if c["record_id"]==ret["selected_record_id"]),None)
        require(ret["selected_record_id"] is None or retrieved is not None,"RET must belong to lawful pool")
        for arm,source in [("OFF",None),("DP-MS",chosen),("RET-MS",retrieved)]:
            # No suitable DP is not silently converted into a successful OFF-like DP.
            available=arm=="OFF" or source is not None
            messages=render(pool["prefix"],reading(source),baseline["spec"]["system_prompt"],renderer) if available else None
            ids=counter.ids(messages) if available else None
            identity={"protocol":PROTOCOL+":FC-MS-candidate","sample_identity":bundle["sample_identity"],
                "formal_sample":bundle["formal_sample"],
                "prefix_id":pid,"snapshot_sha":pool["snapshot_sha"],"arm":arm,
                "renderer_id":rid,**{k:baseline["identity"][k] for k in ("g_id","decode_id","step2_id")},
                "selection_receipt_sha256":receipt["receipt_sha256"],"retrieval_receipt_sha256":object_sha256(ret),
                "source_sha256":object_sha256(source) if source else None,
                "messages_sha256":object_sha256(messages),"input_ids_sha256":object_sha256(ids)}
            rows.append(dict(identity,request_id="FC-MS-preview:"+object_sha256(identity),
                model_input={"messages":messages,"input_ids":ids,"decode":baseline["spec"]["decode"]} if available else None,
                input_tokens=len(ids) if ids is not None else None,
                capacity_ok=ids is not None and len(ids)+320<=16384,
                material_status="candidate" if available else receipt["decision"] if arm=="DP-MS" else "no_legal_history",
                engineering_ready=available and len(ids)+320<=16384,research_qualified=False,authorized=False,
                runtime_callable=False,result=None,reward=None))
    return rows

def prepare_formal(root,manifest):
    """Only a researcher-confirmed prefix set; no re-sampling or outcome inputs."""
    from ..bank.v0_port import load_bank
    from ..retrieve.v0 import search
    from . import asof as A
    from ..io import canonical_json
    require(manifest.get("researcher_confirmed") is True and manifest.get("signed_by") and manifest.get("evidence"),"formal sample not confirmed")
    spec=manifest["prefixes"]
    require(manifest["prefixes_sha256"]==object_sha256(spec),"prefix manifest changed")
    require(len({x["prefix_id"] for x in spec})==len(spec),"duplicate prefix")
    bank,_=load_bank(root);registry=bank.registry;pools=[];retrieval={};snapshots={}
    writer="writer-dp-raw:"+object_sha256({"protocol":PROTOCOL,"mode":"all legal RAW only"})
    for item in spec:
        p=registry.prefix(item["owner_id"],item["session_id"],item["cut_turn"])
        require(p.prefix_id==item["prefix_id"],"prefix differs from frozen sample")
        ledger=A.Ledger()
        for e in registry.visible(p):ledger.append(A.record_from_source(e,kind="MS_RAW",writer=writer),registry)
        snap=A.materialize(registry,p,ledger,writer=writer)
        raw=json.loads(canonical_json(snap))
        snapshots[p.prefix_id]=raw
        candidates=[v["record"] for v in raw["views"] if v["record"]["kind"]=="MS_RAW" and v["disposition"]=="raw_available"]
        prefix=json.loads(canonical_json(p))
        pool={"owner_id":p.owner_id,"prefix_id":p.prefix_id,"prefix":prefix,"snapshot_sha":snap["snapshot_sha"],"candidates":candidates}
        pools.append(pool)
        ranked=search(bank,"MS",p);winner=bank.by_id[ranked.ranked[0].record_id] if ranked.ranked else None
        sid=winner.source_refs[0].session_id if winner else None
        selected=next((r for r in candidates if r["session_id"]==sid),None)
        require(winner is None or selected is not None,"retrieval violates as-of pool")
        retrieval[p.prefix_id]={"selected_record_id":selected["record_id"] if selected else None,
             "retriever":"original lexical-v0; frozen before outcomes","query_identity":ranked.query_identity,
             "bank_version":bank.version,"index_version":bank.index_version}
    bundle=wrap_pools(pools,object_sha256(manifest),formal=True)
    for e in bundle["rows"]:retrieval[e["pool"]["prefix_id"]]["pool_sha256"]=e["pool_sha256"]
    return bundle,{"bundle_sha256":bundle["bundle_sha256"],"rows":retrieval,
        "snapshots_and_source_frontiers":snapshots,"selector_visible":False}

def selection_html(bundle):
    validate_bundle(bundle)
    encoded=base64.b64encode(canonical_json(bundle).encode()).decode()
    template=Path(__file__).with_name("dp_selector.html").read_text()
    return template.replace("__BUNDLE_BASE64__",encoded)


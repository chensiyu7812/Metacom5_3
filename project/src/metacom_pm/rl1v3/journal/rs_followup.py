"""CPU delivery audit and a separate, pre-generation complex RS dev candidate.

Reads frozen inputs and source evidence only, never generated responses. The
original 6 methods / 24 tasks / 144 arm identities are preserved byte-for-byte.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

from ..io import object_sha256
from ..retrieve.native_tokens import NativeTokenizer
from .behavior import ANNOMI_BLOB, read_annomi
from .rs_tasks import deduplicate_utterances, digest, runtime, select_visible, write_once
from .skills import build_skills


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lines(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def verify_sources(candidates, tip35_dir, output):
    """Recompile both views from the pinned official HTML, preserving the old bank."""
    candidates,output=Path(candidates),Path(output)
    manifest=json.loads((candidates/"manifest.json").read_text())
    for name,expected in manifest["files"].items():
        if sha(candidates/name)!=expected:raise ValueError("frozen candidate bytes changed: "+name)
    existing={r["skill_id"]:r for r in lines(candidates/"skills.private.jsonl")}
    rebuilt=build_skills(tip35_dir)
    for row in rebuilt:
        prior=existing[row["skill_id"]]
        for field in ("source_refs","method_reading","raw_reading"):
            if row[field]!=prior[field]:raise ValueError("source/view rebuild mismatch: "+row["skill_id"]+":"+field)
    result=dict(protocol="pmrl1-j-rs-official-source-recompile-v1",methods=6,
        matched_fields=["source_refs","method_reading","raw_reading"],
        official_html_hashes_checked=True,paragraph_identity_checked=True,
        original_candidate_manifest_sha256=sha(candidates/"manifest.json"),
        source_paragraphs=sum(len(r["source_refs"]) for r in rebuilt),
        private_files_unchanged=True,new_generation_calls=0)
    write_once(output/"SOURCE_IDENTITY.json",result)
    return result


def audit(candidates, requests, model, assets, output):
    candidates, requests, output=Path(candidates),Path(requests),Path(output)
    if output.exists():raise FileExistsError("new audit directory required")
    materials=lines(candidates/"request_materials.private.jsonl")
    delivered=[r for r in lines(requests/"requests_logical.private.jsonl") if r["domain"]=="rs"]
    skills=lines(candidates/"skills.private.jsonl")
    retrieval={r["task_id"]:r for r in lines(candidates/"retrieval.private.jsonl")}
    native=NativeTokenizer(model,assets)
    keyed={(r["task_id"],r["arm"]):r for r in delivered}
    if len(materials)!=144 or len(keyed)!=144 or len(skills)!=6:
        raise ValueError("preserved RS coverage changed")
    details=[]
    for material in materials:
        row=keyed[(material["task_id"],material["arm"])]
        packet=row["model_input"]
        if object_sha256(material)!=row["source_material_sha256"]:
            raise ValueError("frozen request source material identity differs")
        if object_sha256(packet)!=row["payload_sha256"]:
            raise ValueError("payload identity differs")
        ids=native.tokenizer.apply_chat_template(packet["messages"],tokenize=True,add_generation_prompt=True,enable_thinking=False)
        if hasattr(ids,"keys"):ids=ids["input_ids"]
        if ids and isinstance(ids[0],list):ids=ids[0]
        if list(ids)!=packet["input_ids"] or len(ids)!=row["input_tokens"]:
            raise ValueError("native tokenizer delivery differs")
        read=material["readings"]
        blocks=[]
        for message in packet["messages"]:
            text=message["content"]
            if "<Notes>" in text:
                root=ET.fromstring(text[text.index("<Notes>"):])
                blocks.extend((element.attrib,element.text or "") for element in root)
        if len(blocks)!=len(read) or any(text!=expected["reading_text"] for (_,text),expected in zip(blocks,read)):
            raise ValueError("resource text was omitted/changed/truncated")
        if [dict(role="user" if t["role"]=="seeker" else "assistant",content=t["text"]) for t in material["runtime"]["turns"]] != packet["messages"][-len(material["runtime"]["turns"]):]:
            raise ValueError("visible user prefix differs across delivery")
        _,selected=select_visible(material["runtime"]["turns"][-1]["text"],skills,"method_reading")
        if selected["skill_id"]!=retrieval[material["task_id"]]["selected_skill"]:
            raise ValueError("real lexical retrieval not reproducible")
        arm=material["arm"]
        content=read[0]["reading_text"] if read else ""
        if arm=="Method" and content!=selected["method_reading"]:raise ValueError("method changed")
        if arm=="Professional-RAW" and content!=selected["raw_reading"]:raise ValueError("raw changed")
        if arm=="F-resident" and content!="\n\n".join(s["method_reading"] for s in skills):raise ValueError("F library content changed")
        off=keyed[(material["task_id"],"R0")]
        details.append(dict(task_id=material["task_id"],arm=arm,request_id=row["request_id"],
            input_tokens=len(ids),resource_tokens=native.count(content) if content else 0,
            marginal_input_tokens_vs_R0=len(ids)-off["input_tokens"],native_retokenization_exact=True,
            readable_content_exact=True,all_six_methods_present=arm=="F-resident",
            source_paragraph_hashes=[p["paragraph_sha256"] for p in selected["source_refs"]] if arm in ("Method","Professional-RAW") else [],
            selection="real_visible_query_lexical_top1" if arm in ("Method","Professional-RAW","Legacy-RS") else "all_six_resident" if arm=="F-resident" else "fixed_generic" if arm=="Generic" else "none"))
    summaries={}
    for arm in sorted({r["arm"] for r in details}):
        members=[r for r in details if r["arm"]==arm]
        summaries[arm]=dict(n=len(members),**{metric:dict(min=min(r[metric] for r in members),median=statistics.median(r[metric] for r in members),max=max(r[metric] for r in members)) for metric in ("input_tokens","resource_tokens","marginal_input_tokens_vs_R0")})
    source_hashes={str(path):sha(path) for path in (candidates/"manifest.json",candidates/"request_materials.private.jsonl",requests/"REQUEST_MANIFEST.json",requests/"requests_logical.private.jsonl")}
    report=dict(protocol="pmrl1-j-rs-source-delivery-audit-v1",preserved_methods=6,preserved_tasks=24,preserved_requests=144,
        exact_native_token_checks=144,exact_reading_content_checks=144,raw_method_same_paragraph_checks=24,
        F_resident_full_library_checks=24,truncation_or_missing_content=0,by_arm=summaries,
        tokenizer_identity=native.identity,tokenizer_files_sha256=native.file_hashes,
        actual_selected_skills=dict(Counter(r["selected_skill"] for r in retrieval.values())),
        direct_versus_retrieval=dict(Method="real lexical Top1 from visible user text; not intended-skill oracle",
             Professional_RAW="the exact original paragraphs belonging to the SAME real-retrieved method",
             F_resident="all six method candidates always present; no retrieval and no gold-target selection",
             Legacy_RS="real visible-text lexical Top1 of preserved legacy case bank",
             direct_intended_skill_diagnostic_in_original_144=False),
        interpretation="RAW versus Method compares original narrative with a nonclinical procedural adaptation; it is not a pure compression contrast. F-resident supplies more content/tokens.",
        new_model_generation_calls=0,gpu_loads=0,prior_outputs_read=False,source_files_sha256=source_hashes)
    write_once(output/"DETAILS.private.jsonl",details,lines=True)
    write_once(output/"RESULTS.json",report)
    write_once(output/"MANIFEST.json",dict(protocol=report["protocol"],files={p.name:sha(p) for p in output.iterdir()}))
    return report


# Source IDs select exact past source utterances. Added context is explicitly
# constructed and never presented as an original AnnoMI observation.
COMPLEX_DESIGN_SHA256 = "c8723215eb7cd2276ac7bd9580295ae14e27869df612fdd1278d356d1159785f"


def build_complex(annomi, old_candidates, case_review, output, design):
    output=Path(output)
    if output.exists():raise FileExistsError("preserve frozen complex candidates")
    rows=deduplicate_utterances(read_annomi(annomi))
    lookup={tuple(r["key"]):r for r in rows}
    old=lines(Path(old_candidates)/"evalspec.private.jsonl")
    cases=lines(Path(case_review)/"cases-v2.private.jsonl")
    excluded={f for r in old for f in r["source_family_ids"]}|{r["video_family"] for r in cases}
    tasks=[];evaluations=[];families=set();readable=["# 新复杂 RS 开发候选（12题；未生成）", "来源引文与构造补充均在下文明确列出。不是独立确认集；不以唯一专家动作作金标。"]
    design=Path(design)
    if sha(design)!=COMPLEX_DESIGN_SHA256:raise ValueError("private complex design hash mismatch")
    design_document=json.loads(design.read_text())
    definitions=design_document["definitions"]
    if len(definitions)!=12:raise ValueError("complex design cardinality changed")
    for definition in definitions:
        source=[lookup[(definition["tid"],str(uid))] for uid in definition["uids"]]
        if any(r["interlocutor"]!="client" for r in source):raise ValueError("expected client source")
        family=source[0]["video_family"]
        if family in excluded or family in families:raise ValueError("source family overlap")
        families.add(family)
        task_id="jrs-complex-"+digest(["v1",definition["tid"],definition["uids"],definition["instruction"]])[:24]
        excerpt="\n".join(r["utterance_text"] for r in source)
        task=dict(task_id=task_id,turns=[dict(role="seeker",text=excerpt+"\n\n"+definition["instruction"])])
        tasks.append(runtime(task))
        evidence=[dict(source_git_blob=ANNOMI_BLOB,transcript_id=r["transcript_id"],utterance_id=r["utterance_id"],
                       exact_quote=r["utterance_text"],quote_sha256=hashlib.sha256(r["utterance_text"].encode()).hexdigest()) for r in source]
        evaluations.append(dict(task_id=task_id,origin="constructed_from_source_client_excerpts",development_exposed=True,
            independent_confirmatory=False,source_family_ids=[family],condition_private=definition["condition"],
            cutoff=dict(kind="selected_source_excerpts_plus_explicit_constructed_current_request",source_future_responses_available=False),
            source_evidence=evidence,original_topic_private=source[0]["topic"],
            constructed_supplement=definition["instruction"],
            adaptation="New current intent/permission/timing/ordinary-domain specification is constructed; source quotes are exact and do not prove added facts.",
            requirements=[dict(id=f"r{i+1}",criterion=criterion,allowed_alternatives=definition["alternatives"],
                source_locator="visible exact excerpt and/or explicit constructed supplement",verification_type="semantic_independent_review_pending") for i,criterion in enumerate(definition["needs"])],
            prohibitions=[dict(id=f"p{i+1}",criterion=criterion,verification_type="semantic_independent_review_pending") for i,criterion in enumerate(definition["forbids"])],
            optional=["Method terminology","Resource citation","A particular expert wording"],
            answerability="nonclinical_communication_constraints_with_accepted_alternatives",
            rubric_version="pmrl1-j-rs-complex12-constraints-v1",review_state="development_candidate_unqualified",
            task_success_rule="Any necessary/forbidden-item failure gives 0; all pass gives 1; otherwise pending [0,1]; technical failures separate.",
            reward_qualified=False,outcome=None))
        readable += ["\n## "+task_id+" / "+definition["condition"],"来源: transcript "+definition["tid"]+", utterance "+",".join(map(str,definition["uids"])),
                     "\n原始 client 引文：\n\n"+excerpt,"\n构造的当前请求：\n\n"+definition["instruction"],
                     "\n必要条件：\n\n"+"\n".join("- "+s for s in definition["needs"]),
                     "\n禁止项：\n\n"+"\n".join("- "+s for s in definition["forbids"]),
                     "\n可接受替代："+"；".join(definition["alternatives"])]
    write_once(output/"TASKS.runtime.jsonl",tasks,lines=True)
    write_once(output/"EVALSPEC.private.jsonl",evaluations,lines=True)
    with (output/"READABLE_TASKS.private.md").open("x") as f:f.write("\n".join(readable)+"\n")
    summary=dict(protocol="pmrl1-j-rs-complex12-candidate-v1",tasks=12,source_video_families=12,
        conditions=dict(Counter(e["condition_private"] for e in evaluations)),
        overlap_with_original24_and_casev2_video_families=0,source_git_blob=ANNOMI_BLOB,
        exact_source_utterances=sum(len(e["source_evidence"]) for e in evaluations),
        original24_replaced=False,original144_changed=False,constructed_tasks=12,
        generated_responses_read=0,new_generation_calls=0,qualified_rewards=0,
        independent_confirmatory=False,selection="fixed source/condition coverage before new outcomes; no outcome-driven replacement",
        prefreeze_source_repair=design_document["prefreeze_source_repair"],
        evaluation="multiple legitimate response moves allowed; behavior label is not the correct-action gold",
        limitations=["All AnnoMI sources have prior corpus-level development exposure.","Exact source snippets support only their own content; added current context is explicitly constructed.","Video URLs are a grouping proxy, not verified independent speakers.","Semantic evaluation awaits independent qualification; no automatic reward is created."])
    write_once(output/"COVERAGE.json",summary)
    write_once(output/"MANIFEST.json",dict(protocol=summary["protocol"],status="frozen_pre_generation_candidate",
        files={p.name:sha(p) for p in output.iterdir()},code_sha256=sha(__file__),source_sha256=sha(annomi),private_design_sha256=sha(design),
        old_candidate_manifest_sha256=sha(Path(old_candidates)/"manifest.json"),
        case_review_manifest_sha256=sha(Path(case_review)/"manifest.json")))
    return summary


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest="command",required=True)
    p=subs.add_parser("audit");p.add_argument("--candidates",required=True);p.add_argument("--requests",required=True)
    p.add_argument("--model",required=True);p.add_argument("--assets",required=True);p.add_argument("--output",required=True)
    p=subs.add_parser("complex");p.add_argument("--annomi",required=True);p.add_argument("--old-candidates",required=True)
    p.add_argument("--case-review",required=True);p.add_argument("--output",required=True);p.add_argument("--design",required=True)
    p=subs.add_parser("sources");p.add_argument("--candidates",required=True);p.add_argument("--tip35-dir",required=True);p.add_argument("--output",required=True)
    a=parser.parse_args()
    if a.command=="audit":result=audit(a.candidates,a.requests,a.model,a.assets,a.output)
    elif a.command=="sources":result=verify_sources(a.candidates,a.tip35_dir,a.output)
    else:result=build_complex(a.annomi,a.old_candidates,a.case_review,a.output,a.design)
    print(json.dumps(result,ensure_ascii=False,indent=2))

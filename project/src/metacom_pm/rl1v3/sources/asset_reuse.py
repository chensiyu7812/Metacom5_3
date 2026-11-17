"""Reproducible CPU audit of existing lawful assets. Does not build a runtime bank.

Exports metadata/hashes only: no transcript bodies, human answers, or judge labels.
Classification is migration readiness, never scientific validation or test independence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import csv
import re

from ..io import file_sha256, object_sha256, sha256_text, write_json_once, write_jsonl_once

CLASSES = ("direct_reuse", "adapt", "repair", "quarantine", "historical_only")


def esconv_family(identity: str) -> str:
    """Normalize source identifiers/known family aliases, never compare body text."""
    value = identity.removeprefix("esconv_dialogue:").removeprefix("esconv:")
    match = re.fullmatch(r"(?:esc|esconv_)([0-9]+)", value)
    if not match:
        raise ValueError("not an ESConv source identity: " + identity)
    return f"esconv:esconv_{int(match[1]):04d}"


def session_family(owner: str, session: str) -> str:
    return esconv_family(session) if re.fullmatch(r"esc[0-9]+", session) else "evoemo_owner:" + owner


def rs_rejection(source_ids, split_by_family, excluded_families):
    if not source_ids:
        return "missing_source"
    try:
        families = {esconv_family(s) for s in source_ids}
    except ValueError:
        return "unknown_family"
    if families & excluded_families:
        return "overlap_family"
    if any(split_by_family.get(f) != "train" for f in families):
        return "non_train_or_unknown_source"
    return None


def verify_unit(unit, sessions):
    """Use original idx for lookup; zero-based ordinal is recorded separately."""
    key = (unit.get("owner_id"), unit.get("source_session_id"))
    source = sessions.get(key)
    errors, bindings = [], []
    if source is None:
        return ["missing_owner_session"], []
    if unit.get("source_session_rank") != source["chronological_rank"]:
        errors.append("rank_mismatch")
    if unit.get("timestamp") != source["timestamp"]:
        errors.append("reported_time_mismatch")
    lookup = defaultdict(list)
    for ordinal, turn in enumerate(source["turns"]):
        lookup[turn["idx"]].append((ordinal, turn))
    if not unit.get("supporting_spans"):
        errors.append("no_spans")
    for span in unit.get("supporting_spans", []):
        matches = lookup.get(span["turn_index"], [])
        if len(matches) != 1:
            errors.append("ambiguous_or_missing_turn")
            continue
        ordinal, turn = matches[0]
        start, end, quote = span["start_char"], span["end_char"], span["exact_text"]
        if not (0 <= start < end <= len(turn["content"])) or turn["content"][start:end] != quote:
            errors.append("quote_offset_mismatch")
        if sha256_text(quote) != span["exact_text_sha256"]:
            errors.append("quote_hash_mismatch")
        if span["turn_id"] != f'{unit["source_session_id"]}:{turn["idx"]}':
            errors.append("turn_identity_mismatch")
        if unit.get("user_anchored") and turn["role"] != "seeker":
            errors.append("user_anchor_role_mismatch")
        bindings.append(dict(original_turn_index=turn["idx"], ordinal_turn=ordinal,
            speaker=turn["role"], start_char=start, end_char=end,
            quote_sha256=sha256_text(quote), raw_turn_sha256=sha256_text(turn["content"])))
    return sorted(set(errors)), bindings


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def audit(*, root: Path, history_root: Path, config: dict, extra_files=(), verify_models=True):
    files, items, diagnostics = {}, [], []

    def fingerprint(path, kind, classification="historical_only", expected=None):
        logical_path = str(Path(path).absolute())
        path = Path(path).resolve()
        if config["excluded_retired_path"] in str(path):
            raise ValueError("retired synthetic source is prohibited")
        if str(path) in files:
            return files[str(path)]
        if not path.is_file():
            entry = dict(path=str(path), kind=kind, exists=False, sha256=None,
                classification="quarantine", reason="missing_local_asset", count=0)
        else:
            digest = file_sha256(path)
            entry = dict(path=str(path), kind=kind, exists=True, bytes=path.stat().st_size,
                sha256=digest, classification=classification, count=1, count_unit="file",
                source_time=None, owner_family="see item ledger or source manifest",
                exposure="previous_research_or_unknown; never independent by default",
                logical_path=logical_path,version=None,source_origin="local prior research; retain upstream source manifest",
                destination="historical replay only" if classification=="historical_only" else "V3 adapter; no automatic admission",
                capabilities_missing=["prefix/version/permission admission"],license_status="retain original; not newly licensed")
            if path.suffix == '.json':
                obj=read_json(path)
                entry['top_level_type']=type(obj).__name__
                entry['top_level_entries']=len(obj) if isinstance(obj,(list,dict)) else None
                if isinstance(obj,dict):
                    entry['section_counts']={k:len(v) for k,v in obj.items() if isinstance(v,(list,dict))}
                    entry['version']=next((obj[k] for k in ('protocol','schema_version','schema','version') if isinstance(obj.get(k),str)),None)
            elif path.suffix == '.jsonl':
                with path.open() as stream:entry['rows']=sum(bool(line.strip()) for line in stream)
            elif path.suffix == '.csv':
                with path.open(newline='') as stream:entry['rows']=max(0,sum(1 for _ in csv.reader(stream))-1)
            if expected is not None:
                entry["previous_sha256"] = expected
                entry["matches_previous"] = digest == expected
                if digest != expected:
                    entry.update(classification="quarantine",reason="changed_since_previous_manifest")
        files[str(path)] = entry
        return entry

    def get(name, lines=False):
        path = root / config[name]
        fingerprint(path, name, "adapt")
        return read_jsonl(path) if lines else read_json(path)

    runtime = get("runtime")
    sessions = {(u["owner_id"],s["session_id"]):s for u in runtime["users"] for s in u["sessions"]}
    seed_holders = defaultdict(list)
    for (owner,sid), source in sessions.items():
        family = session_family(owner,sid)
        if family.startswith("esconv:"): seed_holders[family].append(dict(owner_id=owner,session_id=sid))
        items.append(dict(asset_kind="MS_RAW",old_id=f"ms::{owner}::{sid}",owner_id=owner,
            family_ids=[family],source_path=str((root/config["runtime"]).resolve()),
            source_row_sha256=object_sha256(source),source_rank=source["chronological_rank"],
            reported_at=source["timestamp"],ready_at=None,classification="direct_reuse",
            count_unit="complete_session",reason="immutable dialogue bytes reusable as source; V3 wrapper/ready_at still required",
            destination="sources.SourceSession -> bank.MS/raw",license="inherited_source_terms_not_relicensed",
            exposure="historical_research",capabilities_missing=["V3 ready_at", "prefix-dependent legality"],
            semantic_status="original_utterance_not_verified_world_fact"))
    split_rows = get("esconv_split",True)
    split_by_family = {esconv_family(r["dialogue_id"]):r["split"] for r in split_rows}
    marked = {esconv_family(r["dialogue_id"]) for r in split_rows if r["excluded_for_evoemo_overlap"]}
    overlaps = set(seed_holders)
    if marked != overlaps:
        raise ValueError("ESConv overlap registry disagrees with actual EvoEmo seed family closure")
    excluded = marked | overlaps
    compiled = get("compiled",True); pool = get("pool",True)
    pool_ids = {p["candidate_id"] for p in pool}
    unit_ids = Counter(u["memory_id"] for row in compiled for u in row["accepted_units"])
    for row in compiled:
        for unit in row["accepted_units"]:
            head = "MP" if "profile_slot_key" in unit else "ME"
            errors, spans = verify_unit(unit,sessions)
            if unit_ids[unit["memory_id"]] != 1: errors.append("duplicate_memory_id")
            classification = "quarantine" if errors else "repair" if unit["memory_id"] in config["known_repair_ids"] else "adapt"
            items.append(dict(asset_kind=head,old_id=head.lower()+"::"+unit["memory_id"],
                owner_id=unit["owner_id"],family_ids=[session_family(unit["owner_id"],unit["source_session_id"])],
                source_session_id=unit["source_session_id"],source_rank=unit["source_session_rank"],reported_at=unit["timestamp"],ready_at=None,
                source_path=str((root/config["compiled"]).resolve()),source_row_sha256=object_sha256(unit),
                version=unit["schema_version"],compiler_identity=unit["compiler_identity_sha256"],
                classification=classification,reason=";".join(errors) if errors else "known semantic drift" if classification=="repair" else "exact spans valid; V3 semantics/closure/ready_at pending",
                source_span_checks="fail" if errors else "pass",span_bindings=spans,
                in_old_eligible_pool=head.lower()+"::"+unit["memory_id"] in pool_ids,
                destination=f"bank.ResourceRecord/{head}",semantic_status="unverified",
                license="inherited_source_terms_not_relicensed",exposure="historical_research",
                capabilities_missing=["V3 writer and ready_at", "complete dependency closure", "stage/profile semantic review"]))
    rs_counts = {}
    for name,kind,ids in (("rs_treatments","RS_treatment","source_dialogue_ids"),("rs_strategy","RS_strategy","source_dialogue_id")):
        rows=get(name,True); reasons=Counter()
        for r in rows:
            source_ids=r[ids] if isinstance(r[ids],list) else [r[ids]]
            reason=rs_rejection(source_ids,split_by_family,excluded)
            reasons[reason or "family_train_pass"] += 1
            items.append(dict(asset_kind=kind,old_id=r.get("treatment_id",r.get("strategy_id")),
                source_path=str((root/config[name]).resolve()),source_row_sha256=object_sha256(r),
                owner_id=None,family_ids=sorted({esconv_family(s) for s in source_ids}),
                reported_at=None,ready_at=None,classification="quarantine" if reason else "adapt",
                reason=reason or "family/train gates pass; full context/license/risk review pending",
                destination="bank.RS -> compile.complete_case",semantic_status="unverified",exposure="historical_research",
                license="license evidence must be bound at migration",capabilities_missing=["complete case context", "risk and applicability", "V3 source/license binding"]))
        rs_counts[kind]=dict(reasons)
    raw=get("raw_evoemo"); esconv=get("raw_esconv")
    excluded_sections={k:sum(len(u.get(k,[])) for u in raw) for k in ("event_experience","social_relationship","summaries","questions","subsequent_topics")}
    excluded_sections["basic_info"]=sum(bool(u.get("basic_info")) for u in raw)
    for kind,count in excluded_sections.items():
        items.append(dict(asset_kind="EvoEmo_"+kind,old_id="raw-section:"+kind,count=count,count_unit="original section row",
            source_path=str((root/config["raw_evoemo"]).resolve()),source_row_sha256=object_sha256([u.get(kind) for u in raw]),
            owner_id="multiple",family_ids=sorted(overlaps|{"evoemo_owner:"+u["owner_id"] for u in runtime["users"]}),reported_at=None,ready_at=None,
            classification="quarantine",reason="privileged persona/full trajectory/evaluation task field; not legal prefix evidence",
            destination="offline source provenance only",exposure="historical_research",license="inherited_source_terms_not_relicensed"))
    prep=history_root/config["preparation"]
    for name in ("rs/case_candidates.jsonl","rs/METHOD_UNITS_DRAFT.json","rs/SEMANTIC_REVIEW_ZH.md",
                 "memory/CANDIDATE_VIEW_REPAIRS_PRIVATE.json","memory/CURRENT_VIEW_COMPARISONS_PRIVATE.json",
                 "versions/VERSION_REUSE_MANIFEST.json"):
        fingerprint(prep/name,"prior_preparation")
    cases=read_jsonl(prep/'rs/case_candidates.jsonl')
    for row in cases:
        reason=rs_rejection([row["source"]["dialogue_id"]],split_by_family,excluded)
        fingerprint(prep/'rs'/row["source"]["full_source_file"],"RS_case_source","direct_reuse")
        items.append(dict(asset_kind="RS_case",old_id=row["card_id"],count=1,source_row_sha256=object_sha256(row),
            source_path=str(prep/'rs/case_candidates.jsonl'),family_ids=[esconv_family(row["source"]["dialogue_id"])],owner_id=None,
            classification="quarantine" if reason or row["card_id"] in config["rs_case_negative_ids"] else "repair",
            reason=reason or "prior AI review; no runtime/domain approval",reported_at=None,ready_at=None,
            destination="compile.RS/case; negative cases isolated",exposure="AI_reviewed_20261115_not_independent",
            license="pending exact source license binding",semantic_status="unverified"))
    methods=read_json(prep/'rs/METHOD_UNITS_DRAFT.json')["units"]
    for row in methods:
        items.append(dict(asset_kind="RS_method",old_id=row["method_id"],count=1,source_row_sha256=object_sha256(row),
            source_path=str(prep/'rs/METHOD_UNITS_DRAFT.json'),source_url=row["source_url"],family_ids=[],owner_id=None,
            classification="quarantine",reason="domain applicability, risk and permission not approved",reported_at=None,ready_at=None,
            destination="compile.RS/method candidate only",exposure="AI_draft_not_independent",license="not yet bound"))
    historical=read_json(prep/'versions/VERSION_REUSE_MANIFEST.json')
    for row in historical["source_file_fingerprints"]:
        path=Path(row["path"])
        if str(path).startswith('/home/tokkio/Metacom5_3/'):
            path=history_root/path.relative_to('/home/tokkio/Metacom5_3')
        fingerprint(path,"prior_version_manifest_input",expected=row["sha256"])
    for relative in config["historical_directories"]:
        folder=history_root/relative
        for path in sorted(folder.rglob('*')):
            if path.is_file() and path.suffix in ('.json','.jsonl','.csv','.md'):
                fingerprint(path,"historical_evidence_no_new_independence")
    for path in extra_files: fingerprint(path,"exposure_registry_from_B0")
    for folder in ('project/data/paper1_public_memory','project/data/paper1_public_rs'):
        for path in sorted((root/folder).glob('*')):
            if path.is_file(): fingerprint(path,"historical_index_or_census","adapt" if 'bge' in path.name else "historical_only")
    for relative in ('project/src/metacom_pm/paper1/embeddings/bge_m3.py','project/src/metacom_pm/paper1/multi_view_memory/candidate_adapter.py',
        'project/src/metacom_pm/rl1/temporal_evidence_ledger.py','project/src/metacom_pm/rl1/resource_organization.py',
        'project/src/metacom_pm/rl1/organized_encoding.py','project/src/metacom_pm/rl1/organized_local_backend.py',
        'project/src/metacom_pm/rl1/organized_feedback.py','project/src/metacom_pm/rl1/human_reference_reuse.py'):
        fingerprint(root/relative,"implementation_to_adapt","adapt")
    for path in sorted((root/'project/tests').glob('test_rl1*.py')):
        fingerprint(path,"regression_test","adapt")
    model_paths = set()
    model_expected = {}
    def discover_models(value):
        if isinstance(value,dict):
            if 'model_dir' in value:
                directory=Path(value['model_dir'])
                for name,digest in value.get('model_files',{}).items():
                    model_paths.add(directory/name); model_expected[directory/name]=digest
            if isinstance(value.get('adapter'),dict):
                adapter=value['adapter']
                for name,digest in adapter.get('files',{}).items():
                    path=Path(adapter['path'])/name;model_paths.add(path);model_expected[path]=digest
            for child in value.values():discover_models(child)
        elif isinstance(value,list):
            for child in value:discover_models(child)
    discover_models(historical['G_versions'])
    a0path=root/'project/outputs/pm_rl1/v3/A0/repair_1/ENV_REPORT.json'
    fingerprint(a0path,"previous_CPU_model_inventory")
    a0=read_json(a0path)
    # A0 uses one file map per actual model snapshot; retain all config/tokenizer/weights.
    for model in a0['models'].values():
        directory=Path(model.get('path',model.get('model_dir','')))
        for name,metadata in model.get('files',{}).items():
            model_paths.add(directory/name);model_expected[directory/name]=metadata['sha256']
        if directory.is_dir() and str(directory) != '.':
            for path in directory.iterdir():
                if path.is_file() and path.suffix in ('.json','.safetensors','.model'):
                    model_paths.add(path)
    for path in sorted(model_paths):
        if verify_models or path.suffix != '.safetensors':
            fingerprint(path,"model_weight_or_tokenizer_config","direct_reuse",expected=model_expected.get(path))
    # Presence search only in curated source area; no retired intake is opened.
    failed=[p for p in (history_root/'project/data/external').rglob('*') if p.is_file() and re.search(r'failed.?esconv',p.name,re.I)]
    for path in failed:fingerprint(path,"FailedESConv_unverified_source","quarantine")
    totals=defaultdict(Counter)
    for item in items:totals[item['asset_kind']][item['classification']] += item.get('count',1)
    overview=dict(owners=len(runtime['users']),sessions=len(sessions),raw_esconv_dialogues=len(esconv),
        accepted_units=dict(Counter('MP' if 'profile_slot_key' in u else 'ME' for r in compiled for u in r['accepted_units'])),
        old_eligible_pool=dict(Counter(p['head'] for p in pool)),
        shared_seed_families={k:v for k,v in sorted(seed_holders.items()) if len(v)>1},
        overlap_families=sorted(overlaps),overlap_registry_matches=True,
        esconv_split_counts=dict(Counter(r['split'] for r in split_rows)),rs_family_train_checks=rs_counts,
        classifications={k:{c:counts[c] for c in CLASSES} for k,counts in sorted(totals.items())},
        historical_human_registry_records=next((f.get('top_level_entries') for f in files.values() if f['path'].endswith('history_necessity_human_review_20261105_v1/ANSWER_REGISTRY_PRIVATE.json')),None),
        file_kind_counts=dict(Counter(f['kind'] for f in files.values())),
        previous_manifest_hash_mismatches=sum(f.get('matches_previous') is False for f in files.values()),
        failed_esconv_local_files=len(failed),failed_esconv_search_root=str(history_root/'project/data/external'),
        bank_v0_records_written=0,read_success_rate=None,models_executed=0,gpu_calls=0,paid_calls=0,
        retired_path=config['excluded_retired_path'],retired_source_opened=False,
        remaining=['B review / C0 integration freeze','source/license provenance binding','V3 ready_at and prefix legality','bank-v0 migration/read','A5 dense/BM25/hybrid comparison'])
    return dict(protocol=config['protocol'],overview=overview,files=list(files.values()),
                items=items,diagnostics=diagnostics,scope='asset audit; classification is not bank admission or independent evaluation')


def export_audit(result, out: Path):
    ledger=out/'ASSET_ITEMS.jsonl'
    write_jsonl_once(ledger,result['items'])
    payload={k:v for k,v in result.items() if k!='items'}
    payload['item_ledger']=dict(path=ledger.name,rows=len(result['items']),sha256=file_sha256(ledger))
    payload['manifest_sha256']=object_sha256(payload)
    write_json_once(out/'ASSET_REUSE_MANIFEST.json',payload)
    return payload
